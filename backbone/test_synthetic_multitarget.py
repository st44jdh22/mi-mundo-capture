import tempfile
import unittest
from pathlib import Path
from synthetic_multitarget import SyntheticReconciler, FixtureDrive, Target

JOB = 'synthetic-20261018-checkin'
TARGETS = [
    Target('private_daily_journal', {'date':'2026-10-17','note':'synthetic reflection'}, 'HEALTH'),
    Target('private_emotional_checkin', {'date':'2026-10-17','mood':'synthetic'}, 'HEALTH'),
    Target('kitchen_consumed', {'event':'KIT-029','item':'nuts','mass':'unknown'}),
    Target('kitchen_equipment', {'event':'KIT-030','status':'assembly incomplete'}),
    Target('post_office_food_queue', {'event':'MSG-SYNTHETIC','state':'QUEUED'}),
]

class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'fixture.db')
        self.db = SyntheticReconciler(self.path)
        self.fake = FixtureDrive()

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_five_updates_readback(self):
        result = self.db.run(JOB, TARGETS, self.fake, original_verified=True)
        self.assertTrue(result['all_verified'])
        self.assertEqual(result['counts']['VERIFIED'], 5)
        self.assertFalse(result['post_office_acknowledged'])
        self.assertEqual(len(self.fake.write_count), 5)
        self.assertGreaterEqual(result['total_ms'], 0)

    def test_resume_partial_failure_no_duplicate_writes(self):
        self.fake.block_once.add('kitchen_consumed')
        first = self.db.run(JOB, TARGETS, self.fake, original_verified=True)
        self.assertFalse(first['all_verified'])
        self.assertEqual(first['counts'], {'UNCONFIRMED':1, 'VERIFIED':4})
        self.db.close()
        self.db = SyntheticReconciler(self.path)
        second = self.db.run(JOB, TARGETS, self.fake, original_verified=True)
        self.assertTrue(second['all_verified'])
        self.assertEqual(self.fake.write_count, {t.key:1 for t in TARGETS})

    def test_ambiguous_timeout_must_readback_before_retry(self):
        self.fake.lose_reply_once.add('kitchen_consumed')
        first = self.db.run(JOB, TARGETS, self.fake, original_verified=True)
        self.assertFalse(first['all_verified'])
        second = self.db.run(JOB, TARGETS, self.fake, original_verified=True)
        self.assertTrue(second['all_verified'])
        self.assertEqual(self.fake.write_count['kitchen_consumed'], 1)

    def test_same_target_changed_content_blocked(self):
        self.db.apply(JOB,TARGETS[0],self.fake,original_verified=True)
        changed = Target(TARGETS[0].key,{'different':'meaning'},'HEALTH')
        with self.assertRaisesRegex(ValueError,'changed content'):
            self.db.apply(JOB,changed,self.fake,original_verified=True)

    def test_no_original_blocks_writes(self):
        with self.assertRaisesRegex(RuntimeError,'original not preserved'):
            self.db.run(JOB,TARGETS,self.fake,original_verified=False)
        self.assertEqual(self.fake.write_count,{})

    def test_conflicting_prior_target_does_not_overwrite(self):
        self.fake.records[TARGETS[0].key]={'payload':{'other':'value'},'digest':'f'*64}
        x=self.db.apply(JOB,TARGETS[0],self.fake,original_verified=True)
        self.assertEqual(x['status'],'CONFLICT')
        self.assertEqual(self.fake.records[TARGETS[0].key]['digest'],'f'*64)

    def test_duplicate_keys_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicate target'):
            self.db.run(JOB,[TARGETS[0],TARGETS[0]],self.fake,original_verified=True)

    def test_repeat_five_verified_zero_additional_writes(self):
        self.db.run(JOB,TARGETS,self.fake,original_verified=True)
        prior=dict(self.fake.write_count)
        result=self.db.run(JOB,TARGETS,self.fake,original_verified=True)
        self.assertTrue(result['all_verified'])
        self.assertEqual(prior,self.fake.write_count)

if __name__=='__main__':
    unittest.main()
