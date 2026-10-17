"""Offline capture boundary validation. No extraction, network, storage or routing."""
import hashlib
import json
import re
import zipfile
from pathlib import PurePosixPath
from uuid import UUID

MAX_ARCHIVE = 100 * 1024 * 1024
MAX_ENTRIES = 102


def validate(path):
    if path.stat().st_size > MAX_ARCHIVE:
        raise ValueError('Archive exceeds limit')
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [i.filename for i in entries]
        if len(entries) > MAX_ENTRIES or len(names) != len(set(names)):
            raise ValueError('Too many or duplicate ZIP entries')
        if sum(i.file_size for i in entries) > MAX_ARCHIVE:
            raise ValueError('Expanded archive exceeds limit')
        for item in entries:
            name = item.filename
            if (not name or name.startswith('/') or '\\' in name
                    or any(p in ('', '.', '..') for p in name.split('/'))
                    or ':' in name or item.flag_bits & 1
                    or (item.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('Unsafe archive entry')
        if 'manifest.json' not in names or 'instructions.txt' not in names:
            raise ValueError('Required metadata absent')
        if archive.getinfo('manifest.json').file_size > 1024 * 1024:
            raise ValueError('Manifest exceeds limit')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('version') != '0.3' or manifest.get('status') != 'LOCAL_EXPORT_NOT_TRANSMITTED':
            raise ValueError('Unsupported capture state/version')
        UUID(manifest['job_id'])
        instructions = manifest['instructions']
        if not isinstance(instructions, str):
            raise ValueError('Invalid instructions')
        if archive.read('instructions.txt').decode('utf-8') != (instructions or '(No written instructions)'):
            raise ValueError('Instructions mismatch')
        attachments = manifest['attachments']
        if not isinstance(attachments, list) or len(attachments) > 100:
            raise ValueError('Invalid attachments')
        expected = {'manifest.json', 'instructions.txt'}
        ids = set()
        for item in attachments:
            name, digest = item['archive_path'], item['sha256']
            if (name in expected or not name.startswith('evidence/')
                    or len(PurePosixPath(name).parts) != 2 or item['id'] in ids
                    or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)):
                raise ValueError('Invalid attachment identity')
            expected.add(name)
            ids.add(item['id'])
            info = archive.getinfo(name)
            if type(item['bytes']) is not int or info.file_size != item['bytes']:
                raise ValueError('Attachment size mismatch')
            with archive.open(name) as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual != digest:
                raise ValueError('Attachment checksum mismatch')
        if set(names) != expected:
            raise ValueError('Unlisted archive content')
        # Identity is for later comparison by the EXISTING intake; not a new ledger.
        fingerprint = hashlib.sha256(json.dumps({
            'instructions': instructions,
            'attachments': sorted(i['sha256'] for i in attachments)
        }, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return {'job_id': manifest['job_id'], 'attachments': len(attachments),
                'content_fingerprint': fingerprint, 'status': 'VALIDATED_LOCAL_ONLY',
                'transmitted': False, 'routed': False}


if __name__ == '__main__':
    import sys
    from pathlib import Path
    try:
        print(json.dumps(validate(Path(sys.argv[1])), indent=2))
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile, RuntimeError):
        print(json.dumps({'status': 'REJECTED', 'transmitted': False}))
        sys.exit(1)
