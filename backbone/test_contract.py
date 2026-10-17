import unittest
from model_provider import (ModelRequest,StaticTestProvider,DisabledProvider,classify_for_review)
class ModelContractTests(unittest.TestCase):
 def test_offline_model_fixture(self):
  r=classify_for_review(StaticTestProvider(),ModelRequest('v1','Classify','hello'))
  self.assertEqual(r['classification'],'REVIEW_REQUIRED')
  self.assertFalse(r['action_authorised'])
 def test_disabled_fails_closed(self):
  with self.assertRaises(RuntimeError):
   classify_for_review(DisabledProvider(),ModelRequest('v1','Classify','hello'))
if __name__=='__main__':unittest.main()
