-- Mi Mundo life core v0.1. REVIEW ONLY; no running DB migration.
-- PostgreSQL 15+. Run only with a restricted application DB role (never BYPASSRLS).
BEGIN;
CREATE SCHEMA IF NOT EXISTS life_core;
CREATE TABLE life_core.workspace (
 workspace_id uuid PRIMARY KEY, kind text NOT NULL CHECK (kind IN ('PERSONAL','HOUSEHOLD','ORGANISATION')),
 display_name text NOT NULL, schema_version integer NOT NULL DEFAULT 1,
 created_at timestamptz NOT NULL DEFAULT now(), disabled_at timestamptz
);
CREATE TABLE life_core.person (
 person_id uuid PRIMARY KEY, display_name text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE life_core.membership (
 workspace_id uuid NOT NULL REFERENCES life_core.workspace,
 person_id uuid NOT NULL REFERENCES life_core.person,
 role text NOT NULL CHECK(role IN ('OWNER','ADULT','DEPENDENT','CAREGIVER','SERVICE')),
 status text NOT NULL CHECK(status IN ('ACTIVE','REVOKED')),
 joined_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,person_id)
);
CREATE TABLE life_core.module (
 workspace_id uuid NOT NULL REFERENCES life_core.workspace,
 module_code text NOT NULL CHECK(module_code IN ('PERSONAL','FOOD','HEALTH','FAMILY','SCHEDULE','ASSETS','BUSINESS')),
 enabled boolean NOT NULL DEFAULT false,
 PRIMARY KEY(workspace_id,module_code)
);
-- Person-specific records have a subject as well as an owner workspace.
-- Module permission is enforced by app service + RLS, not just by a UI switch.
CREATE TABLE life_core.record (
 record_id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES life_core.workspace,
 subject_person_id uuid REFERENCES life_core.person,
 module_code text NOT NULL,
 record_type text NOT NULL,
 occurred_at timestamptz, event_key text NOT NULL,
 privacy_class text NOT NULL CHECK(privacy_class IN ('GENERAL','PRIVATE','HEALTH','HIGHLY_PRIVATE')),
 record_data jsonb NOT NULL DEFAULT '{}'::jsonb,
 revision bigint NOT NULL DEFAULT 1 CHECK(revision>0),
 state text NOT NULL DEFAULT 'ACTIVE' CHECK(state IN ('ACTIVE','SUPERSEDED','DELETED')),
 created_at timestamptz NOT NULL DEFAULT now(), modified_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(workspace_id,module_code,event_key),
 FOREIGN KEY(workspace_id,module_code) REFERENCES life_core.module(workspace_id,module_code),
 FOREIGN KEY(workspace_id,subject_person_id) REFERENCES life_core.membership(workspace_id,person_id)
);
CREATE INDEX record_workspace_module_idx ON life_core.record(workspace_id,module_code,occurred_at DESC);
-- Original media stored encrypted in a private object store. This table holds only metadata and locator.
CREATE TABLE life_core.evidence (
 evidence_id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES life_core.workspace,
 original_sha256 text NOT NULL CHECK(original_sha256 ~ '^[a-f0-9]{64}$'),
 byte_length bigint NOT NULL CHECK(byte_length>0),
 mime_type text NOT NULL, object_key text NOT NULL,
 object_version text,
 preservation_state text NOT NULL CHECK(preservation_state IN ('PENDING','DURABLE_VERIFIED','FAILED','REVIEW_REQUIRED')),
 captured_at timestamptz, verified_at timestamptz,
 UNIQUE(workspace_id,object_key), UNIQUE(evidence_id,workspace_id)
);
CREATE TABLE life_core.fact (
 fact_id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES life_core.workspace,
 record_id uuid NOT NULL, evidence_id uuid,
 field_key text NOT NULL, value_json jsonb NOT NULL,
 provenance text NOT NULL CHECK(provenance IN ('USER_REPORTED','DEPARTMENT_REPORTED','MODEL_EXTRACTED','ORIGINAL_VERIFIED')),
 verification_state text NOT NULL CHECK(verification_state IN ('REPORTED_UNVERIFIED','VERIFIED','REJECTED','SUPERSEDED')),
 asserted_by text NOT NULL, asserted_at timestamptz NOT NULL DEFAULT now(),
 verified_by text, verified_at timestamptz,
 FOREIGN KEY(evidence_id,workspace_id) REFERENCES life_core.evidence(evidence_id,workspace_id),
 FOREIGN KEY(record_id) REFERENCES life_core.record(record_id),
 UNIQUE(workspace_id,record_id,field_key,evidence_id,asserted_by)
);
-- Cross-workspace foreign keys on records and facts are enforced by trigger/DB design in next migration.
-- In this first migration prevent accidental cross-workspace fact references by composite key below.
ALTER TABLE life_core.record ADD CONSTRAINT record_id_workspace_unique UNIQUE(record_id,workspace_id);
ALTER TABLE life_core.fact DROP CONSTRAINT fact_record_id_fkey;
ALTER TABLE life_core.fact ADD CONSTRAINT fact_record_workspace_fk FOREIGN KEY(record_id,workspace_id) REFERENCES life_core.record(record_id,workspace_id);
CREATE TABLE life_core.job (
 job_id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES life_core.workspace,
 input_evidence_id uuid, state text NOT NULL CHECK(state IN ('PENDING','RUNNING','BLOCKED','PARTIAL','VERIFIED','FAILED')),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(input_evidence_id,workspace_id) REFERENCES life_core.evidence(evidence_id,workspace_id),
 UNIQUE(job_id,workspace_id)
);
CREATE TABLE life_core.operation (
 operation_id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES life_core.workspace,
 job_id uuid NOT NULL, destination text NOT NULL, idempotency_key text NOT NULL,
 source_version text, state text NOT NULL CHECK(state IN ('PENDING','RETRY_WAIT','POLICY_BLOCKED','AUTH_BLOCKED','CONFLICT','VERIFIED','FAILED')),
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0), next_attempt_at timestamptz,
 last_error_code text, verified_at timestamptz,
 FOREIGN KEY(job_id,workspace_id) REFERENCES life_core.job(job_id,workspace_id),
 UNIQUE(workspace_id,destination,idempotency_key)
);
-- Ensure every tenant-scoped table defaults to deny, including table owners (outside migrations).
DO $$ DECLARE tab text; BEGIN
 FOR tab IN SELECT unnest(ARRAY['workspace','membership','module','record','evidence','fact','job','operation']) LOOP
  EXECUTE format('ALTER TABLE life_core.%I ENABLE ROW LEVEL SECURITY',tab);
  EXECUTE format('ALTER TABLE life_core.%I FORCE ROW LEVEL SECURITY',tab);
  EXECUTE format('CREATE POLICY tenant_match ON life_core.%I USING (workspace_id = NULLIF(current_setting(''mi_mundo.workspace_id'', true),'''')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting(''mi_mundo.workspace_id'', true),'''')::uuid)',tab);
 END LOOP;
END $$;
-- Person identity does not imply tenant access; API must authorise subject access separately.
ALTER TABLE life_core.person ENABLE ROW LEVEL SECURITY;
ALTER TABLE life_core.person FORCE ROW LEVEL SECURITY;
-- Denied by default until a separately security-reviewed person access function/policy exists.
COMMIT;