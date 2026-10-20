"""Executable zero-model-call automatic HTTP round trip; disposable local state."""
import json
import multiprocessing
import secrets
import socket
import sqlite3
import tempfile
import threading
import time
import uuid
from pathlib import Path
from fastapi.testclient import TestClient
from chef_thread import create_app
from chef_receiver import create_receiver
from chef_automatic import AutomaticChef, loopback_client


def receiver_process(path, key, delivery_token, read_token, ready):
    import uvicorn
    app = create_receiver(path,key,delivery_token,read_token)
    app.state.receiver.stop(False)  # Explicit attended disposable test activation.
    sock = socket.socket()
    sock.bind(('127.0.0.1',0))
    ready.send(sock.getsockname()[1]); ready.close()
    uvicorn.Server(uvicorn.Config(app,log_level='critical')).run(sockets=[sock])


class LocalReceiver:
    def __init__(self, root, key, delivery_token, read_token):
        self.root, self.key, self.delivery_token, self.read_token = root,key,delivery_token,read_token
    def __enter__(self):
        ctx = multiprocessing.get_context('spawn')
        parent, child = ctx.Pipe(duplex=False)
        self.process = ctx.Process(target=receiver_process,args=(
            str(Path(self.root)/'actor_chef_receiver_test.sqlite'),self.key,
            self.delivery_token,self.read_token,child))
        self.process.start(); child.close()
        if not parent.poll(10):
            self.process.terminate(); self.process.join(5)
            raise RuntimeError('receiver_start_timeout')
        port = parent.recv(); parent.close()
        self.client = loopback_client('http://127.0.0.1:'+str(port))
        deadline = time.monotonic()+10
        while True:
            try:
                if self.client.get('/healthz').status_code==200:
                    break
            except Exception:
                if time.monotonic()>=deadline:
                    self.__exit__(None,None,None)
                    raise RuntimeError('receiver_health_timeout')
                time.sleep(.05)
        return self
    def __exit__(self,*args):
        self.client.close()
        self.process.terminate(); self.process.join(5)
        if self.process.is_alive():
            self.process.kill(); self.process.join(5)


def run():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        key = secrets.token_bytes(40)
        delivery_token, read_token, owner_token = [secrets.token_urlsafe(40) for _ in range(3)]
        with LocalReceiver(root,key,delivery_token,read_token) as receiver:
            engine = AutomaticChef(root,receiver.client,delivery_token,read_token,key)
            # Inbox API is the EXISTING owner-authenticated app/thread, not a second UI.
            app = create_app('sqlite:///'+str(root/'inbox_chef_test.sqlite'),owner_token)
            headers={'Authorization':'Bearer '+owner_token}
            done=threading.Event(); errors=[]
            def pump():
                try:
                    while not done.is_set():
                        engine.tick(); done.wait(.05)
                except BaseException as error:
                    errors.append(type(error).__name__); done.set()
            with TestClient(app) as inbox:
                thread=inbox.post('/v1/chef-demo/threads',headers=headers).json()['thread_id']
                for n in (1,2):
                    response=inbox.post(f'/v1/chef-demo/threads/{thread}/messages',headers=headers,
                        json={'source_id':str(uuid.uuid4()),'body':f'SYNTHETIC: question request {n}'})
                    assert response.status_code==200
                engine.resume_for_test()
                worker=threading.Thread(target=pump); worker.start()
                try:
                    deadline=time.monotonic()+10
                    while time.monotonic()<deadline:
                        # Read only; no sender dispatch/ACK/execute call after submission.
                        view=inbox.get(f'/v1/chef-demo/threads/{thread}',headers=headers).json()
                        if len(view['messages'])==4 or errors:break
                        time.sleep(.05)
                    assert not errors, errors
                    assert len(view['messages'])==4, view
                    users={m['message_id'] for m in view['messages'] if m['sender']=='USER'}
                    replies=[m for m in view['messages'] if m['sender']=='CHEF_SIGNED_FIXTURE']
                    assert {m['reply_to'] for m in replies}==users
                finally:
                    done.set();worker.join(5);engine.stop();engine.close()
            reopened=AutomaticChef(root,receiver.client,delivery_token,read_token,key)
            assert len(reopened.store.get_thread(thread)['messages'])==4
            reopened.close()
            with sqlite3.connect(root/'actor_chef_receiver_test.sqlite') as db:
                assert db.execute('SELECT count(*) FROM receipts WHERE result IS NOT NULL').fetchone()[0]==2
                assert db.execute('SELECT count(*) FROM effects').fetchone()[0]==2
            result=dict(mode='LOCAL_AUTOMATIC_HTTP_SYNTHETIC',independent_receiver_process=True,
                overlapping_instructions=2,persisted_signed_acks=2,independently_verified_actions=2,
                correlated_original_inbox_replies=2,survived_dispatcher_reopen=True,
                paid_model_calls=0,hosted_acceptance=False,institutional_google_connected=False)
            print(json.dumps(result,indent=2))
            return result

if __name__=='__main__':run()
