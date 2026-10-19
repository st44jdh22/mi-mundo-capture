"""Synthetic-only signed FOOD-CHEF delivery adapter for the existing SQL chat.

This is a LOCAL TEST PROJECTION, not the Group Post Office ledger or an actor
identity provider. No real food, photos, audio, or client records are accepted.
A signing key is injected by the isolated fixture; it is never given to the UI.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

from sqlalchemy import (
    Column, ForeignKeyConstraint, Integer, MetaData, String, Table,
    UniqueConstraint, insert, select, update,
)
from sqlalchemy.exc import IntegrityError

ACTOR = 'food-chef-pilot-v1'
DEPT = 'FOOD-CHEF'
OPERATION = 'REVIEW_SYNTHETIC_ONLY'
STAGED = 'SYNTHETIC_LOCAL_STAGED'
ACKED = 'SYNTHETIC_SIGNED_ACK'
REPLIED = 'SYNTHETIC_SIGNED_REPLY'
TEST_REPLY = 'SYNTHETIC: Chef asks about dietary requirements.'


def sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def synthetic_sign(receipt: dict, key: bytes) -> dict:
    """Test fixture signing helper; NEVER expose through an end-user route."""
    return {'receipt': receipt, 'signature': hmac.new(key, canonical(receipt), hashlib.sha256).hexdigest()}


class SignedChefBridge:
    """Links real SQL *demo* thread rows to verifiable synthetic receipt rows.

    Tables are a staging/projection; the actual institutional Post Office's
    MESSAGES/DELIVERIES/THREADS stay authoritative and unmodified here.
    """
    def __init__(self, store, metadata: MetaData, thread_table: Table,
                 message_table: Table, actor_key: bytes):
        if len(actor_key) < 32:
            raise ValueError('fixture signing key must contain >=32 bytes')
        self.store = store
        self.threads = thread_table
        self.messages = message_table
        self.key = actor_key
        self.deliveries = metadata.tables.get('mm_chef_signed_fixture_deliveries')
        if self.deliveries is None:
            self.deliveries = Table('mm_chef_signed_fixture_deliveries', metadata,
                Column('delivery_id', String(36), primary_key=True),
                Column('thread_id', String(36), nullable=False),
                Column('owner_id', String(40), nullable=False),
                Column('origin_id', String(36), nullable=False),
                Column('user_message_id', String(36), nullable=False, unique=True),
                Column('source_sha256', String(64), nullable=False),
                Column('state', String(32), nullable=False),
                Column('created_at', Integer, nullable=False),
                ForeignKeyConstraint(['thread_id'], ['mm_chef_demo_threads.thread_id']),
            )
        self.receipts = metadata.tables.get('mm_chef_signed_fixture_receipts')
        if self.receipts is None:
            self.receipts = Table('mm_chef_signed_fixture_receipts', metadata,
                Column('nonce', String(36), primary_key=True),
                Column('delivery_id', String(36), nullable=False),
                Column('kind', String(16), nullable=False),
                Column('signed_payload', String(1400), nullable=False),
                Column('signature', String(64), nullable=False),
                UniqueConstraint('delivery_id', 'kind', name='one_signed_receipt_per_kind'),
                ForeignKeyConstraint(['delivery_id'], ['mm_chef_signed_fixture_deliveries.delivery_id']),
            )
        metadata.create_all(self.store.engine, tables=[self.deliveries, self.receipts])

    def _owned(self, conn, tid: str, owner: str):
        if conn.execute(select(self.threads.c.thread_id).where(
            self.threads.c.thread_id == tid, self.threads.c.owner_id == owner
        )).first() is None:
            raise KeyError('thread_not_found')

    def stage(self, tid: str, origin_id: str, user_message_id: str,
              owner: str = 'synthetic-owner') -> dict:
        """Only a previously committed synthetic USER message may be staged."""
        for value in (tid, origin_id, user_message_id):
            uuid.UUID(value)
        with self.store.engine.begin() as conn:
            self._owned(conn, tid, owner)
            msg = conn.execute(select(self.messages).where(
                self.messages.c.thread_id == tid,
                self.messages.c.owner_id == owner,
                self.messages.c.message_id == user_message_id,
                self.messages.c.sender == 'USER',
            )).mappings().first()
            if msg is None:
                raise KeyError('source_message_not_found')
            if not msg['body'].startswith('SYNTHETIC:') or len(msg['body']) > 500:
                raise PermissionError('fixture_scope_denied')
            expected = sha(msg['body'])
            old = conn.execute(select(self.deliveries).where(
                self.deliveries.c.user_message_id == user_message_id
            )).mappings().first()
            if old:
                if (old['thread_id'], old['owner_id'], old['origin_id'], old['source_sha256']) != (
                    tid, owner, origin_id, expected
                ):
                    raise ValueError('immutable_origin_conflict')
                return dict(old)
            did = str(uuid.uuid5(uuid.NAMESPACE_URL, 'mi-mundo:food-chef-fixture:' + user_message_id))
            conn.execute(insert(self.deliveries).values(
                delivery_id=did, thread_id=tid, owner_id=owner, origin_id=origin_id,
                user_message_id=user_message_id, source_sha256=expected, state=STAGED,
                created_at=int(time.time()),
            ))
            # The very same origin message remains in the canonical chat table.
            # Mark it staged so the old simulator cannot also 'reply' to it.
            conn.execute(update(self.messages).where(
                self.messages.c.message_id == user_message_id,
                self.messages.c.thread_id == tid,
                self.messages.c.owner_id == owner,
            ).values(delivery_state='BRIDGE_LOCAL_STAGED_NOT_POST_OFFICE'))
            return self._delivery(conn, did)

    def _delivery(self, conn, did: str) -> dict:
        row = conn.execute(select(self.deliveries).where(
            self.deliveries.c.delivery_id == did
        )).mappings().first()
        if row is None:
            raise KeyError('delivery_not_found')
        return dict(row)

    def thread_deliveries(self, tid: str, owner: str = 'synthetic-owner') -> list[dict]:
        with self.store.engine.connect() as conn:
            self._owned(conn, tid, owner)
            result = conn.execute(select(self.deliveries).where(
                self.deliveries.c.thread_id == tid,
                self.deliveries.c.owner_id == owner,
            ).order_by(self.deliveries.c.created_at, self.deliveries.c.delivery_id)).mappings().all()
            return [dict(row) for row in result]

    def _verify(self, envelope: dict, row: dict, kind: str, now: int) -> dict:
        if not isinstance(envelope, dict) or set(envelope) != {'receipt', 'signature'}:
            raise PermissionError('invalid_envelope_shape')
        receipt, signature = envelope['receipt'], envelope['signature']
        if not isinstance(receipt, dict) or not isinstance(signature, str):
            raise PermissionError('invalid_envelope_type')
        fixed = {
            'version': 1, 'delivery': row['delivery_id'], 'origin': row['origin_id'],
            'thread': row['thread_id'], 'user_message': row['user_message_id'],
            'source_sha256': row['source_sha256'], 'department': DEPT,
            'actor': ACTOR, 'operation': OPERATION, 'kind': kind,
        }
        variable = {'nonce', 'issued', 'expires'}
        if kind == 'RESULT':
            variable |= {'reply_body', 'reply_sha256'}
        if set(receipt) != set(fixed) | variable:
            raise PermissionError('receipt_shape_denied')
        if any(receipt.get(k) != v for k, v in fixed.items()):
            raise PermissionError('receipt_binding_denied')
        if (type(receipt['issued']) is not int or type(receipt['expires']) is not int or
                not (receipt['issued'] <= now < receipt['expires']) or
                receipt['expires'] - receipt['issued'] > 300 or receipt['issued'] < 0):
            raise PermissionError('expired_or_invalid')
        try:
            uuid.UUID(receipt['nonce'])
        except (ValueError, TypeError, AttributeError):
            raise PermissionError('nonce_invalid')
        if kind == 'RESULT':
            if receipt['reply_body'] != TEST_REPLY or receipt['reply_sha256'] != sha(TEST_REPLY):
                raise PermissionError('result_not_allowlisted')
        expected_signature = hmac.new(self.key, canonical(receipt), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_signature, signature):
            raise PermissionError('invalid_signature')
        return receipt

    def receive(self, delivery_id: str, envelope: dict, kind: str, now: int) -> dict:
        """Signatures checked BEFORE any persisted state or message side effect."""
        if kind not in ('ACK', 'RESULT'):
            raise ValueError('unsupported_receipt_kind')
        with self.store.engine.begin() as conn:
            row = self._delivery(conn, delivery_id)
            receipt = self._verify(envelope, row, kind, now)
            prior = conn.execute(select(self.receipts).where(
                self.receipts.c.delivery_id == delivery_id,
                self.receipts.c.kind == kind,
            )).mappings().first()
            if prior:
                if (prior['signed_payload'], prior['signature']) != (
                    canonical(receipt).decode('utf-8'), envelope['signature']
                ):
                    raise ValueError('conflicting_signed_receipt')
                return self._delivery(conn, delivery_id)
            if kind == 'RESULT' and row['state'] != ACKED:
                raise PermissionError('ack_required')
            if kind == 'ACK' and row['state'] != STAGED:
                raise ValueError('unexpected_delivery_state')
            # Nonce is globally unique in this fixture and may not be used for any other delivery.
            conn.execute(insert(self.receipts).values(
                nonce=receipt['nonce'], delivery_id=delivery_id, kind=kind,
                signed_payload=canonical(receipt).decode('utf-8'),
                signature=envelope['signature'],
            ))
            if kind == 'RESULT':
                # Direct same-thread projection, not an independent shadow inbox.
                reply_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'mi-mundo:chef-signed-fixture-reply:' + delivery_id))
                sender_message = conn.execute(select(self.messages).where(
                    self.messages.c.message_id == row['user_message_id'],
                    self.messages.c.thread_id == row['thread_id'],
                    self.messages.c.owner_id == row['owner_id'],
                )).mappings().one()
                conn.execute(insert(self.messages).values(
                    message_id=reply_id, thread_id=row['thread_id'],
                    owner_id=row['owner_id'], source_id=str(uuid.uuid5(uuid.NAMESPACE_URL, 'mi-mundo:chef-signed-fixture-source:' + delivery_id)),
                    idempotency_key=sha(receipt['reply_body']), sender='CHEF_SIGNED_FIXTURE',
                    body=receipt['reply_body'], reply_to=row['user_message_id'],
                    delivery_state='SIGNED_SYNTHETIC_RESULT_NOT_POST_OFFICE',
                    created_at=max(int(time.time()), int(sender_message['created_at']) + 1),
                ))
            conn.execute(update(self.deliveries).where(
                self.deliveries.c.delivery_id == delivery_id
            ).values(state=ACKED if kind == 'ACK' else REPLIED))
            conn.execute(update(self.messages).where(
                self.messages.c.message_id == row['user_message_id'],
                self.messages.c.thread_id == row['thread_id'],
                self.messages.c.owner_id == row['owner_id'],
            ).values(delivery_state='SIGNED_SYNTHETIC_ACK_NOT_POST_OFFICE' if kind == 'ACK'
                     else 'SIGNED_SYNTHETIC_REPLY_NOT_POST_OFFICE'))
            return self._delivery(conn, delivery_id)


def fixture_receipt(delivery: dict, kind: str, now: int,
                    nonce: str | None = None) -> dict:
    """Test-only builder. The engine never signs its own 'Chef' acknowledgements."""
    if kind not in ('ACK', 'RESULT'):
        raise ValueError('unsupported_kind')
    doc = {
        'version': 1, 'delivery': delivery['delivery_id'],
        'origin': delivery['origin_id'], 'thread': delivery['thread_id'],
        'user_message': delivery['user_message_id'],
        'source_sha256': delivery['source_sha256'],
        'department': DEPT, 'actor': ACTOR, 'operation': OPERATION,
        'kind': kind, 'nonce': nonce or str(uuid.uuid4()),
        'issued': now, 'expires': now + 300,
    }
    if kind == 'RESULT':
        doc.update(reply_body=TEST_REPLY, reply_sha256=sha(TEST_REPLY))
    return doc