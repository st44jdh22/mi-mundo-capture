# HS-META-001 — Bird one-photo proof (NOT LIVE)

Commission: [Issue #14, Zara, 10 November 2026](https://github.com/st44jdh22/mi-mundo-capture/issues/14#issuecomment-6774096280).
Engineering master: [HS-META-001](https://docs.google.com/document/d/1iUOvvSCEFKfQPrfdRdI4BOaNJep5z2eFmoKlt8an44M/edit).

This is a small local experiment using the existing v0.3 validator and
`receiver.FixtureStore`. It adds no application, authoritative record service,
HTTP listener, live adapter, dependency or automation. Its base is the existing
synthetic transport branch from draft PR #16. Native Meta DAT draft PR #17 and
the original iPhone PR #13 are separate and unchanged. All PRs remain unmerged.

## What runs

`bird_synthetic.py` accepts only its in-process `MockBird` and `MockWork` doubles.
A fabricated signed event is checked against an explicit local workspace,
BSUID sender, recipient, subscription and scope selection **before media access**.
The selected workspace/message/media/destination tuple determines a stable UUID.
Event URLs are never opened. No numbers, customer messages or live credentials
are included. The signing key is publicly known synthetic test data.

The fetched JPEG is preserved without conversion inside `original.zip`, with
MIME, byte count, attachment ID, SHA-256 and explicit synthetic provenance. The
local fixture oracle pins the expected photo hash; **Bird does not supply this
test oracle**. A future live adapter must define its own trusted correlation and
integrity policy rather than pretending the event includes a provider checksum.
These are original **mock-returned bytes**, not a claim about untouched camera
originals after WhatsApp processing.

The existing temporary receiver store is wrapped as the chosen destination
`sophie-work-mock-not-live`. It is **NOT LIVE** and does not address an actual
Sophie/ChatGPT Work conversation. Its receipt retains `RECEIVED_TEST_ONLY` and
false routing/production flags. The visible CLI receipt binds the package hash,
photo hash, UUID, receipt ID, workspace, sender, recipient, message, media and
mock destination. Acceptance must be followed by a separately reopened copy of
the destination package and photo before reporting verification.

Stages are `EVENT_RECEIVED`, `MEDIA_FETCHED`, `DESTINATION_ACCEPTED`, then
`INDEPENDENTLY_VERIFIED`. `status` is the current outcome; `stage` retains the last
stage reached (possibly on an earlier attempt), and `history` records prior stages.
A failed new verification can never return cached success. `FAILED`/`BLOCKED`
retain originals and diagnostic state; they never imply successful production
delivery. The mutable journal and event markers are local retry state, not a
second engineering master or permanent evidence ledger.

One worker per outbox is required. This is not a concurrent webhook service.
Journal/package publication flushes files and directories; recovery also checks
a published package if termination occurred before the media-stage journal write.
Originals are application-preserved, not protected against local tampering; tests
ensure detected corruption is retained and cannot produce success. Neither the
existing fixture receiver nor this experiment establishes power-loss durability,
access control, encryption, retention compliance or production scalability.

Duplicate deliveries reconcile by identity and exact event-body fingerprint.
Different event IDs for the same selected media do not fetch or deliver twice.
A changed event-ID replay is blocked. Distinct, out-of-order messages retain
their own identities; an older event cannot overwrite a later photo. Fresh
delivery timestamps are separate from event creation times. Lost ACKs are looked
up rather than treated as proof of failure. At most three fetch/delivery attempts
are allowed; later reconciliation of an existing acceptance remains possible.
There are no background retry loops, leases or subscriptions.

## Run without setup

From the repository root with the already available Python 3:

```sh
python3 -B -m unittest discover -s integration -p test_bird_synthetic.py -v
demo_state=$(mktemp -d /private/tmp/hs-meta-001-bird.XXXXXX)
python3 -B integration/bird_synthetic.py --state "$demo_state" --mock-failure readback
# Expected exit 1: DESTINATION_ACCEPTED, FAILED; original and receipt are retained.
python3 -B integration/bird_synthetic.py --state "$demo_state"
# A new process reopens both stores: INDEPENDENTLY_VERIFIED, same UUID/hash/receipt.
python3 -B integration/bird_synthetic.py --state "$demo_state"
# Another new process verifies again, with no duplicate delivery.
```

Run one experiment per state directory. Do not put real media in it. Keep failed
state for diagnosis; remove only that chosen synthetic directory after review.
There is no service to uninstall, account to revoke or deployment to roll back.
The fixture clock, event, package bytes and identities are deterministic; the
existing receiver correctly records its actual acceptance timestamp at runtime.

## Evidence matrix — 10 November 2026, Mac.powerhub / Darwin

| Boundary | Public documentation or supplier statement | Locally verified | Live proof still missing |
| --- | --- | --- | --- |
| Events | [MCP Events](https://bird.com/docs/ai/mcp-events): envelope, workspace-wide WhatsApp events, scopes, signed deliveries | Fabricated envelope; local signature/size/freshness checks; workspace/sender/recipient/subscription/scope rejection before fetch | Authenticated `events/list` payload schema, subscription challenge/lease/renewal/revocation/replay behaviour |
| Media | [Receiving WhatsApp](https://bird.com/docs/guides/whatsapp/receiving-whatsapp): message/media references and retrieval; 404/410; redirect credentials must not cross hosts | Exact synthetic JPEG, MIME/length/hash/correlation rejection; missing/gone doubles | Real media retrieval, redirects, access and deletion timing; no provider HTTP call was made |
| MCP tools | [MCP server](https://bird.com/docs/ai/mcp-server) lists `whatsapp_media`; signed-in user governs access | Own injected `MockBird.fetch` interface only | Actual authenticated tool input/output schemas and account permissions; no invented tool call is asserted as compatible |
| Delivery authenticity | [Webhooks](https://bird.com/docs/guides/webhooks): signing and duplicate delivery semantics | Synthetic HMAC envelope and replay/body-conflict checks | Real signed payloads, key rotation, proxy/header handling and deployed ingress |
| Work destination | Supplier reply does not establish a selected Work conversation byte/ACK contract | Existing local fixture store, correlated NOT LIVE receipt, independent package/photo readback | Supported authenticated destination, conversation selection, media bytes and receipt; **not a real Work integration** |
| Recovery | No assumption of replayable event history | Failed delivery, lost ACK plus failed lookup, bounded retry, termination between package/journal writes and separate-process restart | Real provider/Work outages, expiry, concurrent ingress and recovery |
| Commercial/privacy | Supplier reply filed in HS-META-001: Coexistence, 30-day retrieval, PAYG/no minimum/no extra Coexistence fee | No commercial or eligibility testing | Applicable policy, number eligibility, permissions, deletion semantics, geography and final rates/volume total |

The fabricated `data` fields combine documented WhatsApp message concepts with
local routing assertions. Their names, types and nesting are **not** claimed to
be the exact authenticated MCP event schema. Likewise the test signature secret
is injected raw local bytes, not a provisioned Bird `whsec_` secret. REST webhook
`type` envelopes and MCP `name` envelopes are not interchangeable. No public
contract establishes delivery into the existing Sophie Work conversation.

## Verified checks and limitations

- **20/20 new Bird tests pass**: one photo, each missing scope, wrong sender,
  workspace, recipient, subscription, signature, timestamp, size, malformed
  content, 404/410 doubles, MIME/length/empty/changed bytes, wrong media identity,
  deduplication, changed replay, out-of-order messages, failed delivery, lost ACK,
  lost lookup, interrupted publication, actual new-process recovery, wrong
  receipt/readback bytes, corrupt originals/destination and retry limit.
- **9/9 existing validator/receiver tests pass**, **7/7 existing Node client tests
  pass**, and **5/5 existing photo/audio harness regression tests pass**. These
  existing HTTP regressions use 127.0.0.1 only. The initial sandbox run could not
  bind loopback (`EPERM`); the authorised test rerun outside that sandbox passed.
- The two existing video-dependent harness tests were **not run**: `ffmpeg` and
  `ffprobe` are unavailable. Nothing was installed; no existing test, assertion
  or timeout was altered. Native iPhone/XCTest suites were not rerun for this
  Python-only addition; their earlier results are separate evidence.
- Bird tests guard socket connection/URL-opening entry points, including the
  child restart processes. This proves those paths were unused in this test;
  it is not packet capture or a host-wide claim about zero network traffic.
- macOS `/usr/bin/sips` independently decodes the included **742-byte, 32×24 JPEG**.
  SHA-256: `5096cb4a14663a04ce7aa7ad3274b16e40dc305ad51e7e8e7956e81c7667e0c3`.
  It is the already fabricated photo from the native development fixtures,
  copied byte-for-byte, with no personal image or metadata introduced.
- Stable sample UUID: `666accb2-b0c8-5ef0-97a6-cf18c441209e`;
  receipt: `capture-666accb2-b0c8-5ef0-97a6-cf18c441209e`;
  package SHA-256: `0603ab53fc77f14bfdecfcb723ccb8c208e9b91e2dd5f10d8c273cc266552197`.

## Missing requirements before any live proposal

All items below remain **unapproved and unverified**. This list performs no setup.

1. **Lindsey review:** least-privilege Bird workspace/user/OAuth isolation;
   workspace-wide event exposure and local sender selection are different gates.
   Agree authenticated schemas, secret storage, revocation, data minimisation,
   access geography, media retention/deletion (including local copies), audit
   retention and incident handling. No new scopes are requested here.
2. **Eligibility/policy:** confirm the specific number/account's Coexistence
   eligibility and preservation of the Business app/Mac-linked devices; obtain
   the applicable Meta/Bird policy assessment for the intended AI use. Supplier
   support statements alone do not resolve permission or eligibility.
3. **Work delivery:** identify a supported, authenticated, approved destination
   contract for the chosen Sophie conversation, including exact returned media,
   attachment identity, ACK, independent readback and retry behaviour. A generic
   MCP connection or an incoming event does not prove this route exists.
4. **Dr Ada review:** provenance limitations after WhatsApp processing, original
   returned bytes, time/source labels, interpretation versus evidence and action
   approval gates. This branch performs no interpretation or downstream action.
5. **Cost:** validate current [pricing](https://bird.com/pricing/whatsapp), region,
   currency/taxes, Meta/provider fees, message types, volume, retries, storage,
   event/webhook/tool limits, wallet funding and a hard spend cap. PAYG and no
   additional Coexistence fee are filed supplier statements, not an approved
   budget, independently checked tariff or proof of a free end-to-end service.
6. **Separate Stephen approval:** only after a concrete isolated live test plan,
   fixture/number consent, retention, cost limit, failure/rollback procedure and
   both reviews. Until then: no workspace registration, binding, OAuth, MCP
   subscription, webhook, app/settings/permission change, paid wallet, real
   numbers/media, supplier contact, physical device, deployment or Railway/Render.

No message has been sent to Lindsey or Dr Ada by this implementation. Their
reviews are required handoffs, not claimed approvals. All public evidence is
fabricated; sensitive provider replies remain in the existing engineering master.
