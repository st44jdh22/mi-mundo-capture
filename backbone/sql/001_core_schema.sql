-- Mi Mundo operational backbone v0.1 — PostgreSQL 15+
-- REVIEW ONLY. Not a replacement for authorised departmental masters/Post Office.
BEGIN;
CREATE SCHEMA IF NOT EXISTS mi_mundo;
CREATE TABLE IF NOT EXISTS mi_mundo.intake_job (
  job_id uuid PRIMARY KEY,
  source_system text NOT NULL,
  source_principal text NOT NULL,
  package_sha256 text NOT NULL CHECK(package_sha256 ~ '^[0-9a-f]{64}$'),
  privacy_class text NOT NULL CHECK(privacy_class IN ('GENERAL','BUSINESS_CONFIDENTIAL','FINANCIAL','HEALTH','HIGHLY_PRIVATE')),
  state text NOT NULL DEFAULT 'RECEIVED' CHECK(state IN ('RECEIVED','VALIDATED','EVIDENCE_PENDING','EVIDENCE_VERIFIED','REVIEW_REQUIRED','FAILED')),
  received_at timestamptz NOT NULL DEFAULT now(),
  validated_at timestamptz,
  UNIQUE(source_system,source_principal,job_id)
);
CREATE TABLE IF NOT EXISTS mi_mundo.evidence (
  evidence_id uuid PRIMARY KEY,
  job_id uuid NOT NULL REFERENCES mi_mundo.intake_job(job_id),
  attachment_id text NOT NULL,
  original_name text NOT NULL,
  mime_type text NOT NULL,
  byte_length bigint NOT NULL CHECK(byte_length>0),
  sha256 text NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
  object_key text NOT NULL UNIQUE,
  object_version text,
  privacy_class text NOT NULL CHECK(privacy_class IN ('GENERAL','BUSINESS_CONFIDENTIAL','FINANCIAL','HEALTH','HIGHLY_PRIVATE')),
  captured_at timestamptz, -- NULL unless actual source metadata supports it
  received_at timestamptz NOT NULL,
  filed_at timestamptz,
  verified_at timestamptz,
  status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','FILED','VERIFIED','BLOCKED')),
  UNIQUE(job_id,attachment_id)
);
CREATE INDEX IF NOT EXISTS evidence_sha256_idx ON mi_mundo.evidence(sha256);
CREATE TABLE IF NOT EXISTS mi_mundo.department_reference (
  reference_id uuid PRIMARY KEY,
  evidence_id uuid NOT NULL REFERENCES mi_mundo.evidence(evidence_id),
  department_code text NOT NULL,
  authoritative_record_uri text,
  authoritative_record_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(evidence_id,department_code,authoritative_record_id)
);
-- Intent/references ONLY. Authoritative dispatch queue remains the EXISTING Post Office.
CREATE TABLE IF NOT EXISTS mi_mundo.routing_handoff (
  handoff_id uuid PRIMARY KEY,
  job_id uuid NOT NULL REFERENCES mi_mundo.intake_job(job_id),
  destination_department text NOT NULL,
  external_post_office_message_id text UNIQUE,
  state text NOT NULL DEFAULT 'PROPOSED' CHECK(state IN ('PROPOSED','AWAITING_APPROVAL','SUBMITTED','ACKNOWLEDGED','FAILED','CANCELLED')),
  approved_by text,
  submitted_at timestamptz,
  acknowledged_at timestamptz,
  UNIQUE(job_id,destination_department)
);
CREATE TABLE IF NOT EXISTS mi_mundo.audit_event (
  audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  actor_kind text NOT NULL,
  actor_id text NOT NULL,
  job_id uuid REFERENCES mi_mundo.intake_job(job_id),
  evidence_id uuid REFERENCES mi_mundo.evidence(evidence_id),
  action text NOT NULL,
  result text NOT NULL,
  details jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS audit_job_idx ON mi_mundo.audit_event(job_id,occurred_at);
CREATE TABLE IF NOT EXISTS mi_mundo.model_execution (
  invocation_id uuid PRIMARY KEY,
  job_id uuid NOT NULL REFERENCES mi_mundo.intake_job(job_id),
  provider_id text NOT NULL, -- e.g. local-ollama, openai, anthropic; never vendor SQL columns
  model_id text NOT NULL,
  policy_version text NOT NULL,
  status text NOT NULL CHECK(status IN ('REQUESTED','SUCCEEDED','FAILED','SKIPPED')),
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  output_reference text -- reference to authorised storage, NOT raw sensitive prompts
);
COMMIT;
