import hashlib
import io
import json
import os
import secrets
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from meta_display_harness import make_harness, prepare, fixture, HERE
from receiver import FixtureStore


class MetaHarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.server = make_harness(self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.token = self.request('/harness/session', headers={'X-Harness': 'synthetic'})[1]['token']

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, path, method='GET', data=None, headers=None):
        merged = {'Authorization': 'Bearer ' + getattr(self, 'token', '')}
        merged.update(headers or {})
        request = urllib.request.Request(self.url + path, method=method, data=data, headers=merged)
        try:
            response = urllib.request.urlopen(request, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            body = json.loads(raw) if response.headers.get_content_type() == 'application/json' else raw
            return response.status, body

    def test_three_media_via_existing_javascript_client_and_independent_bytes(self):
        for mode in ('photo', 'video', 'audio'):
            with self.subTest(mode=mode):
                code, local = self.request('/harness/capture/' + mode, 'POST', b'')
                self.assertEqual(code, 201)
                job = local['job_id']
                package = self.root / 'outbox' / (job + '.zip')
                script = '''
import {readFile} from 'node:fs/promises';
const {CaptureClient} = await import(process.env.TEST_MODULE);
const create = () => new CaptureClient({endpoint:process.env.TEST_URL, token:process.env.TEST_TOKEN, testLoopback:true});
const blob = new Blob([await readFile(process.env.TEST_PACKAGE)]);
const first = await create().transmit(process.env.TEST_JOB,blob);
// New client simulates process restart, losing all in-memory pending state.
const second = await create().transmit(process.env.TEST_JOB,blob);
if(first.receipt_id !== second.receipt_id) throw Error('Duplicate receipt');
console.log(JSON.stringify(first));
'''
                result = subprocess.run(['node', '--input-type=module'], input=script,
                    capture_output=True, text=True, timeout=20, env={**os.environ,
                    'TEST_MODULE': (HERE / 'capture-client.mjs').as_uri(),
                    'TEST_URL': self.url, 'TEST_TOKEN': self.token, 'TEST_JOB': job,
                    'TEST_PACKAGE': str(package)})
                self.assertEqual(result.returncode, 0, result.stderr)
                receipt = json.loads(result.stdout)
                self.assertEqual(receipt['status'], 'RECEIVED_TEST_ONLY')
                self.assertFalse(receipt['production_evidence_filed'])
                remote = self.root / 'receiver' / job / 'original.zip'
                self.assertEqual(remote.read_bytes(), package.read_bytes())
                with zipfile.ZipFile(remote) as stored:
                    manifest = json.loads(stored.read('manifest.json'))
                    attachment = manifest['attachments'][0]
                    actual = stored.read(attachment['archive_path'])
                    self.assertEqual(hashlib.sha256(actual).hexdigest(), attachment['sha256'])
                    self.assertEqual(len(actual), attachment['bytes'])
                    self.assertFalse(manifest['source']['physical_glasses'])
                    self.assertEqual(manifest['source']['capture_time_basis'], 'fixture_generated')
                self.assertEqual(FixtureStore(self.root / 'receiver').read(job), receipt)

    def test_network_failure_keeps_original_for_reconciliation(self):
        local = prepare(self.root / 'outbox', 'audio')
        package = self.root / 'outbox' / (local['job_id'] + '.zip')
        original = package.read_bytes()
        script = '''
import {CaptureClient} from './integration/capture-client.mjs';
const client = new CaptureClient({endpoint:'http://127.0.0.1:1', token:'x'.repeat(32),testLoopback:true,
fetchImpl:async()=>{throw Error('OFFLINE')}});
try { await client.transmit(process.env.TEST_JOB,new Blob(['synthetic'])); process.exit(2); }
catch { console.log('NOT_VERIFIED'); }
'''
        result = subprocess.run(['node', '--input-type=module'], input=script, text=True,
                                capture_output=True, timeout=10, cwd=HERE.parent,
                                env={**os.environ, 'TEST_JOB': local['job_id']})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('NOT_VERIFIED', result.stdout)
        self.assertEqual(package.read_bytes(), original)
        self.assertEqual(list((self.root / 'receiver').iterdir()), [])

    def test_wrong_token_origin_host_and_real_file_body_rejected(self):
        path = '/harness/capture/audio'
        self.assertEqual(self.request(path, 'POST', b'', {'Authorization': 'Bearer wrong'})[0], 401)
        self.assertEqual(self.request(path, 'POST', b'', {'Origin': 'https://untrusted.invalid'})[0], 401)
        self.assertEqual(self.request(path, 'POST', b'not-an-import')[0], 400)
        self.assertEqual(self.request('/harness/session', headers={'X-Harness':'synthetic', 'Host':'evil.invalid'})[0], 403)
        self.assertEqual(self.request('/harness/session')[0], 403)
        self.assertEqual(list((self.root / 'outbox').iterdir()), [])

    def test_corrupt_server_copy_cannot_return_success(self):
        local = prepare(self.root / 'outbox', 'audio')
        job = local['job_id']
        package = (self.root / 'outbox' / (job + '.zip')).read_bytes()
        self.assertEqual(self.request('/v1/jobs/' + job, 'PUT', package, {'Content-Type':'application/zip'})[0], 201)
        (self.root / 'receiver' / job / 'original.zip').write_bytes(b'CORRUPT')
        self.assertEqual(self.request('/v1/jobs/' + job)[0], 503)

    def test_same_job_changed_bytes_conflict_and_distinct_events_survive(self):
        one, two = [prepare(self.root / 'outbox', 'audio') for _ in range(2)]
        self.assertNotEqual(one['job_id'], two['job_id'])
        for local in (one, two):
            job = local['job_id']
            data = (self.root / 'outbox' / (job + '.zip')).read_bytes()
            path = '/v1/jobs/' + job
            headers = {'Content-Type': 'application/zip'}
            self.assertEqual(self.request(path, 'PUT', data, headers)[0], 201)
            self.assertEqual(self.request(path, 'PUT', data, headers)[0], 200)
            buf = io.BytesIO(data)
            with zipfile.ZipFile(buf, 'a') as altered:
                altered.comment = b'changed'
            self.assertEqual(self.request(path, 'PUT', buf.getvalue(), headers)[0], 409)

    def test_video_fixture_is_playable_with_audio_track(self):
        target = self.root / 'fixture.mp4'
        target.write_bytes(fixture('video'))
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type',
                                 '-of', 'json', str(target)], capture_output=True, text=True, check=True)
        kinds = [s['codec_type'] for s in json.loads(result.stdout)['streams']]
        self.assertIn('video', kinds)
        self.assertIn('audio', kinds)

    def test_server_restart_preserves_receipt_and_local_original(self):
        local = prepare(self.root / 'outbox', 'photo')
        job = local['job_id']
        package = (self.root / 'outbox' / (job + '.zip')).read_bytes()
        path = '/v1/jobs/' + job
        headers = {'Content-Type': 'application/zip'}
        code, receipt = self.request(path, 'PUT', package, headers)
        self.assertEqual(code, 201)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.server = make_harness(self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.token = self.request('/harness/session', headers={'X-Harness':'synthetic'})[1]['token']
        self.assertEqual(self.request(path), (200, receipt))
        self.assertEqual(self.request(path, 'PUT', package, headers), (200, receipt))
        self.assertEqual((self.root / 'outbox' / (job + '.zip')).read_bytes(), package)


if __name__ == '__main__':
    unittest.main()
