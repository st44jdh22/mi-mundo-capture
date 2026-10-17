"""Prototype authenticated upload receiver. Local tests only; no routing/Drive writes.

The fixture store is deliberately temporary. Deployment must supply the accepted
original-evidence adapter before any production receipt can be issued.
"""
import hashlib
import hmac
import json
import re
import tempfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from uuid import UUID

from validate_job import validate, MAX_ARCHIVE


class Conflict(Exception):
    pass


class FixtureStore:
    """Test-only original package + receipt, with exact-byte retry checks."""
    def __init__(self, root):
        self.root = Path(root)
        self.lock = Lock()

    def read(self, job_id):
        folder = self.root / job_id
        if not folder.exists():
            return None
        try:
            receipt = json.loads((folder / 'receipt.json').read_text())
            if receipt.get('job_id') != job_id or not isinstance(receipt.get('package_sha256'), str):
                raise ValueError('Invalid receipt')
        except (ValueError, AttributeError) as exc:
            raise OSError('Stored receipt unreadable') from exc
        if hashlib.sha256((folder / 'original.zip').read_bytes()).hexdigest() != receipt['package_sha256']:
            raise OSError('Stored package no longer matches receipt')
        return receipt

    def receive(self, job_id, body, checked):
        digest = hashlib.sha256(body).hexdigest()
        with self.lock:
            old = self.read(job_id)
            if old:
                if old['package_sha256'] != digest:
                    raise Conflict()
                return old, False
            folder = self.root / job_id
            receipt = {'job_id': job_id, 'receipt_id': 'capture-' + job_id,
                       'status': 'RECEIVED_TEST_ONLY', 'package_sha256': digest,
                       'attachments': checked['attachments'],
                       'received_at': datetime.now(timezone.utc).isoformat(),
                       'routed': False, 'departmental_updates': False,
                       'production_evidence_filed': False}
            with tempfile.TemporaryDirectory(dir=self.root) as staging:
                stage = Path(staging)
                (stage / 'original.zip').write_bytes(body)
                (stage / 'receipt.json').write_text(json.dumps(receipt))
                # Read back before publishing a receipt.
                if hashlib.sha256((stage / 'original.zip').read_bytes()).hexdigest() != digest:
                    raise OSError('Package readback failed')
                stage.rename(folder)
            return self.read(job_id), True


def make_server(store, token, origin, port=0, host='127.0.0.1'):
    """Loopback only. Caller owns test server lifetime and temporary store."""
    if len(token) < 32:
        raise ValueError('Use a random test token of at least 32 characters')
    if not origin.startswith('https://'):
        raise ValueError('Explicit HTTPS capture origin required')

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.0'

        def log_message(self, *_):
            pass  # Never log credentials, filenames or body.

        def respond(self, code, obj=None):
            payload = json.dumps(obj or {}).encode()
            self.send_response(code)
            if self.headers.get('Origin') == origin:
                self.send_header('Access-Control-Allow-Origin', origin)
                self.send_header('Vary', 'Origin')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def allowed_origin(self):
            return self.headers.get('Origin') in (None, origin)

        def authorised(self):
            return self.allowed_origin() and hmac.compare_digest(
                self.headers.get('Authorization', ''), 'Bearer ' + token)

        def job_id(self):
            match = re.fullmatch(r'/v1/jobs/([0-9a-f-]{36})', self.path)
            if not match:
                return None
            try:
                return str(UUID(match[1]))
            except ValueError:
                return None

        def do_OPTIONS(self):
            if not self.allowed_origin() or not self.job_id():
                return self.respond(403)
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Methods', 'PUT, GET, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
            self.send_header('Content-Length', '0')
            self.end_headers()

        def do_GET(self):
            if self.path == '/healthz':
                return self.respond(200, {'status': 'SYNTHETIC_TEST_RECEIVER', 'storage': 'EPHEMERAL', 'routing': False})
            if not self.authorised():
                return self.respond(401)
            job_id = self.job_id()
            if not job_id:
                return self.respond(404)
            try:
                result = store.read(job_id)
                return self.respond(200 if result else 404, result)
            except OSError:
                return self.respond(503, {'status': 'READBACK_FAILED'})

        def do_PUT(self):
            self.connection.settimeout(5)
            if not self.authorised():
                return self.respond(401)
            job_id = self.job_id()
            if not job_id:
                return self.respond(404)
            if self.headers.get('Transfer-Encoding'):
                return self.respond(400)
            if self.headers.get('Content-Type') != 'application/zip':
                return self.respond(415)
            lengths = self.headers.get_all('Content-Length', [])
            if len(lengths) != 1 or not lengths[0].isdigit():
                return self.respond(411)
            size = int(lengths[0])
            if size <= 0 or size > MAX_ARCHIVE:
                return self.respond(413)
            try:
                body = self.rfile.read(size)
                if len(body) != size:
                    return self.respond(400)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / 'upload.zip'
                    path.write_bytes(body)
                    checked = validate(path)
                if checked['job_id'] != job_id:
                    return self.respond(409, {'status': 'JOB_ID_MISMATCH'})
            except Exception as exc:
                # No malformed payload or exception details echoed to the client.
                return self.respond(408 if isinstance(exc, TimeoutError) else 422,
                                    {'status': 'INVALID_PACKAGE'})
            try:
                receipt, created = store.receive(job_id, body, checked)
                self.respond(201 if created else 200, receipt)
            except Conflict:
                self.respond(409, {'status': 'JOB_CONTENT_CONFLICT'})
            except OSError:
                self.respond(503, {'status': 'STORAGE_NOT_VERIFIED'})

    return ThreadingHTTPServer((host, port), Handler)


if __name__ == '__main__':
    import argparse
    import os
    parser = argparse.ArgumentParser(description='Temporary loopback-only receiver test; no production storage or routing')
    parser.add_argument('--serve-test', action='store_true')
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    if not args.serve_test:
        parser.error('Explicit --serve-test required')
    token = os.environ.get('MI_MUNDO_TEST_TOKEN', '')
    with tempfile.TemporaryDirectory(prefix='mi-mundo-receiver-test-') as root:
        server = make_server(FixtureStore(root), token, 'https://st44jdh22.github.io', args.port)
        print('Temporary test receiver on 127.0.0.1:' + str(server.server_port), flush=True)
        print('No public HTTPS address. No Drive/Post Office connection. Stop with Ctrl-C.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
