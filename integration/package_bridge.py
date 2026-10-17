"""Offline bridge from a *previously validated* Mi Mundo v0.3 ZIP to fixture evidence.
No network, no production Drive/Post Office writes. Revalidates attachment hashes.
"""
from __future__ import annotations
import hashlib
import io
import json
import re
import uuid
import zipfile
from pathlib import Path
from evidence_adapter import EvidenceInput, LocalFixtureEvidenceStore, InvalidEvidence

MAX_ZIP_BYTES = 100 * 1024 * 1024
MAX_FILES = 100

def ingest_package(zip_bytes: bytes, store: LocalFixtureEvidenceStore, *, department: str,
                   privacy_class: str, received_at: str, source: str = 'mi-mundo-capture') -> dict:
    """Bounded local fixture: no authority to mark original archived in Google Drive."""
    if not zip_bytes or len(zip_bytes) > MAX_ZIP_BYTES:
        raise InvalidEvidence('invalid ZIP size')
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            members = z.infolist()
            names = [i.filename for i in members]
            if len(members) > MAX_FILES + 2 or len(names) != len(set(names)):
                raise InvalidEvidence('invalid ZIP entry count')
            for entry in members:
                if (entry.filename.startswith('/') or '\\' in entry.filename
                    or any(p in ('', '.', '..') for p in entry.filename.split('/'))
                    or entry.flag_bits & 1 or entry.file_size > MAX_ZIP_BYTES):
                    raise InvalidEvidence('unsafe ZIP entry')
            if sum(i.file_size for i in members) > MAX_ZIP_BYTES:
                raise InvalidEvidence('expanded ZIP too large')
            if 'manifest.json' not in names or 'instructions.txt' not in names:
                raise InvalidEvidence('manifest missing')
            if z.getinfo('manifest.json').file_size > 1024*1024:
                raise InvalidEvidence('manifest oversized')
            manifest = json.loads(z.read('manifest.json'))
            if manifest.get('version') != '0.3' or manifest.get('status') != 'LOCAL_EXPORT_NOT_TRANSMITTED':
                raise InvalidEvidence('unsupported export')
            job_id = str(uuid.UUID(manifest['job_id']))
            if job_id != manifest['job_id']:
                raise InvalidEvidence('noncanonical job ID')
            instructions = manifest['instructions']
            if not isinstance(instructions, str) or z.read('instructions.txt').decode() != (instructions or '(No written instructions)'):
                raise InvalidEvidence('instructions mismatch')
            attachments = manifest['attachments']
            if not isinstance(attachments, list) or len(attachments) > MAX_FILES:
                raise InvalidEvidence('invalid attachment list')
            expected = {'manifest.json', 'instructions.txt'}
            pending = []
            used_ids = set()
            for att in attachments:
                attachment_id = str(att['id'])
                path = att['archive_path']
                if (not attachment_id or attachment_id in used_ids or not re.fullmatch(r'evidence/[^/]+',path)
                    or path in expected or not re.fullmatch('[0-9a-f]{64}',att['sha256'])
                    or type(att['bytes']) is not int):
                    raise InvalidEvidence('invalid attachment entry')
                used_ids.add(attachment_id); expected.add(path)
                item = z.getinfo(path)
                if item.file_size != att['bytes']:
                    raise InvalidEvidence('size mismatch')
                raw = z.read(path)
                if hashlib.sha256(raw).hexdigest() != att['sha256']:
                    raise InvalidEvidence('checksum mismatch')
                meta = EvidenceInput(job_id=job_id,attachment_id=attachment_id,
                    original_filename=str(att.get('name') or Path(path).name),
                    mime_type=str(att.get('type') or 'application/octet-stream'),
                    source=source, privacy_class=privacy_class,
                    receiving_department=department,received_at=received_at,
                    captured_at=None)
                pending.append((meta,raw))
            if set(names) != expected:
                raise InvalidEvidence('unlisted entries')
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile, RuntimeError) as exc:
        raise InvalidEvidence('invalid capture package') from exc
    results = []
    for meta, raw in pending:
        row = store.ingest(meta,raw)
        store.verify(row['evidence_id'])
        results.append(row)
    return {'job_id':job_id,'status':'FILED_LOCAL_TEST_ONLY','attachments':results,
            'production_evidence_filed':False,'routed':False,'departmental_updates':False}
