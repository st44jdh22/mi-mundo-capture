"""Deterministic, provider-neutral Mi Mundo proposal engine (DESIGN TEST ONLY).

No Post Office sends, departmental writes or learned-rule activation.
A model's classification is untrusted input, never execution authority.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class IntakeSignal:
    kind: str
    confidence: float | None
    evidence_verified: bool
    instructions: str = ""
    duplicate_conflict: bool = False
    domain: str = "GENERAL"
    owner_confirmations: int = 0

@dataclass(frozen=True)
class Decision:
    state: str
    proposed_action: str
    rationale_code: str
    requires_user_reply: bool
    can_execute: bool = False

def evaluate(signal: IntakeSignal) -> Decision:
    """Return a reviewable proposal, not a dispatch or database write."""
    if signal.duplicate_conflict:
        return Decision("BLOCKED", "FLAG_DUPLICATE", "CONTENT_CONFLICT", True)
    if not signal.evidence_verified:
        return Decision("BLOCKED", "REQUEST_CLARIFICATION", "ORIGINAL_UNVERIFIED", True)
    if signal.confidence is not None and not (0 <= signal.confidence <= 1):
        return Decision("BLOCKED", "REQUEST_CLARIFICATION", "INVALID_CONFIDENCE", True)
    kind = signal.kind.upper()
    if kind == "RECEIPT":
        if signal.confidence is None or signal.confidence < 0.85:
            return Decision("NEEDS_CLARIFICATION", "REQUEST_CLARIFICATION", "RECEIPT_LOW_CONFIDENCE", True)
        return Decision("SUGGEST", "PREPARE_HANDOFF", "RECEIPT_REVIEW_PENDING", False)
    if kind == "FOOD_STORAGE":
        if signal.owner_confirmations >= 3:
            return Decision("SUGGEST", "SUGGEST_STORAGE", "OWNER_PATTERN_CANDIDATE_REVIEW", False)
        return Decision("NEEDS_CLARIFICATION", "REQUEST_CLARIFICATION", "STORAGE_LOCATION_UNCONFIRMED", True)
    if kind == "CHIEF_OF_STAFF_IDEA":
        return Decision("REQUIRES_APPROVAL", "PREPARE_HANDOFF", "POST_OFFICE_AUTHORITY_CHECK", True)
    return Decision("NEEDS_CLARIFICATION", "REQUEST_CLARIFICATION", "UNKNOWN_INTENT", True)
