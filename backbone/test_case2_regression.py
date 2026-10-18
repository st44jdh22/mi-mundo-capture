import tempfile
import unittest
from pathlib import Path
from case2_regression import Event, Case2Fixture, choose_current_event, correct_shake

DAY='2026-10-18'
J='synthetic-intake-case2'
Y=Event('morning-med','2026-10-17',{'time':'08:20','fixture':'previous-day'})
T=Event('morning-med',DAY,{'time':'08:20','fixture':'current-day'})

class Case2Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.file=str(Path(self.temp.name)/'checkpoint.db')
        self.f=Case2Fixture(self.file)
    def tearDown(self):
        self.f.close();self.temp.cleanup()
    def test_correct_date_selects_today_not_yesterday(self):
        self.assertEqual(choose_current_event([Y,T],DAY),T)
    def test_ambiguous_same_day_is_not_guessed(self):
        with self.assertRaises(ValueError): choose_current_event([T,T],DAY)
    def test_correction_precedence_and_unknown_portions(self):
        x=correct_shake({'yoghurt_fat':'whole','milk_fat':'0%','whole_shake_fat_free':True},{'yoghurt_fat':'0%','milk_fat':'whole'})
        self.assertEqual(x['yoghurt_fat'],'0%');self.assertEqual(x['milk_fat'],'whole')
        self.assertFalse(x['whole_shake_fat_free']);self.assertIsNone(x['portion_size'])
    def test_four_destinations_verified_but_postoffice_not_acked(self):
        e=Event('kit-031',DAY,{'category':'synthetic food'})
        times=[]
        for d in ['personal-log','kitchen-activity','kitchen-inventory','postoffice-queue']:
            state,ms=self.f.apply(J,d,e);times.append(ms);self.assertEqual(state,'VERIFIED')
        self.assertTrue(self.f.summary(J)['complete']);self.assertFalse(self.f.summary(J)['post_office_acknowledged'])
        self.assertTrue(all(t>=0 for t in times))
    def test_timeout_after_remote_write_does_not_duplicate(self):
        e=Event('kit-031',DAY,{'kind':'synthetic'})
        self.f.lost_ack.add('kitchen-activity')
        self.assertEqual(self.f.apply(J,'kitchen-activity',e)[0],'UNCONFIRMED')
        self.assertEqual(self.f.apply(J,'kitchen-activity',e)[0],'VERIFIED')
        self.assertEqual(self.f.calls[('kitchen-activity','kit-031')],1)
    def test_policy_blocked_handover_survives_restart(self):
        e=Event('case2-report',DAY,{'kind':'generic engineering handover'})
        self.f.denied.add('engineering-charter')
        self.assertEqual(self.f.apply(J,'engineering-charter',e)[0],'POLICY_BLOCKED')
        self.f.close();self.f=Case2Fixture(self.file)
        self.f.denied.add('engineering-charter')
        self.assertEqual(self.f.apply(J,'engineering-charter',e)[0],'POLICY_BLOCKED')
        self.assertEqual(self.f.calls,{})
    def test_policy_clearance_needs_review(self):
        e=Event('case2-report',DAY,{'kind':'fixture'})
        self.f.denied.add('engineering-charter')
        self.f.apply(J,'engineering-charter',e)
        self.f.denied.remove('engineering-charter')
        with self.assertRaises(PermissionError):self.f.release(J,'engineering-charter',False,True)
        self.f.release(J,'engineering-charter',True,True)
        self.assertEqual(self.f.apply(J,'engineering-charter',e)[0],'VERIFIED')
    def test_change_after_checkpoint_conflict(self):
        a=Event('med-event',DAY,{'v':1});b=Event('med-event',DAY,{'v':2})
        self.f.apply(J,'personal-log',a)
        self.assertEqual(self.f.apply(J,'personal-log',b)[0],'CONFLICT')
    def test_repeat_verification_no_second_write(self):
        e=Event('kit-031',DAY,{'kind':'synthetic'})
        self.f.apply(J,'kitchen-inventory',e);self.f.apply(J,'kitchen-inventory',e)
        self.assertEqual(self.f.calls[('kitchen-inventory','kit-031')],1)

if __name__=='__main__':unittest.main()