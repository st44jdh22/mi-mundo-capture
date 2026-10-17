# Receiver prototype — implemented and locally tested

Python 3.11+ standard library. `receiver.py` implements authenticated PUT and GET /v1/jobs/{job_id}, exact configured capture-origin CORS, a 100 MiB compressed/expanded package limit, existing package validation, exact-byte retry/conflict detection and readback before issuing a receipt. Eight unique unittest methods pass across receiver and validator; validation test includes eight invalid-package subcases. HTTP tests use real loopback requests with synthetic packages, not mocks.

All success receipts say RECEIVED_TEST_ONLY, routed=false, departmental_updates=false and production_evidence_filed=false. FixtureStore is NOT the production evidence adapter. Original ZIP + test receipt are temporary test fixtures, not another departmental index. CLI requires --serve-test, binds only to 127.0.0.1, and removes its temporary directory on ordinary shutdown. An abrupt kill may leave temporary files; therefore synthetic/non-sensitive fixtures only. No Google/API keys, user media, actual job contents or token committed.

Run tests from repo root: `python3 -m unittest discover -s integration -v`.

Local manual test: set MI_MUNDO_TEST_TOKEN to a fresh random value of at least 32 characters in the receiver process environment, then `python3 integration/receiver.py --serve-test --port 8766`. Never put tokens in GitHub, query strings or public frontend source. No token persistence/client configuration UI is implemented.

## Proposed next test deployment (not performed)

A foreground receiver on Stephen's existing Mac, using a suitable existing Python runtime. Separate port 8766; no changes to installed Post Office service, LaunchAgents, credentials, quota or worker. A temporary Cloudflare Tunnel supplies the HTTPS transport. Application bearer authentication remains mandatory, including receipt lookup; the tunnel URL alone grants no upload/read access. No public receiver is running. This is a finite attended test, not production hosting. Mac/runtime/cloudflared presence and tunnel operation remain unverified.

Official tunnel reference checked 17 October 2026: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/ . Quick tunnels are temporary development URLs, change after restart and stop with the tunnel process. cloudflared must be installed; no install has occurred. Email-authenticated tunnel mode would need separate browser/CORS compatibility testing and is not assumed working for this cross-origin app.

Before an iPhone test: approve the precise temporary receiver/tunnel operation under the existing charter's new-service/deployment gate, verify runtime/access on Mac, prepare protected per-session client configuration and connect a staged capture build. Frontend currently remains v0.3 and disconnected. Do not ask Stephen to copy backend code. If direct Mac execution is unavailable here, one user-run setup action will be necessary; GitHub write access cannot start a Mac process.

Acceptance: one synthetic package uploads; receipt lookup verifies same job/digest; repeat returns original receipt; altered same-ID package rejects; missing credentials reject; stopping tunnel ends access; stopping receiver clears ordinary test fixtures. No departmental action or verified Drive evidence filing is claimed. Production still requires accepted existing evidence storage/index adapter, permissions/retention, hosting/auth review and actual Post Office operation mapping. This prototype is not a production-hardened HTTP service and must not accept sensitive media.
