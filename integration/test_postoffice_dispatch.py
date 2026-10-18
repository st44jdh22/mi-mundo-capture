"""Review-only regression contract for the durable FOOD-CHEF dispatch checkpoint."""
import os, tempfile, unittest, uuid
from postoffice_contract import MESSAGE_COLUMNS, DELIVERY_COLUMNS, THREAD_COLUMNS
from postoffice_dispatch import SyntheticDispatchOutbox, DispatchConflict

def values(columns, **data): return [data.get(k,'') for k in columns]
class DispatchTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.path=os.path.join(self.tmp.name,'dispatch.sqlite')
  self.out=SyntheticDispatchOutbox(self.path)
  self.item=dict(source_id=str(uuid.uuid4()),thread_id=str(uuid.uuid4()),message_id=str(uuid.uuid4()),body='SYNTHETIC: Chef barbecue menu')
  self.out.prepare(**self.item)
  self.rows=[
   [list(MESSAGE_COLUMNS),values(MESSAGE_COLUMNS,**{'Message ID':'MSG-SYN-1','Idempotency Key':self.item['source_id'],'Source Ref':self.item['message_id']})],
   [list(DELIVERY_COLUMNS),values(DELIVERY_COLUMNS,**{'Delivery ID':'DLV-SYN-1','Message ID':'MSG-SYN-1','Recipient Dept ID':'FOOD-CHEF','Status':'ACKNOWLEDGED — MANUAL'})],
   [list(THREAD_COLUMNS),values(THREAD_COLUMNS,**{'Mail ID':'MAIL-SYN-1','Delivery ID':'DLV-SYN-1','Thread ID':'THR-SYN-1'})]]
 def tearDown(self):self.out.close();self.tmp.cleanup()
 def check(self):return self.out.reconcile(self.item['source_id'],'MSG-SYN-1','DLV-SYN-1',*self.rows)
 def test_restart(self):
  self.out.close();self.out=SyntheticDispatchOutbox(self.path)
  self.assertEqual(self.out.get(self.item['source_id'])['state'],'PREPARED_LOCAL_NOT_POST_OFFICE')
 def test_dedupe(self):
  self.out.prepare(**self.item)
  self.assertEqual(self.out.db.execute('SELECT count(*) FROM synthetic_dispatch_outbox').fetchone()[0],1)
 def test_changed_source_conflicts(self):
  with self.assertRaises(DispatchConflict):self.out.prepare(**{**self.item,'body':'SYNTHETIC: changed'})
 def test_non_synthetic_refused(self):
  with self.assertRaises(PermissionError):self.out.prepare(**{**self.item,'source_id':str(uuid.uuid4()),'body':'private stock'})
 def test_link_no_authenticated_receipt(self):
  result=self.check()
  self.assertEqual(result['thread_id'],'THR-SYN-1')
  self.assertFalse(result['authenticated_chef_ack'])
  self.assertFalse(result['authenticated_chef_result'])
 def test_readback_repeat(self):
  self.check();self.assertEqual(self.check()['status'],'INSTITUTIONAL_LINK_READBACK_ONLY')
 def test_wrong_key(self):
  self.rows[0][1][15]='wrong'
  with self.assertRaises(DispatchConflict):self.check()
 def test_wrong_source(self):
  self.rows[0][1][4]='wrong'
  with self.assertRaises(DispatchConflict):self.check()
 def test_wrong_recipient(self):
  self.rows[1][1][2]='TI-TRADING'
  with self.assertRaises(ValueError):self.check()
 def test_missing_thread(self):
  self.rows[2][1][10]='other'
  with self.assertRaises(ValueError):self.check()
 def test_changed_link_conflicts(self):
  self.check();self.rows[2][1][11]='THR-OTHER'
  with self.assertRaises(DispatchConflict):self.check()
 def test_link_restart(self):
  self.check();self.out.close();self.out=SyntheticDispatchOutbox(self.path)
  self.assertEqual(self.out.get(self.item['source_id'])['institutional_delivery_id'],'DLV-SYN-1')
 def test_existing_chef_message_only(self):
  class Store:
   def get_thread(_, tid):
    return {'messages':[{'sender':'USER',**{k:self.item[k] for k in ('source_id','message_id','body')}}]}
  self.assertEqual(self.out.prepare_from_chef_store(Store(),thread_id=self.item['thread_id'],user_message_id=self.item['message_id'])['source_id'],self.item['source_id'])
 def test_no_fake_chef_source(self):
  class Store:
   def get_thread(_, tid):
    return {'messages':[{'sender':'CHEF_SIMULATOR',**{k:self.item[k] for k in ('source_id','message_id','body')}}]}
  with self.assertRaises(PermissionError):self.out.prepare_from_chef_store(Store(),thread_id=self.item['thread_id'],user_message_id=self.item['message_id'])
 def test_missing_source_refused(self):
  class Store:
   def get_thread(_,tid):return {'messages':[]}
  with self.assertRaises(PermissionError):self.out.prepare_from_chef_store(Store(),thread_id=self.item['thread_id'],user_message_id=self.item['message_id'])
if __name__=='__main__':unittest.main()
