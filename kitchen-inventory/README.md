# Casa Hullock Kitchen Inventory — synthetic development spike

**REVIEW ONLY. NOT PRODUCTION. NO REAL STOCK DATA.**

A synthetic FastAPI/SQLite HTTP proof of the agreed ingestion → transactional stock changes → direct API read contract. This does not replace the current authoritative Chef Inventory Register, and does not connect to the Casa Hullock Home Portal, Railway PostgreSQL or live Post Office.

Run locally (Python 3.11+):
```
pip install fastapi uvicorn httpx pytest
cd kitchen-inventory
pytest -q
uvicorn api_demo:app --host 127.0.0.1 --port 8000
```
The test headers `X-Demo-Token: test-read-only` and `X-Demo-Token: test-kitchen-writer` are **public test fixtures, NOT security credentials**. Never expose/deploy this demo.

GET `/v1/kitchen/current-stock?location=fridge` returns persisted current balances without AI arithmetic. POST `/v1/kitchen/stock-events` requires a synthetic writer test token and `Idempotency-Key`; retries do not double-deduct. GET `/v1/kitchen/shopping-needs` reads confirmed balances and threshold rules.

Outstanding blockers: PostgreSQL transaction implementation and actual database integration tests, authenticated actor identification, durable outbox/ACK, restart recovery, real Portal inspection, stock reconciliation, private storage/privacy assurance, release approval.

Owner coordination: Lindsey (project lead), Zara (application/SQL), Charlotte (Post Office), Marco (kitchen authority).
