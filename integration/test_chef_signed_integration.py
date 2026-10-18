"""Synthetic signed Chef receipt -> existing SQL Mi Mundo thread API contract."""
import copy
import secrets
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from chef_thread import Store, create_app, metadata, threads, messages
from chef_signed_bridge import (
    ACKED, REPLIED, STAGED, TEST_REPLY, SignedChefBridge, fixture_receipt,
    sha, synthetic_sign,
)

USER_TOKEN='synthetic-ui-'+'u'*40
ACTOR_TOKEN='synthetic-actor-'+'a'*40
KEY=b'fixture-secret-test-not-for-production-0123456789abcdef'
USER={'Authorization':'Bearer '+USER_TOKEN}
ACTOR={'Authorization':'Bearer '+ACTOR_TOKEN}


class ChefSignedIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db_url='sqlite:///'+str(Path(self.tmp.name)/'chef.sqlite3')
        self.app=create_app(self.db_url,USER_TOKEN,actor_key=KEY,actor_token=ACTOR_TOKEN)
        self.client=TestClient(self.app)
        self.client.__enter__()
        created=self.client.post('/v1/chef-demo/threads',headers=USER)
        self.assertEqual(created.status_code,201)
        self.thread=created.json()['thread_id']
        self.source_id=str(uuid.uuid4())
        self.origin=str(uuid.uuid4())
        out=self.client.post(f'/v1/chef-demo/threads/{self.thread}/messages',headers=USER,
            json={'source_id':self.source_id,'body':'SYNTHETIC: 10 people for a barbecue'})
        self.assertEqual(out.status_code,200)
        self.user_message=out.json()['messages'][0]['message_id']

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.tmp.cleanup()

    def stage(self,**overrides):
        body={'origin_id':self.origin,'user_message_id':self.user_message}
        body.update(overrides)
        return self.client.post(f'/v1/chef-demo/threads/{self.thread}/bridge/stage',headers=USER,json=body)

    def sign(self,delivery,kind,*,now=None):
        now=int(time.time()) if now is None else now
        return synthetic_sign(fixture_receipt(delivery,kind,now),KEY)

    def receipt(self,delivery,kind,envelope=None,auth=ACTOR):
        return self.client.post('/v1/chef-fixture/actor/receipt',headers=auth,
            json={'delivery_id':delivery['delivery_id'],'envelope':envelope or self.sign(delivery,kind)})

    def test_bridged_message_is_not_replied_to_by_legacy_simulator(self):
        d=self.stage().json()
        first=self.client.get(f'/v1/chef-demo/threads/{self.thread}',headers=USER).json()
        self.assertEqual(first['messages'][0]['delivery_state'],'BRIDGE_LOCAL_STAGED_NOT_POST_OFFICE')
        simulated=self.client.post(f'/v1/chef-demo/threads/{self.thread}/simulate-response',headers=USER)
        self.assertEqual(simulated.status_code,200)
        self.assertEqual(len(simulated.json()['messages']),1)
        self.assertEqual(self.receipt(d,'ACK').status_code,200)
        acked=self.client.get(f'/v1/chef-demo/threads/{self.thread}',headers=USER).json()
        self.assertEqual(acked['messages'][0]['delivery_state'],'SIGNED_SYNTHETIC_ACK_NOT_POST_OFFICE')
        self.assertEqual(self.receipt(d,'RESULT').status_code,200)
        final=self.client.post(f'/v1/chef-demo/threads/{self.thread}/simulate-response',headers=USER).json()
        self.assertEqual(len(final['messages']),2)
        self.assertEqual(final['messages'][0]['delivery_state'],'SIGNED_SYNTHETIC_REPLY_NOT_POST_OFFICE')
        self.assertEqual(final['messages'][1]['sender'],'CHEF_SIGNED_FIXTURE')

    def test_source_is_existing_sql_message_not_second_inbox(self):
        r=self.stage()
        self.assertEqual(r.status_code,200,r.text)
        d=r.json()
        self.assertEqual(d['state'],STAGED)
        self.assertEqual(d['source_sha256'],sha('SYNTHETIC: 10 people for a barbecue'))
        self.assertEqual(d['user_message_id'],self.user_message)
        self.assertEqual(len(self.client.get(f'/v1/chef-demo/threads/{self.thread}',headers=USER).json()['messages']),1)
        self.assertFalse(self.client.get('/healthz').json()['post_office_connected'])

    def test_verified_ack_then_signed_result_projects_into_original_thread(self):
        d=self.stage().json()
        ack=self.receipt(d,'ACK')
        self.assertEqual(ack.status_code,200,ack.text)
        self.assertEqual(ack.json()['state'],ACKED)
        result=self.receipt(d,'RESULT')
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['state'],REPLIED)
        v=self.client.get(f'/v1/chef-demo/threads/{self.thread}',headers=USER).json()
        self.assertEqual(len(v['messages']),2)
        chef=v['messages'][1]
        self.assertEqual(chef['sender'],'CHEF_SIGNED_FIXTURE')
        self.assertEqual(chef['body'],TEST_REPLY)
        self.assertEqual(chef['reply_to'],self.user_message)
        self.assertEqual(chef['delivery_state'],'SIGNED_SYNTHETIC_RESULT_NOT_POST_OFFICE')
        self.assertEqual(v['mode'],'SYNTHETIC_SCRIPTED_REVIEW')

    def test_receipt_must_be_signed_by_separate_actor(self):
        d=self.stage().json()
        r=self.receipt(d,'ACK',auth=USER)
        self.assertEqual(r.status_code,401)
        self.assertEqual(self.receipt(d,'ACK',auth={}).status_code,401)
        self.assertEqual(self.client.get(f'/v1/chef-demo/threads/{self.thread}/bridge',headers=ACTOR).status_code,401)
        self.assertEqual(self.client.get(f'/v1/chef-demo/threads/{self.thread}/bridge',headers=USER).json()['deliveries'][0]['state'],STAGED)

    def test_forged_actor_signature_refused(self):
        d=self.stage().json()
        fake=synthetic_sign(fixture_receipt(d,'ACK',int(time.time())),secrets.token_bytes(40))
        self.assertEqual(self.receipt(d,'ACK',fake).status_code,403)
        self.assertEqual(len(self.client.get(f'/v1/chef-demo/threads/{self.thread}',headers=USER).json()['messages']),1)

    def test_wrong_origin_bound_receipt_refused(self):
        d=self.stage().json();e=self.sign(d,'ACK')
        e['receipt']['origin']=str(uuid.uuid4())
        e=synthetic_sign(e['receipt'],KEY)
        self.assertEqual(self.receipt(d,'ACK',e).status_code,403)

    def test_wrong_actor_and_wrong_department_refused_even_valid_signature(self):
        d=self.stage().json()
        for field,value in (('actor','bad-actor'),('department','TI-TRADING')):
            with self.subTest(field=field):
                envelope=self.sign(d,'ACK')
                envelope['receipt'][field]=value
                envelope=synthetic_sign(envelope['receipt'],KEY)
                self.assertEqual(self.receipt(d,'ACK',envelope).status_code,403)

    def test_expired_and_non_uuid_nonce_refused(self):
        d=self.stage().json()
        old=self.sign(d,'ACK',now=int(time.time())-310)
        self.assertEqual(self.receipt(d,'ACK',old).status_code,403)
        wrong=self.sign(d,'ACK')
        wrong['receipt']['nonce']='not-a-uuid'
        wrong=synthetic_sign(wrong['receipt'],KEY)
        self.assertEqual(self.receipt(d,'ACK',wrong).status_code,403)

    def test_result_cannot_appear_without_ack(self):
        d=self.stage().json()
        self.assertEqual(self.receipt(d,'RESULT').status_code,403)
        v=self.client.get(f'/v1/chef-demo/threads/{self.thread}',headers=USER).json()
        self.assertEqual(len(v['messages']),1)

    def test_replay_identical_ack_and_result_does_not_duplicate(self):
        d=self.stage().json();ack=self.sign(d,'ACK');result=self.sign(d,'RESULT')
        self.assertEqual(self.receipt(d,'ACK',ack).status_code,200)
        self.assertEqual(self.receipt(d,'ACK',ack).status_code,200)
        self.assertEqual(self.receipt(d,'RESULT',result).status_code,200)
        self.assertEqual(self.receipt(d,'RESULT',result).status_code,200)
        self.assertEqual(len(self.client.get(f'/v1/chef-demo/threads/{self.thread}',headers=USER).json()['messages']),2)

    def test_changed_ack_nonce_on_replay_is_conflict(self):
        d=self.stage().json();self.assertEqual(self.receipt(d,'ACK').status_code,200)
        self.assertEqual(self.receipt(d,'ACK').status_code,409)

    def test_stage_same_origin_idempotent_new_origin_conflicts(self):
        first=self.stage().json()
        second=self.stage().json()
        self.assertEqual(first['delivery_id'],second['delivery_id'])
        self.assertEqual(self.stage(origin_id=str(uuid.uuid4())).status_code,409)

    def test_cannot_stage_nonsynthetic_message(self):
        sid=str(uuid.uuid4())
        r=self.client.post(f'/v1/chef-demo/threads/{self.thread}/messages',headers=USER,
            json={'source_id':sid,'body':'real personal info not for fixture'})
        user=[x for x in r.json()['messages'] if x['source_id']==sid][0]
        self.assertEqual(self.stage(user_message_id=user['message_id']).status_code,403)

    def test_wrong_source_message_and_wrong_thread_not_accepted(self):
        self.assertEqual(self.stage(user_message_id=str(uuid.uuid4())).status_code,404)
        t=str(uuid.uuid4())
        r=self.client.post(f'/v1/chef-demo/threads/{t}/bridge/stage',headers=USER,
            json={'origin_id':self.origin,'user_message_id':self.user_message})
        self.assertEqual(r.status_code,404)

    def test_restart_preserves_signed_projection_and_repeated_receipts(self):
        d=self.stage().json();ack=self.sign(d,'ACK');result=self.sign(d,'RESULT')
        self.assertEqual(self.receipt(d,'ACK',ack).status_code,200)
        self.assertEqual(self.receipt(d,'RESULT',result).status_code,200)
        self.client.__exit__(None,None,None)
        self.app=create_app(self.db_url,USER_TOKEN,actor_key=KEY,actor_token=ACTOR_TOKEN)
        self.client=TestClient(self.app);self.client.__enter__()
        self.assertEqual(self.receipt(d,'ACK',ack).status_code,200)
        self.assertEqual(self.receipt(d,'RESULT',result).status_code,200)
        t=self.client.get(f'/v1/chef-demo/threads/{self.thread}',headers=USER).json()
        self.assertEqual(len(t['messages']),2)
        self.assertEqual(t['messages'][1]['reply_to'],self.user_message)
        self.assertEqual(len(self.client.get(f'/v1/chef-demo/threads/{self.thread}/bridge',headers=USER).json()['deliveries']),1)

    def test_no_secret_in_public_health_or_html(self):
        h=self.client.get('/healthz').json()
        self.assertFalse(h['real_chef_connected'])
        self.assertTrue(h['signed_fixture_adapter'])
        page=self.client.get('/chef-demo').text
        self.assertNotIn(ACTOR_TOKEN,page)
        self.assertNotIn(USER_TOKEN,page)
        self.assertNotIn(KEY.decode(),page)

    def test_off_by_default_no_actor_routes(self):
        app=create_app('sqlite:///'+str(Path(self.tmp.name)/'separate.sqlite3'),USER_TOKEN)
        with TestClient(app) as client:
            self.assertFalse(client.get('/healthz').json()['signed_fixture_adapter'])
            self.assertEqual(client.post('/v1/chef-fixture/actor/receipt').status_code,404)

    def test_staging_duplicate_source_from_user_is_single_delivery(self):
        self.stage()
        r=self.client.post(f'/v1/chef-demo/threads/{self.thread}/messages',headers=USER,
            json={'source_id':self.source_id,'body':'SYNTHETIC: 10 people for a barbecue'})
        self.assertEqual(r.status_code,200)
        self.assertEqual(self.stage().status_code,200)
        self.assertEqual(len(self.client.get(f'/v1/chef-demo/threads/{self.thread}/bridge',headers=USER).json()['deliveries']),1)

if __name__=='__main__':unittest.main()