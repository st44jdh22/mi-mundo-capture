# Durable filing service — repository and security review

19 October 2026. Development and synthetic testing only.
Technical owner: Post Office Systems Engineering Lead.
Incident: `ESC-20261019-A58-CONTRACTOR-BRIEF-01`.
Action: `ACT-20261019-PO-A58-RELIABILITY-01`.

## Repository assessment and dependencies

The inspected PRs are stacked, not three independent merge candidates:

| PR | Inspected commit | Base | Reusable component |
|---|---|---|---|
| #2 | e07f3e7b2f245e86bb3436be836adcc55cc9c1b2 | main | PostgreSQL intake/evidence/audit design; immutable source and per-target recovery contracts |
| #4 | 7aba899bdc94c5f493ebeda72fde73673715c6ea | review/mi-mundo-postgres-backbone | SQLAlchemy PostgreSQL/SQLite engine pattern, recovery state/Inbox patterns and existing dependencies |
| #6 | b63575b6485bd38283509db3abab2ba3ed0880e8 | review/mi-mundo-durable-inbox | Chef origin/thread correlation, signed fixture tests, actual Post Office column constants |

New branch: `review/postoffice-filing-recovery`, based on the inspected #6
commit; draft PR targets `review/chef-conversation-mvp`. No PR was merged.
The default deployment branch, Dockerfile and hosted service are unchanged.

`postoffice_contract.MESSAGE_COLUMNS` and `DELIVERY_COLUMNS` are reused
directly. ACTIONS, ESCALATIONS and RUN LOG columns were checked against the
existing institutional Sheet. SQLAlchemy and FastAPI are existing PR4/PR6
dependencies. The new code extends their architecture, rather than changing
the fixed three-target health fixture or Chef scripted reply engine.

The old `backbone/recovery_queue.py` has no PostgreSQL leases and its general
retry path has backoff without a full terminal cap. PR4's worker is explicitly
single-process and hard-codes journal/emotion/narrative targets. These are not
safe drop-in document workers. PR6's signed bridge authenticates a fixture
actor, not a production department, and its Post Office mapping is local.
The new filing module does not promote that simulated acknowledgement.

No secure deployed document staging mechanism was established by this source
review. PR6's `audio_pipeline.py` retains synthetic audio using local fsync and
SQLite. That provides an implementation pattern, not an approved private
object-storage service. `filing.storage.PrivateObjects` defines the required
boundary; `LocalSyntheticObjects` is a local synthetic-only implementation.
No cloud bucket, credential or storage subscription has been provisioned.

## Database and execution design

The `mm_filing_test_*` tables are **private transaction/recovery state**, not
another institutional departmental dispatch master. They use the existing
SQLAlchemy architecture with an explicitly supplied database URL. Creation is
opt-in and allowed only in a disposable database named `*_filing_test` or a
SQLite filename ending `_filing_test.sqlite`. No automatic live migration.
The compiled PostgreSQL review DDL is in `backbone/sql/003_filing_test_review.sql`.

| Table suffix | Durable purpose |
|---|---|
| control | Stopped-by-default switch; serial pilot claims and five-job cap |
| jobs | Immutable intake/origin, requester, instructions, source/object hash, approval, state, three-attempt budget, lease and error |
| targets | Separate required file/register operations and independent verification evidence |
| attempts | Reserved job attempts, worker/token, outcome and exact private error text |
| events | Ordered private audit, including source-staging failure evidence |
| outbox | Ordered, idempotent Post Office status projections and reporting lease/budget |
| report_attempts | Persisted reporting attempts, including crashes before response |

Original bytes are fsynced and independently hashed before the accepted job,
targets, audit and outbox are committed. Only then can the worker claim a job.
A missing source or unavailable object store produces a durable MANUAL REVIEW
job, never a safe-source receipt. The original instruction, expected source hash
and private error are retained. restore_source accepts only bytes matching the
original hash and does not itself release the job. A failure of SQL acceptance
is not an accepted job; the caller
must retain its original outbox and the intake can be retried with the same ID.
Staged objects left by rejected/uncommitted intake are retained as orphans for
review, not silently removed. No binary bytes are stored in transaction rows.

A PostgreSQL control-row lock (SQLite BEGIN IMMEDIATE in local tests) serializes
duplicate detection, budgets and claims. A token/expiry lease fences stale
worker updates. External calls occur outside SQL transactions. Effect identities
are exclusive across jobs. Target completion never projects overall completion
until **all** required targets have independently passed verification.

The external adapter contract requires immutable effect IDs with atomic
create-if-absent semantics. For a future real Drive uploader, reserve and persist
a Google-generated file ID before upload and GET that ID during recovery.
Search-only deduplication is insufficient after an uncertain upload. An expired
worker cannot be prevented from finishing an already-started external request;
server-enforced immutable IDs prevent a replacement worker creating a duplicate.

State flow: RECEIVED -> QUEUED -> PROCESSING -> WRITE REPORTED -> VERIFIED COMPLETE.
Exceptions: RETRY PENDING, PARTIALLY COMPLETE, BLOCKED, MANUAL REVIEW, FAILED,
CANCELLED. Successful API responses are ignored for completion: a new independent
read checks parent, identity/name, size/hash, permissions and duplicate count.
Record effects use a synthetic immutable-record adapter; production mutable
register updates still require revision/CAS implementation and review.

Retries are capped at three job attempts, durably reserved before effects, with
30s then 60s exponential backoff. Reporting has its own three-attempt budget,
also reserved before calls, with read-first recovery. Unknown outcomes are
reconciled before any further create. Policy/permission failures stop. No safety
control is bypassed by reviewed release; the original adapter must permit the
operation. Review preserves attempts and original errors. Exhaustion cannot
reset the budget. Jobs remain queryable if every Google projection is unavailable.

The existing Post Office tables receive schema-checked keyed projections through
an injected gateway. Partial/lost reporting responses replay stable row IDs;
per-job event ordering prevents old QUEUED state overwriting completion. Other
jobs can progress while one reporting event is held. Reporting pending is
explicitly distinct from verified underlying filing. The origin API retrieves
jobs using their conversation as well as individual job ID. It does not claim
delivery to a specialist chat or a live owner Inbox notification.

## Security report and remaining risks

- Fixed synthetic owner; only FOOD-CHEF and SYS-POSTOFFICE. Five distinct jobs,
  three attempts, one active controlled worker. Stopped by default.
- Bounded synthetic source signatures and synthetic-prefixed names/IDs prevent
  accidental real-record use. The A58 fixture is a new harmless one-page PDF.
- API needs an independently supplied 32+ character test token. No token is in
  source or logs. This is single-owner fixture authentication, not production
  tenant/RBAC. Callers must not expose the service publicly as production.
- Raw exception strings stay in private SQL attempt/audit rows. Institutional projections
  contain safe failure codes and correlation/evidence references, not raw errors,
  documents, health data or credentials. Production needs retention, encryption
  and a restricted diagnostic-reader role for these private error records.
- Local object directory is 0700 and files are created with private temporary
  permissions, atomic immutable links, fsync and hash readback. This is not
  encryption, approved cloud storage or a demonstrated cross-region backup.
- No Google credentials or live Google transport are included. The injected
  Google filing adapter and Post Office gateway are exercised with independent
  durable destination/sheet fixtures. Production implementation needs SDK timeout,
  actual policy/permission error classification, immutable Drive IDs, exact
  target allowlists, schema/revision guards and independent API acceptance.
- Sheet permissions are file-level. A row allowlist in application code does not
  reduce the underlying credential's access. IT must review the actual gateway
  principal, Google scopes and private source/object permissions before release.
- Static test database suffixes are an accidental-use guard, not an access-control
  boundary. Production must use separately approved credentials and migrations.
- No runtime scheduler, hosted worker activation, real Chef AI, purchases or
  external messages. No real A58 re-upload. Existing file
  `16Vxj7CQUUi2WFzCs-_VLTCZj0PsxVMqK` remains untouched.
- The original OpenAI tool safety block remains diagnostically unresolved. These
  changes make a similarly classified failure durable; they do not establish
  its cause, imply an OAuth/network fault or clear the real incident.

Production release additionally requires disposable PostgreSQL test evidence,
authenticated hosted acceptance, private original-file storage, database/object
restore proof, exact gateway permission review, cost/expiry limits and a tested
operational stop/rollback. None is implied by local unit-test success.
