-- REVIEW ONLY: disposable *_filing_test database. NEVER apply to deployed pilot.
-- Generated from integration/filing/service.py with PostgreSQL dialect.
BEGIN;

CREATE TABLE mm_filing_test_control (
	id SERIAL NOT NULL, 
	stopped BOOLEAN NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE TABLE mm_filing_test_jobs (
	job_id VARCHAR(36) NOT NULL, 
	intake_id VARCHAR(36) NOT NULL, 
	requester VARCHAR(80) NOT NULL, 
	department VARCHAR(32) NOT NULL, 
	conversation_id VARCHAR(80) NOT NULL, 
	idempotency_key VARCHAR(100) NOT NULL, 
	fingerprint VARCHAR(64) NOT NULL, 
	instruction TEXT NOT NULL, 
	source_ref TEXT NOT NULL, 
	object_key VARCHAR(64), 
	source_sha256 VARCHAR(64), 
	approval_ref VARCHAR(120) NOT NULL, 
	authoritative_record VARCHAR(120) NOT NULL, 
	state VARCHAR(32) NOT NULL, 
	attempts INTEGER NOT NULL, 
	next_attempt INTEGER NOT NULL, 
	lease_token VARCHAR(36), 
	lease_owner VARCHAR(80), 
	lease_until INTEGER NOT NULL, 
	cancel_requested BOOLEAN NOT NULL, 
	created_at INTEGER NOT NULL, 
	updated_at INTEGER NOT NULL, 
	error_code VARCHAR(80), 
	exact_error TEXT, 
	PRIMARY KEY (job_id), 
	CONSTRAINT filing_idempotency UNIQUE (requester, idempotency_key)
)

;

CREATE TABLE mm_filing_test_attempts (
	job_id VARCHAR(36) NOT NULL, 
	number INTEGER NOT NULL, 
	token VARCHAR(36) NOT NULL, 
	worker VARCHAR(80) NOT NULL, 
	started_at INTEGER NOT NULL, 
	finished_at INTEGER, 
	outcome VARCHAR(40), 
	error_code VARCHAR(80), 
	exact_error TEXT, 
	PRIMARY KEY (job_id, number), 
	FOREIGN KEY(job_id) REFERENCES mm_filing_test_jobs (job_id)
)

;

CREATE TABLE mm_filing_test_events (
	event_id VARCHAR(36) NOT NULL, 
	sequence INTEGER NOT NULL, 
	job_id VARCHAR(36) NOT NULL, 
	at INTEGER NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	details JSON NOT NULL, 
	PRIMARY KEY (event_id), 
	UNIQUE (sequence), 
	FOREIGN KEY(job_id) REFERENCES mm_filing_test_jobs (job_id)
)

;

CREATE TABLE mm_filing_test_targets (
	job_id VARCHAR(36) NOT NULL, 
	target_id VARCHAR(80) NOT NULL, 
	spec JSON NOT NULL, 
	state VARCHAR(32) NOT NULL, 
	verification JSON, 
	updated_at INTEGER NOT NULL, 
	PRIMARY KEY (job_id, target_id), 
	FOREIGN KEY(job_id) REFERENCES mm_filing_test_jobs (job_id)
)

;

CREATE TABLE mm_filing_test_outbox (
	event_id VARCHAR(36) NOT NULL, 
	job_id VARCHAR(36) NOT NULL, 
	sequence INTEGER NOT NULL, 
	payload JSON NOT NULL, 
	state VARCHAR(32) NOT NULL, 
	attempts INTEGER NOT NULL, 
	next_attempt INTEGER NOT NULL, 
	lease_token VARCHAR(36), 
	lease_until INTEGER NOT NULL, 
	error_code VARCHAR(80), 
	PRIMARY KEY (event_id), 
	FOREIGN KEY(event_id) REFERENCES mm_filing_test_events (event_id), 
	FOREIGN KEY(job_id) REFERENCES mm_filing_test_jobs (job_id), 
	UNIQUE (sequence)
)

;

CREATE TABLE mm_filing_test_report_attempts (
	event_id VARCHAR(36) NOT NULL, 
	number INTEGER NOT NULL, 
	at INTEGER NOT NULL, 
	outcome VARCHAR(32) NOT NULL, 
	exact_error TEXT, 
	PRIMARY KEY (event_id, number), 
	FOREIGN KEY(event_id) REFERENCES mm_filing_test_outbox (event_id)
)

;

COMMIT;

