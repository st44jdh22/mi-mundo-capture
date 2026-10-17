"""Offline Mi Mundo evidence ingestion reference adapter.

NO Google Drive writes, Post Office writes, network connections or production activation.
Receiver must supply verified original bytes and an authenticated principal.
"""
from __future__ import annotations
import hashlib
import json
import os
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

class Conflict(Exception): pass
class InvalidEvidence(Exception): pass

@dataclass(frozen=True)
class EvidenceInput:
    job_id: str
    attachment_id: str
    original_filename: str
    mime_type: str
    source: str
    privacy_class: str
    receiving_department: str
    received_at: str
    captured_at: Optional[str] = None

class LocalFixtureEvidenceStore:
    """Local-only file and SQLite index for controlled fixture tests.

    Production requires a different authorised Drive adapter and readback.
    """
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.blobs = self.root / 'blobs'
        self.blobs.mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.root / 'index.sqlite3')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS evidence (
            evidence_id TEXT PRIMARY KEY, job_id TEXT NOT NULL,
            attachment_id TEXT NOT NULL, sha256 TEXT NOT NULL,
            size INTEGER NOT NULL, metadata_json TEXT NOT NULL,
            storage_path TEXT NOT NULL, filed_at TEXT NOT NULL,
            UNIQUE(job_id,attachment_id))''')
        self.db.commit()

    def ingest(self, meta: EvidenceInput, original: bytes) -> dict:
        try: uuid.UUID(meta.job_id)
        except (ValueError, AttributeError): raise InvalidEvidence('invalid job ID')
        if not meta.attachment_id or not meta.source or not meta.receiving_department:
            raise InvalidEvidence('missing provenance')
        if meta.privacy_class not in {'GENERAL','BUSINESS-CONFIDENTIAL','FINANCIAL','HEALTH/WELLNESS','HIGHLY PRIVATE'}:
            raise InvalidEvidence('unknown privacy class')
        if not original or len(original) > 100*1024*1024:
            raise InvalidEvidence('empty/oversized blob')
        digest = hashlib.sha256(original).hexdigest()
        meta_text = json.dumps(asdict(meta),sort_keys=True)
        self.db.execute('BEGIN IMMEDIATE')
        prior = self.db.execute('SELECT evidence_id,sha256,metadata_json,storage_path,size FROM evidence WHERE job_id=? AND attachment_id=?', (meta.job_id,meta.attachment_id)).fetchone()
        if prior:
            if prior[1]!=digest or prior[2]!=meta_text or prior[4]!=len(original):
                self.db.rollback()
                raise Conflict('same job/attachment ID with changed evidence')
            path = self.root / prior[3]
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                self.db.rollback()
                raise InvalidEvidence('stored bytes missing/corrupt')
            self.db.commit()
            return {'evidence_id':prior[0],'status':'FILED_LOCAL_TEST_ONLY','duplicate':True,'sha256':digest,'size':len(original)}
        evidence_id = 'EV-'+uuid.uuid4().hex.upper()
        relative = f'blobs/{evidence_id}.bin'
        path = self.root / relative
        temp = self.blobs / ('.'+uuid.uuid4().hex+'.tmp')
        try:
            with temp.open('xb') as f:
                f.write(original)
                f.flush(); os.fsync(f.fileno())
            os.replace(temp,path)
            if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                raise InvalidEvidence('post-write byte readback failed')
            self.db.execute('INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?)',
                (evidence_id,meta.job_id,meta.attachment_id,digest,len(original),meta_text,relative,datetime.now(timezone.utc).isoformat()))
            self.db.commit()
        except Exception:
            self.db.rollback()
            temp.unlink(missing_ok=True)
            path.unlink(missing_ok=True)
            raise
        return {'evidence_id':evidence_id,'status':'FILED_LOCAL_TEST_ONLY','duplicate':False,'sha256':digest,'size':len(original)}

    def verify(self, evidence_id: str) -> dict:
        """Independent local readback; no production evidence claim."""
        row = self.db.execute('SELECT sha256,size,storage_path FROM evidence WHERE evidence_id=?', (evidence_id,)).fetchone()
        if not row:
            raise InvalidEvidence('unknown evidence ID')
        path = self.root / row[2]
        if not path.is_file():
            raise InvalidEvidence('stored file missing')
        original = path.read_bytes()
        if len(original) != row[1] or hashlib.sha256(original).hexdigest() != row[0]:
            raise InvalidEvidence('stored file corrupt')
        return {'evidence_id': evidence_id, 'status': 'VERIFIED_LOCAL_TEST_ONLY', 'sha256': row[0], 'size': row[1]}

    def close(self): self.db.close()


def business_duplicate_decision(existing_finance:bool, existing_kitchen:bool, existing_inventory:bool)->dict:
    """Read-only planning; NEVER posts or adjusts records."""
    return {'finance':'NOOP' if existing_finance else 'REVIEW_REQUIRED',
            'kitchen':'NOOP' if existing_kitchen else 'REVIEW_REQUIRED',
            'inventory':'NOOP' if existing_inventory else 'REVIEW_REQUIRED',
            'writes_performed':0}
