# Filing recovery acceptance — 19 October 2026

Technical owner: Post Office Systems Engineering Lead.
Existing incident ESC-20261019-A58-CONTRACTOR-BRIEF-01 and engineering action
ACT-20261019-PO-A58-RELIABILITY-01. **Development acceptance only.**

## Actual local evidence

Python 3.12, SQLAlchemy 2.1.5, FastAPI 0.148.0, psycopg 3.3.6, SQLite files and
independent destination fixtures. No live Google write, hosted test, worker
activation, new credential, production migration or real A58 re-upload.

- 34 new filing acceptance tests executed and passed on SQLite.
- 90 pre-existing integration tests passed alongside them.
- 45 backbone tests passed.
- 36 PostgreSQL test cases were skipped locally because no disposable server
  was supplied (34 filing cases and 2 existing integration cases).
- Python compilation and whitespace checks passed.
- The executable A58 and Head Chef demonstration passed; its actual output is
  retained in `docs/filing-acceptance-evidence.json`.

The full integration command runs 160 cases: 124 execute, 36 skip. Combined
with the backbone suite, that is **169 executed passing tests**, not 205
executed tests. The PostgreSQL workflow is supplied but a green CI run must
be independently observed before claiming PostgreSQL acceptance.

Local PostgreSQL installation was attempted for isolated testing and blocked
by environment setgroups/setuid permissions. No escalation, existing hosted DB
use or infrastructure workaround was performed. GitHub CI uses a disposable
PostgreSQL 16 service and no production credentials.

## Required scenarios

| Scenario | Demonstrated result |
|---|---|
| Normal filing | One synthetic PDF effect; independent parent/name/ID/size/hash/permission readback |
| Temporary upload failure | Durable source/job/attempt retained; due-time retry completes |
| Policy/security block | BLOCKED; exact private error retained; no automatic retry |
| Permission failure | BLOCKED; separate reviewed continuation preserves attempt history |
| Duplicate submission | Same immutable request returns original job; one destination effect |
| Changed replay | Conflict; original job and targets preserved |
| Crash before write | Lease expires; original source resumes |
| Crash after write before acknowledgement | Existing immutable effect detected; no repeat upload |
| Source absent or object storage down | MANUAL REVIEW with instruction/hash/error, no fabricated safe capture |
| Multiple records | Receipt/file, inventory and activity independently verified; partial results survive |
| Reporting outage | SQL result remains retrievable even when Google-style failure logging fails |
| Reporting crash/lost reply | Reserved reporting attempt survives restart; stable row IDs reconcile |
| User returns | Original conversation lists accepted jobs and accurate pending/verified states |
| Backups | SQLite online backup + original-object restore resumes the same job |
| Worker controls | Five-job cap, three attempts, single active claim, lease fencing, cancellation and persistent stop |
| Wrong access/schema | Wrong owner/conversation and changed institutional headers rejected |

The A58 demonstration uses a new harmless one-page PDF; it injects upload
failure and an exception-reporting failure, reopens recovery state, and
verifies completion without another destination effect. It does not use the
real eight-page brief or file ID 16Vxj7CQUUi2WFzCs-_VLTCZj0PsxVMqK.

The Head Chef demonstration simulates receipt intake and inventory/activity
updates in independent test destinations and retrieves the outcome by origin.
It explicitly reports department_acknowledged=false: a filing test result is
not an authenticated reply from the real Head Chef.

## Outstanding release evidence

Disposable PostgreSQL CI, real Google gateway/CAS implementation and adapter
acceptance, private cloud-original storage and restore, production principal
and tenant authorisation, hosted origin Inbox delivery, cancellation of actual
in-flight requests and operational monitoring remain unverified. The optional
HTTP API uses test-only owner-token auth, not production identity.

No production merge/deployment/migration is requested by these local results.
The original safety-block diagnostic remains open separately; this service
does not establish its cause or bypass it.
