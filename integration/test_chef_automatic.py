"""Local synthetic integration/fault acceptance. No model calls or cloud services."""
import asyncio
import json
import secrets
import sqlite3
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
import httpx
from sqlalchemy import select

from chef_automatic import AutomaticChef, ReceiverTransport, InboxReturn, loopback_client
from chef_receiver import create_receiver, target_for, ACTION
from chef_signed_bridge import REPLIED, STAGED
from chef_agents_adapter import AgentsPlanner, Plan
from filing.service import jobs, outbox, StopRequested

class Crash(BaseException):pass

class AutomaticTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.key=secrets.token_bytes(40)
        self.send,self.read=[secrets.token_urlsafe(40) for _ in range(2)]
        self.app=create_receiver(self.root/'actor_chef_receiver_test.sqlite',self.key,self.send,self.read)
        self.app.state.receiver.stop(False)
        self.client=TestClient(self.app)
        self.now=int(time.time())
        self.e=AutomaticChef(self.root,self.client,self.send,self.read,self.key,clock=lambda:self.now)
        self.e.resume_for_test()

    def tearDown(self):
        self.e.close();self.client.close();self.tmp.cleanup()

    def submit(self, tid=None):
        tid=tid or self.e.store.new_thread()
        self.e.store.send(tid,str(uuid.uuid4()),'SYNTHETIC: prepare a review question')
        return tid

    def rows(self,table):
        with self.e.queue.engine.connect() as conn:
            return [dict(x) for x in conn.execute(select(table)).mappings()]

    def count(self,table):
        with sqlite3.connect(self.root/'actor_chef_receiver_test.sqlite') as db:
            return db.execute('SELECT count(*) FROM '+table).fetchone()[0]

    def reopen(self):
        self.e.close()
        self.e=AutomaticChef(self.root,self.client,self.send,self.read,self.key,clock=lambda:self.now)

    def test_two_overlapping_same_thread_automatic_once(self):
        tid=self.submit();self.submit(tid)
        self.e.tick();self.e.tick()
        view=self.e.store.get_thread(tid)
        users={m['message_id'] for m in view['messages'] if m['sender']=='USER'}
        replies=[m for m in view['messages'] if m['sender']=='CHEF_SIGNED_FIXTURE']
        self.assertEqual({m['reply_to'] for m in replies},users)
        self.assertEqual(self.count('effects'),2)
        self.assertEqual(self.count('receipts'),2)
        self.assertTrue(all(j['state']=='VERIFIED COMPLETE' for j in self.rows(jobs)))
        self.assertTrue(all(x['state']=='DELIVERED' for x in self.rows(outbox)))

    def test_two_overlapping_different_threads_do_not_cross_reply(self):
        a,b=self.submit(),self.submit();self.e.tick()
        for tid in (a,b):
            ms=self.e.store.get_thread(tid)['messages']
            self.assertEqual(len(ms),2);self.assertEqual(ms[1]['reply_to'],ms[0]['message_id'])

    def test_duplicate_delivery_has_one_ack_one_effect_and_one_reply(self):
        tid=self.submit();self.e.tick()
        with sqlite3.connect(self.root/'actor_chef_receiver_test.sqlite') as db:
            package=json.loads(db.execute('SELECT package FROM receipts').fetchone()[0])
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda _:self.client.post('/deliver',json=package,
                headers={'Authorization':'Bearer '+self.send}),range(2)))
        self.assertTrue(all(r.status_code==200 for r in results))
        self.assertEqual(results[0].json()['ack'],results[1].json()['ack'])
        self.e.tick();self.assertEqual(self.count('effects'),1)
        self.assertEqual(len(self.e.store.get_thread(tid)['messages']),2)

    def test_stop_before_dispatch_zero_effects(self):
        self.submit();self.e.stop();self.e.tick();self.assertEqual(self.count('effects'),0)
        self.assertEqual(self.rows(jobs),[])

    def test_stop_after_claim_before_unsent_effect(self):
        self.submit()
        self.e.tick(hook=lambda point,claim:self.e.stop() if point=='before_write' else None)
        self.assertEqual(self.count('effects'),0)
        self.assertEqual(self.rows(jobs)[0]['state'],'MANUAL REVIEW')

    def test_receiver_policy_stop_is_not_retried(self):
        tid=self.submit();self.app.state.receiver.stop(True);self.e.tick()
        self.assertEqual(self.rows(jobs)[0]['state'],'BLOCKED')
        self.assertEqual(self.count('effects'),0);self.assertEqual(len(self.e.store.get_thread(tid)['messages']),1)
        self.app.state.receiver.stop(False);self.e.tick()
        self.assertEqual(self.count('effects'),0)

    def test_timeout_before_delivery_bounded_three_attempts(self):
        self.submit()
        original=self.client.request
        def timeout(method,path,**kwargs):
            if method=='POST':raise httpx.ReadTimeout('synthetic timeout')
            return original(method,path,**kwargs)
        with patch.object(self.client,'request',side_effect=timeout):
            for _ in range(5):self.e.tick();self.now+=120
        self.assertEqual(self.rows(jobs)[0]['attempts'],3)
        self.assertEqual(self.rows(jobs)[0]['state'],'MANUAL REVIEW')
        self.assertEqual(self.count('effects'),0)

    def test_lost_response_after_effect_reopens_without_repeat(self):
        tid=self.submit();original=self.client.request
        def lost(method,path,**kwargs):
            result=original(method,path,**kwargs)
            if method=='POST':raise httpx.ReadTimeout('synthetic reply lost after commit')
            return result
        with patch.object(self.client,'request',side_effect=lost):self.e.tick()
        self.assertEqual(self.count('effects'),1)
        self.assertEqual(len(self.e.store.get_thread(tid)['messages']),1)
        self.reopen();self.now+=61;self.e.tick()
        self.assertEqual(self.count('effects'),1)
        self.assertEqual(len(self.e.store.get_thread(tid)['messages']),2)

    def test_crash_after_remote_effect_before_queue_checkpoint(self):
        tid=self.submit()
        def crash(point,claim):
            if point=='after_write':raise Crash()
        with self.assertRaises(Crash):self.e.tick(hook=crash)
        self.assertEqual(self.count('effects'),1)
        self.reopen();self.now+=61;self.e.tick()
        self.assertEqual(self.count('effects'),1)
        self.assertEqual(len(self.e.store.get_thread(tid)['messages']),2)

    def test_receiver_crash_after_ack_recovers_same_ack(self):
        self.submit();self.e.stage_pending()
        with self.e.store.engine.connect() as conn:
            tid=conn.execute(select(self.e.bridge.deliveries.c.thread_id)).scalar_one()
        d=self.e.bridge.thread_deliveries(tid)[0]
        package=dict(delivery={k:d[k] for k in ('delivery_id','thread_id','owner_id','origin_id','user_message_id','source_sha256')},
            target=target_for(d),source='SYNTHETIC: prepare a review question',action=ACTION)
        def crash(point):
            if point=='ack_committed':raise Crash()
        with self.assertRaises(Crash):self.app.state.receiver.deliver(package,hook=crash)
        self.assertEqual(self.count('receipts'),1);self.assertEqual(self.count('effects'),0)
        from chef_receiver import Receiver
        restarted=Receiver(self.root/'actor_chef_receiver_test.sqlite',self.key)
        restarted.deliver(package)
        self.e.tick();self.assertEqual(self.count('receipts'),1);self.assertEqual(self.count('effects'),1)

    def test_wrong_principal_cannot_deliver_or_read(self):
        self.submit();self.e.read_token=self.send;self.e.tick()
        self.assertEqual(self.rows(jobs)[0]['state'],'BLOCKED')
        self.assertEqual(self.count('receipts'),0)
        self.assertEqual(self.client.post('/deliver',json={},headers={'Authorization':'Bearer wrong'}).status_code,422)
        self.assertEqual(self.client.get('/effects/x',headers={'Authorization':'Bearer '+self.send}).status_code,401)

    def test_tampered_signed_result_does_not_reach_inbox(self):
        tid=self.submit();original=self.client.request
        def tamper(method,path,**kwargs):
            result=original(method,path,**kwargs)
            if method=='GET' and result.status_code==200 and result.json():
                packet=result.json();packet['result']['signature']='0'*64
                return httpx.Response(200,json=packet)
            return result
        with patch.object(self.client,'request',side_effect=tamper):self.e.tick()
        self.assertEqual(len(self.e.store.get_thread(tid)['messages']),1)
        self.assertEqual(self.rows(jobs)[0]['state'],'MANUAL REVIEW')

    def test_reporting_outage_restarts_without_reexecuting_action(self):
        tid=self.submit()
        with patch.object(InboxReturn,'publish_guarded',side_effect=ConnectionError('synthetic Inbox offline')):
            self.e.tick()
        self.assertEqual(self.count('effects'),1);self.assertEqual(len(self.e.store.get_thread(tid)['messages']),1)
        self.reopen();self.now+=61;self.e.tick()
        self.assertEqual(self.count('effects'),1);self.assertEqual(len(self.e.store.get_thread(tid)['messages']),2)

    def test_stop_between_ack_and_result_blocks_unsent_inbox_write(self):
        tid=self.submit();original=self.e.bridge.receive
        def stopped(did,envelope,kind,now):
            result=original(did,envelope,kind,now)
            if kind=='ACK':self.e.stop()
            return result
        with patch.object(self.e.bridge,'receive',side_effect=stopped):self.e.tick()
        self.assertEqual(len(self.e.store.get_thread(tid)['messages']),1)
        self.assertTrue(any(x['state']=='RETRY PENDING' for x in self.rows(outbox)))
        self.e.resume_for_test();self.now+=61;self.e.tick()
        self.assertEqual(len(self.e.store.get_thread(tid)['messages']),2)

    def test_default_stopped_and_loopback_only(self):
        self.e.stop();self.reopen();self.assertTrue(self.e.stopped())
        for url in ('https://example.com','http://localhost','http://127.0.0.1@evil.test'):
            with self.assertRaises(PermissionError):loopback_client(url)

class PlannerTests(unittest.TestCase):
    def test_not_approved_never_imports_or_calls_sdk(self):
        with self.assertRaises(PermissionError):AgentsPlanner('explicit-model')

    def test_bounded_no_tools_adapter_with_fake_sdk(self):
        calls=[]
        class Runner:
            @staticmethod
            async def run(agent,source,**kwargs):
                calls.append((agent,kwargs))
                class Result:final_output=Plan(action=ACTION)
                return Result()
        planner=AgentsPlanner('approved-test-model',approved=True,runner=Runner,
            agent_factory=lambda **k:k,config_factory=lambda **k:k)
        result=asyncio.run(planner.plan('SYNTHETIC: question'))
        self.assertEqual(result.action,ACTION)
        self.assertEqual(calls[0][0]['tools'],[])
        self.assertEqual(calls[0][1]['max_turns'],1)
        self.assertTrue(calls[0][1]['run_config']['tracing_disabled'])
        with self.assertRaises(PermissionError):asyncio.run(planner.plan('real data'))

class ProjectionStopTests(unittest.TestCase):
    def test_stop_between_postoffice_projection_writes(self):
        from filing.service import FilingService
        from filing.storage import LocalSyntheticObjects
        from filing.adapters import PostOfficeStatusAdapter
        from test_filing_service import Projection, specification, DATA
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            service=FilingService('sqlite:///'+str(root/'projection_filing_test.sqlite'))
            service.initialize_test_schema();service.set_stopped(False)
            service.submit(specification(),DATA,LocalSyntheticObjects(root/'objects'))
            gateway=Projection();original=gateway.upsert
            def stop_after_first(table,key,payload):
                original(table,key,payload);service.set_stopped(True)
            gateway.upsert=stop_after_first
            service.flush_reporting(PostOfficeStatusAdapter(gateway))
            self.assertEqual(len(gateway.rows),1)
            with service.engine.connect() as conn:
                pending=conn.execute(select(outbox).order_by(outbox.c.sequence)).mappings().first()
            self.assertEqual(pending['state'],'RETRY PENDING')
            service.close()
