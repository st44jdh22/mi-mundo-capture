# Mi Mundo — Offline-first capture, Outbox, Inbox & Post Office contract v0.1
**Status:** Engineering review, SYNTHETIC FIXTURES ONLY. Nothing in this document authorises production intake, automatic routing, paid deployment or access expansion. Existing production chat and Cloudflare/Railway apps unchanged.

## Non-negotiable user journey
1. Person captures a photo or starts **raw audio recording**. Preserve original bytes on the device *before* any cloud speech transcription, model inference, upload or document conversion. Plain dictation mode alone is **unsafe** as the only recording: its service can stop in a low-signal area and the source audio may be unrecoverable. Use media recording with on-device retention; speech-to-text is a secondary, retryable enrichment step.
2. On finalising a capture, assign a UUID; generate *one immutable package* with original media, user-supplied text if present, timestamps and SHA-256 digests. Save the package in the local Outbox with readback and SHA-256 verification before enabling Send. If local storage fails, explicitly warn and offer manual original-file saving; never say 'saved'.
3. QUEUED -> SENDING -> either UNCONFIRMED or test RECEIVED_TEST_ONLY. A lost network response means unknown, **not confirmed failure**. Keep the exact original package and UUID. Before retry, authenticated GET for a receipt; only re-PUT if not present. Never quietly discard, auto-delete or rebuild a different ZIP with the same UUID.
4. User-facing local Outbox must show 'Saved on this phone, not yet backed up', 'Waiting for connection', 'Upload not confirmed—tap to retry', 'Test receiver confirmed—temporary server only', and later 'Permanent storage verified' **only after a separate durable evidence adapter readback**. Test receipt MUST NOT use the durable/complete label.
5. Actual **server-originated** Inbox receives a message after durable evidence commit, transcription done/failed, clarification requested, existing Post Office handoff accepted, department acknowledged, and departmental records independently reconciled. Keep a message/thread even if push notification fails.
6. When online, inbox sync uses authenticated paginated event cursor and message IDs, not replacing entire chat histories. Client can reply by stored voice recording, with original audio preserved; text extraction later. Push/alert optional, rate-limited, private on lock screen. An offline phone cannot receive server push until connectivity returns; local unsent-state indicators work whenever the app can run.

## Browser reliability boundary
The IndexedDB prototype at integration/offline-outbox.mjs persists Blob bytes and checksums, but iOS may clear website data, storage quota may fail, Safari private modes may not persist, and a tab can be killed **during** recording before finalisation. Web Background Sync and service worker scheduling on iOS are not unconditional guarantees, nor is unlimited recording/media storage. For meaningful prescription/client data, production acceptance must explicitly choose and test a more durable approach: **native iOS app** with app-managed local files + proper background transfer, or a confirmed platform-level Save-to-Files capture-first workflow, while preserving the same shared API. Regardless of client choice, an independent private cloud archive/backup remains necessary.

## Draft service API (not yet live)
- POST /v1/intake -> auth/session, idempotent job creation and upload permission; never embed long-lived bearer token in public HTML
- PUT /v1/evidence/{job_id} -> authenticated original exact bytes, digest verified, provisional ACCEPTED only (server durable write pending)
- GET /v1/jobs/{job_id} -> states RECEIVED, EVIDENCE_VERIFIED, AWAITING_CLARIFICATION, POST_OFFICE_SUBMITTED, POST_OFFICE_ACKNOWLEDGED, DEPARTMENT_RECONCILED, FAILED; response includes immutable digest, receipt, event cursor and durable status
- GET /v1/inbox?cursor=... -> user's permitted messages only, chronological cursor and stable message IDs
- POST /v1/inbox/{thread_id}/replies -> authenticated idempotent text/voice evidence reply; server must ensure same user owns thread
- Notification worker -> transactionally committed message -> delivery outbox; retries safe and audited. Notification payload should be generic for health/highly private information.

## Existing Post Office integration
Mi Mundo does **not** become a second departmental dispatch engine. It submits an authorised *intent/evidence reference* to the EXISTING Post Office API/adapter (where implemented/approved), using stable correlation ID and idempotency key. Its own Inbox displays the authorised Post Office's actual accepted/acknowledged/completed statuses and authoritative departmental record references. A proposed handoff is not a delivered message or completed record update. Until APIs exist, use human-reviewed handoff with explicit pending state.

## Security, safety and long-term scale
- Separate device local cache, private per-user evidence object storage and PostgreSQL metadata. Do not store large images/audio/video as SQL blobs.
- Access control and privacy classification; account-level auth with rotation; encryption, short-lived signed URLs, HTTPS, file-size/quota limits and upload malware validation; never public media bucket.
- Keep structured rule candidates (provenance, confidence), explicit rule approval history and full audit; AI output is not execution permission. Differentiate image recognition from user-approved fact.
- Local storage requests can fail; always check committed IndexedDB transaction and readback, never just capture in JavaScript memory. Reopen/recovery tests after app restart.
- Use idempotent worker/outbox transactions so backend restarts, retries and model outages do not duplicate jobs or departmental writes. Persistent messages also need retention/backup and independently testable restoration.
- Archive media by object storage lifecycle policy only after approved retention/privacy policy; never treat housekeeping as silent deletion.
- Future camera glasses, Siri trigger and other capture devices use the same source-authenticated intake contract; passive location/recording strictly opt-in.

## Synthetic acceptance suite before any production migration
A. Camera photo locally saved while offline; page closed/reopened; exact bytes and SHA-256 match.
B. Raw audio recorded offline and saved without speech recognition; transcription failure does not erase audio.
C. Server outage/timeout creates UNCONFIRMED; UI displays pending without declaring upload success.
D. GET-first retry reconciles previously accepted PUT, using the original UUID/digest; no duplicate filing.
E. Server checksum or receipt mismatch blocks any 'verified' state.
F. Browser quota full/IndexedDB denied/private mode produces explicit warning and backup option.
G. App killed during recording: user gets accurate recovery/no-guarantee warning; evaluate native capture.
H. Restored online, Inbox sync resumes from cursor; deduped notifications, no lost clarification thread.
I. Post Office submission shows SENT/ACKNOWLEDGED/COMPLETED only on independent evidence.
J. Personal/private health and financial capture never enters public/test cloud receiver or public repository.
K. Test real PostgreSQL migration, server object-store readback and an independent restore drill.
L. Verify iPhone Safari/Home Screen/low-signal conditions and local-storage persistence; desktop unit tests are insufficient.

## Current evidence as of 18 Oct 2026
- Synthetic HTTPS Railway PUT/GET confirmed separately for one harmless photo; no permanent evidence store.
- PostgreSQL schema 001_core_schema.sql and 002_rules_inbox.sql, AI model provider contract, and local-outbox module are on a **review branch** only.
- Local Node contract tests for the outbox were run with an evented in-memory IndexedDB simulation (8 cases). Real iPhone IndexedDB reliability, background upload, voice capture, Post Office handoff, push notifications and a production server Inbox are NOT validated.
- No real personal data should be uploaded to the temporary test app; do not treat a green SYNTHETIC receipt as a backup.
