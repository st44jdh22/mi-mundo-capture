import tempfile,unittest,uuid
from pathlib import Path
from fastapi.testclient import TestClient
from chef_thread import Store,create_app
TOKEN='X'*40
class StoreTests(unittest.TestCase):
 def setUp(self):
  self.dir=tempfile.TemporaryDirectory();self.path=str(Path(self.dir.name)/'db.sqlite');self.db=Store('sqlite:///'+self.path);self.t=self.db.new_thread()
 def tearDown(self):self.db.close();self.dir.cleanup()
 def test_two_turns_same_thread(self):
  first=self.db.send(self.t,uuid.uuid4(),'Ten people for a barbecue');self.assertEqual(len(first['messages']),1)
  a=self.db.respond_synthetic(self.t);self.assertEqual(len(a['messages']),2)
  self.db.send(self.t,uuid.uuid4(),'Mediterranean menu please');b=self.db.respond_synthetic(self.t);self.assertEqual(len(b['messages']),4)
  self.assertEqual({m['sender'] for m in b['messages']},{'USER','CHEF_SIMULATOR'})
 def test_identical_replay_is_noop(self):
  id=uuid.uuid4();self.db.send(self.t,id,'BBQ');self.db.send(self.t,id,'BBQ');self.assertEqual(len(self.db.get_thread(self.t)['messages']),1)
 def test_modified_replay_conflicts(self):
  id=uuid.uuid4();self.db.send(self.t,id,'BBQ');self.assertRaises(ValueError,self.db.send,self.t,id,'DIFFERENT')
 def test_reconnect_has_same_history(self):
  self.db.send(self.t,uuid.uuid4(),'BBQ');self.db.respond_synthetic(self.t);self.db.close();self.db=Store('sqlite:///'+self.path);self.assertEqual(len(self.db.get_thread(self.t)['messages']),2)
 def test_wrong_owner_rejected(self):
  self.assertRaises(KeyError,self.db.get_thread,self.t,'other-owner')
  self.assertRaises(KeyError,self.db.send,self.t,uuid.uuid4(),'Hi','other-owner')
 def test_simulator_retry_no_duplicate(self):
  self.db.send(self.t,uuid.uuid4(),'BBQ');self.db.respond_synthetic(self.t);self.db.respond_synthetic(self.t);self.assertEqual(len(self.db.get_thread(self.t)['messages']),2)
class ApiTests(unittest.TestCase):
 def setUp(self):
  self.dir=tempfile.TemporaryDirectory();self.app=create_app('sqlite:///'+str(Path(self.dir.name)/'api.sqlite'),TOKEN);self.client=TestClient(self.app);self.client.__enter__();self.h={'Authorization':'Bearer '+TOKEN}
 def tearDown(self):self.client.__exit__(None,None,None);self.dir.cleanup()
 def test_auth_and_end_to_end(self):
  self.assertEqual(self.client.post('/v1/chef-demo/threads').status_code,401)
  r=self.client.post('/v1/chef-demo/threads',headers=self.h);self.assertEqual(r.status_code,201);t=r.json()['thread_id']
  m=self.client.post(f'/v1/chef-demo/threads/{t}/messages',headers=self.h,json={'source_id':str(uuid.uuid4()),'body':'Hello Chef'})
  self.assertEqual(len(m.json()['messages']),1)
  rr=self.client.post(f'/v1/chef-demo/threads/{t}/simulate-response',headers=self.h);self.assertEqual(len(rr.json()['messages']),2)
  self.assertFalse(self.client.get('/healthz').json()['post_office_connected'])
 def test_html_has_real_no_live_disclaimer(self):
  p=self.client.get('/chef-demo');self.assertEqual(p.status_code,200);self.assertIn('Replies are scripted',p.text);self.assertNotIn(TOKEN,p.text)
if __name__=='__main__':unittest.main()
