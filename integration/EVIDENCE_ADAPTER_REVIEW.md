# Universal evidence adapter — offline review

Scope: candidate code only; no deployed service, no Google Drive evidence storage, no Post Office writes. This review branch leaves GitHub Pages main untouched.

Files: `evidence_adapter.py`, `package_bridge.py`, `test_evidence_pipeline.py`. The package bridge consumes Mi Mundo capture v0.3 exports and verifies ZIP member counts, manifest, attachment lengths and SHA-256 before writing synthetic local test files. The local SQLite fixture store has exact job+attachment replay identity and independent byte hash readback. Outputs deliberately say `FILED_LOCAL_TEST_ONLY`, `production_evidence_filed=false`, `routed=false`, `departmental_updates=false`.

To test: `cd integration && python3 -m unittest test_evidence_pipeline -v`. 19 tests were run successfully against the corresponding local development package before this branch was written; the separately reconstructed GitHub branch should be re-run and reviewed independently before any merge.

Known limitations and review blockers: no durable Drive connector/registry, no original media transferred; the package multi-attachment write is not atomic, so a partial failure can leave a subset saved; `received_at` currently participates in strict metadata equality so retries with a new received_at will conflict; SQLite fixture not certified multihost durable; ZIP checks need alignment with the canonical `validate_job.py` and safe handling of unsupported archive entry types; potential EXIF/privacy/retention policies unresolved. The evidence adapter itself must never run client-side on public GitHub Pages. Neither an HTTP receiver integration nor a live Transmit button is included.

Ownership: Capture Engineering reviews receiver interface and deployment; Universal Intake specifies evidence filing and business dedup; IT Secretary coordinates canonical folder/register decision; existing Post Office owns approved routing. Do not merge into main or enable broad worker scope without independent review.
