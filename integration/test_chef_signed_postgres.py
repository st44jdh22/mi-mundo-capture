"""Disposable-CI PostgreSQL proof; skipped locally unless MI_MUNDO_CI_PG_URL set."""
import os
import secrets
import time
import unittest
import uuid

from fastapi.testclient import TestClient
from chef_thread import create_app
from chef_signed_bridge import TEST_REPLY, fixture_receipt, synthetic_sign


@unittest.skipUnless(os.environ.get('MI_MUNDO_CI_PG_URL'), 'requires disposable PostgreSQL CI')
class SignedChefPostgresContract(unittest.TestCase):
    def test_sign_ack_reply_reopen_and_exactly_once(self):
        url=os.environ['MI_MUNDO_CI_PG_URL']
        token=secrets.token_urlsafe(32)
        actor_token=secrets.token_urlsafe(32)
        key=secrets.token_bytes(40)
        uh={'Authorization':'Bearer '+token}
        ah={'Authorization':'Bearer '+actor_token}
        def app():return create_app(url,token,actor_key=key,actor_token=actor_token)
        with TestClient(app()) as client:
            r=client.post('/v1/chef-demo/threads',headers=uh)
            self.assertEqual(r.status_code,201)
            tid=r.json()['thread_id']
            sent=client.post(f'/v1/chef-demo/threads/{tid}/messages',headers=uh,json={
                'source_id':str(uuid.uuid4()),'body':'SYNTHETIC: 10 people for a barbecue'})
            self.assertEqual(sent.status_code,200)
            mid=sent.json()['messages'][0]['message_id']
            result=client.post(f'/v1/chef-demo/threads/{tid}/bridge/stage',headers=uh,json={
                'origin_id':str(uuid.uuid4()),'user_message_id':mid})
            self.assertEqual(result.status_code,200,result.text)
            delivery=result.json()
            envelopes=[synthetic_sign(fixture_receipt(delivery,kind,int(time.time())),key)
                       for kind in ('ACK','RESULT')]
            for e in envelopes:
                response=client.post('/v1/chef-fixture/actor/receipt',headers=ah,json={
                    'delivery_id':delivery['delivery_id'],'envelope':e})
                self.assertEqual(response.status_code,200,response.text)
        with TestClient(app()) as client:
            for e in envelopes:
                response=client.post('/v1/chef-fixture/actor/receipt',headers=ah,json={
                    'delivery_id':delivery['delivery_id'],'envelope':e})
                self.assertEqual(response.status_code,200,response.text)
            thread=client.get(f'/v1/chef-demo/threads/{tid}',headers=uh).json()
            self.assertEqual(len(thread['messages']),2)
            self.assertEqual(thread['messages'][1]['body'],TEST_REPLY)
            self.assertEqual(thread['messages'][1]['reply_to'],mid)
            self.assertFalse(client.get('/healthz').json()['post_office_connected'])

if __name__=='__main__':unittest.main()