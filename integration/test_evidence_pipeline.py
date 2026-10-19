import hashlib, io, json, tempfile, unittest, uuid, zipfile
from pathlib import Path
from dataclasses import replace
from evidence_adapter import EvidenceInput, LocalFixtureEvidenceStore, Conflict, InvalidEvidence, business_duplicate_decision
from package_bridge import ingest_package

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=LocalFixtureEvidenceStore(Path(self.tmp.name))
        self.meta=EvidenceInput(str(uuid.uuid4()),'receipt-1','sainsbury.jpg','image/jpeg','MI_MUNDO','FINANCIAL','HEAD_CHEF','2026-10-17T09:33:00+01:00')
    def tearDown(self): self.store.close(); self.tmp.cleanup()
    def test_file_and_readback(self):
        r=self.store.ingest(self.meta,b'fake fixture jpeg');self.assertEqual(r['status'],'FILED_LOCAL_TEST_ONLY');self.assertFalse(r['duplicate'])
    def test_replay_preserves_id(self):
        a=self.store.ingest(self.meta,b'photo');b=self.store.ingest(self.meta,b'photo');self.assertEqual(a['evidence_id'],b['evidence_id']);self.assertTrue(b['duplicate'])
    def test_changed_bytes_conflict(self):
        self.store.ingest(self.meta,b'a')
        with self.assertRaises(Conflict): self.store.ingest(self.meta,b'b')
    def test_changed_metadata_conflict(self):
        self.store.ingest(self.meta,b'a')
        with self.assertRaises(Conflict): self.store.ingest(replace(self.meta,original_filename='another.jpg'),b'a')
    def test_corrupted_saved_blob_fails_closed(self):
        r=self.store.ingest(self.meta,b'a');(self.store.blobs/(r['evidence_id']+'.bin')).write_bytes(b'bad')
        with self.assertRaises(InvalidEvidence):self.store.ingest(self.meta,b'a')
    def test_restart_persists(self):
        r=self.store.ingest(self.meta,b'a');self.store.close();self.store=LocalFixtureEvidenceStore(Path(self.tmp.name))
        self.assertEqual(self.store.ingest(self.meta,b'a')['evidence_id'],r['evidence_id'])
    def test_invalid_scope(self):
        with self.assertRaises(InvalidEvidence):self.store.ingest(replace(self.meta,privacy_class='UNKNOWN'),b'a')
    def test_empty_file(self):
        with self.assertRaises(InvalidEvidence):self.store.ingest(self.meta,b'')
    def test_different_job_same_bytes_distinct_event(self):
        a=self.store.ingest(self.meta,b'a');b=self.store.ingest(replace(self.meta,job_id=str(uuid.uuid4())),b'a');self.assertNotEqual(a['evidence_id'],b['evidence_id'])
    def test_independent_verify(self):
        r=self.store.ingest(self.meta,b'original')
        self.assertEqual(self.store.verify(r['evidence_id'])['status'],'VERIFIED_LOCAL_TEST_ONLY')
    def test_unknown_evidence_id(self):
        with self.assertRaises(InvalidEvidence):self.store.verify('EV-UNKNOWN')
    def test_verify_detects_corrupt_file(self):
        r=self.store.ingest(self.meta,b'original')
        (self.store.blobs/(r['evidence_id']+'.bin')).write_bytes(b'changed')
        with self.assertRaises(InvalidEvidence):self.store.verify(r['evidence_id'])
    def test_sainsbury_already_recorded_no_writes(self):
        d=business_duplicate_decision(True,True,True);self.assertEqual(d['writes_performed'],0);self.assertTrue(all(d[k]=='NOOP' for k in ('finance','kitchen','inventory')))

class PackageBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=LocalFixtureEvidenceStore(Path(self.tmp.name))
        self.job=str(uuid.uuid4());self.data=b'test image - not user data'
    def tearDown(self): self.store.close();self.tmp.cleanup()
    def make(self,*,corrupt=False,extra=False):
        digest=hashlib.sha256(self.data).hexdigest()
        manifest={'version':'0.3','status':'LOCAL_EXPORT_NOT_TRANSMITTED','job_id':self.job,'instructions':'Store photo',
                  'attachments':[{'id':'a1','archive_path':'evidence/photo.jpg','name':'photo.jpg','type':'image/jpeg','bytes':len(self.data),'sha256':digest}]}
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:
            z.writestr('manifest.json',json.dumps(manifest));z.writestr('instructions.txt','Store photo')
            z.writestr('evidence/photo.jpg',self.data+(b'x' if corrupt else b''))
            if extra:z.writestr('unknown.txt','extra')
        return b.getvalue()
    def call(self,blob):
        return ingest_package(blob,self.store,department='Head Chef',privacy_class='GENERAL',received_at='2026-10-17T20:00:00+01:00')
    def test_filed_and_readback(self):
        r=self.call(self.make());self.assertEqual(r['status'],'FILED_LOCAL_TEST_ONLY');self.assertFalse(r['production_evidence_filed'])
    def test_exact_repeat_one_record(self):
        blob=self.make();a=self.call(blob);b=self.call(blob)
        self.assertEqual(a['attachments'][0]['evidence_id'],b['attachments'][0]['evidence_id']);self.assertTrue(b['attachments'][0]['duplicate'])
    def test_checksum_rejects_before_write(self):
        with self.assertRaises(InvalidEvidence):self.call(self.make(corrupt=True))
        self.assertEqual(self.store.db.execute('select count(*) from evidence').fetchone()[0],0)
    def test_unlisted_file_rejects(self):
        with self.assertRaises(InvalidEvidence):self.call(self.make(extra=True))
    def test_invalid_privacy_rejects(self):
        with self.assertRaises(InvalidEvidence):ingest_package(self.make(),self.store,department='Chef',privacy_class='INVALID',received_at='now')
    def test_no_post_office_side_effects(self):
        r=self.call(self.make());self.assertFalse(r['routed']);self.assertFalse(r['departmental_updates'])

if __name__=='__main__': unittest.main()
