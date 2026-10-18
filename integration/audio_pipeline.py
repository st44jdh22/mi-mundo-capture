"""Review-only, synthetic audio archive and resumable transcription state machine.

No real personal recordings or provider traffic. This module intentionally has no
external microphone, cloud API, Post Office, or real Chef side effects. The fixture
transcriber demonstrates adapter boundaries and restart/lost-ack reconciliation.
"""
from __future__ import annotations
import hashlib
import hmac
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import uuid
from dataclasses import dataclass

ALLOWED_MIME = {'audio/webm', 'audio/wav', 'audio/mp4', 'audio/ogg'}
MAX_BYTES = 8 * 1024 * 1024  # fixture-only bound, NOT a real product voice limit
MAX_ATTEMPTS = 3

class PayloadConflict(Exception): pass
class PolicyBlocked(Exception): pass
class Unavailable(Exception): pass

@dataclass(frozen=True)
class ArchiveResult:
    source_id: str
    sha256: str
    state: str
    byte_length: int

class SyntheticTranscriber:
    """Deterministic test adapter. Never transcribes actual spoken words."""
    def __init__(self, *, fail: bool = False):
        self.calls = 0
        self.fail = fail

    def transcribe(self, audio: bytes, source_id: str) -> str:
        self.calls += 1
        if self.fail: raise Unavailable('provider_unavailable')
        return 'Synthetic transcription fixture for source ' + source_id[:8]

class AudioPipeline:
    """One local fixture owner; server-side durable disk and SQLite checkpoints.

    Run only in disposable isolated test environment. No multi-tenant authentication,
    encryption, cloud object storage, concurrent cross-process leases or provider STT.
    """
    def __init__(self, root: str | Path, adapter: SyntheticTranscriber | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.objects = self.root/'objects'
        self.objects.mkdir(exist_ok=True)
        self.path = self.root/'audio_jobs.sqlite3'
        self.db = sqlite3.connect(str(self.path), timeout=15, isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('''CREATE TABLE IF NOT EXISTS recordings(
            source_id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, byte_length INTEGER NOT NULL,
            mime_type TEXT NOT NULL, object_name TEXT NOT NULL, created_at INTEGER NOT NULL,
            archive_state TEXT NOT NULL CHECK(archive_state IN ('DURABLE_LOCAL','FAILED')),
            transcription_state TEXT NOT NULL CHECK(transcription_state IN
              ('PENDING','IN_FLIGHT','RETRY_WAIT','TRANSCRIBED','REVIEW_REQUIRED','POLICY_BLOCKED')),
            attempts INTEGER NOT NULL DEFAULT 0, next_retry_at INTEGER,
            transcript TEXT, transcript_sha256 TEXT, last_error TEXT)''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS dispatches(
            source_id TEXT PRIMARY KEY REFERENCES recordings(source_id),
            source_sha256 TEXT NOT NULL, transcript_sha256 TEXT NOT NULL,
            stage TEXT NOT NULL CHECK(stage IN ('READY_FOR_POST_OFFICE','ACKNOWLEDGED_EXTERNALLY')),
            created_at INTEGER NOT NULL)''')
        self.adapter = adapter or SyntheticTranscriber()

    def close(self): self.db.close()

    def _valid_uuid(self, source_id):
        try: return str(uuid.UUID(source_id))
        except (ValueError, TypeError): raise ValueError('Invalid source UUID')

    def accept(self, source_id: str, audio: bytes, mime_type='audio/webm', now: int | None = None):
        source_id = self._valid_uuid(source_id)
        if mime_type not in ALLOWED_MIME: raise PolicyBlocked('Unsupported synthetic audio type')
        if not 0 < len(audio) <= MAX_BYTES: raise PolicyBlocked('Invalid fixture size')
        digest = hashlib.sha256(audio).hexdigest()
        row = self.db.execute('SELECT sha256,byte_length,mime_type,object_name FROM recordings WHERE source_id=?',(source_id,)).fetchone()
        if row:
            if row[:3] != (digest,len(audio),mime_type): raise PayloadConflict('Source reused with changed content')
            if not self._verify_object(row[3],digest):
                raise PayloadConflict('Original evidence missing or corrupt; manual review required')
            return ArchiveResult(source_id,digest,'DURABLE_LOCAL',len(audio))
        # Atomic file replacement and fsync, then independently read back bytes.
        name = f'{source_id}-{digest}.blob'
        fd, temp_name = tempfile.mkstemp(prefix='incoming-', dir=self.objects)
        try:
            with os.fdopen(fd,'wb') as handle:
                handle.write(audio)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.objects/name)
            try:
                dir_fd=os.open(self.objects,os.O_DIRECTORY)
                try:os.fsync(dir_fd)
                finally:os.close(dir_fd)
            except (AttributeError,OSError): pass
        finally:
            if os.path.exists(temp_name):os.unlink(temp_name)
        if not self._verify_object(name,digest):raise IOError('Archive readback failed')
        with self.db:
            self.db.execute('''INSERT INTO recordings(source_id,sha256,byte_length,mime_type,object_name,created_at,
              archive_state,transcription_state) VALUES (?,?,?,?,?,?,'DURABLE_LOCAL','PENDING')''',
              (source_id,digest,len(audio),mime_type,name,int(time.time()) if now is None else now))
        return ArchiveResult(source_id,digest,'DURABLE_LOCAL',len(audio))

    def _verify_object(self,name,digest):
        try:return hmac.compare_digest(hashlib.sha256((self.objects/name).read_bytes()).hexdigest(),digest)
        except FileNotFoundError:return False

    def status(self,source_id):
        source_id=self._valid_uuid(source_id)
        row=self.db.execute('''SELECT sha256,byte_length,archive_state,transcription_state,
          attempts,next_retry_at,transcript,transcript_sha256,last_error,object_name
          FROM recordings WHERE source_id=?''',(source_id,)).fetchone()
        if row is None:raise KeyError('Unknown source')
        digest, size, saved, state, attempts, retry, transcript, text_sha, error, name=row
        return {'source_id':source_id,'audio_sha256':digest,'bytes':size,
          'original_readback_verified':self._verify_object(name,digest),
          'archive_state':saved,'transcription_state':state,'attempts':attempts,
          'next_retry_at':retry,'transcript':transcript,'transcript_sha256':text_sha,
          'last_error_code':error,'post_office_connected':False,'real_transcription':False}

    def process(self,source_id,now: int | None = None):
        source_id=self._valid_uuid(source_id)
        now=int(time.time()) if now is None else now
        status=self.status(source_id)
        if not status['original_readback_verified']:
            with self.db:self.db.execute("UPDATE recordings SET transcription_state='REVIEW_REQUIRED',last_error='source_unavailable' WHERE source_id=?",(source_id,))
            return self.status(source_id)
        if status['transcription_state']=='IN_FLIGHT':
            # Unknown remote outcome after process death. Never bill a second time
            # without provider job-ID reconciliation / explicit reviewed release.
            with self.db:self.db.execute("UPDATE recordings SET transcription_state='REVIEW_REQUIRED',last_error='remote_outcome_unknown' WHERE source_id=?",(source_id,))
            return self.status(source_id)
        if status['transcription_state'] not in ('PENDING','RETRY_WAIT'):return status
        if status['next_retry_at'] is not None and now<status['next_retry_at']:return status
        if status['attempts']>=MAX_ATTEMPTS:
            with self.db:self.db.execute("UPDATE recordings SET transcription_state='REVIEW_REQUIRED',last_error='attempts_exhausted' WHERE source_id=?",(source_id,))
            return self.status(source_id)
        # Durable attempt reservation occurs before simulated external call.
        with self.db:
            self.db.execute("UPDATE recordings SET attempts=attempts+1,transcription_state='IN_FLIGHT',next_retry_at=NULL WHERE source_id=?",(source_id,))
        name=self.db.execute('SELECT object_name FROM recordings WHERE source_id=?',(source_id,)).fetchone()[0]
        try: transcription=self.adapter.transcribe((self.objects/name).read_bytes(),source_id)
        except PolicyBlocked:
            with self.db:self.db.execute("UPDATE recordings SET transcription_state='POLICY_BLOCKED',last_error='provider_policy' WHERE source_id=?",(source_id,))
            return self.status(source_id)
        except Unavailable:
            attempts=self.status(source_id)['attempts']
            state='RETRY_WAIT' if attempts<MAX_ATTEMPTS else 'REVIEW_REQUIRED'
            delay=30 if attempts==1 else 120
            with self.db:self.db.execute('UPDATE recordings SET transcription_state=?,next_retry_at=?,last_error=? WHERE source_id=?',
                (state,now+delay if state=='RETRY_WAIT' else None,'provider_unavailable',source_id))
            return self.status(source_id)
        if not isinstance(transcription,str) or not transcription.strip():
            with self.db:self.db.execute("UPDATE recordings SET transcription_state='REVIEW_REQUIRED',last_error='empty_transcript' WHERE source_id=?",(source_id,))
            return self.status(source_id)
        transcription=transcription.strip()
        transcript_sha=hashlib.sha256(transcription.encode()).hexdigest()
        with self.db:self.db.execute('''UPDATE recordings SET transcription_state='TRANSCRIBED',
          transcript=?,transcript_sha256=?,last_error=NULL,next_retry_at=NULL WHERE source_id=?''',
          (transcription,transcript_sha,source_id))
        return self.status(source_id)

    def stage_for_post_office(self,source_id):
        """No dispatch; record only an idempotent intent pending actual Post Office adapter."""
        s=self.status(source_id)
        if s['transcription_state']!='TRANSCRIBED' or not s['original_readback_verified']:
            raise ValueError('Source not safe and transcribed')
        with self.db:self.db.execute('''INSERT OR IGNORE INTO dispatches
          (source_id,source_sha256,transcript_sha256,stage,created_at)
          VALUES (?,?,?,'READY_FOR_POST_OFFICE',?)''',
          (source_id,s['audio_sha256'],s['transcript_sha256'],int(time.time())))
        return {'source_id':source_id,'stage':'READY_FOR_POST_OFFICE','delivered':False}

    def synthetic_restore_check(self,source_id):
        s=self.status(source_id)
        if not s['original_readback_verified']:raise IOError('Original not retrievable')
        return {'source_id':source_id,'sha256':s['audio_sha256'],'bytes':s['bytes']}