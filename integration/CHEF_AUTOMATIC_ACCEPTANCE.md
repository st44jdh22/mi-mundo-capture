# FOOD-CHEF automatic local acceptance — Issue #9

Implementation: `review/food-chef-automatic-roundtrip`, stacked on draft PR #10
at `88ad8975b5a276adbaa2846a24ca582472988f62`. That PR builds directly on
PR #8 at `c93c22fd70284ebbb1ea6851b82305819ca12898`. No upstream merge.

## Run the working software

From a disposable checkout with Python 3.12:

```sh
python -m pip install -r integration/recovery_requirements.txt httpx
python integration/run_chef_automatic.py
python -m unittest discover -s integration -p test_chef_automatic.py -v
```

The executable starts a separate loopback HTTP actor process and an attended
background dispatcher. It submits TWO instructions through the existing
owner-authenticated Chef app API before processing. No sender dispatch, action,
ACK or reply operation is needed after submission. Polling is read-only.
It asserts two actor effects, two signed ACKs, two replies with the original
`reply_to` message IDs in the original thread, and persistence after reopen.
Every process stops and all temporary files are deleted on exit. No hosted
service, model, Google access, real food record or real document is involved.

## Exact existing integration points reused

| Existing module | Reuse / change |
|---|---|
| `chef_thread.py` | Existing `Store`, owner-authenticated `/v1/chef-demo/threads` and message API, tables and `/chef-demo` conversation UI. No replacement Inbox. |
| `chef_signed_bridge.py` | `SignedChefBridge.stage/receive`, original source hash/correlation bindings, persisted signed receipts, deterministic original-thread reply. Unmodified protocol. |
| `postoffice_dispatch.py` | `SyntheticDispatchOutbox.prepare_from_chef_store` checkpoints the canonical USER turn. This is a local staging integration point; it is NOT the historical Mac BUS-COS dispatcher. |
| `filing/service.py` | Existing jobs/targets/leases/fencing, STOP, five-job/three-attempt caps, independent target verification and ordered durable reporting outbox. Adds fresh STOP/lease checks for reporting and guarded multi-write publishers. |
| `filing/adapters.py` | Existing `SyntheticRecordAdapter` verifies immutable receiver identity, bytes and hash. `PostOfficeStatusAdapter` now checks the reporting guard before EACH unsent projection write. |
| `filing/storage.py` | Existing fsynced private local synthetic-source retention, unchanged. |
| `recovery_api.py` and `filing/api.py` | Inspected existing Recovery Inbox/job endpoints. These are NOT silently connected to the new receiver. Filing status remains retrievable by the existing origin/job contract. The demonstrated reply surface is the existing PR #6 owned Chef conversation. |

`chef_automatic.py` is the narrow new coordinator and HTTP adapter. It derives
stable job/intake IDs from existing staged deliveries, invokes the filing queue,
and returns results through its existing reporting outbox. Intermediate outbox
events do not invent Chef replies. Non-final status remains in the queue/status
contract; final signed replies use `InboxReturn` and original thread readback.
There is no new institutional queue or Google Sheet.

`chef_receiver.py` owns a separate disposable SQLite receipt/effect store.
`POST /deliver` requires its delivery principal; `GET /effects/{id}` requires a
different read principal. The fixed action is `PREPARE_SYNTHETIC_QUESTION`: persist
the existing bridge's synthetic dietary-question text, once per delivery.
The receiver commits ACK BEFORE the action, commits an immutable effect, reads
it in a fresh transaction, then persists RESULT. The dispatcher independently
GETs bytes/metadata and validates both signed envelopes before final return.
Queue acceptance, actor ACK, action verification and Inbox projection remain
separate records. Existing filing status `department_acknowledged=False` is not
relabelled; actor proof lives in the bridge/receiver receipt records.

## Verified local evidence

- PR #10 regression: 35 SQLite filing tests passed; 35 PostgreSQL cases skipped.
- New automatic/SDK-seam/STOP suite: 18 tests passed.
- Full integration suite: 180 collected, 143 passed, 37 PostgreSQL cases
  skipped. Backbone: 45 passed. Total executed passing tests: 188.
  CI reruns the full suite and disposable PostgreSQL filing contract.
- Executable real HTTP process demonstration passed: 2 instructions, 2 ACKs,
  2 independently verified effects, 2 original-thread replies, reopen passed,
  zero paid model calls. This is local process/HTTP evidence, NOT hosted proof.

Tests cover overlapping requests in one/two threads, duplicate concurrent
HTTP deliveries, receiver ACK commit then crash, lost action response, dispatcher
crash after remote effect, timeout exhaustion, wrong credentials, altered signed
result, reporting outage/restart, STOP before dispatch, STOP before action, STOP
between ACK and result projection, STOP between Post Office table writes,
default-stopped state and loopback allowlisting. Existing suites retain the
PostgreSQL queue contract, budgets, stale leases and origin isolation checks.

## Security, recovery and rollback boundaries

All ephemeral test credentials are generated in memory, never committed/logged.
HMAC reuses the existing bridge fixture protocol: the verifier holds a shared
key. Separate-process, authenticated synthetic actor evidence does NOT establish
production non-repudiation, workload identity, tenant isolation or a live Chef AI.
Persisted receipt validity is five minutes; expired/unverifiable receipts remain
held for review, never silently re-signed by the dispatcher. Automatic future
recovery beyond that receipt window needs a reviewed renewal protocol.

Both queue and receiver default STOPPED. Local demo explicitly enables only its
disposable synthetic fixture. STOP blocks unsent writes; already-sent remote
requests can still commit and must be reconciled by immutable identity.
Permission/policy failures require review; transient work has three attempts.
One active filing/reporting lease at a time; two accepted instructions overlap
in the queue while processing remains serial. No multi-worker claim is made.
The test runner terminates its actor; rollback is STOP + terminate + retain
state for reconciliation, then return to the parent review branch. No schema,
Dockerfile, Railway runtime or production migration is activated by this PR.

## Optional model adapter and exact next dependency

`chef_agents_adapter.py` prepares a replaceable OpenAI Agents SDK planner: explicit
approved model, no tools/handoffs, one turn, ten-second outer timeout, tracing off,
typed allowlisted action. It is disabled unless separately approved, and is NOT
called by transport acceptance. Tests inject a fake SDK runner; actual installed
SDK/model compatibility and paid inference remain UNVERIFIED. The deterministic
receiver executes the allowlist, not arbitrary model tools. SDK dependency/version,
identity, API key secure-store pointer and cost bound require review before wiring
it into the receiver. Official API reference consulted:
https://developers.openai.com/api/docs/guides/agents/running-agents

Next technical step is hosted integration, not another local transport design:
replace the deliberately loopback-only/disposable-SQLite receiver transport with
reviewed service authentication/HTTPS and durable hosted receipt persistence,
connect the selected owned Inbox runtime, and run this exact fault contract on
an isolated PostgreSQL-backed environment. The current hosted Recovery Inbox is
not connected by this PR; no supported cross-ChatGPT-thread push is claimed.
The historical Mac dispatcher and institutional Google projection transport are
also not present as authenticated live adapters in this repository.

No further Stephen approval is needed to review/extend this local synthetic PR.
Before hosted activation: concrete environment/service/database IDs, scoped
service principals, migration/restore/rollback evidence, TLS/network policy,
expiry, shutdown operator and exact incremental cost must be assembled for a
separate bounded approval. Existing production release HOLD remains in effect.
