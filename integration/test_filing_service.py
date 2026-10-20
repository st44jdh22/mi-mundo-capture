"""Synthetic acceptance on local SQLite and opt-in disposable PostgreSQL."""
import concurrent.futures
import base64
import json
import os
import sqlite3
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

from sqlalchemy import select, update
from filing.service import (FilingService, LeaseLost, attempts, events, jobs,
                            metadata, outbox, report_attempts)
from filing.storage import LocalSyntheticObjects
from filing.adapters import (GoogleDriveFilingAdapter, SyntheticRecordAdapter,
    PostOfficeStatusAdapter, PolicyBlock, PermissionFailure, TransientFailure, Conflict)
from postoffice_contract import MESSAGE_COLUMNS, DELIVERY_COLUMNS

def synthetic_pdf():
    """A real one-page harmless PDF; no original A58 bytes or dependencies."""
    stream=b'BT /F1 12 Tf 50 750 Td (Synthetic A58 filing test only) Tj ET'
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
    result=b'%PDF-1.4\n%SYNTHETIC\n';offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(result));result+=str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
    start=len(result)
    result+=b'xref\n0 6\n0000000000 65535 f \n'
    result+=b''.join(f'{n:010d} 00000 n \n'.encode() for n in offsets[1:])
    result+=b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n'+str(start).encode()+b'\n%%EOF\n'
    return result


DATA = synthetic_pdf()


class Crash(BaseException): pass


class Transport:
    """Independent durable destination fixture, separate from recovery SQL."""
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS effect (id TEXT PRIMARY KEY, data BLOB, attrs TEXT)')
        self.mode = None
        self.writes = 0

    def find(self, effect_id):
        if self.mode == 'offline':
            raise TransientFailure('synthetic Drive unavailable')
        row = self.db.execute('SELECT data,attrs FROM effect WHERE id=?', (effect_id,)).fetchone()
        return [] if not row else [dict(json.loads(row[1]), data=row[0])]

    def create_if_absent(self, identity, data, attrs):
        if self.mode == 'policy': raise PolicyBlock('synthetic policy block; SECRET PRIVATE ERROR')
        if self.mode == 'permission': raise PermissionFailure('synthetic permission denied')
        if self.mode == 'transient': raise TransientFailure('synthetic safe pre-write failure')
        self.writes += 1
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO effect VALUES (?,?,?)', (identity,data,json.dumps(attrs)))
        if self.mode == 'lost_response':
            self.mode = None
            raise TimeoutError('synthetic committed upload; reply lost')

    def close(self): self.db.close()


class Projection:
    def __init__(self):
        self.rows = {}
        self.fail = False
        self.fail_on_error = False
        self.lost_reply = False
        self.conflicting_schema = False

    def headers(self, table):
        if self.conflicting_schema: return ('CHANGED',)
        return {
            'MESSAGES': MESSAGE_COLUMNS, 'DELIVERIES': DELIVERY_COLUMNS,
            'ACTIONS': ('Action ID','Message ID','Delivery ID','Department ID','Action','Owner','Status','Due / Review Condition','Completion Evidence','Record Updated','Last Updated'),
            'ESCALATIONS': ('Escalation ID','Message ID','Delivery ID','Severity','Issue','Owner','Stephen Required','Status','Created At','Resolved At','Resolution'),
            'RUN LOG': ('Run ID','Timestamp','Department ID','Message ID','Trigger','Model / Profile','Records Read','Records Written','Outcome','Duration Sec','Token / API Usage','Error','Retry','Approval State'),
        }[table]

    def upsert(self, table, key, payload):
        if self.fail or (self.fail_on_error and (table=='ESCALATIONS' or payload.get('Error'))):
            raise TransientFailure('synthetic Sheets logging unavailable')
        self.rows[table,key] = dict(payload)
        if self.lost_reply:
            self.lost_reply = False
            raise TimeoutError('synthetic reply lost after projection')

    def read(self, table, key): return self.rows.get((table,key))


def specification(*, chef=False):
    job = str(uuid.uuid4())
    def target(name, kind):
        return {'target_id':'synthetic-'+name, 'kind':kind, 'destination':'synthetic-folder',
            'name':'synthetic-'+name+'.pdf', 'effect_id':'synthetic-'+job+'-'+name,
            'permissions':['synthetic-owner:owner'], 'value':'SYNTHETIC: '+name}
    return {'job_id':job, 'intake_id':str(uuid.uuid4()), 'requester':'synthetic-owner',
        'department':'FOOD-CHEF' if chef else 'SYS-POSTOFFICE',
        'conversation_id':'synthetic-conversation', 'idempotency_key':'synthetic-'+job,
        'instruction':'SYNTHETIC: file and independently verify this fixture',
        'source_ref':'fixture://A58' if not chef else 'fixture://chef-receipt',
        'approval_ref':'synthetic-approval-20261019', 'authoritative_record':'synthetic-master',
        'targets':[target('receipt','FILE'),target('inventory','RECORD'),target('activity','RECORD')]
            if chef else [target('brief','FILE')]}


class FilingTests(unittest.TestCase):
    pg_url = None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 1000
        self.url = self.pg_url or 'sqlite:///'+str(Path(self.tmp.name)/'case_filing_test.sqlite')
        self.s = FilingService(self.url, clock=lambda: self.now)
        if self.pg_url:
            metadata.drop_all(self.s.engine)  # Explicit disposable DB only.
        self.s.initialize_test_schema()
        self.s.set_stopped(False)
        self.objects = LocalSyntheticObjects(Path(self.tmp.name)/'private')
        self.transport = Transport(str(Path(self.tmp.name)/'destination.sqlite'))
        self.adapters = {'FILE':GoogleDriveFilingAdapter(self.transport),
                         'RECORD':SyntheticRecordAdapter(self.transport)}
        self.spec = specification()

    def tearDown(self):
        self.s.close(); self.transport.close(); self.tmp.cleanup()

    def submit(self, spec=None, data=DATA):
        spec = spec or self.spec
        return self.s.submit(spec, data, self.objects)

    def status(self):
        return self.s.status(self.spec['job_id'], 'synthetic-owner', 'synthetic-conversation')

    def run_job(self, hook=lambda *args:None):
        return self.s.run_once(self.spec['job_id'],'synthetic-worker-1',self.objects,self.adapters,hook=hook)

    def reopen(self):
        self.s.close()
        self.s = FilingService(self.url, clock=lambda:self.now)

    def test_normal_file_with_independent_verification(self):
        self.submit(); self.run_job()
        self.assertEqual(self.status()['state'],'VERIFIED COMPLETE')
        self.assertEqual(self.transport.writes,1)
        self.assertTrue(self.status()['targets'][0]['verification']['independent_readback'])

    def test_durable_commit_and_original_precede_first_write(self):
        self.submit()
        def check(stage, claim):
            if stage == 'before_write':
                other = FilingService(self.url)
                try:
                    self.assertEqual(other.status(self.spec['job_id'],'synthetic-owner','synthetic-conversation')['attempts'],1)
                    self.assertEqual(self.objects.get(claim['object_key']),DATA)
                finally: other.close()
        self.run_job(check)

    def test_transient_then_safe_retry_retains_history(self):
        self.submit(); self.transport.mode='transient'; self.run_job()
        self.assertEqual(self.status()['state'],'RETRY PENDING')
        self.assertFalse(self.run_job())
        self.reopen(); self.now+=30; self.transport.mode=None; self.run_job()
        self.assertEqual(self.status()['state'],'VERIFIED COMPLETE')
        with self.s.engine.connect() as c:
            rows=c.execute(select(attempts).where(attempts.c.job_id==self.spec['job_id'])).mappings().all()
            self.assertEqual(len(rows),2)
            self.assertIsNotNone(rows[0]['exact_error'])

    def test_policy_blocks_and_google_exception_logging_can_fail(self):
        self.submit(); self.transport.mode='policy'; self.run_job()
        p=Projection();p.fail_on_error=True
        for _ in range(20):
            if not self.s.flush_reporting(PostOfficeStatusAdapter(p)):break
        self.reopen();self.now+=1000;self.transport.mode=None
        self.assertFalse(self.run_job())
        self.assertEqual(self.status()['state'],'BLOCKED')
        self.assertEqual(self.transport.writes,0)
        self.assertNotIn('SECRET',json.dumps(self.status()))
        with self.s.engine.connect() as c:
            self.assertIn('SECRET',c.execute(select(attempts.c.exact_error)).scalar_one())
            self.assertNotIn('SECRET',str(c.execute(select(outbox.c.payload)).scalars().all()))
            failed=c.execute(select(report_attempts.c.exact_error).where(report_attempts.c.exact_error.is_not(None))).scalars().all()
            self.assertEqual(failed,['synthetic Sheets logging unavailable'])

    def test_permission_block_requires_review(self):
        self.submit();self.transport.mode='permission';self.run_job()
        self.assertEqual(self.status()['error_code'],'permission_denied')
        with self.assertRaises(PermissionError):
            self.s.reviewed_release(self.spec['job_id'],'synthetic-owner','missing-approval')
        self.transport.mode=None
        self.s.reviewed_release(self.spec['job_id'],'synthetic-owner','synthetic-review-1')
        self.run_job();self.assertEqual(self.status()['state'],'VERIFIED COMPLETE')

    def test_duplicate_submission_has_one_job_and_effect(self):
        first=self.submit();self.assertEqual(self.submit(),first)
        other=dict(self.spec,job_id=str(uuid.uuid4()))
        self.assertEqual(self.submit(other),first)
        self.run_job();self.assertFalse(self.run_job());self.assertEqual(self.transport.writes,1)

    def test_changed_duplicate_rejected(self):
        self.submit()
        changed=dict(self.spec,instruction='SYNTHETIC: changed filing request')
        with self.assertRaises(Conflict):self.submit(changed)

    def test_crash_before_write_restarts_from_durable_source(self):
        self.submit()
        def crash(stage,claim):
            if stage=='before_write':raise Crash()
        with self.assertRaises(Crash):self.run_job(crash)
        self.assertEqual(self.transport.writes,0)
        self.reopen();self.now+=61;self.run_job()
        self.assertEqual(self.status()['state'],'VERIFIED COMPLETE')

    def test_crash_after_write_before_any_checkpoint_no_duplicate(self):
        self.submit()
        def crash(stage,claim):
            if stage=='after_write':raise Crash()
        with self.assertRaises(Crash):self.run_job(crash)
        self.reopen();self.now+=61;self.run_job()
        self.assertEqual(self.transport.writes,1)
        self.assertEqual(self.status()['state'],'VERIFIED COMPLETE')

    def test_lost_upload_reply_reconciles_committed_file(self):
        self.submit();self.transport.mode='lost_response';self.run_job()
        self.assertEqual(self.status()['error_code'],'outcome_unknown')
        self.now+=30;self.run_job()
        self.assertEqual(self.transport.writes,1)

    def test_source_unavailable_has_actionable_retained_job(self):
        self.submit(data=None)
        self.assertEqual(self.status()['state'],'MANUAL REVIEW')
        self.assertEqual(self.status()['error_code'],'source_unavailable')
        self.assertFalse(self.run_job())

    def test_source_missing_after_restart_is_not_fabricated_completion(self):
        self.submit()
        with self.s.engine.connect() as c:key=c.execute(select(jobs.c.object_key)).scalar_one()
        (self.objects.root/key).unlink()
        self.reopen();self.run_job()
        self.assertEqual(self.status()['error_code'],'source_unavailable')
        self.assertEqual(self.transport.writes,0)

    def test_chef_receipt_inventory_and_activity_individually_verified(self):
        self.spec=specification(chef=True);self.submit();self.run_job()
        self.assertEqual(len(self.status()['targets']),3)
        self.assertTrue(all(t['state']=='VERIFIED COMPLETE' for t in self.status()['targets']))
        self.assertFalse(self.status()['department_acknowledged'])
        self.assertEqual(self.transport.writes,3)

    def test_partial_result_preserved_without_repeating_success(self):
        self.spec=specification(chef=True);self.submit()
        original=self.adapters['RECORD'].write
        def fail_second(target,data):
            if target['target_id']=='synthetic-inventory':raise TransientFailure('fixture register unavailable')
            return original(target,data)
        self.adapters['RECORD'].write=fail_second
        self.run_job();self.assertTrue(self.status()['partially_complete'])
        with self.s.engine.connect() as c:
            projected=c.execute(select(outbox.c.payload)).scalars().all()
            self.assertNotIn('VERIFIED COMPLETE',[event['state'] for event in projected])
        self.adapters['RECORD'].write=original;self.now+=30;self.run_job()
        self.assertEqual(self.status()['state'],'VERIFIED COMPLETE')
        self.assertEqual(self.transport.writes,3)

    def test_three_attempt_limit_survives_restart(self):
        self.submit();self.transport.mode='transient'
        for advance in (0,30,60):
            self.now+=advance;self.run_job();self.reopen()
        self.now+=1000
        self.assertFalse(self.run_job())
        self.assertEqual(self.status()['attempts'],3)
        self.assertEqual(self.status()['state'],'MANUAL REVIEW')

    def test_atomic_claim_across_two_connections(self):
        self.submit();other=FilingService(self.url,clock=lambda:self.now)
        try:
            with concurrent.futures.ThreadPoolExecutor(2) as executor:
                futures=[executor.submit(s.claim,self.spec['job_id'],'synthetic-worker-'+str(i))
                         for i,s in enumerate((self.s,other))]
                self.assertEqual(sum(f.result() is not None for f in futures),1)
        finally:other.close()

    def test_one_worker_limit_across_jobs(self):
        self.submit();second=specification();self.submit(second)
        self.s.claim(self.spec['job_id'],'synthetic-worker-1')
        self.assertIsNone(self.s.claim(second['job_id'],'synthetic-worker-2'))

    def test_stale_lease_cannot_update_new_claim(self):
        self.submit();old=self.s.claim(self.spec['job_id'],'synthetic-worker-1')
        self.now+=61;new=self.s.claim(self.spec['job_id'],'synthetic-worker-2')
        self.assertNotEqual(old['lease_token'],new['lease_token'])
        with self.assertRaises(LeaseLost):self.s._finish(old,'VERIFIED COMPLETE')

    def test_cancel_before_claim_is_retained(self):
        self.submit();self.s.cancel(self.spec['job_id'],'synthetic-owner')
        self.assertFalse(self.run_job());self.assertEqual(self.status()['state'],'CANCELLED')

    def test_stop_between_claim_and_write_prevents_effect(self):
        self.submit()
        def stop(stage,claim):
            if stage=='before_write':self.s.set_stopped(True)
        self.run_job(stop)
        self.assertEqual(self.transport.writes,0)
        self.assertEqual(self.status()['state'],'MANUAL REVIEW')

    def test_origin_access_checks(self):
        self.submit();self.reopen()
        with self.assertRaises(PermissionError):self.s.status(self.spec['job_id'],'other-owner','synthetic-conversation')
        with self.assertRaises(PermissionError):self.s.status(self.spec['job_id'],'synthetic-owner','other-conversation')
        self.assertEqual(self.status()['job_id'],self.spec['job_id'])

    def test_outcome_survives_reporting_outage_and_reprojects_in_order(self):
        self.submit();self.run_job();p=Projection();p.fail=True
        self.s.flush_reporting(PostOfficeStatusAdapter(p));self.reopen()
        self.assertEqual(self.status()['state'],'VERIFIED COMPLETE')
        self.assertTrue(self.status()['reporting_pending'])
        p.fail=False;self.now+=30
        for _ in range(30):
            if not self.s.flush_reporting(PostOfficeStatusAdapter(p)):break
        self.assertFalse(self.status()['reporting_pending'])
        mid='SYN-MSG-'+self.spec['job_id']
        self.assertEqual(p.rows['MESSAGES',mid]['Overall Status'],'VERIFIED COMPLETE')
        self.assertEqual(self.transport.writes,1)

    def test_lost_projection_ack_reuses_stable_row_ids(self):
        self.submit();self.run_job();p=Projection();p.lost_reply=True
        self.s.flush_reporting(PostOfficeStatusAdapter(p));self.now+=30
        for _ in range(30):
            if not self.s.flush_reporting(PostOfficeStatusAdapter(p)):break
        self.assertEqual(len([k for k in p.rows if k[0]=='MESSAGES']),1)
        self.assertFalse(self.status()['reporting_pending'])

    def test_projection_retry_cap_and_schema_change_hold(self):
        self.submit();p=Projection();p.conflicting_schema=True
        self.s.flush_reporting(PostOfficeStatusAdapter(p))
        self.now+=1000
        self.assertFalse(self.s.flush_reporting(PostOfficeStatusAdapter(p)))
        with self.s.engine.connect() as c:
            self.assertEqual(c.execute(select(report_attempts.c.outcome)).scalar_one(),'MANUAL REVIEW')

    def test_five_job_budget(self):
        for _ in range(5):self.submit(specification())
        with self.assertRaises(PermissionError):self.submit(specification())

    def test_invalid_target_rejected_before_source_staging(self):
        """Invalid synthetic target must not create external object effects."""
        original = self.objects.put
        calls = []
        def spy(data):
            calls.append(data)
            return original(data)
        self.objects.put = spy
        bad = specification(chef=True)
        bad['targets'][1]['destination'] = 'real-business-folder'
        with self.assertRaises(PermissionError):
            self.submit(bad)
        self.assertEqual(calls, [])
        with self.s.engine.connect() as conn:
            self.assertEqual(conn.execute(select(jobs)).first(), None)

    def test_real_scope_and_path_traversal_rejected(self):
        with self.assertRaises(ValueError):self.submit(data=b'Real personal document')
        with self.assertRaises(PermissionError):self.submit(dict(self.spec,department='MARINE'))
        with self.assertRaises(ValueError):self.objects.get('../private')

    def test_empty_success_response_is_not_completion(self):
        self.submit()
        self.adapters['FILE'].write=lambda *args: {'success':True}
        self.run_job()
        self.assertEqual(self.status()['state'],'RETRY PENDING')
        self.assertEqual(self.status()['error_code'],'outcome_unknown')

    def test_wrong_permissions_or_content_never_verified(self):
        self.submit();self.run_job()
        with self.transport.db:
            self.transport.db.execute("UPDATE effect SET data=?",(b'changed',))
        target=dict(self.spec['targets'][0])
        with self.s.engine.connect() as c:
            from filing.service import targets
            target=c.execute(select(targets.c.spec)).scalar_one()
        with self.assertRaises(Conflict):self.adapters['FILE'].observe(target)

    def test_reporting_crash_attempt_is_persisted_before_external_call(self):
        self.submit();self.run_job();p=Projection()
        def crash(stage,row):
            if stage=='report_written':raise Crash()
        with self.assertRaises(Crash):self.s.flush_reporting(PostOfficeStatusAdapter(p),hook=crash)
        self.reopen()
        with self.s.engine.connect() as c:
            self.assertEqual(c.execute(select(report_attempts.c.outcome)).scalar_one(),'RESERVED')
        self.now+=61
        for _ in range(30):
            if not self.s.flush_reporting(PostOfficeStatusAdapter(p)):break
        self.assertFalse(self.status()['reporting_pending'])

    def test_reporting_three_failures_cannot_silently_reset_budget(self):
        self.submit();p=Projection();p.fail=True
        for advance in (0,30,60):
            self.now+=advance;self.s.flush_reporting(PostOfficeStatusAdapter(p));self.reopen()
        self.now+=1000;p.fail=False
        self.assertFalse(self.s.flush_reporting(PostOfficeStatusAdapter(p)))
        with self.s.engine.connect() as c:
            self.assertEqual(len(c.execute(select(report_attempts)).all()),3)

    def test_filing_api_accepts_next_job_and_retrieves_after_restart(self):
        from fastapi.testclient import TestClient
        from filing.api import create_app
        token='fixture-only-independent-test-token-'+'X'*32
        headers={'Authorization':'Bearer '+token}
        with TestClient(create_app(self.s,self.objects,token=token)) as client:
            body={'spec':self.spec,'document_base64':base64.b64encode(DATA).decode()}
            self.assertEqual(client.post('/v1/filing-test/jobs',json=body).status_code,401)
            accepted=client.post('/v1/filing-test/jobs',headers=headers,json=body)
            self.assertEqual(accepted.status_code,202)
            self.assertEqual(accepted.json()['state'],'QUEUED')
            body['spec']=specification(chef=True)
            self.assertEqual(client.post('/v1/filing-test/jobs',headers=headers,json=body).status_code,202)
            self.assertEqual(self.transport.writes,0)
        self.run_job();self.reopen()
        with TestClient(create_app(self.s,self.objects,token=token)) as client:
            rows=client.get('/v1/filing-test/conversations/synthetic-conversation/jobs',headers=headers).json()
            self.assertEqual(len(rows),2)
            self.assertEqual({r['state'] for r in rows},{'VERIFIED COMPLETE','QUEUED'})
            self.assertFalse(rows[0]['department_acknowledged'])

    def test_database_and_original_object_backup_restore(self):
        if self.pg_url:
            self.skipTest('SQLite backup test; PostgreSQL pg_dump/restore remains a release gate')
        self.submit();self.transport.mode='transient';self.run_job()
        restored_path=Path(self.tmp.name)/'restored_filing_test.sqlite'
        with sqlite3.connect(self.s.engine.url.database) as original, sqlite3.connect(restored_path) as restored:
            original.backup(restored)
        restored_objects=LocalSyntheticObjects(Path(self.tmp.name)/'restored-objects')
        shutil.copytree(self.objects.root,restored_objects.root,dirs_exist_ok=True)
        restored=FilingService('sqlite:///'+str(restored_path),clock=lambda:self.now)
        self.now+=30;self.transport.mode=None
        try:
            restored.run_once(self.spec['job_id'],'synthetic-worker-restored',restored_objects,self.adapters)
            status=restored.status(self.spec['job_id'],'synthetic-owner','synthetic-conversation')
            self.assertEqual(status['state'],'VERIFIED COMPLETE')
            self.assertEqual(status['attempts'],2)
        finally:restored.close()

    def test_object_storage_failure_preserves_instruction_and_source_hash(self):
        class OfflineObjects:
            def put(self,data):raise OSError('synthetic object store unavailable')
        job=self.s.submit(self.spec,DATA,OfflineObjects())
        self.assertEqual(self.status()['error_code'],'source_retention_failed')
        self.reopen()
        with self.s.engine.connect() as c:
            row=c.execute(select(jobs).where(jobs.c.job_id==job)).mappings().one()
            self.assertEqual(row['instruction'],self.spec['instruction'])
            self.assertIsNone(row['object_key'])
            self.assertEqual(row['exact_error'],'synthetic object store unavailable')
        self.s.restore_source(job,'synthetic-owner',DATA,self.objects)
        self.assertFalse(self.run_job())  # Source restoration alone is not release.
        self.s.reviewed_release(job,'synthetic-owner','synthetic-review-storage')
        self.run_job();self.assertEqual(self.status()['state'],'VERIFIED COMPLETE')

    def test_source_restoration_rejects_altered_original(self):
        class OfflineObjects:
            def put(self,data):raise OSError('synthetic store unavailable')
        job=self.s.submit(self.spec,DATA,OfflineObjects())
        with self.assertRaises(Conflict):
            self.s.restore_source(job,'synthetic-owner',b'SYNTHETIC\naltered',self.objects)


@unittest.skipUnless(os.environ.get('MI_MUNDO_FILING_TEST_PG_URL'), 'Disposable PostgreSQL not supplied')
class FilingPostgresTests(FilingTests):
    pg_url = os.environ.get('MI_MUNDO_FILING_TEST_PG_URL')


if __name__=='__main__':unittest.main()
