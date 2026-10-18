"""Durable, synthetic-only preparation for the existing institutional Post Office.

No Google Sheets writes, real data, worker activation, or invented institutional IDs.
Only canonical Chef SQL messages can be staged; institutional links require readback.
"""
import hashlib
import sqlite3
import uuid
from pathlib import Path
from postoffice_contract import PostOfficeReadModel

DEPARTMENT = 'FOOD-CHEF'

class DispatchConflict(ValueError):
    pass

class SyntheticDispatchOutbox:
    def __init__(self, path):
        self.path = str(Path(path))
        self.db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA busy_timeout=15000')
        self.db.execute("""CREATE TABLE IF NOT EXISTS synthetic_dispatch_outbox (
            source_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL,
            message_id TEXT NOT NULL UNIQUE, digest TEXT NOT NULL,
            body TEXT NOT NULL, state TEXT NOT NULL,
            institutional_message_id TEXT, institutional_delivery_id TEXT,
            institutional_thread_id TEXT, UNIQUE(thread_id, message_id))""")

    def close(self):
        self.db.close()

    def get(self, source_id):
        row = self.db.execute('SELECT * FROM synthetic_dispatch_outbox WHERE source_id=?',(source_id,)).fetchone()
        if row is None:
            raise KeyError('Unknown staged source')
        return dict(row)

    def prepare(self, *, source_id, thread_id, message_id, body):
        for value in (source_id, thread_id, message_id):
            uuid.UUID(value)
        if not isinstance(body, str) or not body.startswith('SYNTHETIC:') or len(body) > 500:
            raise PermissionError('Only bounded synthetic Chef test input permitted')
        digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old = self.db.execute('SELECT thread_id,message_id,digest FROM synthetic_dispatch_outbox WHERE source_id=?',(source_id,)).fetchone()
            if old:
                if tuple(old) != (thread_id, message_id, digest):
                    raise DispatchConflict('Immutable source replay conflict')
            else:
                self.db.execute("""INSERT INTO synthetic_dispatch_outbox
                    (source_id,thread_id,message_id,digest,body,state)
                    VALUES (?,?,?,?,?,?)""",
                    (source_id,thread_id,message_id,digest,body,'PREPARED_LOCAL_NOT_POST_OFFICE'))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.get(source_id)

    def prepare_from_chef_store(self, store, *, thread_id, user_message_id):
        """Bind the outbox checkpoint to an actual read-back USER message in Chef SQL."""
        uuid.UUID(thread_id)
        uuid.UUID(user_message_id)
        thread = store.get_thread(thread_id)
        matching = [m for m in thread['messages'] if m['message_id'] == user_message_id]
        if len(matching) != 1 or matching[0]['sender'] != 'USER':
            raise PermissionError('Only an existing canonical user turn may be prepared')
        row = matching[0]
        return self.prepare(source_id=row['source_id'], thread_id=thread_id,
                            message_id=user_message_id, body=row['body'])

    def reconcile(self, source_id, message_id, delivery_id, message_rows, delivery_rows, thread_rows):
        """Correlate readback IDs only, never claim genuine worker ACK or RESULT."""
        existing = self.get(source_id)
        model = PostOfficeReadModel(message_rows, delivery_rows, thread_rows)
        evidence = model.reconcile(message_id, delivery_id, target=DEPARTMENT)
        institutional = model.messages[message_id]
        if institutional['Idempotency Key'] != source_id:
            raise DispatchConflict('Institutional idempotency key mismatch')
        if institutional['Source Ref'] != existing['message_id']:
            raise DispatchConflict('Institutional source message link mismatch')
        prior = (existing['institutional_message_id'],existing['institutional_delivery_id'],existing['institutional_thread_id'])
        new = (message_id,delivery_id,evidence.thread_id)
        if any(v is not None for v in prior) and prior != new:
            raise DispatchConflict('Institutional identity changed after reconciliation')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT institutional_message_id,institutional_delivery_id,institutional_thread_id FROM synthetic_dispatch_outbox WHERE source_id=?',(source_id,)).fetchone()
            if any(v is not None for v in row) and tuple(row) != new:
                raise DispatchConflict('Concurrent institutional identity conflict')
            self.db.execute("""UPDATE synthetic_dispatch_outbox
                SET state='INSTITUTIONAL_LINK_READBACK_ONLY',
                institutional_message_id=?,institutional_delivery_id=?,institutional_thread_id=?
                WHERE source_id=?""",(*new,source_id))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {'source_id':source_id,'message_id':message_id,'delivery_id':delivery_id,
                'thread_id':evidence.thread_id,'status':'INSTITUTIONAL_LINK_READBACK_ONLY',
                'authenticated_chef_ack':False,'authenticated_chef_result':False}
