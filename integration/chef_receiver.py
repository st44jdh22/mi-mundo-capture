"""Loopback-only FOOD-CHEF actor. Separate persisted ACK and immutable effect.

Synthetic transport fixture, not a production identity provider. HMAC is the
existing bridge's test protocol; deployment requires reviewed service identity.
"""
import hmac
import json
import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from chef_signed_bridge import fixture_receipt, synthetic_sign, TEST_REPLY, sha

ACTION = 'PREPARE_SYNTHETIC_QUESTION'

class Package(BaseModel):
    model_config = ConfigDict(extra='forbid')
    delivery: dict
    target: dict
    source: str = Field(max_length=500)
    action: str

class Receiver:
    def __init__(self, path, key):
        if not str(path).endswith('_chef_receiver_test.sqlite') or len(key) < 32:
            raise ValueError('Disposable receiver path and fixture key required')
        self.path, self.key = str(path), key
        with self.tx() as db:
            db.execute('CREATE TABLE IF NOT EXISTS control (id INTEGER PRIMARY KEY, stopped INTEGER NOT NULL)')
            db.execute('INSERT OR IGNORE INTO control VALUES (1,1)')
            db.execute('''CREATE TABLE IF NOT EXISTS receipts (
                delivery TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                package TEXT NOT NULL, ack TEXT NOT NULL, result TEXT)''')
            db.execute('''CREATE TABLE IF NOT EXISTS effects (
                id TEXT PRIMARY KEY, delivery TEXT UNIQUE NOT NULL, data TEXT NOT NULL,
                attrs TEXT NOT NULL, FOREIGN KEY(delivery) REFERENCES receipts(delivery))''')

    @contextmanager
    def tx(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=FULL')
        db.execute('BEGIN IMMEDIATE')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def stop(self, value):
        with self.tx() as db:
            db.execute('UPDATE control SET stopped=? WHERE id=1', (int(value),))

    def deliver(self, package, *, hook=lambda *a: None):
        from uuid import UUID, uuid5, NAMESPACE_URL
        d, t = package['delivery'], package['target']
        # No free-form task, URL, owner, department, target or tool selection.
        required = {'delivery_id','thread_id','owner_id','origin_id','user_message_id','source_sha256'}
        if set(d) != required or d['owner_id'] != 'synthetic-owner':
            raise PermissionError('identity_denied')
        for name in required - {'owner_id','source_sha256'}:
            UUID(d[name])
        if (package['action'] != ACTION or not package['source'].startswith('SYNTHETIC:')
                or sha(package['source']) != d['source_sha256']):
            raise PermissionError('scope_denied')
        expected = target_for(d)
        if t != expected or d['delivery_id'] != str(uuid5(NAMESPACE_URL,
                'mi-mundo:food-chef-fixture:' + d['user_message_id'])):
            raise PermissionError('target_denied')
        fingerprint = sha(json.dumps(package, sort_keys=True))
        # ACK commits before any effect. A restart retains exactly the same ACK.
        with self.tx() as db:
            if db.execute('SELECT stopped FROM control').fetchone()[0]:
                raise PermissionError('receiver_stopped')
            old = db.execute('SELECT * FROM receipts WHERE delivery=?', (d['delivery_id'],)).fetchone()
            if old and old['fingerprint'] != fingerprint:
                raise ValueError('immutable_delivery_conflict')
            if not old:
                if db.execute('SELECT count(*) FROM receipts').fetchone()[0] >= 5:
                    raise PermissionError('five_job_cap')
                ack = synthetic_sign(fixture_receipt(d, 'ACK', int(time.time())), self.key)
                db.execute('INSERT INTO receipts VALUES (?,?,?,?,NULL)',
                           (d['delivery_id'], fingerprint, json.dumps(package), json.dumps(ack)))
        hook('ack_committed')
        # The only effect: persist the fixed synthetic review question once.
        with self.tx() as db:
            if db.execute('SELECT stopped FROM control').fetchone()[0]:
                raise PermissionError('receiver_stopped')
            db.execute('INSERT OR IGNORE INTO effects VALUES (?,?,?,?)',
                       (t['effect_id'], d['delivery_id'], TEST_REPLY, json.dumps(t)))
        hook('effect_committed')
        # Independently reread committed effect before signing RESULT.
        with self.tx() as db:
            effect = db.execute('SELECT * FROM effects WHERE id=?', (t['effect_id'],)).fetchone()
            if effect['data'] != TEST_REPLY or json.loads(effect['attrs']) != t:
                raise ValueError('effect_readback_failed')
            old = db.execute('SELECT result FROM receipts WHERE delivery=?', (d['delivery_id'],)).fetchone()
            if old['result'] is None:
                result = synthetic_sign(fixture_receipt(d, 'RESULT', int(time.time())), self.key)
                db.execute('UPDATE receipts SET result=? WHERE delivery=?',
                           (json.dumps(result), d['delivery_id']))
        return self.get(t['effect_id'])

    def get(self, effect_id):
        with self.tx() as db:
            row = db.execute('''SELECT e.*,r.ack,r.result FROM effects e
                JOIN receipts r ON r.delivery=e.delivery WHERE e.id=?''', (effect_id,)).fetchone()
            if row is None or row['result'] is None:
                return None
            return {'data':row['data'], 'attrs':json.loads(row['attrs']),
                    'ack':json.loads(row['ack']), 'result':json.loads(row['result'])}


def target_for(delivery):
    value = TEST_REPLY
    return {'target_id':'synthetic-question', 'kind':'RECORD',
            'destination':'synthetic-chef-question', 'name':'synthetic-question',
            'effect_id':'synthetic-'+delivery['delivery_id'],
            'permissions':['synthetic-owner:owner'], 'value':value,
            'expected_sha256':sha(value), 'size':len(value.encode())}


def create_receiver(path, key, delivery_token, read_token):
    if min(len(delivery_token), len(read_token)) < 32 or delivery_token == read_token:
        raise ValueError('Distinct strong receiver credentials required')
    receiver = Receiver(path, key)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.receiver = receiver
    def auth(value, expected):
        if not value or not hmac.compare_digest(value, 'Bearer '+expected):
            raise HTTPException(401, 'Unauthorised fixture principal')
    @app.get('/healthz')
    def health():
        return {'mode':'LOCAL_SYNTHETIC_ONLY'}
    @app.post('/deliver')
    def deliver(body:Package, authorization:str|None=Header(default=None)):
        auth(authorization, delivery_token)
        try:
            return receiver.deliver(body.model_dump())
        except PermissionError:
            raise HTTPException(403, 'Receiver stopped or scope denied')
        except (ValueError, KeyError, TypeError):
            raise HTTPException(409, 'Invalid or conflicting synthetic package')
    @app.get('/effects/{effect_id}')
    def get(effect_id:str, authorization:str|None=Header(default=None)):
        auth(authorization, read_token)
        return receiver.get(effect_id)
    return app
