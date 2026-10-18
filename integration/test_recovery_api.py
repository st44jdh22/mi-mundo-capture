"""Synthetic-only HTTP, durable checkpoint and Inbox contract tests."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from recovery_api import create_app, RecoveryDatabase, sha, LABELS, targets, fixture_results, faults, inbox
from sqlalchemy import select, insert

TOKEN='synthetic-fixture-token-'+'R'*40
HEAD={'Authorization':'Bearer '+TOKEN}

class DurableRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=str(Path(self.tmp.name)/'recovery.sqlite3')
        self.url='sqlite:///'+self.path
        self.db=RecoveryDatabase(self.url)
    def tearDown(self):
        self.db.dispose();self.tmp.cleanup()
    def create(self):return self.db.create_fixture(now=1000)

    def test_exact_three_destinations_and_source_scope(self):
        r=self.create();self.assertEqual(r['status'],'INCOMPLETE_SYNTHETIC')
        self.assertEqual({t['target_key'] for t in r['targets']},set(LABELS))
        self.assertEqual(r['evidence_status'],'SYNTHETIC_FIXTURE_ONLY')

    def test_two_verifications_one_policy_block(self):
        r=self.create();a=self.db.process_once(r['job_id'],now=1001)
        self.assertEqual(a['counts']['VERIFIED'],2)
        self.assertEqual(a['counts']['POLICY_BLOCKED'],1)
        self.assertFalse(a['complete_test_only'])
        b=self.db.inbox_view();self.assertEqual(b['attention_count'],1)
        self.assertIn('hold',b['entries'][0]['message'])

    def test_worker_restart_keeps_pending_and_does_not_duplicate(self):
        r=self.create();id=r['job_id'];self.db.process_once(id,now=1001)
        before=self.db.engine.connect()
        try:n=before.execute(select(fixture_results)).fetchall();self.assertEqual(len(n),2)
        finally:before.close()
        self.db.dispose();self.db=RecoveryDatabase(self.url)
        second=self.db.process_once(id,now=2000)
        self.assertEqual(second['counts']['POLICY_BLOCKED'],1)
        self.assertEqual(second['counts']['VERIFIED'],2)
        with self.db.engine.connect() as c:
            self.assertEqual(len(c.execute(select(fixture_results)).fetchall()),2)
            self.assertEqual(len(c.execute(select(inbox)).fetchall()),1)

    def test_review_requires_explicit_confirmation_then_only_third_writes(self):
        j=self.create()['job_id'];self.db.process_once(j,now=1001)
        with self.assertRaises(PermissionError):
            self.db.release_demo_hold(j,reviewed=False,now=1005)
        after=self.db.release_demo_hold(j,reviewed=True,now=1006)
        self.assertEqual(after['counts']['PENDING'],1)
        done=self.db.process_once(j,now=1007)
        self.assertTrue(done['complete_test_only'])
        self.assertEqual(self.db.inbox_view()['attention_count'],0)
        self.assertEqual({x['type'] for x in self.db.inbox_view()['entries']},{'ATTENTION','RESOLVED'})
        with self.db.engine.connect() as c:
            self.assertEqual(len(c.execute(select(fixture_results)).fetchall()),3)
        self.db.process_once(j,now=1008)
        with self.db.engine.connect() as c:
            self.assertEqual(len(c.execute(select(inbox)).fetchall()),2)

    def test_lost_ack_checkpoint_recovers_without_new_result(self):
        j=self.create()['job_id']
        with self.db.engine.begin() as c:
            c.execute(insert(fixture_results).values(job_id=j,target_key='journal',
                      actual_sha256=sha(j+':journal'),created_at=1001))
        x=self.db.process_once(j,now=1002)
        self.assertEqual(x['counts']['VERIFIED'],2)
        with self.db.engine.connect() as c:
            self.assertEqual(len(c.execute(select(fixture_results)).fetchall()),2)

    def test_source_idempotence(self):
        j=self.create()['job_id'];self.assertEqual(self.db.create_fixture(j)['job_id'],j)
        with self.db.engine.connect() as c:
            self.assertEqual(len(c.execute(select(targets)).fetchall()),3)

    def test_wrong_digest_conflict_no_overwrite(self):
        j=self.create()['job_id']
        with self.db.engine.begin() as c:
            c.execute(insert(fixture_results).values(job_id=j,target_key='journal',
                      actual_sha256='f'*64,created_at=1001))
        x=self.db.process_once(j,now=1002)
        self.assertEqual(x['counts']['CONFLICT'],1)
        self.assertEqual(self.db.inbox_view()['attention_count'],2)
        with self.db.engine.connect() as c:
            self.assertEqual(c.execute(select(fixture_results.c.actual_sha256).where(
                fixture_results.c.job_id==j,fixture_results.c.target_key=='journal')).scalar_one(),'f'*64)

    def test_transient_backoff_then_attempt_when_due(self):
        j=self.create()['job_id'];self.db.set_test_transient(j,'journal')
        x=self.db.process_once(j,now=1001)
        self.assertEqual(x['counts']['RETRY_WAIT'],1)
        self.assertEqual(x['counts']['VERIFIED'],1)
        self.assertEqual(x['counts']['POLICY_BLOCKED'],1)
        before=self.db.process_once(j,now=1010)
        self.assertEqual(before['counts']['RETRY_WAIT'],1)
        done=self.db.process_once(j,now=1032)
        self.assertEqual(done['counts']['VERIFIED'],2)

    def test_inbox_read_receipt_survives_restart(self):
        j=self.create()['job_id'];self.db.process_once(j,now=1001)
        event=self.db.inbox_view()['entries'][0]['id']
        self.db.mark_read(event,now=1003)
        self.db.dispose();self.db=RecoveryDatabase(self.url)
        x=self.db.inbox_view();self.assertTrue(x['entries'][0]['read'])
        self.assertEqual(x['attention_count'],1)

    def test_failure_safely_does_not_contain_private_contents(self):
        j=self.create()['job_id'];self.db.process_once(j,now=1001)
        self.assertNotIn('medical',str(self.db.inbox_view()).lower())
        self.assertNotIn('personal note',str(self.db.inbox_view()).lower())

    def test_sqlite_dump_restores_pending_inbox(self):
        j=self.create()['job_id'];self.db.process_once(j,now=1001)
        import sqlite3
        backup=str(Path(self.tmp.name)/'snapshot.sqlite3')
        # SQLite proper online backup API rather than raw database file copy.
        with sqlite3.connect(self.path) as src,sqlite3.connect(backup) as dest:
            src.backup(dest)
        restored=RecoveryDatabase('sqlite:///'+backup)
        try:
            self.assertEqual(restored.status(j)['counts']['POLICY_BLOCKED'],1)
            self.assertEqual(restored.inbox_view()['attention_count'],1)
        finally:restored.dispose()

class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=create_app('sqlite:///'+str(Path(self.tmp.name)/'http.sqlite3'),TOKEN,poll_seconds=0.05)
        self.client=TestClient(self.app);self.client.__enter__()
    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.tmp.cleanup()

    def test_health_fails_closed_to_synthetic_mode(self):
        r=self.client.get('/healthz');self.assertEqual(r.status_code,200)
        self.assertFalse(r.json()['original_evidence_stored'])
        self.assertFalse(r.json()['departmental_routing'])
        self.assertEqual(r.json()['status'],'SYNTHETIC_REVIEW_ONLY')

    def test_auth_required_all_mutating_and_inbox_routes(self):
        for path in ['/v1/inbox','/v1/jobs/00000000-0000-4000-8000-000000000000']:
            self.assertEqual(self.client.get(path).status_code,401)
        self.assertEqual(self.client.post('/v1/demo/jobs').status_code,401)
        self.assertEqual(self.client.post('/v1/demo/jobs',headers={'Authorization':'Bearer wrong'}).status_code,401)

    def test_synthetic_job_background_processing_and_inbox(self):
        created=self.client.post('/v1/demo/jobs',headers=HEAD)
        self.assertEqual(created.status_code,201)
        jid=created.json()['job_id']
        for i in range(100):
            s=self.client.get('/v1/jobs/'+jid,headers=HEAD).json()
            if s['counts']['POLICY_BLOCKED']==1:break
            time.sleep(.02)
        self.assertEqual(s['counts']['VERIFIED'],2)
        box=self.client.get('/v1/inbox',headers=HEAD).json()
        self.assertEqual(box['attention_count'],1)
        self.assertFalse(box['push_enabled'])
        self.assertFalse(box['post_office_linked'])
        blocked=self.client.post('/v1/demo/jobs/'+jid+'/resolve',headers=HEAD,json={'reviewed':False})
        self.assertEqual(blocked.status_code,409)
        approved=self.client.post('/v1/demo/jobs/'+jid+'/resolve',headers=HEAD,json={'reviewed':True})
        self.assertEqual(approved.status_code,200)
        for i in range(100):
            s=self.client.get('/v1/jobs/'+jid,headers=HEAD).json()
            if s['complete_test_only']:break
            time.sleep(.02)
        self.assertTrue(s['complete_test_only'])
        final=self.client.get('/v1/inbox',headers=HEAD).json()
        self.assertEqual(final['attention_count'],0)
        self.assertEqual(len(final['entries']),2)

    def test_recovery_demo_page_is_real_html_and_token_absent(self):
        page=self.client.get('/demo')
        self.assertEqual(page.status_code,200)
        self.assertIn('Recovery Inbox',page.text)
        self.assertNotIn(TOKEN,page.text)
        self.assertIn('Content-Security-Policy',page.headers)
        script=self.client.get('/recovery-demo.js')
        self.assertEqual(script.status_code,200)
        self.assertIn('/v1/inbox',script.text)

    def test_missing_job_and_inbox_event_return_404(self):
        self.assertEqual(self.client.get('/v1/jobs/'+str('0'*8+'-0000-4000-8000-000000000000'),headers=HEAD).status_code,404)
        self.assertEqual(self.client.post('/v1/inbox/non-existent/read',headers=HEAD).status_code,404)

    def test_no_real_original_data_endpoint_and_unknown_body_not_supported(self):
        self.assertEqual(self.client.post('/v1/medical',headers=HEAD,json={'text':'not stored'}).status_code,404)
        # Demo rejects unsolicited private data rather than silently dropping it.
        r=self.client.post('/v1/demo/jobs',headers=HEAD,json={'private':'DO NOT STORE'})
        self.assertEqual(r.status_code,422)
        self.assertNotIn('DO NOT STORE',str(self.client.get('/v1/inbox',headers=HEAD).json()))

if __name__=='__main__':unittest.main()