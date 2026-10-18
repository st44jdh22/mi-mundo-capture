import sqlite3
import tempfile
import unittest
from pathlib import Path
from recovery_queue import RecoveryQueue, Destination, PolicyDenied, AuthDenied

J='synthetic-check-in-20261018'
D=[Destination('journal','digest-j','HEALTH'),
   Destination('emotion','digest-e','HEALTH'),
   Destination('narrative','digest-n','HEALTH')]

class FakeBackend:
    def __init__(self):
        self.records={}
        self.writes={}
        self.blocked=set()
        self.auth_blocked=set()
        self.timeout_after_write=set()
        self.fail_connect_once=set()
    def read(self,key):
        return self.records.get(key)
    def write(self,key,digest):
        if key in self.blocked:
            raise PolicyDenied('private fixture guard')
        if key in self.auth_blocked:
            raise AuthDenied('fixture permissions')
        if key in self.fail_connect_once:
            self.fail_connect_once.remove(key)
            raise ConnectionError('fixture offline')
        self.records[key]=digest
        self.writes[key]=self.writes.get(key,0)+1
        if key in self.timeout_after_write:
            self.timeout_after_write.remove(key)
            raise TimeoutError('lost reply after commit')

class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.dbpath=str(Path(self.tmp.name)/'recovery.db')
        self.q=RecoveryQueue(self.dbpath)
        self.fake=FakeBackend()
    def tearDown(self):
        self.q.close()
        self.tmp.cleanup()
    def start(self,ds=D):
        self.q.start(J,'source-digest','private://fixture',ds,
                     original_verified=True,now=100)

    def test_everything_verified_creates_single_resolution_event(self):
        self.start()
        x=self.q.run_once(J,self.fake,now=100)
        self.assertTrue(x['complete'])
        self.q.run_once(J,self.fake,now=200)
        self.assertEqual(self.fake.writes,{d.key:1 for d in D})
        self.assertEqual([x['event_type'] for x in self.q.notices(J)],['RESOLVED'])

    def test_p0_two_verified_one_policy_blocked_persists_without_retry(self):
        self.start()
        self.fake.blocked.add('narrative')
        x=self.q.run_once(J,self.fake,now=100)
        self.assertEqual((x['counts']['VERIFIED'],x['counts']['POLICY_BLOCKED']),(2,1))
        self.q.close()
        self.q=RecoveryQueue(self.dbpath)
        x=self.q.run_once(J,self.fake,now=600)
        self.assertFalse(x['complete'])
        self.assertEqual(self.fake.writes,{'emotion':1,'journal':1})
        self.assertEqual(self.q.target(J,'narrative')['attempts'],1)
        notices=self.q.notices(J)
        self.assertEqual(len(notices),1)
        self.assertEqual(notices[0]['event_type'],'ATTENTION')
        self.assertNotIn('narrative',notices[0]['generic_text'])

    def test_review_resumes_only_blocked_destination_after_safety_clearance(self):
        self.start()
        self.fake.blocked.add('narrative')
        self.q.run_once(J,self.fake,now=100)
        self.fake.blocked.remove('narrative')
        self.q.run_once(J,self.fake,now=500)
        self.assertEqual(self.q.target(J,'narrative')['state'],'POLICY_BLOCKED')
        with self.assertRaises(PermissionError):
            self.q.release_after_review(J,'narrative',authorised=False,
              policy_permits=True,reason='fixture review',now=501)
        self.q.release_after_review(J,'narrative',authorised=True,
          policy_permits=True,reason='fixture review cleared',now=501)
        x=self.q.run_once(J,self.fake,now=502)
        self.assertTrue(x['complete'])
        self.assertEqual(self.fake.writes,{'emotion':1,'journal':1,'narrative':1})
        self.assertEqual({e['event_type'] for e in self.q.notices(J)},
                         {'ATTENTION','RESOLVED'})

    def test_lost_reply_read_first_avoids_second_write(self):
        self.start([D[0]])
        self.fake.timeout_after_write.add('journal')
        x=self.q.run_once(J,self.fake,now=100)
        self.assertEqual(x['counts']['RETRY_WAIT'],1)
        self.assertEqual(self.q.target(J,'journal')['next_attempt_at'],130)
        self.q.run_once(J,self.fake,now=110)
        self.assertEqual(self.fake.writes['journal'],1)
        x=self.q.run_once(J,self.fake,now=130)
        self.assertTrue(x['complete'])
        self.assertEqual(self.fake.writes['journal'],1)

    def test_offline_retry_schedules_and_attention_is_deduped(self):
        self.start([D[0]])
        self.fake.fail_connect_once.add('journal')
        self.q.run_once(J,self.fake,now=100)
        self.assertTrue(self.q.attention_due(J,now=1100))
        self.assertTrue(self.q.attention_due(J,now=1101))
        self.assertEqual(len(self.q.notices(J)),1)
        self.q.run_once(J,self.fake,now=1150)
        self.assertTrue(self.q.status(J)['complete'])
        self.assertEqual(len(self.q.notices(J)),2)

    def test_conflict_never_overwrites(self):
        self.start([D[0]])
        self.fake.records['journal']='other-payload'
        x=self.q.run_once(J,self.fake,now=100)
        self.assertEqual(x['counts']['CONFLICT'],1)
        self.assertEqual(self.fake.writes,{})
        self.q.run_once(J,self.fake,now=999)
        self.assertEqual(len(self.q.notices(J)),1)

    def test_auth_failure_is_hold_not_repeat(self):
        self.start([D[0]])
        self.fake.auth_blocked.add('journal')
        self.q.run_once(J,self.fake,now=100)
        self.q.run_once(J,self.fake,now=500)
        self.assertEqual(self.q.target(J,'journal')['attempts'],1)
        self.assertEqual(self.q.status(J)['counts']['AUTH_BLOCKED'],1)

    def test_idempotent_input_and_changed_source_rejected(self):
        self.start()
        self.start()
        with self.assertRaises(ValueError):
            self.q.start(J,'different-source','private://fixture',D,
                  original_verified=True,now=110)
        with self.assertRaises(ValueError):
            self.q.start(J,'source-digest','private://fixture',
                   [Destination('journal','different-digest')],
                   original_verified=True,now=110)

    def test_unverified_original_never_enqueued(self):
        with self.assertRaises(ValueError):
            self.q.start(J,'source-digest','private://fixture',D,
                         original_verified=False,now=100)
        with self.assertRaises(ValueError):
            self.q.status(J)

    def test_noncompliant_review_never_unblocks(self):
        self.start([D[0]])
        self.fake.blocked.add('journal')
        self.q.run_once(J,self.fake,now=100)
        with self.assertRaises(PermissionError):
            self.q.release_after_review(J,'journal',authorised=True,
                       policy_permits=False,reason='request unsafe',now=101)
        self.assertEqual(self.q.target(J,'journal')['state'],'POLICY_BLOCKED')

    def test_sqlite_restore_preserves_state_and_pending_notice(self):
        self.start()
        self.fake.blocked.add('narrative')
        self.q.run_once(J,self.fake,now=100)
        self.q.close()
        self.q=RecoveryQueue(self.dbpath)
        snapshot=str(Path(self.tmp.name)/'recover.db')
        with self.q.db:
            restored=sqlite3.connect(snapshot)
            self.q.db.backup(restored)
            restored.close()
        self.q.close()
        self.q=RecoveryQueue(snapshot)
        self.assertEqual(self.q.status(J)['counts']['POLICY_BLOCKED'],1)
        self.assertEqual(len(self.q.notices(J)),1)
        self.assertEqual(self.q.target(J,'journal')['state'],'VERIFIED')

if __name__=='__main__':
    unittest.main()