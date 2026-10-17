import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from validate_job import validate


class BoundaryTests(unittest.TestCase):
    def package(self, root, change=None, extra=None, data=b'original'):
        m = {'version': '0.3', 'job_id': 'a54e5f03-da6c-44fa-834a-9a613d323fee',
             'status': 'LOCAL_EXPORT_NOT_TRANSMITTED', 'instructions': '',
             'attachments': [{'id': 1, 'archive_path': 'evidence/test.bin',
                              'bytes': 8, 'sha256': hashlib.sha256(b'original').hexdigest()}]}
        if change:
            change(m)
        p = Path(root) / 'test.zip'
        with zipfile.ZipFile(p, 'w') as z:
            z.writestr('manifest.json', json.dumps(m))
            z.writestr('instructions.txt', '(No written instructions)')
            z.writestr('evidence/test.bin', data)
            if extra:
                z.writestr(extra, 'x')
        return p

    def test_valid_and_repeat_identity(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.package(d)
            self.assertEqual(validate(p), validate(p))
            self.assertFalse(validate(p)['transmitted'])

    def test_rejects_mutation_cases(self):
        cases = [
            {'data': b'changed!'},
            {'extra': '../escape'},
            {'extra': 'unlisted.txt'},
            {'change': lambda m: m.update(status='SENT')},
            {'change': lambda m: m.update(instructions='different')},
            {'change': lambda m: m.update(job_id='invalid')},
            {'change': lambda m: m['attachments'][0].update(bytes=9)},
            {'change': lambda m: m['attachments'].append(dict(m['attachments'][0]))},
        ]
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as d:
                with self.assertRaises((ValueError, KeyError)):
                    validate(self.package(d, **case))


if __name__ == '__main__':
    unittest.main()
