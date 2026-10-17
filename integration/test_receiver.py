import io
import json
import secrets
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from receiver import FixtureStore, make_server
import test_validate_job


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / 'store').mkdir()
        self.store = FixtureStore(root / 'store')
        self.token = secrets.token_urlsafe(32)
        self.origin = 'https://st44jdh22.github.io'
        self.server = make_server(self.store, self.token, self.origin)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)
        self.job_id = 'a54e5f03-da6c-44fa-834a-9a613d323fee'
        self.body = test_validate_job.BoundaryTests().package(root).read_bytes()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, method='PUT', body=None, token=True, origin=None, job_id=None):
        headers = {'Content-Type': 'application/zip', 'Origin': origin or self.origin}
        if token:
            headers['Authorization'] = 'Bearer ' + self.token
        req = urllib.request.Request(self.url + '/v1/jobs/' + (job_id or self.job_id),
                                     data=body, headers=headers, method=method)
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}, response.headers

    def test_receive_readback_retry_and_restart(self):
        code, receipt, headers = self.request(body=self.body)
        self.assertEqual(code, 201)
        self.assertEqual(receipt['status'], 'RECEIVED_TEST_ONLY')
        self.assertFalse(receipt['routed'])
        self.assertEqual(headers['Access-Control-Allow-Origin'], self.origin)
        self.assertEqual(self.request('GET')[:2], (200, receipt))
        self.assertEqual(self.request(body=self.body)[:2], (200, receipt))
        self.assertEqual(FixtureStore(self.store.root).read(self.job_id), receipt)
        self.assertEqual((self.store.root / self.job_id / 'original.zip').read_bytes(), self.body)

    def test_auth_and_origin_reject_without_storage(self):
        self.assertEqual(self.request(body=self.body, token=False)[0], 401)
        self.assertEqual(self.request(body=self.body, origin='https://untrusted.invalid')[0], 401)
        self.assertEqual(list(self.store.root.iterdir()), [])

    def test_malformed_and_mismatched_job_reject(self):
        self.assertEqual(self.request(body=b'broken ZIP')[0], 422)
        other = 'b54e5f03-da6c-44fa-834a-9a613d323fee'
        self.assertEqual(self.request(body=self.body, job_id=other)[0], 409)
        self.assertEqual(list(self.store.root.iterdir()), [])

    def test_changed_package_conflicts(self):
        self.assertEqual(self.request(body=self.body)[0], 201)
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.body)) as original, zipfile.ZipFile(buf, 'w') as updated:
            for name in original.namelist():
                updated.writestr(name, original.read(name))
            updated.comment = b'different package, same job'
        self.assertEqual(self.request(body=buf.getvalue())[0], 409)
        self.assertEqual((self.store.root / self.job_id / 'original.zip').read_bytes(), self.body)

    def test_corrupt_storage_never_returns_success(self):
        self.request(body=self.body)
        (self.store.root / self.job_id / 'original.zip').write_bytes(b'corrupt')
        self.assertEqual(self.request('GET')[0], 503)
        self.assertEqual(self.request(body=self.body)[0], 503)

    def test_preflight_and_missing_receipt(self):
        self.assertEqual(self.request('OPTIONS')[0], 204)
        self.assertEqual(self.request('GET')[0], 404)


if __name__ == '__main__':
    unittest.main()
