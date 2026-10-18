# Mi Mundo — durable recovery queue and functioning Inbox: synthetic milestone

**18 October 2026 · REVIEW ONLY**

This connects a recoverable SQL job/target backend to a real HTTP Inbox API and a responsive browser screen. It is **not** connected to real Google Drive records, ChatGPT conversations, the Post Office or private evidence storage. Synthetic fixtures only; no user originals or medical details permitted.

## Functions implemented

- 3-target deterministic synthetic intake, unique UUID and source digest, one target intentionally policy-blocked.
- SQL persistence (SQLAlchemy supporting PostgreSQL with `psycopg`; SQLite file is supported **only for local fixtures**).
- Per-target `PENDING`, `RETRY_WAIT`, `POLICY_BLOCKED`, `AUTH_BLOCKED`, `CONFLICT`, `VERIFIED` checkpoints. Read-first idempotency and separately committed synthetic result permit lost-ack recovery.
- A **real background poller inside the server process** checks queued synthetic work independent of any open browser tab. Safety-denied targets remain held; the model cannot override the safety gate. Single-worker/replica design only: no distributed claims, leases or production authorisation.
- Durable server-side Inbox notifications: generic `ATTENTION` event retained while job incomplete, `RESOLVED` event after all 3 synthetic readbacks; attention badge drops to zero. Read receipt endpoint. Polling UI while active and refresh on network/reopen; not APNs/Web Push.
- Explicit synthetic review fixture release endpoint. Only unblocks simulated policy denial; real platform checks remain intact. No route exists for real user content.
- Bearer pilot token supplied through server environment, entered by user for each browser page session and never embedded in publicly served JS or persistent browser storage. Still **not sufficient authentication for production or multi-user personal data**.

## API endpoints

| Endpoint | Function |
| --- | --- |
| `GET /healthz` | Read-only mode/storage/worker errors; no secrets |
| `GET /demo` | Synthetic HTML/JS Inbox screen |
| `POST /v1/demo/jobs` | Generate exactly one 3-target fixture, no request body |
| `GET /v1/jobs/{uuid}` | Job checkpoint/readback statuses |
| `GET /v1/inbox` | Stored Inbox events, active attention count |
| `POST /v1/inbox/{event_id}/read` | Mark event read (does not clear active issue) |
| `POST /v1/demo/jobs/{uuid}/resolve` | Explicit simulation-only reviewer confirmation |
| `POST /v1/demo/jobs/{uuid}/tick` | Controlled processing tick for acceptance checks |

All non-health/demo endpoints require `Authorization: Bearer <temporary-secret>`. The `/demo` page serves from the **same origin** as the API; no cross-origin privileges are granted. Strict CSP disallows third-party scripts, origins, inline JS.

## Local verification (no network dependencies)

From the repository root, with Python 3.12+:

```sh
python -m pip install -r integration/recovery_requirements.txt
cd integration
python -m unittest -v test_recovery_api.py
```

17 local database/API unittest cases pass on SQLite file. A real loopback HTTP smoke test additionally passed (create -> background P0 attention -> explicitly synthetic resolution -> resolved notice). JavaScript syntax checked using Node 22. Browser visual/interaction test is **not yet independently verified on iPhone**. PostgreSQL smoke must pass in GitHub Actions or approved isolated test DB before staging. No claim of independent cloud backup or restore outside fixture SQLite online-backup test.

## Isolated synthetic PostgreSQL CI

The draft `.github/workflows/recovery-inbox-contract.yml` provisions disposable PostgreSQL for schema and 3-target execution, with no real user content or secrets. A passing run is not assumed until evidence is checked in Actions. Avoid mixing SQL fixture tables with the eventual canonical schema: migrate/adapt to authoritative versioned tables only after IT review.

## Railway staging gate

The live `synthetic-intake-receiver` is a **separate legacy test** hosted by Railway with EPHEMERAL package bytes, no volume/database. **Do not change or redeploy it** for this milestone. Before exposing the new pilot on Railway, provision isolated PostgreSQL (or otherwise durable private DB), verify credentials are environment-scoped and never served, restrict to one instance and synthetic mode, set `MI_MUNDO_DATABASE_URL`, `MI_MUNDO_TEST_TOKEN` server-side, use `Dockerfile.recovery`, and require explicit IT/release cost approval. Do not use SQLite on a disposable container filesystem and call it durable. No private originals permitted at any stage.

## What remains to earn production acceptance

1. Approved private object storage and independently restorable backups for actual audio/photo/document originals.
2. Owner-scoped authentication and least-privilege per source, user, domain and department; rotate credentials, auditing, traffic limits and abuse protection.
3. PostgreSQL migrations, row-level/concurrency locks, multi-replica leases, deduplication, transactional outbox, bounded retries and operational monitoring; safe schema reconciliation with existing PR #2.
4. Exact authorised Google Docs/Sheets adapter with readback, version/row collision checks and classification of tool-level policy-denied versus transient API failures, without bypassing safety controls.
5. Post Office metadata-only routing, genuine acknowledgements and verified departmental record updates. Current test Inbox is **not** a Post Office Inbox.
6. Actual iPhone local-first capture, native/background reliability evaluation, safe notifications, restore drill and security review before real personal use.

Status: **coded and locally tested prototype** → real PostgreSQL+Railway+phone acceptance **pending**, no financial/production authorisation assumed.