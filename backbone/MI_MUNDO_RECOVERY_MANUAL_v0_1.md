# Mi Mundo — System Recovery & AI Handover Manual (v0.1)

**17 October 2026 | Draft/bootstrap | Owner: Stephen / Group Executive Office.** This is an initial recovery index and architecture; **NOT a verified backup of every department or a proven disaster-recovery system**. Do not store secrets in this file.

## First hour for a replacement AI or engineer
1. Read this manual, source control history, and existing engineering charter at https://docs.google.com/document/d/1H3ns5nhUKNhazOHQTYHBO-4z-xhJrfQxXTj5FuHf6KM/edit .
2. Inspect https://github.com/st44jdh22/mi-mundo-capture (main) and read only approved release commits. Review evidence PR #1 and SQL/model PR #2 but **do not merge or deploy** automatically.
3. Inspect Mi Mundo Control Directory https://docs.google.com/document/d/19zJOwQDMRtrZKaB5HS7Gwn__9_OPabaK1-FZelJ8jWk/edit ; existing Post Office log https://docs.google.com/document/d/1l_eUYvZMJrl0Kl8Akj7ki3U9mV96POgksrORKer7fKQ/edit ; executive agenda https://docs.google.com/document/d/1khGtsxmz2-5egnnMgjtLTlXA1gnJ0zjCKPKPXoKuJCA/edit .
4. Establish actual service accessibility and ownership. If cloud SQL, storage or uploads are not deployed, report **NOT OPERATIONAL**. No chat memory is necessary or authoritative.
5. Respect ownership: Post Office handles authorised execution; departmental masters remain authoritative until individually migrated with explicit approval.

## Mandated architecture
Captures (phone/web/glasses/authorised connectors) → independent authenticated Intake API → PostgreSQL intake/evidence metadata, immutable IDs, idempotent state and audit **plus private original-object storage** → replaceable commercial/local model or deterministic/manual rules → **existing Internal Post Office** → authoritative departments → verified readback. AI recommendations are not execution permissions. File hashes, provenance and permissions are checked on ingest, retrieval and retention.

## Working references
- Capture website https://st44jdh22.github.io/mi-mundo-capture/ . Local capture/export works; there is **no verified live transmit/upload pipeline**.
- GitHub https://github.com/st44jdh22/mi-mundo-capture . Local test receiver in integration/receiver.py is not publicly deployed.
- Offline evidence/ZIP pilot https://github.com/st44jdh22/mi-mundo-capture/pull/1 — draft, unmerged.
- PostgreSQL schema / model-neutral adapter https://github.com/st44jdh22/mi-mundo-capture/pull/2 — draft, unmerged; **no operational cloud database**.
- Mi Mundo Drive root https://drive.google.com/drive/folders/15E-ysjeSH29H_cHtKfh3j2pRCUxWVCsQ
- Evidence pilot folder https://drive.google.com/drive/folders/1TOx6FkixGwnl_g9g0k0PGabgk6QgJaz1
- Pilot register https://docs.google.com/spreadsheets/d/1w7lH_tr317MUYxDgT_HoV6eFfNh0ti1udwcToSVG8gs/edit . Headers only: photo registration write was blocked; don't claim accepted entry.
- Pilot IMG_9501.JPG Drive ID 1KOKMTgA7iui_okxDCtY8pAU5AcJOP-sg. Metadata/parent verified; original byte checksum not verified.
- IT master charter https://docs.google.com/document/d/1zKFJo42KBsvvZKzzKMzpmuGUlgqEepdfHGVJzt5yqeg/edit
- Group Master Action Register https://docs.google.com/document/d/1GkM7Ts6Pm_cnBnPublML7o6y2KblBOXrx2D0INj3VrQ/edit
- AI wearables R&D https://docs.google.com/document/d/1WWY9cGwUrTnaA9czO42Q-whn60_nK5htdlri09cGk5Y/edit

## Boundaries and source of truth
Model interface must support multiple providers and model-off mode; never expose raw credentials, allow independent sensitive-data policies and validate model outputs. Original evidence lives in authorised restricted object storage; metadata and audit in SQL. Department records retain departmental permissions. Statuses **received / validated / file stored / checksum verified / Post Office routed / department acknowledged / authoritative write independently verified** are separate. A manual Drive upload is not a live app transmission. No replacement dispatch queue.

## Security and restore
Secrets are stored only in owner-controlled vault and offline recovery kit (reference location, not values, in manual). Adopt least privilege, TLS/encryption, restricted bucket access, storage versioning, database PITR when available, separate backups, documented restore times and maximum allowed data loss. **Every backup must be reopened, checksummed and restored in an isolated environment to count as verified**. Never expand permissions or deploy without explicit approval.

## Nightly operation
An interim ChatGPT task is set to attempt a dated consolidated recovery archive at 03:00 Europe/London and email it; first check 11:00 on 18 Oct. Scheduling does **not** prove any backup happened or guarantee Gmail/Drive success. The permanent cloud solution must own its own backup mechanism outside ChatGPT.

## Required next phases
(0) CoS, IT/Coding Secretaries, Head AI and Post Office approvals/owners; (1) disposable live PostgreSQL migration and independent API tests; (2) approved cloud pilot with byte-level image preservation, SQL row, new-session retrieval, duplicate test; (3) bounded Post Office handoff with authorised readback; (4) nightly verified backup, isolated restoration, alternate-model and absent-ChatGPT drill; (5) ongoing departmental manual inventory with source IDs, revisions and coverage matrix. No hosting purchase, production deployment or master migration authorised yet.

## Manual completeness / recovery test
This edition is **only a starting map**, not a merged copy of each departmental handbook. The next release must include a departmental document inventory and safe full-text backup/export, a machine-readable inventory, source revisions and checksums, recovery runbooks, paid-hosting inventory, data residency and billing, specific Post Office contract and acknowledgement protocol. Test whether a new operator can use only the manual, permitted account access and backed-up code to run safe fixtures and restore sample data. If not, recovery readiness = **FAILED**.

**Change rule:** Every deployment must update this manual, version, release SHA, migration and rollback instructions. Never say another department received a document merely because it is linked here.
