import unittest
from postoffice_contract import (PostOfficeReadModel,ContractError,MESSAGE_COLUMNS,DELIVERY_COLUMNS,THREAD_COLUMNS)

def row(cols,**v):return [v.get(k,'') for k in cols]

def fixtures():
    m=[list(MESSAGE_COLUMNS),row(MESSAGE_COLUMNS,**{'Message ID':'MSG-TEST-1','Idempotency Key':'synthetic-1','Overall Status':'ROUTED'})]
    d=[list(DELIVERY_COLUMNS),row(DELIVERY_COLUMNS,**{'Delivery ID':'DLV-TEST-1','Message ID':'MSG-TEST-1','Recipient Dept ID':'FOOD-CHEF','Status':'QUEUED','Routed At':'now'})]
    t=[list(THREAD_COLUMNS),row(THREAD_COLUMNS,**{'Mail ID':'MAIL-TEST-1','Delivery ID':'DLV-TEST-1','Thread ID':'THR-TEST-1','Status':'QUEUED — WORKER OFF'})]
    return m,d,t

class ReadContractTests(unittest.TestCase):
    def test_matches_actual_headers(self):
        x=PostOfficeReadModel(*fixtures()).reconcile('MSG-TEST-1','DLV-TEST-1')
        self.assertEqual(x.thread_id,'THR-TEST-1');self.assertEqual(x.mail_ids,('MAIL-TEST-1',));self.assertFalse(x.automated_chef_ack_proven)
    def test_missing_message(self):
        with self.assertRaisesRegex(ContractError,'MESSAGE'):PostOfficeReadModel(*fixtures()).reconcile('unknown','DLV-TEST-1')
    def test_missing_delivery(self):
        with self.assertRaisesRegex(ContractError,'DELIVERY'):PostOfficeReadModel(*fixtures()).reconcile('MSG-TEST-1','unknown')
    def test_crosslinked_delivery(self):
        m,d,t=fixtures();d[1][1]='MSG-OTHER'
        with self.assertRaisesRegex(ContractError,'different'):PostOfficeReadModel(m,d,t).reconcile('MSG-TEST-1','DLV-TEST-1')
    def test_wrong_department(self):
        m,d,t=fixtures();d[1][2]='TI-TRADING'
        with self.assertRaisesRegex(ContractError,'recipient'):PostOfficeReadModel(m,d,t).reconcile('MSG-TEST-1','DLV-TEST-1')
    def test_missing_thread(self):
        m,d,t=fixtures();t[1][10]='DLV-OTHER'
        with self.assertRaisesRegex(ContractError,'linkage'):PostOfficeReadModel(m,d,t).reconcile('MSG-TEST-1','DLV-TEST-1')
    def test_ambiguous_thread(self):
        m,d,t=fixtures();t.append(row(THREAD_COLUMNS,**{'Mail ID':'MAIL-TEST-2','Delivery ID':'DLV-TEST-1','Thread ID':'THR-OTHER'}))
        with self.assertRaisesRegex(ContractError,'Ambiguous'):PostOfficeReadModel(m,d,t).reconcile('MSG-TEST-1','DLV-TEST-1')
    def test_duplicate_ledger_id(self):
        m,d,t=fixtures();d.append(d[1])
        with self.assertRaisesRegex(ContractError,'duplicate'):PostOfficeReadModel(m,d,t)
    def test_schema_change_stops(self):
        m,d,t=fixtures();m[0][0]='Wrong Header'
        with self.assertRaisesRegex(ContractError,'schema changed'):PostOfficeReadModel(m,d,t)
    def test_manual_verified_label_not_auto_actor(self):
        m,d,t=fixtures();d[1][3]='ACKNOWLEDGED — MANUAL REVIEW';d[1][7]='2026-10-18'
        x=PostOfficeReadModel(m,d,t).reconcile('MSG-TEST-1','DLV-TEST-1')
        self.assertEqual(x.verified_at,'2026-10-18');self.assertFalse(x.automated_chef_ack_proven)
    def test_blank_id_stops(self):
        m,d,t=fixtures();m[1][0]=''
        with self.assertRaisesRegex(ContractError,'blank primary'):PostOfficeReadModel(m,d,t)

if __name__=='__main__':unittest.main()