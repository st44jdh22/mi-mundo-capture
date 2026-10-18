"""Mi Mundo synthetic recovery Inbox API, durable DB-backed staging vertical slice.

IMPORTANT: This service accepts synthetic markers ONLY. Never real health/business
content, documents, photos, raw audio or Post Office actions. A database record
alone is not an original-evidence archive. Intended for authenticated isolated
integration acceptance before any production review.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import re
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (Boolean, CheckConstraint, Column, ForeignKeyConstraint,
                        Integer, MetaData, String, Table, Text, create_engine,
                        select, func, update, insert, text as sqltext)
from sqlalchemy.exc import IntegrityError

LABELS = ('journal', 'emotion', 'narrative')
PRIVACY = ('GENERAL', 'BUSINESS_CONFIDENTIAL', 'FINANCIAL', 'HEALTH', 'HIGHLY_PRIVATE')
STATES = ('PENDING', 'RETRY_WAIT', 'POLICY_BLOCKED', 'AUTH_BLOCKED', 'CONFLICT', 'VERIFIED')
sha = lambda s: hashlib.sha256(s.encode('utf-8')).hexdigest()
meta = MetaData()

jobs = Table('mm_demo_jobs', meta,
    Column('job_id', String(36), primary_key=True),
    Column('source_sha256', String(64), nullable=False),
    Column('privacy_class', String(32), nullable=False),
    Column('evidence_status', String(40), nullable=False),
    Column('created_at', Integer, nullable=False),
    Column('updated_at', Integer, nullable=False),
    CheckConstraint("evidence_status = 'SYNTHETIC_FIXTURE_ONLY'", name='synthetic_only'))
targets = Table('mm_demo_targets', meta,
    Column('job_id', String(36), primary_key=True),
    Column('target_key', String(32), primary_key=True),
    Column('expected_sha256', String(64), nullable=False),
    Column('state', String(32), nullable=False),
    Column('attempts', Integer, nullable=False, default=0),
    Column('next_retry_at', Integer, nullable=False, default=0),
    Column('last_error', String(80)),
    Column('updated_at', Integer, nullable=False),
    ForeignKeyConstraint(['job_id'],['mm_demo_jobs.job_id']),
    CheckConstraint("state IN ('PENDING','RETRY_WAIT','POLICY_BLOCKED','AUTH_BLOCKED','CONFLICT','VERIFIED')",name='valid_target_state'))
fixture_results = Table('mm_demo_results',meta,
    Column('job_id',String(36),primary_key=True),
    Column('target_key',String(32),primary_key=True),
    Column('actual_sha256',String(64),nullable=False),
    Column('created_at',Integer,nullable=False),
    ForeignKeyConstraint(['job_id','target_key'],['mm_demo_targets.job_id','mm_demo_targets.target_key']))
faults = Table('mm_demo_faults',meta,
    Column('job_id',String(36),primary_key=True),
    Column('target_key',String(32),primary_key=True),
    Column('fault_type',String(32),nullable=False),
    Column('remaining',Integer,nullable=False),
    ForeignKeyConstraint(['job_id','target_key'],['mm_demo_targets.job_id','mm_demo_targets.target_key']))
inbox = Table('mm_demo_inbox',meta,
    Column('event_id',String(140),primary_key=True),
    Column('job_id',String(36),nullable=False),
    Column('target_key',String(32)),
    Column('event_type',String(20),nullable=False),
    Column('message',String(200),nullable=False),
    Column('active',Boolean,nullable=False),
    Column('read_at',Integer),
    Column('created_at',Integer,nullable=False),
    ForeignKeyConstraint(['job_id'],['mm_demo_jobs.job_id']))
audit = Table('mm_demo_audit',meta,
    Column('seq',Integer,primary_key=True,autoincrement=True),
    Column('job_id',String(36),nullable=False),
    Column('target_key',String(32)),
    Column('code',String(60),nullable=False),
    Column('at',Integer,nullable=False),
    ForeignKeyConstraint(['job_id'],['mm_demo_jobs.job_id']))

class RecoveryDatabase:
    """Database contract works on SQLite fixture and PostgreSQL via SQLAlchemy.

    PostgreSQL instance and private access not provisioned automatically.
    Not production-safe multi-worker claiming; single worker/replica only.
    """
    def __init__(self, url: str):
        kwargs={'pool_pre_ping':True}
        if url.startswith('sqlite:'):
            kwargs['connect_args']={'check_same_thread':False, 'timeout':15}
        if url.startswith('postgresql://'):
            url='postgresql+psycopg://'+url[len('postgresql://'):]
        self.engine=create_engine(url,**kwargs)
        if url.startswith('sqlite:'):
            from sqlalchemy import event
            @event.listens_for(self.engine, 'connect')
            def pragma(dbapi_conn,_):
                cursor=dbapi_conn.cursor()
                cursor.execute('PRAGMA journal_mode=WAL')
                cursor.execute('PRAGMA synchronous=FULL')
                cursor.execute('PRAGMA foreign_keys=ON')
                cursor.execute('PRAGMA busy_timeout=15000')
                cursor.close()
        meta.create_all(self.engine)
        self.lock=threading.RLock()

    def dispose(self): self.engine.dispose()

    def create_fixture(self, job_id: str | None = None, *, now: int | None = None):
        job_id=job_id or str(uuid.uuid4())
        try: job_id=str(uuid.UUID(job_id))
        except ValueError: raise ValueError('Invalid fixture UUID')
        now=int(time.time()) if now is None else now
        with self.lock, self.engine.begin() as conn:
            old=conn.execute(select(jobs).where(jobs.c.job_id==job_id)).mappings().first()
            if old:
                if old['source_sha256']!=sha(job_id+':synthetic-source'):
                    raise ValueError('Immutable source conflict')
                return self.status(job_id)
            conn.execute(insert(jobs).values(job_id=job_id,source_sha256=sha(job_id+':synthetic-source'),
                   privacy_class='GENERAL',evidence_status='SYNTHETIC_FIXTURE_ONLY',
                   created_at=now,updated_at=now))
            for key in LABELS:
                conn.execute(insert(targets).values(job_id=job_id,target_key=key,
                     expected_sha256=sha(job_id+':'+key),state='PENDING',attempts=0,
                     next_retry_at=0,updated_at=now))
            # Only the narrative is deliberately held in the synthetic fixture.
            conn.execute(insert(faults).values(job_id=job_id,target_key='narrative',
                                fault_type='POLICY_BLOCK',remaining=1))
            conn.execute(insert(audit).values(job_id=job_id,code='SYNTHETIC_CREATED',at=now))
        return self.status(job_id)

    def _event(self,conn,job,key,kind,message,now):
        eid=f'{job}:{key or "all"}:{kind}'
        if conn.execute(select(inbox.c.event_id).where(inbox.c.event_id==eid)).first() is None:
            conn.execute(insert(inbox).values(event_id=eid,job_id=job,target_key=key,
                     event_type=kind,message=message,active=(kind=='ATTENTION'),created_at=now))

    def _set(self,conn,job,key,state,now,error=None,attempt=False,next_retry=0):
        vals={'state':state,'updated_at':now,'last_error':error,'next_retry_at':next_retry}
        if attempt:
            row=conn.execute(select(targets.c.attempts).where((targets.c.job_id==job)&
                              (targets.c.target_key==key))).scalar_one()
            vals['attempts']=row+1
        conn.execute(update(targets).where((targets.c.job_id==job)&
                        (targets.c.target_key==key)).values(**vals))
        conn.execute(insert(audit).values(job_id=job,target_key=key,code='TARGET_'+state,at=now))

    def process_once(self,job_id, *, now=None):
        now=int(time.time()) if now is None else now
        with self.lock:
            with self.engine.begin() as conn:
                if not conn.execute(select(jobs.c.job_id).where(jobs.c.job_id==job_id)).first():
                    raise KeyError('Unknown fixture job')
                rows=conn.execute(select(targets).where(targets.c.job_id==job_id).order_by(
                                  targets.c.target_key)).mappings().all()
            for row in rows:
                key=row['target_key']
                if row['state'] not in ('PENDING','RETRY_WAIT') or (row['state']=='RETRY_WAIT' and now<row['next_retry_at']):
                    continue
                with self.engine.begin() as conn:
                    # Read existing result FIRST, recover committed-write/lost-ack cases.
                    actual=conn.execute(select(fixture_results.c.actual_sha256).where(
                        (fixture_results.c.job_id==job_id)&(fixture_results.c.target_key==key))).scalar_one_or_none()
                    if actual is not None:
                        if actual==row['expected_sha256']:
                            self._set(conn,job_id,key,'VERIFIED',now)
                        else:
                            self._set(conn,job_id,key,'CONFLICT',now,'digest_conflict')
                            self._event(conn,job_id,key,'ATTENTION','A synthetic update needs conflict review.',now)
                        continue
                    fault=conn.execute(select(faults).where(
                        (faults.c.job_id==job_id)&(faults.c.target_key==key))).mappings().first()
                    if fault and fault['remaining']>0:
                        if fault['fault_type']=='POLICY_BLOCK':
                            self._set(conn,job_id,key,'POLICY_BLOCKED',now,'policy_denial',attempt=True)
                            self._event(conn,job_id,key,'ATTENTION',
                                        'One synthetic update is on hold for safe review.',now)
                        elif fault['fault_type']=='TRANSIENT_ONCE':
                            conn.execute(update(faults).where((faults.c.job_id==job_id)&
                                (faults.c.target_key==key)).values(remaining=fault['remaining']-1))
                            delay=min(900,30*2**min(row['attempts'],4))
                            self._set(conn,job_id,key,'RETRY_WAIT',now,'temporary_network',True,now+delay)
                        else:
                            self._set(conn,job_id,key,'AUTH_BLOCKED',now,'not_authorised',attempt=True)
                            self._event(conn,job_id,key,'ATTENTION',
                                        'One synthetic update needs access review.',now)
                        continue
                    # Verified synthetic write: two separate transactions to emulate
                    # result existing despite an interrupted acknowledgement.
                with self.engine.begin() as conn:
                    existing=conn.execute(select(fixture_results.c.actual_sha256).where(
                        (fixture_results.c.job_id==job_id)&(fixture_results.c.target_key==key))).scalar_one_or_none()
                    if existing is None:
                        conn.execute(insert(fixture_results).values(job_id=job_id,target_key=key,
                            actual_sha256=row['expected_sha256'],created_at=now))
                with self.engine.begin() as conn:
                    verified=conn.execute(select(fixture_results.c.actual_sha256).where(
                        (fixture_results.c.job_id==job_id)&(fixture_results.c.target_key==key))).scalar_one_or_none()
                    if verified==row['expected_sha256']:
                        self._set(conn,job_id,key,'VERIFIED',now,attempt=True)
                    else:
                        self._set(conn,job_id,key,'CONFLICT',now,'readback_mismatch')
                        self._event(conn,job_id,key,'ATTENTION','A synthetic write was not verified.',now)
            with self.engine.begin() as conn:
                states=conn.execute(select(targets.c.state).where(targets.c.job_id==job_id)).scalars().all()
                if states and all(s=='VERIFIED' for s in states):
                    conn.execute(update(inbox).where((inbox.c.job_id==job_id)&
                        (inbox.c.event_type=='ATTENTION')).values(active=False))
                    self._event(conn,job_id,None,'RESOLVED',
                                'All three synthetic destinations have been independently checked.',now)
                    conn.execute(update(jobs).where(jobs.c.job_id==job_id).values(updated_at=now))
            return self.status(job_id)

    def set_test_transient(self, job_id, key='journal'):
        """Fault injection before first processing ONLY (test harness)."""
        with self.lock, self.engine.begin() as conn:
            row=conn.execute(select(targets).where((targets.c.job_id==job_id)&
                   (targets.c.target_key==key))).mappings().first()
            if row is None or row['state']!='PENDING':raise ValueError('not pending')
            conn.execute(insert(faults).values(job_id=job_id,target_key=key,
                   fault_type='TRANSIENT_ONCE',remaining=1))

    def release_demo_hold(self, job_id, *, reviewed:bool, now:int|None=None):
        if reviewed is not True:raise PermissionError('explicit fixture review confirmation required')
        now=int(time.time()) if now is None else now
        with self.lock, self.engine.begin() as conn:
            row=conn.execute(select(targets).where((targets.c.job_id==job_id)&
                            (targets.c.target_key=='narrative'))).mappings().first()
            if not row or row['state']!='POLICY_BLOCKED':
                raise ValueError('no policy-blocked synthetic narrative target')
            fault=conn.execute(select(faults).where((faults.c.job_id==job_id)&
                               (faults.c.target_key=='narrative'))).mappings().first()
            if not fault or fault['fault_type']!='POLICY_BLOCK':
                raise ValueError('policy fixture not verified')
            conn.execute(update(faults).where((faults.c.job_id==job_id)&
                              (faults.c.target_key=='narrative')).values(remaining=0))
            self._set(conn,job_id,'narrative','PENDING',now)
            conn.execute(insert(audit).values(job_id=job_id,code='SYNTHETIC_REVIEW_APPROVED',at=now))
        return self.status(job_id)

    def status(self,job_id):
        with self.engine.connect() as conn:
            j=conn.execute(select(jobs).where(jobs.c.job_id==job_id)).mappings().first()
            if not j:raise KeyError('Unknown fixture job')
            rows=conn.execute(select(targets).where(targets.c.job_id==job_id).order_by(
                              targets.c.target_key)).mappings().all()
            counts={s:sum(r['state']==s for r in rows) for s in STATES}
            return {'job_id':job_id,'evidence_status':j['evidence_status'],
                    'status':'VERIFIED_SYNTHETIC_ONLY' if counts['VERIFIED']==len(rows) else 'INCOMPLETE_SYNTHETIC',
                    'complete_test_only':counts['VERIFIED']==len(rows),
                    'counts':counts,
                    'targets':[{'target_key':r['target_key'],'state':r['state'],
                      'attempts':r['attempts'],'last_error_code':r['last_error'],
                      'next_retry_at':r['next_retry_at']} for r in rows]}

    def job_ids(self):
        with self.engine.connect() as conn:
            return conn.execute(select(jobs.c.job_id)).scalars().all()

    def inbox_view(self,limit=100):
        with self.engine.connect() as conn:
            rows=conn.execute(select(inbox).order_by(inbox.c.created_at.desc(),
                 inbox.c.event_id.desc()).limit(limit)).mappings().all()
            entries=[{'id':r['event_id'],'job_id':r['job_id'],
                 'type':r['event_type'],'message':r['message'],
                 'needs_attention':bool(r['active']),
                 'read':r['read_at'] is not None,
                 'created_at':r['created_at']} for r in rows]
            count=conn.execute(select(func.count()).select_from(inbox).where(
                          (inbox.c.event_type=='ATTENTION')&(inbox.c.active==True))).scalar_one()
            return {'entries':entries,'attention_count':count,'source':'PERSISTENT_SYNTHETIC_DB',
                    'push_enabled':False,'post_office_linked':False}

    def mark_read(self,event_id,now=None):
        now=int(time.time()) if now is None else now
        with self.lock,self.engine.begin() as conn:
            row=conn.execute(select(inbox.c.event_id).where(inbox.c.event_id==event_id)).first()
            if not row:raise KeyError('Unknown Inbox message')
            conn.execute(update(inbox).where((inbox.c.event_id==event_id)&
                 (inbox.c.read_at.is_(None))).values(read_at=now))
        return {'id':event_id,'read':True}

class DemoReviewBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reviewed: bool = Field(description='Explicit reviewer approval for synthetic-only demo')

class Service:
    def __init__(self, db:RecoveryDatabase, token:str, poll_seconds:float=4):
        if len(token)<32:raise ValueError('Synthetic API requires token length >=32')
        self.db=db;self.token=token;self.poll_seconds=poll_seconds
        self.wake=asyncio.Event();self.task=None
        self.worker_error_count=0;self.last_worker_error=None;self.last_worker_error_at=None

    def auth(self,authorization:str|None=Header(default=None)):
        if not isinstance(authorization,str) or not hmac.compare_digest(
                authorization,'Bearer '+self.token):
            raise HTTPException(status_code=401,detail='Authentication required')

    async def run_worker(self):
        # Single replica/worker pilot only. Cross-process PostgreSQL leases
        # and provider-specific adapters require separate approval.
        while True:
            try:
                for jid in self.db.job_ids():
                    self.db.process_once(jid)
            except Exception as exc:
                # Expose a generic health failure; never log private input or secrets.
                self.worker_error_count+=1
                self.last_worker_error=type(exc).__name__
                self.last_worker_error_at=int(time.time())
            try:
                await asyncio.wait_for(self.wake.wait(),timeout=self.poll_seconds)
                self.wake.clear()
            except asyncio.TimeoutError:pass

    def app(self):
        service=self
        @asynccontextmanager
        async def lifespan(app):
            service.task=asyncio.create_task(service.run_worker())
            try:yield
            finally:
                service.task.cancel()
                try:await service.task
                except asyncio.CancelledError:pass
        api=FastAPI(title='Mi Mundo Synthetic Recovery Inbox',lifespan=lifespan,
                    docs_url=None,redoc_url=None,openapi_url=None)
        @api.middleware('http')
        async def protect(request:Request,call_next):
            if request.method=='OPTIONS':
                return JSONResponse(status_code=403,content={'detail':'Same-origin pilot only'})
            response=await call_next(request)
            response.headers.update({'Cache-Control':'no-store',
                 'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
                 'X-Frame-Options':'DENY','Content-Security-Policy':
                 "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"})
            return response
        @api.get('/healthz')
        def health():return {'status':'SYNTHETIC_DEGRADED' if service.worker_error_count else 'SYNTHETIC_REVIEW_ONLY',
             'worker_error_count':service.worker_error_count,'last_worker_error_class':service.last_worker_error,
             'database':'PERSISTENT_SQL' if service.db.engine.dialect.name=='postgresql' else 'SQLITE_LOCAL_FIXTURE',
             'original_evidence_stored':False,'departmental_routing':False,'push_notifications':False}
        @api.get('/demo',response_class=HTMLResponse)
        def demo():
            # No token in page source or persistent browser storage.
            return (Path(__file__).parent/'recovery_demo.html').read_text()
        @api.get('/recovery-demo.js')
        def demojs():
            return HTMLResponse((Path(__file__).parent/'recovery_demo.js').read_text(),
                media_type='application/javascript')
        @api.get('/recovery-demo.css')
        def democss():
            return HTMLResponse((Path(__file__).parent/'recovery_demo.css').read_text(),
                 media_type='text/css')
        @api.post('/v1/demo/jobs',dependencies=[Depends(service.auth)])
        def create(request:Request):
            # Reject unsolicited body so real-life originals cannot be accidentally
            # sent into a route that only generates synthetic fixture markers.
            length=request.headers.get('content-length','0')
            if length not in ('', '0') or request.headers.get('transfer-encoding'):
                raise HTTPException(status_code=422,detail='Synthetic demo takes no user content')
            result=service.db.create_fixture()
            service.wake.set()
            return JSONResponse(status_code=201,content=result)
        @api.get('/v1/jobs/{job_id}',dependencies=[Depends(service.auth)])
        def status(job_id:str):
            try:return service.db.status(str(uuid.UUID(job_id)))
            except (ValueError,KeyError):raise HTTPException(status_code=404,detail='Not found')
        @api.get('/v1/inbox',dependencies=[Depends(service.auth)])
        def read_inbox(limit:int=Query(100,ge=1,le=200)):
            return service.db.inbox_view(limit)
        @api.post('/v1/inbox/{event_id}/read',dependencies=[Depends(service.auth)])
        def read_notice(event_id:str):
            if len(event_id)>140:raise HTTPException(status_code=404,detail='Not found')
            try:return service.db.mark_read(event_id)
            except KeyError:raise HTTPException(status_code=404,detail='Not found')
        @api.post('/v1/demo/jobs/{job_id}/resolve',dependencies=[Depends(service.auth)])
        def resolve(job_id:str,body:DemoReviewBody):
            try:result=service.db.release_demo_hold(str(uuid.UUID(job_id)),reviewed=body.reviewed)
            except (ValueError,KeyError,PermissionError):
                raise HTTPException(status_code=409,detail='Safe synthetic review is required')
            service.wake.set()
            return result
        @api.post('/v1/demo/jobs/{job_id}/tick',dependencies=[Depends(service.auth)])
        def tick(job_id:str):
            try:return service.db.process_once(str(uuid.UUID(job_id)))
            except (ValueError,KeyError):raise HTTPException(status_code=404,detail='Not found')
        return api

def create_app(database_url=None,token=None,poll_seconds=4):
    database_url=database_url or os.environ.get('MI_MUNDO_DATABASE_URL')
    token=token or os.environ.get('MI_MUNDO_TEST_TOKEN')
    if os.environ.get('MI_MUNDO_REVIEW_MODE','synthetic')!='synthetic':
        raise RuntimeError('Production mode is not supported')
    if not database_url:
        raise RuntimeError('Explicit durable DB URL required; no in-memory default')
    if not token or len(token)<32:raise RuntimeError('Test-only bearer token missing')
    return Service(RecoveryDatabase(database_url),token,poll_seconds).app()

# Used by uvicorn integration.recovery_api:app in staged synthetic service.
if os.environ.get('MI_MUNDO_DATABASE_URL') and os.environ.get('MI_MUNDO_TEST_TOKEN'):
    app=create_app()
else:
    app=None