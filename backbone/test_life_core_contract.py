"""Static migration smoke, NOT PostgreSQL/RLS integration evidence."""
from pathlib import Path
import unittest

SQL=Path(__file__).with_name('003_life_core.sql').read_text()
DOC=Path(__file__).with_name('PORTABILITY.md').read_text()
class CoreContract(unittest.TestCase):
    def test_isolated_workspace_scoped_tables(self):
        for name in ('workspace','membership','module','record','evidence','fact','job','operation'):
            self.assertIn("'"+name+"'",SQL)
        self.assertIn('FORCE ROW LEVEL SECURITY',SQL)
        self.assertIn('WITH CHECK (workspace_id',SQL)
    def test_cross_workspace_foreign_keys(self):
        for key in ('FOREIGN KEY(record_id,workspace_id)','FOREIGN KEY(evidence_id,workspace_id)',
                    'FOREIGN KEY(job_id,workspace_id)','FOREIGN KEY(workspace_id,subject_person_id)'):
            self.assertIn(key,SQL)
    def test_exact_evidence_separate_from_sql_bytes(self):
        self.assertIn('object_key text',SQL)
        self.assertIn('original_sha256 text',SQL)
        self.assertNotIn('bytea',SQL.lower())
    def test_optional_domains_and_uncertainty(self):
        for item in ('PERSONAL','HEALTH','FOOD','FAMILY','SCHEDULE','ASSETS','BUSINESS',
                     'REPORTED_UNVERIFIED','ORIGINAL_VERIFIED','POLICY_BLOCKED'):
            self.assertIn(item,SQL)
    def test_portability_and_security_gates_documented(self):
        for item in ('BYPASSRLS','PostgreSQL','export bundles','private object storage',
                     'independent restore','synthetic Railway'):
            self.assertIn(item,DOC)
if __name__=='__main__':unittest.main()