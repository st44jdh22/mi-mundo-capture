# Test-only filing service runbook

Owner: Post Office Systems Engineering Lead. 19 October 2026.
Existing action ACT-20261019-PO-A58-RELIABILITY-01; incident
ESC-20261019-A58-CONTRACTOR-BRIEF-01. No new institutional register.

## Installation and validation

Use the dedicated review branch in an isolated development checkout. Python 3.12:

```sh
python3 -m venv .venv
.venv/bin/pip install -r integration/recovery_requirements.txt httpx
cd integration
../.venv/bin/python -m unittest -v test_filing_service.FilingTests
../.venv/bin/python run_filing_acceptance.py
```

The demonstration uses temporary synthetic SQL/object/destination stores and
closes them after execution. It makes no external calls or production changes.
Do not pass the existing Railway database URL to these tests. No deployment
Dockerfile or default server entry point has been changed.

## PostgreSQL acceptance

The GitHub workflow `filing-recovery-contract.yml` provisions a disposable
PostgreSQL 16 database called `po_filing_test`. It runs the full filing contract
against that database, not the existing hosted database. The test class drops
its own test tables between cases: **never supply a real database**.

```sh
# Only after obtaining a disposable test DB connection; no secrets in chat/logs.
export MI_MUNDO_FILING_TEST_PG_URL='postgresql+psycopg://.../po_filing_test'
python -m unittest -v test_filing_service.FilingPostgresTests
```

Read the review DDL before any schema action. `FilingService(url)` does not create
tables. `initialize_test_schema()` is an explicit development action. Its new
control row is STOPPED; `set_stopped(False)` is permitted only within the
isolated synthetic harness. No live migration or unattended activation is
authorised by this runbook.

## Integrating a reviewed harness

Inject `PrivateObjects`, FILE/RECORD adapters and a `PostOfficeStatusAdapter`.
The included API factory takes these existing objects and an independent test
token; it does not initialize schema or start a worker. Intake returns 202 with
an accurate QUEUED or MANUAL REVIEW state after durable commit.
The next unrelated intake can be accepted while the first remains pending.
Invoke `run_once(job_id, 'synthetic-worker-1', objects, adapters)` under an
attended controller. Invoke `flush_reporting(adapter)` to deliver outbox events.
Do not run uncontrolled busy loops or create a background service from this PR.

Job statuses are available through `status(job, requester, conversation)` and
`outcomes_for_origin(requester, conversation)`, or the optional synthetic API.
`reporting_pending=True` means the filing result is retained but some status
projections have not been independently read back. `department_acknowledged`
is always false in this filing prototype; it does not forge a Chef receipt.

## Failure and recovery

1. Inspect job/targets, attempt history and original object hash through authorised
   private access. Inspect safe codes in institutional projections.
   If source staging failed, restore_source can retain bytes only when they match
   the original accepted hash. The job remains held until separately reviewed.
2. For RETRY PENDING/PARTIALLY COMPLETE, wait until next_attempt. The same job and
   effect identities must be reused. Never make a replacement upload to clear a warning.
3. After worker death, let the lease expire. A new claim reads the original
   destination before writing, including at the exhausted-attempt boundary.
4. Policy/permission/conflict blocks require review. Fixing a policy block must
   use the legitimate upstream permission/safety process; this worker provides
   no bypass. An explicit synthetic reviewed_release may continue an eligible
   held job without resetting attempts. Cancelled/exhausted jobs cannot be reset.
5. If a projection exhausts its three attempts, retain it for manual review. This
   version deliberately has no automatic budget reset/release endpoint. Fixing
   or replaying that outbox after review is a separately scoped engineering action.
6. Do not mark VERIFIED COMPLETE from an upload response, empty extraction,
   queued outbox notice, copied message or unverified destination.

## Stop and cancellation

`set_stopped(True)` persists the pilot stop switch. It prevents new filing or
reporting claims and the worker checks it before each document write. A remote
write already in flight may still finish: let the lease expire, inspect the
destination by its immutable ID, and reconcile before a later authorised resume.
Cancellation before execution becomes CANCELLED. Cancellation after execution
may have begun retains MANUAL REVIEW for effect reconciliation; it does not
pretend to undo a committed remote upload.

## Backup, restore and rollback

Back up transaction state **and** the original objects with an integrity manifest.
SQLite synthetic acceptance uses the online backup API plus a copy of private
objects; the restored service resumes the original job without replacing it.
For future PostgreSQL deployment use approved encrypted pg_dump/restore or
provider snapshots, plus versioned private-object backup; rehearse the pair
against a disposable restore before release. A DB backup alone is insufficient.

Stop claims before code rollback. Record the current code commit and migration
version, preserve the DB, original bytes, attempts and audit, and reconcile all
uncertain external effects before starting a prior worker. Do not DROP tables,
delete jobs or repeat completed operations to roll back a software release.
This PR is additive: no existing PR4/PR6 schema or default runtime changed.

## Release decision

Development and synthetic tests are approved. Production migration, credentials,
private object provisioning, live gateway writes, worker activation, deployment
branch merge and expenditure require a separate exact approval. Submit the
immutable reviewed commit, actual principal/scopes, target IDs, hosted acceptance,
backup restore, three-attempt/five-job caps, expiry, cost and tested shutdown.
The already-filed real A58 PDF must never be used as an upload acceptance fixture.
