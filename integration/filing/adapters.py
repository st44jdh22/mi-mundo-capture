"""Injected adapters only: no credentials, Google client or external requests."""
from __future__ import annotations

from typing import Protocol
from .storage import digest


class TransientFailure(Exception): pass
class PolicyBlock(Exception): pass
class PermissionFailure(Exception): pass
class UnknownOutcome(Exception): pass
class Conflict(Exception): pass
class PermanentFailure(Exception): pass


class EffectTransport(Protocol):
    """An immutable external identity is mandatory, not search-only dedupe.

    A future Drive transport must reserve/store a Drive file ID before upload,
    create only that ID, and GET it on recovery. Existing-ID conflicts must not
    overwrite. A timeout/connector policy block must retain its actual category.
    """
    def find(self, effect_id: str) -> list[dict]: ...
    def create_if_absent(self, effect_id: str, data: bytes, metadata: dict): ...


class GoogleDriveFilingAdapter:
    def __init__(self, transport: EffectTransport):
        self.transport = transport

    def observe(self, target: dict) -> dict | None:
        found = self.transport.find(target['effect_id'])
        if not found:
            return None
        if len(found) != 1:
            raise Conflict('duplicate external identities')
        actual = found[0]
        expected = {key: target[key] for key in
                    ('effect_id', 'destination', 'name', 'permissions', 'expected_sha256', 'size')}
        if any(actual.get(key) != value for key, value in expected.items()):
            raise Conflict('destination identity/content/permissions mismatch')
        if digest(actual.get('data', b'')) != target['expected_sha256']:
            raise Conflict('independent byte hash mismatch')
        return {**expected, 'independent_readback': True}

    def write(self, target, data):
        if digest(data) != target['expected_sha256']:
            raise Conflict('source differs from accepted target')
        self.transport.create_if_absent(target['effect_id'], data, {
            key: target[key] for key in ('effect_id', 'destination', 'name',
                                        'permissions', 'expected_sha256', 'size')})


# Records use the same independently checked immutable-effect interface.
# The real register adapter additionally needs revision/CAS semantics at release.
class SyntheticRecordAdapter(GoogleDriveFilingAdapter):
    pass


class ProjectionGateway(Protocol):
    def headers(self, table: str) -> tuple: ...
    def upsert(self, table: str, identity: str, payload: dict): ...
    def read(self, table: str, identity: str) -> dict | None: ...


class PostOfficeStatusAdapter:
    """Schema-checked projection of SQL events into existing Post Office tables.

    SQL events are the durable delivery outbox; retry uses stable row identities.
    This class never invents departmental acknowledgement or a new master queue.
    """
    def __init__(self, gateway: ProjectionGateway):
        self.gateway = gateway

    def _changes(self, event):
        from postoffice_contract import MESSAGE_COLUMNS, DELIVERY_COLUMNS
        schemas = {
            'MESSAGES': MESSAGE_COLUMNS,
            'DELIVERIES': DELIVERY_COLUMNS,
            'ACTIONS': ('Action ID','Message ID','Delivery ID','Department ID','Action','Owner',
                        'Status','Due / Review Condition','Completion Evidence','Record Updated','Last Updated'),
            'ESCALATIONS': ('Escalation ID','Message ID','Delivery ID','Severity','Issue','Owner',
                            'Stephen Required','Status','Created At','Resolved At','Resolution'),
            'RUN LOG': ('Run ID','Timestamp','Department ID','Message ID','Trigger','Model / Profile',
                        'Records Read','Records Written','Outcome','Duration Sec','Token / API Usage',
                        'Error','Retry','Approval State'),
        }
        job, eid = event['job_id'], event['event_id']
        mid, did = 'SYN-MSG-' + job, 'SYN-DLV-' + job
        status = event['state']
        evidence = event.get('evidence', '')
        changes = {
            'MESSAGES': (mid, {'Message ID':mid,'Source Dept':event['department'],
                              'Source Ref':event['conversation_id'],'Overall Status':status}),
            'DELIVERIES': (did, {'Delivery ID':did,'Message ID':mid,'Recipient Dept ID':event['department'],
                                 'Status':status,'Completion Ref':evidence}),
            'ACTIONS': ('SYN-ACT-'+job, {'Action ID':'SYN-ACT-'+job,'Message ID':mid,'Delivery ID':did,
                        'Department ID':event['department'],'Status':status,'Completion Evidence':evidence}),
            'RUN LOG': (eid, {'Run ID':eid,'Department ID':event['department'],'Message ID':mid,
                              'Outcome':status,'Error':event.get('error_code','')}),
        }
        if event.get('error_code'):
            changes['ESCALATIONS'] = ('SYN-ESC-'+job, {'Escalation ID':'SYN-ESC-'+job,
                'Message ID':mid,'Delivery ID':did,'Issue':event['error_code'],
                'Owner':'Post Office Systems Engineering Lead','Status':'OPEN'})
        elif status == 'VERIFIED COMPLETE':
            changes['ESCALATIONS'] = ('SYN-ESC-'+job, {'Escalation ID':'SYN-ESC-'+job,
                'Message ID':mid,'Delivery ID':did,'Issue':'','Owner':'Post Office Systems Engineering Lead',
                'Status':'RESOLVED','Resolution':evidence})
        return schemas, changes

    def verify(self, event):
        schemas, changes = self._changes(event)
        for table in changes:
            if tuple(self.gateway.headers(table)) != schemas[table]:
                raise Conflict('Post Office schema changed: ' + table)
        return all(self.gateway.read(table, identity) == payload
                   for table, (identity, payload) in changes.items())

    def publish(self, event):
        schemas, changes = self._changes(event)
        for table in changes:
            if tuple(self.gateway.headers(table)) != schemas[table]:
                raise Conflict('Post Office schema changed: ' + table)
        for table, (identity, payload) in changes.items():
            self.gateway.upsert(table, identity, payload)
            if self.gateway.read(table, identity) != payload:
                raise UnknownOutcome('Post Office projection readback missing')
