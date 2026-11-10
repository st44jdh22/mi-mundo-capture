"""HS-META-001: in-process Bird/Work doubles only. NOT LIVE; no network adapter.

The fixture hash is a local test oracle, NOT a checksum supplied by Bird.
One worker per local outbox. This is an experiment, not a webhook service.
"""
import base64
import hashlib
import hmac
import io
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from receiver import FixtureStore
from validate_job import validate

JPEG = Path(__file__).parent / 'fixtures' / 'bird-synthetic.jpg'
JPEG_SHA256 = '5096cb4a14663a04ce7aa7ad3274b16e40dc305ad51e7e8e7956e81c7667e0c3'
NOW = 1794312000  # Fixed synthetic delivery clock, not a claimed real capture time.
SECRET = b'HS-META-001 fabricated local signing key NOT LIVE'
STAGES = ('EVENT_RECEIVED', 'MEDIA_FETCHED', 'DESTINATION_ACCEPTED', 'INDEPENDENTLY_VERIFIED')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def atomic(path, data):
    """Replace mutable journal atomically; flush file and containing directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.pending-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Blocked(Exception):
    """A synthetic precondition or integrity check failed."""


@dataclass(frozen=True)
class Selection:
    workspace: str = 'synthetic-workspace'
    sender: str = 'synthetic-bsuid'
    recipient: str = 'synthetic-recipient'
    destination: str = 'sophie-work-mock-not-live'
    subscription: str = 'synthetic-subscription'
    scopes: frozenset = frozenset({'whatsapp:read', 'webhooks:write'})


def event(event_id='synthetic-event-1', message_id='synthetic-message-1', created_at=NOW):
    """MCP envelope + fabricated content fields; authenticated schema NOT verified."""
    return {'eventId': event_id, 'name': 'whatsapp.received', 'timestamp': created_at,
            'cursor': None, 'data': {'workspace_id': 'synthetic-workspace',
            'whatsapp_id': message_id, 'direction': 'inbound',
            'from': {'bsuid': 'synthetic-bsuid'}, 'to': 'synthetic-recipient',
            'image': {'id': 'synthetic-media-1', 'mime_type': 'image/jpeg',
                      'url': 'https://media.example.invalid/never-follow-this'}}}


def signed(payload, timestamp=NOW):
    body = encoded(payload)
    identity = payload['eventId']
    signature = base64.b64encode(hmac.digest(
        SECRET, f'{identity}.{timestamp}.'.encode() + body, 'sha256')).decode()
    return body, {'webhook-id': identity, 'webhook-timestamp': str(timestamp),
                  'webhook-signature': 'v1,' + signature,
                  'X-MCP-Subscription-Id': 'synthetic-subscription'}


@dataclass(frozen=True)
class Media:
    workspace: str
    message_id: str
    media_id: str
    data: bytes
    content_type: str = 'image/jpeg'
    content_length: int = 742


class MockBird:
    """Own injected interface, NOT the authenticated whatsapp_media tool schema."""
    def __init__(self, failure=None):
        self.failure = failure
        self.calls = 0

    def fetch(self, workspace, message_id, media_id):
        self.calls += 1
        if self.failure:
            raise self.failure
        return Media(workspace, message_id, media_id, JPEG.read_bytes())


class MockWork:
    """Existing FixtureStore contract; no connection to a real Sophie/Work thread."""
    def __init__(self, root, failure=None):
        Path(root).mkdir(parents=True, exist_ok=True)
        self.store = FixtureStore(root)
        self.failure = failure
        self.deliveries = 0

    def lookup(self, job_id):
        return self.store.read(job_id)

    def deliver(self, job_id, body, checked):
        self.deliveries += 1
        if self.failure == 'delivery':
            raise OSError('mock delivery unavailable')
        receipt, _ = self.store.receive(job_id, body, checked)
        if self.failure == 'lost_ack':
            raise OSError('mock acknowledgement lost AFTER acceptance')
        return receipt

    def readback(self, job_id):
        if self.failure == 'readback':
            raise OSError('mock independent readback unavailable')
        return (self.store.root / job_id / 'original.zip').read_bytes()


class Pipeline:
    def __init__(self, outbox, bird, work, selection=Selection(), now=NOW):
        if type(bird) is not MockBird or type(work) is not MockWork:
            raise ValueError('Only the local NOT LIVE doubles are supported')
        if selection.destination != 'sophie-work-mock-not-live':
            raise ValueError('Only the NOT LIVE mock destination is supported')
        self.root, self.bird, self.work = Path(outbox), bird, work
        self.selection, self.now = selection, now

    def check(self, body, headers):
        if len(body) > 256 * 1024:
            raise Blocked('EVENT_TOO_LARGE')
        if not {'whatsapp:read', 'webhooks:write'} <= self.selection.scopes:
            raise Blocked('UNAUTHORISED_SCOPE')
        try:
            stamp = headers['webhook-timestamp']
            identity = headers['webhook-id']
            expected = base64.b64encode(hmac.digest(
                SECRET, f'{identity}.{stamp}.'.encode() + body, 'sha256')).decode()
            if (abs(self.now - int(stamp)) > 300 or
                    not hmac.compare_digest(headers['webhook-signature'], 'v1,' + expected) or
                    headers['X-MCP-Subscription-Id'] != self.selection.subscription):
                raise Blocked('UNTRUSTED_DELIVERY')
            item = json.loads(body)
            data, image = item['data'], item['data']['image']
            if (item['eventId'] != identity or item['name'] != 'whatsapp.received' or
                    item['cursor'] is not None or data['direction'] != 'inbound' or
                    data['workspace_id'] != self.selection.workspace or
                    data['from']['bsuid'] != self.selection.sender or
                    data['to'] != self.selection.recipient or image['mime_type'] != 'image/jpeg' or
                    any(key in data for key in ('video', 'audio', 'document', 'text'))):
                raise Blocked('UNSELECTED_EVENT')
            for value in (identity, data['whatsapp_id'], image['id']):
                if not isinstance(value, str) or not 1 <= len(value) <= 128:
                    raise Blocked('INVALID_IDENTITY')
            return item
        except (KeyError, TypeError, ValueError) as exc:
            raise Blocked('INVALID_EVENT') from exc

    def run(self, body, headers):
        """One bounded attempt. Retry requires another explicit call/process run."""
        try:
            item = self.check(body, headers)
        except Blocked as exc:
            return {'label': 'NOT LIVE', 'status': 'BLOCKED', 'stage': None, 'reason': str(exc)}
        data = item['data']
        correlation = {'workspace': self.selection.workspace, 'sender': self.selection.sender,
                       'recipient': self.selection.recipient, 'message_id': data['whatsapp_id'],
                       'media_id': data['image']['id'], 'destination': self.selection.destination}
        job_id = str(uuid5(NAMESPACE_URL, encoded(correlation).decode()))
        folder = self.root / job_id
        journal = folder / 'state.json'
        state = {'label': 'NOT LIVE', 'job_id': job_id, 'correlation': correlation,
                 'stage': 'EVENT_RECEIVED', 'history': ['EVENT_RECEIVED'], 'events': {},
                 'attempts': 0, 'live_provider_verified': False, 'production_routed': False}
        try:
            if journal.exists():
                state = json.loads(journal.read_text())
                if state['correlation'] != correlation:
                    raise Blocked('CORRELATION_CONFLICT')
            # Event-ID collision across different messages is also rejected on restart.
            marker = self.root / 'events' / (digest(item['eventId'].encode()) + '.json')
            fingerprint = digest(body)
            if marker.exists() and json.loads(marker.read_text()) != {'body_sha256': fingerprint, 'job_id': job_id}:
                raise Blocked('EVENT_ID_CONTENT_CONFLICT')
            atomic(marker, encoded({'body_sha256': fingerprint, 'job_id': job_id}))
            state['events'][item['eventId']] = fingerprint
            state['attempts'] += 1
            state['status'] = 'PENDING'
            state.pop('reason', None)
            atomic(journal, encoded(state))
            package = folder / 'original.zip'
            if package.exists():
                checked = validate(package)
                manifest, photo = unpack(package.read_bytes())
                if (checked['job_id'] != job_id or manifest['source']['correlation'] != correlation or
                        digest(photo) != JPEG_SHA256 or
                        package.read_bytes() != make_package(job_id, correlation, photo) or
                        ('package_sha256' in state and digest(package.read_bytes()) != state['package_sha256'])):
                    raise Blocked('ORIGINAL_INTEGRITY_FAILED')
            else:
                if state['stage'] != 'EVENT_RECEIVED':
                    raise Blocked('ORIGINAL_MISSING')
                if state['attempts'] > 3:
                    raise Blocked('RETRY_LIMIT')
                media = self.bird.fetch(correlation['workspace'], correlation['message_id'], correlation['media_id'])
                if (media.workspace, media.message_id, media.media_id) != (
                        correlation['workspace'], correlation['message_id'], correlation['media_id']):
                    raise Blocked('MEDIA_CORRELATION_FAILED')
                if (media.content_type != 'image/jpeg' or media.content_length != len(media.data) or
                        not media.data or digest(media.data) != JPEG_SHA256):
                    raise Blocked('MEDIA_INTEGRITY_FAILED')
                atomic(package, make_package(job_id, correlation, media.data))
                checked = validate(package)
                manifest, photo = unpack(package.read_bytes())
            state['media_sha256'], state['media_bytes'] = digest(photo), len(photo)
            state['package_sha256'] = digest(package.read_bytes())
            self.advance(state, journal, 'MEDIA_FETCHED')
            receipt = self.work.lookup(job_id)
            if receipt is None:
                if state['attempts'] > 3:
                    raise Blocked('RETRY_LIMIT')
                try:
                    receipt = self.work.deliver(job_id, package.read_bytes(), checked)
                except OSError:
                    # Lost acknowledgement is uncertain, never proof of delivery failure.
                    receipt = self.work.lookup(job_id)
                    if receipt is None:
                        raise
            if (receipt.get('job_id') != job_id or receipt.get('receipt_id') != 'capture-' + job_id or
                    receipt.get('package_sha256') != state['package_sha256'] or
                    receipt.get('status') != 'RECEIVED_TEST_ONLY' or receipt.get('attachments') != 1 or
                    any(receipt.get(key) is not False for key in
                        ('routed', 'departmental_updates', 'production_evidence_filed'))):
                raise Blocked('DESTINATION_RECEIPT_MISMATCH')
            state['receipt_id'] = receipt['receipt_id']
            self.advance(state, journal, 'DESTINATION_ACCEPTED')
            independent = self.work.readback(job_id)
            verified_manifest, verified_photo = unpack(independent)
            if (digest(independent) != state['package_sha256'] or
                    verified_manifest != manifest or verified_photo != photo or
                    digest(verified_photo) != state['media_sha256']):
                raise Blocked('DESTINATION_READBACK_MISMATCH')
            self.advance(state, journal, 'INDEPENDENTLY_VERIFIED')
            state['status'] = 'INDEPENDENTLY_VERIFIED'
        except (Blocked, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
            state['status'] = 'BLOCKED' if isinstance(exc, Blocked) else 'FAILED'
            state['reason'] = str(exc) if isinstance(exc, Blocked) else 'LOCAL_OR_MOCK_OPERATION_FAILED'
        # Preserve the original package and the last proven stage on every failure.
        atomic(journal, encoded(state))
        return state

    @staticmethod
    def advance(state, journal, stage):
        state['stage'] = stage
        if stage not in state['history']:
            state['history'].append(stage)
        atomic(journal, encoded(state))


def make_package(job_id, correlation, photo):
    manifest = {'version': '0.3', 'status': 'LOCAL_EXPORT_NOT_TRANSMITTED',
                'job_id': job_id, 'instructions': 'Synthetic Bird to Sophie/Work test. NOT LIVE.',
                'source': {'kind': 'synthetic_bird_media_mock', 'label': 'NOT LIVE',
                           'physical_glasses': False, 'bird_live': False,
                           'hash_basis': 'local synthetic fixture oracle, not provider checksum',
                           'correlation': correlation},
                'attachments': [{'id': str(uuid5(NAMESPACE_URL, job_id + '/photo')),
                    'archive_path': 'evidence/bird-synthetic.jpg', 'name': 'bird-synthetic.jpg',
                    'content_type': 'image/jpeg', 'bytes': len(photo), 'sha256': digest(photo)}]}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, value in (('manifest.json', encoded(manifest)),
                            ('instructions.txt', manifest['instructions'].encode()),
                            ('evidence/bird-synthetic.jpg', photo)):
            archive.writestr(zipfile.ZipInfo(name, date_time=(2026, 11, 10, 12, 0, 0)), value)
    return buffer.getvalue()


def unpack(body):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        return json.loads(archive.read('manifest.json')), archive.read('evidence/bird-synthetic.jpg')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='NOT LIVE local synthetic Bird/Work experiment. No sockets.')
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--mock-failure', choices=('delivery', 'lost_ack', 'readback'))
    args = parser.parse_args()
    result = Pipeline(args.state / 'outbox', MockBird(),
                      MockWork(args.state / 'work-mock', args.mock_failure)).run(*signed(event()))
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result['status'] == 'INDEPENDENTLY_VERIFIED' else 1)
