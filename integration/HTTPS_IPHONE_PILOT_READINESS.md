# HTTPS iPhone synthetic pilot — readiness gate (17 October 2026)
Status: NOT DEPLOYED. No hostname, spending or production approval.
## Verified existing components
- Public GitHub Pages UI is static and cannot run a Python backend.
- Receiver lives at integration/receiver.py and binds 127.0.0.1, accepts authenticated PUT/GET under /v1/jobs/<uuid>.
- Test fixture store is temporary; response must say RECEIVED_TEST_ONLY, not production filed.
- UI branch sends a ZIP and verifies SHA-256 against the PUT and GET receipts.
## Necessary gates before iPhone test
1. Owner approves a bounded cloud pilot, provider, UK/EU region as appropriate, spending cap and pilot duration.
2. Deploy receiver behind valid HTTPS TLS, set strict permitted origin https://st44jdh22.github.io, issue a short-lived random test bearer token. Keep token out of repo, URL, browser persistent storage and logs.
3. Use non-sensitive synthetic text/sample image only. Never upload existing ARA, finance, relationships, IDs, or personal originals to a fixture store.
4. Restrict upload size, request timeouts, retention and authentication; use external private storage with encryption before any non-synthetic evidence.
5. From iPhone Safari confirm: correct package stored, matching digest/GET receipt, retry same bytes idempotent, altered same job ID rejected, bad token denied, bad origin CORS rejected, interrupted upload not marked received.
6. Test packet capture/logs for unintended credentials, CORS and HTTPS security; clear test tokens and fixture data when done.
7. Approve merge and production-grade storage only after independent audit and board/governance approval.
## Acceptance evidence
Save commit SHA, test run URL and logs, user-agent/iOS version, HTTPS certificate domain and expiry, endpoint exposure check, test job ID, digests, HTTP result, persisted/readback receipt, security outcomes and cleanup proof. Never mark complete based only on a branch commit.
## Current blocker
No approved HTTPS deployment or running cloud endpoint. Do not tell users the Send button transmits successfully from iPhone until the live HTTPS synthetic test passes.
