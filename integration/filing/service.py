"""Durable TEST-ONLY document operations on the existing SQLAlchemy substrate.

Schema creation is explicit and limited to disposable *_filing_test databases.
No module import, worker, API or default Dockerfile applies this schema.
"""
from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager

from sqlalchemy import (Boolean, Column, ForeignKey, Integer, JSON, MetaData,
                        String, Table, Text, UniqueConstraint, create_engine,
                        event, insert, select, update, func)
from sqlalchemy.engine import make_url

from .storage import digest
from .adapters import (Conflict, PermanentFailure, PermissionFailure, PolicyBlock,
                       TransientFailure, UnknownOutcome)

metadata = MetaData()
pilot = Table('mm_filing_test_control', metadata,
    Column('id', Integer, primary_key=True), Column('stopped', Boolean, nullable=False))
jobs = Table('mm_filing_test_jobs', metadata,
    Column('job_id', String(36), primary_key=True),
    Column('intake_id', String(36), nullable=False),
    Column('requester', String(80), nullable=False),
    Column('department', String(32), nullable=False),
    Column('conversation_id', String(80), nullable=False),
    Column('idempotency_key', String(100), nullable=False),
    Column('fingerprint', String(64), nullable=False),
    Column('instruction', Text, nullable=False), Column('source_ref', Text, nullable=False),
    Column('object_key', String(64)), Column('source_sha256', String(64)),
    Column('approval_ref', String(120), nullable=False),
    Column('authoritative_record', String(120), nullable=False),
    Column('state', String(32), nullable=False), Column('attempts', Integer, nullable=False),
    Column('next_attempt', Integer, nullable=False), Column('lease_token', String(36)),
    Column('lease_owner', String(80)), Column('lease_until', Integer, nullable=False),
    Column('cancel_requested', Boolean, nullable=False),
    Column('created_at', Integer, nullable=False), Column('updated_at', Integer, nullable=False),
    Column('error_code', String(80)), Column('exact_error', Text),
    UniqueConstraint('requester','idempotency_key', name='filing_idempotency'))
targets = Table('mm_filing_test_targets', metadata,
    Column('job_id', String(36), ForeignKey(jobs.c.job_id), primary_key=True),
    Column('target_id', String(80), primary_key=True),
    Column('spec', JSON, nullable=False), Column('state', String(32), nullable=False),
    Column('verification', JSON), Column('updated_at', Integer, nullable=False))
attempts = Table('mm_filing_test_attempts', metadata,
    Column('job_id', String(36), ForeignKey(jobs.c.job_id), primary_key=True),
    Column('number', Integer, primary_key=True), Column('token', String(36), nullable=False),
    Column('worker', String(80), nullable=False), Column('started_at', Integer, nullable=False),
    Column('finished_at', Integer), Column('outcome', String(40)),
    Column('error_code', String(80)), Column('exact_error', Text))
events = Table('mm_filing_test_events', metadata,
    Column('event_id', String(36), primary_key=True),
    Column('sequence', Integer, nullable=False, unique=True),
    Column('job_id', String(36), ForeignKey(jobs.c.job_id), nullable=False),
    Column('at', Integer, nullable=False), Column('code', String(64), nullable=False),
    Column('details', JSON, nullable=False))
outbox = Table('mm_filing_test_outbox', metadata,
    Column('event_id', String(36), ForeignKey(events.c.event_id), primary_key=True),
    Column('job_id', String(36), ForeignKey(jobs.c.job_id), nullable=False),
    Column('sequence', Integer, nullable=False, unique=True),
    Column('payload', JSON, nullable=False), Column('state', String(32), nullable=False),
    Column('attempts', Integer, nullable=False), Column('next_attempt', Integer, nullable=False),
    Column('lease_token', String(36)), Column('lease_until', Integer, nullable=False, default=0),
    Column('error_code', String(80)))
report_attempts = Table('mm_filing_test_report_attempts', metadata,
    Column('event_id', String(36), ForeignKey(outbox.c.event_id), primary_key=True),
    Column('number', Integer, primary_key=True), Column('at', Integer, nullable=False),
    Column('outcome', String(32), nullable=False), Column('exact_error', Text))

TERMINAL = {'VERIFIED COMPLETE', 'FAILED', 'CANCELLED', 'BLOCKED', 'MANUAL REVIEW'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


class LeaseLost(RuntimeError): pass
class StopRequested(RuntimeError): pass


class FilingService:
    def __init__(self, url, *, clock=time.time):
        parsed = make_url(url)
        if parsed.drivername.startswith('postgresql'):
            if not (parsed.database or '').endswith('_filing_test'):
                raise PermissionError('Disposable *_filing_test PostgreSQL database required')
            parsed = parsed.set(drivername='postgresql+psycopg')
        elif parsed.drivername != 'sqlite' or not (parsed.database or '').endswith('_filing_test.sqlite'):
            raise PermissionError('Disposable *_filing_test.sqlite fixture required')
        self.engine = create_engine(parsed, pool_pre_ping=True,
            connect_args={'check_same_thread': False, 'timeout': 15} if parsed.drivername == 'sqlite' else {})
        if parsed.drivername == 'sqlite':
            @event.listens_for(self.engine, 'connect')
            def configure(conn, _):
                conn.execute('PRAGMA foreign_keys=ON')
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA synchronous=FULL')
        self.clock = clock

    def close(self):
        self.engine.dispose()

    def initialize_test_schema(self):
        """Explicit development action; do not call against existing pilot DB."""
        metadata.create_all(self.engine)
        with self.transaction() as conn:
            if conn.execute(select(pilot)).first() is None:
                conn.execute(insert(pilot).values(id=1, stopped=True))

    @contextmanager
    def transaction(self):
        with self.engine.connect() as conn:
            if conn.dialect.name == 'sqlite':
                conn.exec_driver_sql('BEGIN IMMEDIATE')
            else:
                conn.begin()
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def _control(self, conn):
        return conn.execute(select(pilot).where(pilot.c.id == 1).with_for_update()).mappings().one()

    def set_stopped(self, stopped):
        with self.transaction() as conn:
            self._control(conn)
            conn.execute(update(pilot).where(pilot.c.id == 1).values(stopped=bool(stopped)))

    def _event(self, conn, job, code, details=None):
        eid, now = str(uuid.uuid4()), int(self.clock())
        sequence = (conn.execute(select(func.max(events.c.sequence))).scalar_one() or 0) + 1
        conn.execute(insert(events).values(event_id=eid, sequence=sequence, job_id=job['job_id'], at=now,
                                           code=code, details=details or {}))
        # Only safe codes/correlation/evidence go to institutional projections.
        payload = {'event_id': eid, 'job_id': job['job_id'], 'state': job['state'],
                   'department': job['department'], 'conversation_id': job['conversation_id'],
                   'error_code': job.get('error_code') or '',
                   'evidence': 'SQL verification: ' + job['job_id'] if job['state'] == 'VERIFIED COMPLETE' else ''}
        conn.execute(insert(outbox).values(event_id=eid, sequence=sequence, job_id=job['job_id'], payload=payload,
            state='PENDING', attempts=0, next_attempt=0))

    def submit(self, spec, data, objects):
        """Commit immutable instruction+source retention BEFORE destination effects."""
        spec = json.loads(canonical(spec))
        required = {'job_id','intake_id','requester','department','conversation_id','idempotency_key',
                    'instruction','source_ref','approval_ref','authoritative_record','targets'}
        if set(spec) != required or spec['requester'] != 'synthetic-owner':
            raise PermissionError('Only the synthetic owner and exact filing contract are permitted')
        for key in ('job_id','intake_id'):
            if str(uuid.UUID(spec[key])) != spec[key]:
                raise ValueError('Canonical UUID required')
        if spec['department'] not in {'FOOD-CHEF','SYS-POSTOFFICE'}:
            raise PermissionError('Department outside synthetic scope')
        for key in ('conversation_id','idempotency_key','approval_ref','authoritative_record'):
            if not isinstance(spec[key], str) or not spec[key].startswith('synthetic-') or len(spec[key]) > 80:
                raise PermissionError('Synthetic correlation and approval required')
        if (not spec['source_ref'].startswith('fixture://') or len(spec['source_ref']) > 500
                or not spec['instruction'].startswith('SYNTHETIC:') or len(spec['instruction']) > 4000):
            raise PermissionError('Only synthetic sources and instructions permitted')
        if not 1 <= len(spec['targets']) <= 5:
            raise ValueError('One to five target operations required')
        if data is not None and (not isinstance(data, bytes) or not data.startswith(
                (b'SYNTHETIC\n', b'%PDF-1.4\n%SYNTHETIC\n')) or not 0 < len(data) <= 8*1024*1024):
            raise ValueError('Only bounded synthetic documents are permitted')
        # Validate every destination and effect identity before staging any
        # source bytes outside the SQL transaction. An invalid envelope must
        # never create an orphaned source object.
        source_hash = digest(data) if data is not None else None
        target_ids, effect_ids = set(), set()
        for target in spec['targets']:
            if set(target) != {'target_id','kind','destination','name','effect_id','permissions','value'}:
                raise ValueError('Exact target schema required')
            if target['kind'] not in {'FILE','RECORD'}:
                raise PermissionError('Operation not permitted')
            for field in ('target_id','destination','name','effect_id'):
                if not isinstance(target[field], str) or not target[field].startswith('synthetic-') or len(target[field]) > 100:
                    raise PermissionError('Only synthetic destinations/identities permitted')
            if target['permissions'] != ['synthetic-owner:owner']:
                raise PermissionError('Unexpected permissions')
            if not isinstance(target['value'], str) or not target['value'].startswith('SYNTHETIC:') or len(target['value']) > 4096:
                raise PermissionError('Only synthetic record values permitted')
            if target['target_id'] in target_ids or target['effect_id'] in effect_ids:
                raise ValueError('Duplicate target/effect identity')
            target_ids.add(target['target_id']); effect_ids.add(target['effect_id'])
            value = data if target['kind'] == 'FILE' else target['value'].encode()
            target.update(expected_sha256=digest(value) if value is not None else '',
                          size=len(value) if value is not None else 0)
        key, source_error = None, None
        if data is not None:
            try:
                key = objects.put(data)
                if digest(objects.get(key)) != source_hash:
                    raise ValueError('Original bytes not independently retained')
            except (OSError, ValueError) as error:
                key, source_error = None, str(error)
        fingerprint = digest(canonical({k:v for k,v in spec.items() if k != 'job_id'}).encode() + (source_hash or '').encode())
        now = int(self.clock())
        with self.transaction() as conn:
            self._control(conn)  # Serialize duplicate checks and five-job budget.
            existing = conn.execute(select(jobs).where(
                (jobs.c.job_id == spec['job_id']) |
                ((jobs.c.requester == spec['requester']) & (jobs.c.idempotency_key == spec['idempotency_key'])))).mappings().all()
            if existing:
                if len(existing) != 1 or existing[0]['fingerprint'] != fingerprint:
                    raise Conflict('Immutable job or idempotency key was changed')
                return existing[0]['job_id']
            if conn.execute(select(func.count()).select_from(jobs)).scalar_one() >= 5:
                raise PermissionError('Five-job synthetic pilot budget exhausted')
            # External effect identities must be exclusive across jobs as well.
            for row in conn.execute(select(targets.c.spec)).scalars():
                if row['effect_id'] in effect_ids:
                    raise Conflict('Effect identity already belongs to another job')
            row = {k:spec[k] for k in required - {'targets'}}
            row.update(fingerprint=fingerprint, object_key=key, source_sha256=source_hash,
                state='RECEIVED', attempts=0, next_attempt=0, lease_until=0,
                cancel_requested=False, created_at=now, updated_at=now)
            conn.execute(insert(jobs).values(**row))
            self._event(conn, row, 'RECEIVED')
            for target in spec['targets']:
                conn.execute(insert(targets).values(job_id=row['job_id'], target_id=target['target_id'],
                    spec=target, state='QUEUED', updated_at=now))
            row['state'] = 'QUEUED' if key else 'MANUAL REVIEW'
            row['error_code'] = 'source_retention_failed' if source_error else (None if key else 'source_unavailable')
            conn.execute(update(jobs).where(jobs.c.job_id == row['job_id']).values(
                state=row['state'], error_code=row['error_code'], exact_error=source_error))
            self._event(conn, row, row['state'], {'private_error':source_error} if source_error else None)
        return spec['job_id']

    def restore_source(self, job_id, requester, data, objects):
        """Recover only the originally hashed source; no target write or release."""
        with self.engine.connect() as conn:
            row = conn.execute(select(jobs).where(jobs.c.job_id==job_id,
                jobs.c.requester==requester)).mappings().one()
        if not row['source_sha256'] or digest(data) != row['source_sha256']:
            raise Conflict('Restoration bytes do not match the original accepted hash')
        key = objects.put(data)
        if digest(objects.get(key)) != row['source_sha256']:
            raise Conflict('Restored source readback differs')
        with self.transaction() as conn:
            self._control(conn)
            current = conn.execute(select(jobs).where(jobs.c.job_id==job_id).with_for_update()).mappings().one()
            if current['object_key'] is not None or current['state']!='MANUAL REVIEW' or current['lease_token']:
                raise PermissionError('Source restoration is not eligible')
            conn.execute(update(jobs).where(jobs.c.job_id==job_id).values(object_key=key))
            self._event(conn, dict(current), 'SOURCE_RESTORED')

    def claim(self, job_id, worker, lease_seconds=60):
        now, token = int(self.clock()), str(uuid.uuid4())
        if not worker.startswith('synthetic-worker-') or not 1 <= lease_seconds <= 60:
            raise PermissionError('Bounded synthetic worker required')
        with self.transaction() as conn:
            if self._control(conn)['stopped']:
                return None
            row = conn.execute(select(jobs).where(jobs.c.job_id == job_id).with_for_update()).mappings().one()
            if row['state'] in TERMINAL or row['next_attempt'] > now or row['lease_until'] > now:
                return None
            # One active worker across this five-job test pilot, not just per job.
            if conn.execute(select(jobs.c.job_id).where(jobs.c.lease_until > now)).first():
                return None
            if conn.execute(select(outbox.c.event_id).where(outbox.c.lease_until > now)).first():
                return None
            number = min(3, row['attempts'] + 1)
            reconciliation_only = row['attempts'] >= 3
            conn.execute(update(jobs).where(jobs.c.job_id == job_id).values(state='PROCESSING',
                attempts=number, lease_token=token, lease_owner=worker, lease_until=now+lease_seconds, updated_at=now))
            if not reconciliation_only:
                conn.execute(insert(attempts).values(job_id=job_id, number=number, token=token,
                                                      worker=worker, started_at=now))
            claimed = dict(row, state='PROCESSING', lease_token=token, attempts=number,
                           reconciliation_only=reconciliation_only)
            self._event(conn, claimed, 'CLAIMED', {'attempt':number,'reconciliation_only':reconciliation_only})
            return claimed

    def _guard(self, conn, claim, *, allow_stop=False):
        control = self._control(conn)  # Same lock order as claim/submit.
        row = conn.execute(select(jobs).where(jobs.c.job_id == claim['job_id']).with_for_update()).mappings().one()
        if row['lease_token'] != claim['lease_token'] or row['lease_until'] <= int(self.clock()):
            raise LeaseLost('Lease expired or replaced; reconcile under a fresh claim')
        if not allow_stop and (control['stopped'] or row['cancel_requested']):
            raise StopRequested('Stop or cancellation requested; reconcile before another write')
        return row

    def _target_state(self, claim, target_id, state, evidence=None):
        with self.transaction() as conn:
            self._guard(conn, claim)
            conn.execute(update(targets).where(targets.c.job_id == claim['job_id'], targets.c.target_id == target_id)
                         .values(state=state, verification=evidence, updated_at=int(self.clock())))
            if state == 'WRITE REPORTED':
                conn.execute(update(jobs).where(jobs.c.job_id == claim['job_id']).values(state=state))
            # A target's completion is NOT overall job completion. Project only
            # the current global job state until every required target passes.
            job_state = conn.execute(select(jobs.c.state).where(jobs.c.job_id == claim['job_id'])).scalar_one()
            self._event(conn, dict(claim, state=job_state), 'TARGET_'+state, {'target_id':target_id})

    def _finish(self, claim, state, code=None, error=None, delay=0):
        with self.transaction() as conn:
            row = self._guard(conn, claim, allow_stop=True)
            now = int(self.clock())
            if state == 'RETRY PENDING' and conn.execute(select(targets.c.target_id).where(
                    targets.c.job_id == row['job_id'], targets.c.state == 'VERIFIED COMPLETE')).first():
                state = 'PARTIALLY COMPLETE'
            conn.execute(update(jobs).where(jobs.c.job_id == row['job_id']).values(state=state,
                error_code=code, exact_error=str(error) if error else None,
                lease_token=None, lease_owner=None, lease_until=0, next_attempt=now+delay, updated_at=now))
            conn.execute(update(attempts).where(attempts.c.job_id == row['job_id'], attempts.c.token == claim['lease_token'])
                         .values(finished_at=now, outcome=state, error_code=code,
                                 exact_error=str(error) if error else None))
            self._event(conn, dict(row, state=state, error_code=code), state)

    def run_once(self, job_id, worker, objects, adapters, *, hook=lambda *args: None):
        claim = self.claim(job_id, worker)
        if claim is None:
            return False
        hook('claimed', claim)
        try:
            try:
                data = objects.get(claim['object_key'])
                if digest(data) != claim['source_sha256']:
                    raise ValueError('Retained source hash changed')
            except (OSError, ValueError, TypeError) as error:
                self._finish(claim, 'MANUAL REVIEW', 'source_unavailable', error)
                return True
            with self.engine.connect() as conn:
                rows = conn.execute(select(targets).where(targets.c.job_id == job_id).order_by(targets.c.target_id)).mappings().all()
            for row in rows:
                target, adapter = row['spec'], adapters[row['spec']['kind']]
                with self.transaction() as conn:
                    self._guard(conn, claim)
                # Always inspect existing effects, including after crash/timeout.
                observed = adapter.observe(target)
                if observed is None:
                    if row['state'] == 'VERIFIED COMPLETE':
                        raise Conflict('Previously verified effect is now missing')
                    if claim['reconciliation_only']:
                        raise PermanentFailure('attempt budget exhausted; effect absent')
                    with self.transaction() as conn:
                        self._guard(conn, claim)
                    hook('before_write', claim)
                    with self.transaction() as conn:
                        self._guard(conn, claim)
                    value = data if target['kind'] == 'FILE' else target['value'].encode()
                    try:
                        adapter.write(target, value)
                    except (TimeoutError, ConnectionError) as error:
                        raise UnknownOutcome(str(error)) from error
                    hook('after_write', claim)
                    self._target_state(claim, row['target_id'], 'WRITE REPORTED')
                    # The returned API value is deliberately ignored.
                    observed = adapter.observe(target)
                    if observed is None:
                        raise UnknownOutcome('Write response received but independent effect absent')
                self._target_state(claim, row['target_id'], 'VERIFIED COMPLETE', observed)
            with self.transaction() as conn:
                self._guard(conn, claim)
                remaining = conn.execute(select(targets.c.state).where(targets.c.job_id == job_id)).scalars().all()
                if not remaining or any(s != 'VERIFIED COMPLETE' for s in remaining):
                    raise Conflict('Required target verification is incomplete')
            self._finish(claim, 'VERIFIED COMPLETE')
        except LeaseLost:
            raise  # Stale worker must not change state held by another claim.
        except StopRequested as error:
            self._finish(claim, 'MANUAL REVIEW', 'stop_reconciliation_required', error)
        except (PolicyBlock, PermissionFailure) as error:
            self._finish(claim, 'BLOCKED', 'policy_block' if isinstance(error, PolicyBlock) else 'permission_denied', error)
        except Conflict as error:
            self._finish(claim, 'MANUAL REVIEW', 'verification_conflict', error)
        except PermanentFailure as error:
            self._finish(claim, 'FAILED', 'permanent_failure', error)
        except (TransientFailure, UnknownOutcome, TimeoutError, ConnectionError) as error:
            state = 'RETRY PENDING' if claim['attempts'] < 3 else 'MANUAL REVIEW'
            self._finish(claim, state, 'outcome_unknown' if isinstance(error, (UnknownOutcome, TimeoutError)) else 'transient', error,
                         delay=30 * 2 ** (claim['attempts']-1) if state == 'RETRY PENDING' else 0)
        except Exception as error:
            self._finish(claim, 'MANUAL REVIEW', 'unclassified_failure', error)
        return True

    def cancel(self, job_id, requester):
        with self.transaction() as conn:
            self._control(conn)
            row = conn.execute(select(jobs).where(jobs.c.job_id == job_id, jobs.c.requester == requester).with_for_update()).mappings().one()
            if row['state'] == 'VERIFIED COMPLETE':
                return
            state = 'MANUAL REVIEW' if row['attempts'] else 'CANCELLED'
            conn.execute(update(jobs).where(jobs.c.job_id == job_id).values(cancel_requested=True,
                state=state if not row['lease_token'] else row['state']))
            self._event(conn, dict(row, state=state), 'CANCEL_REQUESTED')

    def reviewed_release(self, job_id, requester, approval_ref):
        if not approval_ref.startswith('synthetic-review-'):
            raise PermissionError('Separate synthetic review evidence required')
        with self.transaction() as conn:
            self._control(conn)
            row = conn.execute(select(jobs).where(jobs.c.job_id == job_id, jobs.c.requester == requester).with_for_update()).mappings().one()
            if row['state'] not in {'BLOCKED','MANUAL REVIEW'} or row['attempts'] >= 3 or row['lease_until'] > int(self.clock()) or row['cancel_requested']:
                raise PermissionError('Not eligible for reviewed continuation')
            conn.execute(update(jobs).where(jobs.c.job_id == job_id).values(state='QUEUED', next_attempt=0))
            self._event(conn, dict(row, state='QUEUED'), 'REVIEWED_RELEASE', {'approval_ref':approval_ref})

    def status(self, job_id, requester, conversation_id):
        with self.engine.connect() as conn:
            row = conn.execute(select(jobs).where(jobs.c.job_id == job_id,
                jobs.c.requester == requester, jobs.c.conversation_id == conversation_id)).mappings().first()
            if not row:
                raise PermissionError('Job not accessible for this origin')
            values = conn.execute(select(targets).where(targets.c.job_id == job_id)).mappings().all()
            reporting = conn.execute(select(func.count()).select_from(outbox).where(outbox.c.job_id == job_id, outbox.c.state != 'DELIVERED')).scalar_one()
            return {'job_id':job_id,'intake_id':row['intake_id'],'conversation_id':conversation_id,
                'state':row['state'],'attempts':row['attempts'],'error_code':row['error_code'],
                'next_attempt':row['next_attempt'],
                'partially_complete':any(t['state']=='VERIFIED COMPLETE' for t in values) and row['state']!='VERIFIED COMPLETE',
                'targets':[{'target_id':t['target_id'],'state':t['state'],'verification':t['verification']} for t in values],
                'reporting_pending':bool(reporting),'department_acknowledged':False,
                'test_only':True}

    def outcomes_for_origin(self, requester, conversation_id):
        with self.engine.connect() as conn:
            ids = conn.execute(select(jobs.c.job_id).where(jobs.c.requester == requester,
                jobs.c.conversation_id == conversation_id).order_by(jobs.c.created_at, jobs.c.job_id)).scalars().all()
        return [self.status(job, requester, conversation_id) for job in ids]

    def flush_reporting(self, adapter, *, hook=lambda *args: None):
        """Reserve attempts before projection; recover partial/lost reporting replies."""
        now, token = int(self.clock()), str(uuid.uuid4())
        with self.transaction() as conn:
            if self._control(conn)['stopped']:
                return False
            if conn.execute(select(jobs.c.job_id).where(jobs.c.lease_until > now)).first():
                return False
            if conn.execute(select(outbox.c.event_id).where(outbox.c.lease_until > now)).first():
                return False
            pending = conn.execute(select(outbox).where(outbox.c.state != 'DELIVERED')
                .order_by(outbox.c.sequence).with_for_update()).mappings().all()
            blocked_jobs, row = set(), None
            for candidate in pending:
                if candidate['job_id'] in blocked_jobs:
                    continue
                blocked_jobs.add(candidate['job_id'])
                if candidate['state'] != 'MANUAL REVIEW' and candidate['next_attempt'] <= now:
                    row = candidate
                    break
            if row is None:
                return False
            count = min(3, row['attempts']+1)
            reconciliation_only = row['attempts'] >= 3
            conn.execute(update(outbox).where(outbox.c.event_id == row['event_id']).values(
                state='PROCESSING', attempts=count, lease_token=token, lease_until=now+60))
            if not reconciliation_only:
                conn.execute(insert(report_attempts).values(event_id=row['event_id'], number=count,
                    at=now, outcome='RESERVED'))
        # No SQL transaction is held during an injected network call.
        hook('report_claimed', row)
        def report_guard():
            with self.transaction() as conn:
                control = self._control(conn)
                current = conn.execute(select(outbox).where(outbox.c.event_id == row['event_id'])).mappings().one()
                if current['lease_token'] != token or current['lease_until'] <= int(self.clock()):
                    raise LeaseLost('Reporting lease expired or replaced')
                if control['stopped']:
                    raise StopRequested('Reporting stopped before unsent write')
        failure = None
        try:
            report_guard()
            if not adapter.verify(row['payload']):
                if reconciliation_only:
                    raise PermanentFailure('Reporting budget exhausted; delivery not verified')
                report_guard()
                if hasattr(adapter, 'publish_guarded'):
                    adapter.publish_guarded(row['payload'], report_guard)
                else:
                    adapter.publish(row['payload'])
            hook('report_written', row)
            if not adapter.verify(row['payload']):
                raise UnknownOutcome('Post Office result readback absent')
        except Exception as error:
            failure = error
        with self.transaction() as conn:
            self._control(conn)
            current = conn.execute(select(outbox).where(outbox.c.event_id == row['event_id']).with_for_update()).mappings().one()
            if current['lease_token'] != token or current['lease_until'] <= int(self.clock()):
                raise LeaseLost('Reporting lease expired or replaced')
            if failure:
                state = 'MANUAL REVIEW' if count >= 3 or isinstance(failure, (PolicyBlock,PermissionFailure,Conflict,PermanentFailure)) else 'RETRY PENDING'
                conn.execute(update(outbox).where(outbox.c.event_id == row['event_id']).values(state=state,
                    lease_token=None, lease_until=0, next_attempt=int(self.clock())+30*2**(count-1), error_code=type(failure).__name__))
            else:
                state = 'DELIVERED'
                conn.execute(update(outbox).where(outbox.c.event_id == row['event_id']).values(state=state,
                    lease_token=None, lease_until=0, error_code=None))
            if not reconciliation_only:
                conn.execute(update(report_attempts).where(report_attempts.c.event_id == row['event_id'],
                    report_attempts.c.number == count).values(outcome=state,
                    exact_error=str(failure) if failure else None))
        return True
