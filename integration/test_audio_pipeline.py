import tempfile,uuid,unittest
from pathlib import Path
from audio_pipeline import AudioPipeline,SyntheticTranscriber,PayloadConflict,PolicyBlocked
class PipelineTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.transcriber=SyntheticTranscriber();self.p=AudioPipeline(self.tmp.name,self.transcriber);self.id=str(uuid.uuid4());self.audio=b'fixture-audio-not-personal-information'
 def tearDown(self):self.p.close();self.tmp.cleanup()
 def save(self):return self.p.accept(self.id,self.audio)
 def test_archive_bytes_and_hash_readback(self):
  s=self.save();self.assertEqual(s.state,'DURABLE_LOCAL');self.assertTrue(self.p.status(self.id)['original_readback_verified'])
 def test_exact_idempotent_upload(self):
  self.save();self.save();self.assertEqual(self.p.db.execute('select count(*) from recordings').fetchone()[0],1)
 def test_changed_payload_conflicts(self):
  self.save();self.assertRaises(PayloadConflict,self.p.accept,self.id,b'different')
 def test_wrong_mime_and_empty_rejected(self):
  with self.assertRaises(PolicyBlocked):self.p.accept(self.id,b'abc','application/pdf')
  with self.assertRaises(PolicyBlocked):self.p.accept(self.id,b'')
 def test_transcribe_after_restart(self):
  self.save();self.p.close();self.p=AudioPipeline(self.tmp.name,self.transcriber)
  s=self.p.process(self.id);self.assertEqual(s['transcription_state'],'TRANSCRIBED');self.assertEqual(self.transcriber.calls,1)
 def test_completed_retry_does_not_rebill(self):
  self.save();self.p.process(self.id);self.p.process(self.id)
  self.assertEqual(self.transcriber.calls,1)
 def test_transient_retry_is_bounded_and_preserves_original(self):
  self.save();self.transcriber.fail=True;a=self.p.process(self.id,now=1000)
  self.assertEqual(a['transcription_state'],'RETRY_WAIT');self.assertEqual(a['next_retry_at'],1030)
  self.p.process(self.id,now=1005);self.assertEqual(self.transcriber.calls,1)
  b=self.p.process(self.id,now=1030);self.assertEqual(b['next_retry_at'],1150)
  c=self.p.process(self.id,now=1150);self.assertEqual(c['transcription_state'],'REVIEW_REQUIRED');self.assertEqual(self.transcriber.calls,3)
  self.assertTrue(c['original_readback_verified']);self.p.process(self.id,now=1200);self.assertEqual(self.transcriber.calls,3)
 def test_unknown_remote_outcome_stops_duplicate_billing(self):
  self.save()
  with self.p.db:
   self.p.db.execute("UPDATE recordings SET transcription_state='IN_FLIGHT',attempts=1 WHERE source_id=?",(self.id,))
  self.p.close();self.p=AudioPipeline(self.tmp.name,self.transcriber)
  s=self.p.process(self.id)
  self.assertEqual(s['transcription_state'],'REVIEW_REQUIRED')
  self.assertEqual(s['last_error_code'],'remote_outcome_unknown')
  self.assertEqual(self.transcriber.calls,0)
  self.assertTrue(s['original_readback_verified'])
 def test_network_recovers_without_data_loss(self):
  self.save();self.transcriber.fail=True;self.p.process(self.id,now=1000);self.p.close();self.transcriber.fail=False
  self.p=AudioPipeline(self.tmp.name,self.transcriber);b=self.p.process(self.id,now=1030)
  self.assertEqual(b['transcription_state'],'TRANSCRIBED');self.assertTrue(b['original_readback_verified'])
 def test_corrupt_source_holds_and_cannot_send(self):
  self.save();name=self.p.db.execute('select object_name from recordings').fetchone()[0]
  (Path(self.tmp.name)/'objects'/name).write_bytes(b'corrupted')
  s=self.p.process(self.id);self.assertEqual(s['transcription_state'],'REVIEW_REQUIRED')
  with self.assertRaises(ValueError):self.p.stage_for_post_office(self.id)
 def test_queued_intent_not_false_post_office_receipt(self):
  self.save();self.p.process(self.id)
  a=self.p.stage_for_post_office(self.id);b=self.p.stage_for_post_office(self.id)
  self.assertEqual(a,b);self.assertFalse(a['delivered'])
  self.assertEqual(self.p.db.execute('select count(*) from dispatches').fetchone()[0],1)
 def test_cannot_stage_untranscribed(self):
  self.save();self.assertRaises(ValueError,self.p.stage_for_post_office,self.id)
 def test_no_private_or_real_provider_calls(self):
  self.save();s=self.p.process(self.id);self.assertFalse(s['real_transcription']);self.assertFalse(s['post_office_connected'])
if __name__=='__main__':unittest.main()