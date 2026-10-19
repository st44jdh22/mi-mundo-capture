"""Read-only adapter to the EXISTING institutional Post Office Sheets schema.

This module NEVER writes Sheets, dispatches messages, invokes Chef, or manufactures
acknowledgements. It binds IDs already assigned by the authoritative records.
Synthetic test fixtures are permitted; actual food/health user content is not.
"""
from dataclasses import dataclass
from typing import Sequence

MESSAGE_COLUMNS = ('Message ID','Created At','Source Org','Source Dept','Source Ref','Type','Subject','Body / Instruction','Priority','Privacy','Action Required','Approval Required','Due / Review Condition','Related Record(s)','Attachments','Idempotency Key','Overall Status','Closed At','Last Updated')
DELIVERY_COLUMNS = ('Delivery ID','Message ID','Recipient Dept ID','Status','Routed At','Claimed At','Actioned At','Verified At','Completion Ref','Blocker','Retry Count','Last Error','Escalation Status','Last Updated')
THREAD_COLUMNS = ('Mail ID','Created','From','To','Subject','Message','Status','Department Reply','Next step / Decision','Updated','Delivery ID','Thread ID','Parent Message','Alert')

class ContractError(ValueError): pass


def index_rows(rows: Sequence[Sequence], headers: tuple[str, ...], key: str) -> dict[str, dict]:
    if not rows or tuple(str(v).strip() for v in rows[0][:len(headers)]) != headers:
        raise ContractError(f'{key}: source schema changed; review required')
    result = {}
    for idx, raw in enumerate(rows[1:], start=2):
        if not any(str(x).strip() for x in raw): continue
        values = {column: str(raw[i]).strip() if i < len(raw) and raw[i] is not None else '' for i,column in enumerate(headers)}
        primary = values[key]
        if not primary: raise ContractError(f'{key}: blank primary key at row {idx}')
        if primary in result: raise ContractError(f'{key}: duplicate primary key {primary}')
        result[primary] = values
    return result

@dataclass(frozen=True)
class InstitutionalEvidence:
    message_id: str
    delivery_id: str
    recipient: str
    route_status: str
    thread_id: str | None
    mail_ids: tuple[str,...]
    claimed_at: str | None
    actioned_at: str | None
    verified_at: str | None
    completion_ref: str | None
    automated_chef_ack_proven: bool = False
    note: str = 'Sheet status/filled timestamp is not a cryptographic actor receipt or proof of autonomous chat delivery.'


class PostOfficeReadModel:
    def __init__(self, message_rows, delivery_rows, thread_rows):
        self.messages=index_rows(message_rows,MESSAGE_COLUMNS,'Message ID')
        self.deliveries=index_rows(delivery_rows,DELIVERY_COLUMNS,'Delivery ID')
        self.threads=index_rows(thread_rows,THREAD_COLUMNS,'Mail ID')

    def reconcile(self, message_id: str, delivery_id: str, *, target: str='FOOD-CHEF') -> InstitutionalEvidence:
        """Reject missing/contradictory ledger identities, but never infer a verified worker."""
        if message_id not in self.messages: raise ContractError('No institutional MESSAGE record')
        delivery=self.deliveries.get(delivery_id)
        if not delivery: raise ContractError('No institutional DELIVERY record')
        if delivery['Message ID'] != message_id: raise ContractError('Delivery linked to a different institutional message')
        if delivery['Recipient Dept ID'] != target: raise ContractError('Wrong recipient department')
        related=[v for v in self.threads.values() if v['Delivery ID']==delivery_id]
        if not related: raise ContractError('No original POST OFFICE THREADS linkage')
        thread_ids={t['Thread ID'] for t in related if t['Thread ID']}
        if len(thread_ids)!=1: raise ContractError('Ambiguous or missing institutional thread ID')
        # A row's 'Department Reply' can be manually entered; it cannot substitute
        # for a verified signed actor receipt issued under an approved principal.
        return InstitutionalEvidence(message_id, delivery_id, delivery['Recipient Dept ID'],
              delivery['Status'],next(iter(thread_ids)),tuple(sorted(t['Mail ID'] for t in related)),
              delivery['Claimed At'] or None,delivery['Actioned At'] or None,
              delivery['Verified At'] or None,delivery['Completion Ref'] or None)