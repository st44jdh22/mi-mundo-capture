# Mi Mundo → Head Chef conversation MVP (synthetic)

This is a standalone **local prototype**, not the production Post Office or a live Head Chef AI. It persists synthetic conversation threads in SQL (SQLite locally; PostgreSQL DSN accepted with psycopg), uses a test bearer credential, and replies from a scripted fixture. No real private, food, or medical information should be entered. The `send` route only records synthetic messages; the demo's simulated response route provides scripted replies; no independent departmental worker/Google Sheet action exists.

## Run locally

```bash
python -m pip install fastapi uvicorn sqlalchemy httpx
export MI_MUNDO_TEST_TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(40))')"
python chef_thread.py
```

Open http://127.0.0.1:8078/chef-demo and paste the generated local test token. The script as written listens only on loopback. **Do not share the token or expose this server to the public Internet.** For a remote deployment, use an approved and reviewed scope-limited identity instead of the single static token.

Tests: `python -m unittest -v test_chef_thread.py`.

## Verified locally, October 18, 2026

8/8 tests passed with independent SQLite storage/reopen, duplicate replay, changed-payload conflict, wrong-owner rejection, scripted multi-turn conversation and unauthenticated API rejection.

## Important limitations

- `CHEF_SIMULATOR` is **not** a real departmental acknowledgement. `QUEUED_SYNTHETIC` is **not** the existing Post Office queue.
- This is a reference service, deliberately separated on `review/chef-conversation-mvp`; not deployed to Railway and not merged with existing PR #4.
- No original image/audio archive, actor-signed departmental reply, notification delivery, production tenancy/consent, migration or hosted acceptance.
- Further integration MUST use the existing institutional Post Office for dispatch and correlate thread_id, intake_id, delivery_id, signed receipt and reply_id. IT Secretary must approve identity, data access, expiry, retry cap and stop switch before any hosted Chef worker is enabled.