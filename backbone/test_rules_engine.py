"""Tests for proposal engine. No external services or mutable records."""
import unittest
from rules_engine import IntakeSignal, evaluate

class ProposalTests(unittest.TestCase):
    def signal(self, kind, confidence=0.95, **kw):
        return IntakeSignal(kind=kind, confidence=confidence, evidence_verified=True, **kw)

    def test_known_receipt_makes_proposal_not_write(self):
        d = evaluate(self.signal("RECEIPT"))
        self.assertEqual((d.state, d.proposed_action), ("SUGGEST", "PREPARE_HANDOFF"))
        self.assertFalse(d.can_execute)

    def test_low_confidence_receipt_asks(self):
        self.assertTrue(evaluate(self.signal("RECEIPT", 0.4)).requires_user_reply)

    def test_floor_photo_asks(self):
        self.assertEqual(evaluate(self.signal("UNKNOWN_PHOTO")).state, "NEEDS_CLARIFICATION")

    def test_unverified_original_is_blocked(self):
        d = evaluate(IntakeSignal("RECEIPT", .99, False))
        self.assertEqual(d.rationale_code, "ORIGINAL_UNVERIFIED")

    def test_duplicate_conflict_is_blocked(self):
        self.assertEqual(evaluate(self.signal("RECEIPT", duplicate_conflict=True)).state, "BLOCKED")

    def test_repeated_storage_confirmation_only_suggests(self):
        d = evaluate(self.signal("FOOD_STORAGE", owner_confirmations=3))
        self.assertEqual(d.rationale_code, "OWNER_PATTERN_CANDIDATE_REVIEW")
        self.assertFalse(d.can_execute)

    def test_storage_first_time_asks(self):
        self.assertEqual(evaluate(self.signal("FOOD_STORAGE")).state, "NEEDS_CLARIFICATION")

    def test_chief_of_staff_does_not_auto_route(self):
        d = evaluate(self.signal("CHIEF_OF_STAFF_IDEA"))
        self.assertEqual(d.state, "REQUIRES_APPROVAL")
        self.assertFalse(d.can_execute)

    def test_invalid_confidence_rejected(self):
        self.assertEqual(evaluate(self.signal("RECEIPT", 2)).state, "BLOCKED")

if __name__ == "__main__":
    unittest.main()
