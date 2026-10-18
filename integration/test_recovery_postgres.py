"""Test PostgreSQL API contract on disposable CI database, no user sources."""
import os
import unittest
import uuid
from recovery_api import RecoveryDatabase

@unittest.skipUnless(os.environ.get('MI_MUNDO_CI_PG_URL'), 'requires disposable PostgreSQL in CI')
class PostgresIntegrationTests(unittest.TestCase):
    def setUp(self):self.db=RecoveryDatabase(os.environ['MI_MUNDO_CI_PG_URL'])
    def tearDown(self):self.db.dispose()
    def test_create_block_restart_release_resolve(self):
        jid=str(uuid.uuid4())
        r=self.db.create_fixture(jid)
        self.assertEqual(r['evidence_status'],'SYNTHETIC_FIXTURE_ONLY')
        blocked=self.db.process_once(jid)
        self.assertEqual(blocked['counts']['VERIFIED'],2)
        self.assertEqual(blocked['counts']['POLICY_BLOCKED'],1)
        self.assertEqual(self.db.inbox_view()['attention_count']>=1,True)
        self.db.dispose();self.db=RecoveryDatabase(os.environ['MI_MUNDO_CI_PG_URL'])
        again=self.db.process_once(jid)
        self.assertEqual(again['counts']['VERIFIED'],2)
        self.db.release_demo_hold(jid,reviewed=True)
        done=self.db.process_once(jid)
        self.assertTrue(done['complete_test_only'])
        self.assertEqual(self.db.create_fixture(jid)['counts']['VERIFIED'],3)

if __name__=='__main__': unittest.main()