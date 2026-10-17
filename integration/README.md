# Capture-to-intake boundary — prepared, not connected

validate_job.py validates the existing v0.3 ZIP locally without extraction, network, evidence storage or Post Office submission. It is a first boundary validator, not a production upload service or media-security certification. Python 3.11+ standard library only.

Run: `python validate_job.py /path/to/job.zip`
Tests: `python -m unittest discover -s integration -v` from repository root.

Validated on 17 October 2026: the supplied iPhone job contains five attachments; ZIP integrity, manifest byte sizes/checksums and instructions match. Synthetic tests cover valid/repeat identity and eight rejection cases. No real user media, filenames, job contents or credentials are committed here.

The content fingerprint is a comparison aid, not proof a business event is a duplicate. Existing authoritative records must still be compared by the Universal Intake engine. Hashes establish internal consistency, not sender identity, capture date or safety of media.

## Required integration handoff

The existing Universal Intake/Post Office owners need to establish the actual authenticated HTTPS receiver, identity/session mechanism, allowed capture origin, upload limits/retention and permission-appropriate original-evidence destination. Do not invent a URL or embed service credentials in the public app.

Proposed receiver behaviour: validate the package; preserve original supplied bytes through the existing evidence module; return a job-linked durable receipt only after storage/readback. Receipt is not routing or completion. Reuse job ID plus content comparison to detect retries; conflict on changed content under one job ID. Provide authenticated result lookup so uncertain network responses are reconciled before retrying. Existing Post Office retains approval/routing and verified departmental results; BUS-COS pilot permissions/capacity are unchanged.

These are proposed requirements, not an agreed backend API. Live Transmit remains disconnected. No public receiver, new evidence store or departmental worker has been deployed. Next step: confirm the actual intake service/module implementation and adapt this validator there, then run an authorised non-sensitive upload/readback test.
