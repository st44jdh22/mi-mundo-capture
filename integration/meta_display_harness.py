"""HS-META-001 synthetic media harness. Loopback only; NOT a glasses driver.

Reuses the existing v0.3 package validator, receiver and CaptureClient. There is
no arbitrary file import, camera/microphone access, routing or cloud deployment.
"""
import base64
import hashlib
import io
import json
import os
import re
import secrets
import subprocess
import tempfile
import wave
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from receiver import FixtureStore, make_server
from validate_job import validate

HERE = Path(__file__).resolve().parent
MODES = {'photo': ('image/png', 'png'), 'video': ('video/mp4', 'mp4'),
         'audio': ('audio/wav', 'wav')}


def fixture(mode):
    """Generate only fabricated media. Video includes a silent audio track."""
    if mode == 'photo':
        return base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aXioAAAAASUVORK5CYII=')
    if mode == 'audio':
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b'\0\0' * 16000)
        return buf.getvalue()
    if mode != 'video':
        raise ValueError('Unsupported synthetic mode')
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / 'fixture.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-f', 'lavfi',
                        '-i', 'color=c=black:s=160x160:r=10', '-f', 'lavfi',
                        '-i', 'anullsrc=r=16000:cl=mono', '-t', '1',
                        '-c:v', 'mpeg4', '-c:a', 'aac', '-shortest', str(target)],
                       check=True, capture_output=True, timeout=15)
        return target.read_bytes()


def prepare(root, mode):
    """Commit immutable ZIP last; the ZIP is the local retry source, not a ledger."""
    content_type, suffix = MODES[mode]
    data = fixture(mode)
    job_id, attachment_id = str(uuid4()), str(uuid4())
    captured_at = datetime.now(timezone.utc).isoformat()
    media_path = f'evidence/{attachment_id}.{suffix}'
    instructions = 'HS-META-001 fabricated media test. No routing or real-world actions.'
    manifest = {'version': '0.3', 'status': 'LOCAL_EXPORT_NOT_TRANSMITTED',
                'job_id': job_id, 'instructions': instructions,
                'source': {'kind': 'synthetic_meta_display_harness',
                           'physical_glasses': False, 'device_id': 'synthetic-device',
                           'captured_at': captured_at, 'capture_time_basis': 'fixture_generated'},
                'attachments': [{'id': attachment_id, 'archive_path': media_path,
                                 'name': f'synthetic-{mode}.{suffix}',
                                 'content_type': content_type, 'bytes': len(data),
                                 'sha256': hashlib.sha256(data).hexdigest()}]}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('instructions.txt', instructions)
        archive.writestr(media_path, data)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = root / f'{job_id}.zip'
    body = buf.getvalue()
    # Exclusive creation, flush and directory fsync before saying locally saved.
    with target.open('xb') as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(root, os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    validate(target)
    if target.read_bytes() != body:
        raise OSError('Local package readback failed')
    return {'job_id': job_id, 'mode': mode, 'package_sha256': hashlib.sha256(body).hexdigest(),
            'status': 'LOCAL_SYNTHETIC_SAVED'}


def make_harness(root, port=0):
    root = Path(root)
    for name in ('outbox', 'receiver'):
        (root / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    token = secrets.token_urlsafe(32)  # Ephemeral session, not written to disk/log.
    server = make_server(FixtureStore(root / 'receiver'), token, 'https://synthetic.invalid', port)
    parent = server.RequestHandlerClass

    class Handler(parent):
        def allowed_origin(self):
            # Narrow local harness exception; the existing receiver is unchanged.
            expected = f'127.0.0.1:{self.server.server_port}'
            return self.headers.get('Host') == expected and self.headers.get('Origin') in (
                None, 'http://' + expected)

        def send_bytes(self, data, content_type):
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self.allowed_origin():
                return self.respond(403)
            static = {'/': ('meta_display_harness.html', 'text/html; charset=utf-8'),
                      '/meta-display.mjs': ('meta_display_harness.mjs', 'text/javascript'),
                      '/meta-display.css': ('meta_display_harness.css', 'text/css'),
                      '/capture-client.mjs': ('capture-client.mjs', 'text/javascript')}
            if self.path in static:
                name, mime = static[self.path]
                return self.send_bytes((HERE / name).read_bytes(), mime)
            if self.path == '/harness/session':
                # Non-simple request header blocks cross-origin form/image access.
                if self.headers.get('X-Harness') != 'synthetic':
                    return self.respond(403)
                return self.respond(200, {'token': token})
            match = re.fullmatch(r'/harness/package/([0-9a-f-]{36})', self.path)
            if match:
                if not self.authorised():
                    return self.respond(401)
                try:
                    job_id = str(UUID(match[1]))
                    package = root / 'outbox' / f'{job_id}.zip'
                    validate(package)
                    return self.send_bytes(package.read_bytes(), 'application/zip')
                except (OSError, ValueError, zipfile.BadZipFile, KeyError):
                    return self.respond(404)
            return super().do_GET()

        def do_POST(self):
            if not self.authorised():
                return self.respond(401)
            match = re.fullmatch(r'/harness/capture/(photo|video|audio)', self.path)
            if not match:
                return self.respond(404)
            if self.headers.get('Content-Length', '0') != '0' or self.headers.get('Transfer-Encoding'):
                return self.respond(400)
            try:
                return self.respond(201, prepare(root / 'outbox', match[1]))
            except (OSError, ValueError, subprocess.SubprocessError):
                return self.respond(503, {'status': 'FIXTURE_NOT_SAVED'})

    server.RequestHandlerClass = Handler
    return server


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Local synthetic HS-META-001 harness, never physical glasses')
    parser.add_argument('--synthetic', action='store_true', required=True)
    parser.add_argument('--workspace', type=Path, required=True, help='Private LOCAL test folder, outside the repository')
    parser.add_argument('--port', type=int, default=8767)
    args = parser.parse_args()
    server = make_harness(args.workspace, args.port)
    print(f'Synthetic review only: http://127.0.0.1:{server.server_port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
