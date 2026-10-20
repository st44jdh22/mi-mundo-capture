"""Automatic local Chef vertical slice over the existing durable queue and Inbox.

No background worker starts on import. One explicitly started bounded pump uses
FilingService leases/retries/outbox, not a replacement delivery master.
"""
import json
import time
import uuid
from urllib.parse import urlparse
import httpx
from sqlalchemy import select

from chef_thread import Store, metadata, threads, messages
from chef_signed_bridge import SignedChefBridge, STAGED, ACKED, REPLIED
from postoffice_dispatch import SyntheticDispatchOutbox
from filing.service import FilingService, jobs
from filing.storage import LocalSyntheticObjects
from filing.adapters import (SyntheticRecordAdapter, PolicyBlock, PermissionFailure,
                             Conflict, TransientFailure)
from chef_receiver import ACTION, target_for

BINDINGS = ('delivery_id','thread_id','owner_id','origin_id','user_message_id','source_sha256')

class ReceiverTransport:
    def __init__(self, client, delivery_token, read_token, delivery, source, bridge):
        self.client, self.delivery_token, self.read_token = client, delivery_token, read_token
        self.delivery, self.source, self.bridge = delivery, source, bridge

    def request(self, method, path, **kwargs):
        token = self.read_token if method == 'GET' else self.delivery_token
        try:
            response = self.client.request(method, path,
                headers={'Authorization':'Bearer '+token}, **kwargs)
        except httpx.TimeoutException as error:
            raise TimeoutError('synthetic_receiver_timeout') from error
        except httpx.TransportError as error:
            raise TransientFailure('synthetic_receiver_unavailable') from error
        if response.status_code == 401:
            raise PermissionFailure('receiver_auth_denied')
        if response.status_code == 403:
            raise PolicyBlock('receiver_stop_or_policy')
        if response.status_code == 409:
            raise Conflict('receiver_identity_conflict')
        if response.status_code != 200:
            raise TransientFailure('receiver_http_failure')
        return response.json()

    def packet(self, identity):
        packet = self.request('GET', '/effects/'+identity)
        if packet is not None:
            # Cryptographic bindings checked before treating any effect as observed.
            for name, kind in [('ack','ACK'), ('result','RESULT')]:
                self.bridge._verify(packet[name], self.delivery, kind, int(time.time()))
        return packet

    def find(self, identity):
        packet = self.packet(identity)
        return [] if packet is None else [dict(packet['attrs'], data=packet['data'].encode())]

    def create_if_absent(self, identity, data, attrs):
        if data.decode() != target_for(self.delivery)['value']:
            raise Conflict('action_value_not_allowlisted')
        self.request('POST', '/deliver', json={
            'delivery':{k:self.delivery[k] for k in BINDINGS},
            'source':self.source, 'target':target_for(self.delivery), 'action':ACTION})


class AutomaticChef:
    def __init__(self, root, client, delivery_token, read_token, actor_key, *, clock=time.time):
        from pathlib import Path
        self.root = Path(root)
        self.store = Store('sqlite:///'+str(self.root/'inbox_chef_test.sqlite'))
        self.bridge = SignedChefBridge(self.store, metadata, threads, messages, actor_key)
        self.queue = FilingService('sqlite:///'+str(self.root/'automatic_filing_test.sqlite'), clock=clock)
        self.queue.initialize_test_schema()
        self.objects = LocalSyntheticObjects(self.root/'objects')
        self.client, self.delivery_token, self.read_token = client, delivery_token, read_token

    def close(self):
        self.queue.close(); self.store.close()

    def stopped(self):
        with self.queue.transaction() as conn:
            return self.queue._control(conn)['stopped']

    def stop(self):
        self.queue.set_stopped(True)

    def resume_for_test(self):
        self.queue.set_stopped(False)

    def stage_pending(self):
        with self.store.engine.connect() as conn:
            pending = conn.execute(select(messages).where(messages.c.sender=='USER',
                messages.c.delivery_state=='QUEUED_SYNTHETIC')).mappings().all()
        for row in pending:
            if self.stopped():
                return
            dispatch = SyntheticDispatchOutbox(self.root/'dispatch_chef_test.sqlite')
            try:
                dispatch.prepare_from_chef_store(self.store, thread_id=row['thread_id'],
                                                user_message_id=row['message_id'])
            finally:
                dispatch.close()
            self.bridge.stage(row['thread_id'], str(uuid.uuid5(uuid.NAMESPACE_URL,
                'automatic-chef-origin:'+row['source_id'])), row['message_id'])

    def tick(self, *, hook=lambda *a: None):
        if self.stopped():
            return
        self.stage_pending()
        with self.store.engine.connect() as conn:
            deliveries = conn.execute(select(self.bridge.deliveries).where(
                self.bridge.deliveries.c.state != REPLIED)).mappings().all()
        for delivery in deliveries:
            if self.stopped():
                return
            delivery = dict(delivery)
            thread = self.store.get_thread(delivery['thread_id'])
            source = next(m['body'] for m in thread['messages']
                          if m['message_id']==delivery['user_message_id'])
            jid = str(uuid.uuid5(uuid.NAMESPACE_URL, 'automatic-chef-job:'+delivery['delivery_id']))
            target = target_for(delivery)
            target = {k:v for k,v in target.items() if k not in ('expected_sha256','size')}
            spec = dict(job_id=jid, intake_id=delivery['origin_id'], requester='synthetic-owner',
                department='FOOD-CHEF', conversation_id='synthetic-'+delivery['thread_id'],
                idempotency_key='synthetic-'+delivery['delivery_id'], instruction=source,
                source_ref='fixture://chef/'+delivery['user_message_id'],
                approval_ref='synthetic-local-only', authoritative_record='synthetic-chef-inbox',
                targets=[target])
            self.queue.submit(spec, ('SYNTHETIC\n'+source).encode(), self.objects)
            transport = ReceiverTransport(self.client, self.delivery_token, self.read_token,
                                          delivery, source, self.bridge)
            self.queue.run_once(jid, 'synthetic-worker-chef', self.objects,
                {'RECORD':SyntheticRecordAdapter(transport)}, hook=hook)
        # Existing durable reporting outbox retries the same correlated Inbox return.
        for _ in range(60):
            if not self.queue.flush_reporting(InboxReturn(self)):
                break


class InboxReturn:
    def __init__(self, engine):
        self.engine = engine

    def context(self, event):
        e = self.engine
        with e.queue.engine.connect() as conn:
            job = conn.execute(select(jobs).where(jobs.c.job_id==event['job_id'])).mappings().one()
        with e.store.engine.connect() as conn:
            delivery = conn.execute(select(e.bridge.deliveries).where(
                e.bridge.deliveries.c.origin_id==job['intake_id'])).mappings().one()
        delivery = dict(delivery)
        thread = e.store.get_thread(delivery['thread_id'])
        source = next(m['body'] for m in thread['messages'] if m['message_id']==delivery['user_message_id'])
        return delivery, thread, ReceiverTransport(e.client, e.delivery_token, e.read_token,
                                                  delivery, source, e.bridge)

    def verify(self, event):
        if event['state'] != 'VERIFIED COMPLETE':
            return True  # No reply is fabricated for intermediate queue events.
        delivery, thread, _ = self.context(event)
        return delivery['state']==REPLIED and any(
            m['reply_to']==delivery['user_message_id'] and m['body']==target_for(delivery)['value']
            for m in thread['messages'])

    def publish_guarded(self, event, guard):
        delivery, _, transport = self.context(event)
        packet = transport.packet(target_for(delivery)['effect_id'])
        if packet is None or not SyntheticRecordAdapter(transport).observe(target_for(delivery)):
            raise Conflict('verified_receiver_effect_missing')
        guard()
        if delivery['state']==STAGED:
            self.engine.bridge.receive(delivery['delivery_id'],packet['ack'],'ACK',int(time.time()))
        guard()
        self.engine.bridge.receive(delivery['delivery_id'],packet['result'],'RESULT',int(time.time()))



def loopback_client(url):
    parsed = urlparse(url)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.username or parsed.password:
        raise PermissionError('Only an explicitly configured loopback receiver is permitted')
    return httpx.Client(base_url=url, timeout=2, trust_env=False, follow_redirects=False)
