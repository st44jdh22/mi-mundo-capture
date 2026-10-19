"""One-click isolated signed Chef demonstration, no external services/data."""
import json
import multiprocessing
import secrets
import tempfile
import time
import uuid
from pathlib import Path
from fastapi.testclient import TestClient

from chef_thread import create_app
from chef_signed_bridge import fixture_receipt, synthetic_sign

MARKER='SYNTHETIC: 10 people for a barbecue'


def fixture_actor(conn, package, key):
    """Separate process signs two allowlisted synthetic protocol messages."""
    try:
        if package['source'] != MARKER or package['department'] != 'FOOD-CHEF':
            conn.send({'error':'scope_denied'})
            return
        now=int(time.time())
        conn.send({'envelopes':[
            synthetic_sign(fixture_receipt(package['delivery'],kind,now),key)
            for kind in ('ACK','RESULT')
        ]})
    finally:
        conn.close()


def run():
    with tempfile.TemporaryDirectory() as d:
        url='sqlite:///'+str(Path(d)/'signed-fixture.sqlite3')
        user_key=secrets.token_urlsafe(40)
        actor_token=secrets.token_urlsafe(40)
        signing_key=secrets.token_bytes(40)
        uh={'Authorization':'Bearer '+user_key}
        ah={'Authorization':'Bearer '+actor_token}
        with TestClient(create_app(url,user_key,actor_key=signing_key,actor_token=actor_token)) as cli:
            thread=cli.post('/v1/chef-demo/threads',headers=uh).json()['thread_id']
            sent=cli.post(f'/v1/chef-demo/threads/{thread}/messages',headers=uh,json={
                'source_id':str(uuid.uuid4()),'body':MARKER}).json()
            message_id=sent['messages'][0]['message_id']
            staged=cli.post(f'/v1/chef-demo/threads/{thread}/bridge/stage',headers=uh,json={
                'origin_id':str(uuid.uuid4()), 'user_message_id':message_id})
            assert staged.status_code==200,staged.text
            delivery=staged.json()
            parent,child=multiprocessing.Pipe(duplex=False)
            worker=multiprocessing.Process(target=fixture_actor,args=(child,{
                'source':MARKER,'department':'FOOD-CHEF','delivery':delivery},signing_key))
            worker.start();child.close()
            try:
                if not parent.poll(5):raise RuntimeError('fixture actor did not reply in time')
                packet=parent.recv()
            finally:
                parent.close();worker.join(5)
                if worker.is_alive():worker.terminate();worker.join(5)
            if worker.exitcode!=0 or 'envelopes' not in packet:
                raise RuntimeError('fixture actor denied or failed')
            states=[delivery['state']]
            for envelope in packet['envelopes']:
                received=cli.post('/v1/chef-fixture/actor/receipt',headers=ah,json={
                    'delivery_id':delivery['delivery_id'],'envelope':envelope})
                assert received.status_code==200,received.text
                states.append(received.json()['state'])
            rendered=cli.get(f'/v1/chef-demo/threads/{thread}',headers=uh).json()
            assert len(rendered['messages'])==2
            assert rendered['messages'][1]['reply_to']==message_id
            assert rendered['messages'][1]['sender']=='CHEF_SIGNED_FIXTURE'
            result={
                'mode':'LOCAL SYNTHETIC — NOT THE INSTITUTIONAL POST OFFICE',
                'separate_fixture_actor_process':True,
                'same_original_sql_thread':True,
                'states':states,
                'message_count':len(rendered['messages']),
                'reply_sender':rendered['messages'][1]['sender'],
                'reply_text':rendered['messages'][1]['body'],
                'institutional_post_office_connected':False,
            }
        # Verify persisted conversation by reopening server connection.
        with TestClient(create_app(url,user_key,actor_key=signing_key,actor_token=actor_token)) as cli:
            persisted=cli.get(f'/v1/chef-demo/threads/{thread}',headers=uh).json()
            result['reply_survived_server_reopen']=len(persisted['messages'])==2
        print(json.dumps(result,indent=2))

if __name__=='__main__':run()