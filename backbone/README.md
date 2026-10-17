# Mi Mundo — provider-independent operational backbone (design review)

**Status:** PostgreSQL schema and offline model interface authored; neither deployed nor production-tested.

- PostgreSQL 15+ holds jobs, evidence metadata, references, handoff status and audit; original image/video bytes belong in **private object storage**, not SQL.
- The **existing Post Office** remains the only authorised routing/execution engine. This database stores references to Post Office messages, not a replacement dispatch queue.
- A narrow authenticated intake API will verify uploaded package hashes, insert metadata transactionally, save originals, verify readback and recover interrupted uploads.
- Model inference is pluggable behind `ModelProvider`. A self-hosted model (e.g. Ollama-compatible service), commercial API or model-free rules engine can implement it. No model decides whether payments, writes or routing are authorised.
- Existing Google Sheets and departmental masters remain authoritative until explicit migration and dual-read reconciliation. No financial data migrated here.
- Postgres record commit and object-store writes cannot be one SQL transaction: use PENDING, independently verified bytes, reconciliation and idempotent retry.
- Security review required: separate DB roles, row-level/tenant scoping if applicable, restricted private bucket, encryption, backups/restore, retention, secret management, resource limits, schema migrations and operational monitoring.
- Notably source photos from ChatGPT are **not** automatically available; intake must be from a supported direct capture/upload channel. No passwords or model API keys belong in client HTML or Git.
- The initial SQL is schema only, without a live database to execute against. Check SQL in a real ephemeral PostgreSQL instance before any production approval.

Test provider contract from repository root:
`PYTHONPATH=backbone python3 -m unittest backbone/test_contract.py -v`

**Release gate:** identify hosting ownership, acceptance tests for real SQL+blob storage, authenticated signed per-session uploads, secure model adapter, backup/recovery verification, approvals and IT Secretary sign-off. Do not merge automatically.
