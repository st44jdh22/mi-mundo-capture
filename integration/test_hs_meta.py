"""HS-META-001: synthetic media-shaped ZIPs through the existing validator/store.

Fixtures contain markers, NOT playable media or personal recordings.
Never use this test store for actual user footage.
"""
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
import zipfile

from validate_job import validate
from receiver import FixtureStore, Conflict

MEDIA = {'photo': 'image/jpeg', 'video': 'video/mp4', 'audio': 'audio/mp4'}

def synthetic_package(kind, job_id, suffix=''):
    if kind not in MEDIA:
        raise ValueError('Invalid synthetic kind')
    payload = f'SYNTHETIC-NOT-PLAYABLE-{kind}-{suffix}'.encode()
    filename = f'evidence/{kind}.bin'
    instructions = 'HS-META-001 isolated synthetic intake fixture only.'
    manifest = {
        'version': '0.3',
        'status': 'LOCAL_EXPORT_NOT_TRANSMITTED',
        'job_id': job_id,
        'instructions': instructions,
        'source': 'hs-meta-001-test-harness',
        'attachments': [{
            'id': str(uuid4()),
            'archive_path': filename,
            'content_type_claim': MEDIA[kind],
            'format_verified': False,
            'capture_mode': kind,
            'bytes': len(payload),
            'sha256': hashlib.sha256(payload).hexdigest(),
        }],
    }
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, 'w', zipfile.ZIP_STORED) as z:
        z.writestr('manifest.json', json.dumps(manifest))
        z.writestr('instructions.txt', instructions)
        z.writestr(filename, payload)
    return blob.getvalue(), payload

class HSMetaBoundaryTests(unittest.TestCase):
    def test_three_modes_validate_without_claiming_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            for kind in MEDIA:
                with self.subTest(kind=kind):
                    job_id = str(uuid4())
                    body, payload = synthetic_package(kind, job_id)
                    path = Path(directory) / (kind + '.zip')
                    path.write_bytes(body)
                    checked = validate(path)
                    self.assertEqual(checked['status'], 'VALIDATED_LOCAL_ONLY')
                    self.assertFalse(checked['transmitted'])
                    self.assertEqual(checked['attachments'], 1)
                    with zipfile.ZipFile(path) as z:
                        self.assertEqual(z.read('evidence/' + kind + '.bin'), payload)

    def test_verified_store_and_same_byte_retry_after_reopening(self):
        with tempfile.TemporaryDirectory() as directory:
            job_id = str(uuid4())
            body, _ = synthetic_package('photo', job_id)
            store = FixtureStore(directory)
            first, created = store.receive(job_id, body, {'attachments': 1})
            self.assertTrue(created)
            later, created = FixtureStore(directory).receive(job_id, body, {'attachments': 1})
            self.assertFalse(created)
            self.assertEqual(first, later)
            self.assertEqual(first['status'], 'RECEIVED_TEST_ONLY')
            self.assertFalse(first['routed'])
            self.assertEqual(first['package_sha256'], hashlib.sha256(body).hexdigest())

    def test_same_job_id_with_changed_media_conflicts(self):
        with tempfile.TemporaryDirectory() as directory:
            job_id = str(uuid4())
            photo, _ = synthetic_package('photo', job_id)
            video, _ = synthetic_package('video', job_id)
            store = FixtureStore(directory)
            store.receive(job_id, photo, {'attachments': 1})
            with self.assertRaises(Conflict):
                store.receive(job_id, video, {'attachments': 1})
            self.assertEqual(store.read(job_id)['package_sha256'], hashlib.sha256(photo).hexdigest())

    def test_corrupted_original_never_returns_success(self):
        with tempfile.TemporaryDirectory() as directory:
            job_id = str(uuid4())
            body, _ = synthetic_package('audio', job_id)
            store = FixtureStore(directory)
            store.receive(job_id, body, {'attachments': 1})
            (Path(directory) / job_id / 'original.zip').write_bytes(b'corrupted')
            with self.assertRaises(OSError):
                store.read(job_id)

if __name__ == '__main__':
    unittest.main()
