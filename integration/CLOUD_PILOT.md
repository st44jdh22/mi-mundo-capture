# Cloud-first receiver pilot — prepared, not deployed

The strategic direction supplied in project context is cloud-first, provider-independent Mi Mundo, with final vendor/cost/production deployment separately approved. It supersedes using Stephen's Mac as the primary intended host. The prior Mac/tunnel file remains historical local-test guidance only. Nothing has been installed on the Mac.

## Implemented

- Provider-independent Python ZIP validator + authenticated local HTTP test receiver.
- Staged JavaScript CaptureClient: HTTPS receiver-origin configuration, token held in memory, redirects refused, request timeout, 100 MiB pilot package bound, stable Blob retained per job ID.
- GET before PUT; checksum/job-matched test receipt; independent GET after PUT; lost PUT response reconciled by GET without automatic resend. Changed package under the same ID rejected. Unknown state preserves local job.
- Client explicitly accepts RECEIVED_TEST_ONLY receipts with routed=false, departmental_updates=false and production_evidence_filed=false. This is not a production completion API.
- Seven Node client test cases passed; nine Python tests passed including JavaScript-to-Python HTTP upload, receipt, retry and exact package readback. Synthetic fixtures only. These are not browser, Safari, TLS or cloud tests.

Run `node --test integration/test_capture_client.mjs` and `python3 -m unittest discover -s integration -v` from repository root (Node + Python 3.11+ required for the cross-language test).

## Concrete first cloud test scope

One separate Mi Mundo HTTPS test receiver, using portable source and standard runtime. No weather resources or Post Office worker changes. Non-sensitive synthetic packages only, maximum 100 MiB. No model calls or departmental operations. Return only test receipts after package readback. Per-session secrets configured server-side, entered into a protected staged client at runtime, never embedded in public source. Current shared test token design is temporary test authentication, not approved production identity.

Before deployment: select and approve one host/region, exact costs/caps and access method; choose finite attended pilot window and test retention; prepare host configuration, HTTPS/auth/request limits and deployment rollback. Current receiver binds loopback and uses temporary FixtureStore, so it is not deploy-ready production server software. Cloud network serving/runtime adaptation, production identity, storage and abuse controls remain work. Do not deploy it by simply exposing Python's test HTTP server to the internet.

The new existing Drive pilot folder and register were discovered on 17 October: folder 1TOx6FkixGwnl_g9g0k0PGabgk6QgJaz1, register 1w7lH_tr317MUYxDgT_HoV6eFfNh0ti1udwcToSVG8gs. Their metadata/existence is verified; their schema, service-account visibility, write authority and backend integration are not established here. Reuse them only after that source/permission review; do not invent a competing evidence index. General intake policy/receipt does not grant permission to change these records.

## Next engineering gates

1. Cloud deployment proposal: one named host with verified current capability/pricing, budget and region, minimal access, runtime, storage/retention and rollback. Vendor choice remains undecided, not silently selected by this file.
2. Harden HTTP boundary and adapt serving for selected host; keep storage/receipt API independent of cloud and AI provider.
3. Prepare staged capture UI connection: generate ZIP once per transmission attempt, hold that same Blob for recovery, configure authenticated session, surface received-test versus uncertain states. Live index.html remains unchanged/disconnected. An imported ZIP and library-level client are not yet an integrated capture UI.
4. Run nonproduction hosted upload/readback test and Safari test, then integrate original-evidence adapter and existing Post Office under their accepted contracts/authority.

No automated backup or scheduled recovery manual is created by this code change. Source in GitHub supports software recovery; it is not a backup of live evidence, credentials or authoritative departmental records.
