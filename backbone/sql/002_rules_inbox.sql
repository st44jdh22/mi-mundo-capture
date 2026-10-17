-- Mi Mundo provider-neutral rules, clarifications & two-way Inbox v0.2
-- DESIGN REVIEW ONLY. Depends on 001_core_schema.sql; unexecuted migration.
-- Existing Post Office retains sole departmental execution authority.
BEGIN;
CREATE TABLE IF NOT EXISTS mi_mundo.rule_version (
  rule_id uuid NOT NULL,
  version integer NOT NULL CHECK(version >= 1),
  domain text NOT NULL CHECK(domain IN ('KITCHEN','FINANCE','MARINE','PERSONAL','WORK','GENERAL')),
  trigger_code text NOT NULL,
  condition_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  proposed_action text NOT NULL CHECK(proposed_action IN
    ('CLASSIFY_ONLY','REQUEST_CLARIFICATION','SUGGEST_STORAGE','PREPARE_HANDOFF','FLAG_DUPLICATE')),
  source_kind text NOT NULL CHECK(source_kind IN
    ('EXPLICIT_OWNER','CONFIRMED_PATTERN','DOMAIN_DEFAULT','ADMIN_POLICY')),
  approval_state text NOT NULL CHECK(approval_state IN
    ('DRAFT','OWNER_APPROVED','SUSPENDED','RETIRED')),
  risk_tier text NOT NULL CHECK(risk_tier IN ('LOW','REVIEW','RESTRICTED')),
  owner_principal text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  effective_at timestamptz,
  retired_at timestamptz,
  PRIMARY KEY (rule_id,version)
);
CREATE UNIQUE INDEX IF NOT EXISTS rule_version_effective_idx
ON mi_mundo.rule_version(rule_id)
WHERE approval_state = 'OWNER_APPROVED' AND retired_at IS NULL;

CREATE TABLE IF NOT EXISTS mi_mundo.extraction_candidate (
  candidate_id uuid PRIMARY KEY,
  job_id uuid NOT NULL REFERENCES mi_mundo.intake_job(job_id),
  evidence_id uuid REFERENCES mi_mundo.evidence(evidence_id),
  candidate_kind text NOT NULL,
  candidate_payload jsonb NOT NULL,
  confidence numeric(5,4) CHECK(confidence >= 0 AND confidence <= 1),
  model_invocation_id uuid REFERENCES mi_mundo.model_execution(invocation_id),
  extraction_policy_version text NOT NULL,
  source_span text,
  state text NOT NULL DEFAULT 'PROPOSED'
    CHECK(state IN ('PROPOSED','CONFIRMED','REJECTED','SUPERSEDED')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS candidate_job_idx ON mi_mundo.extraction_candidate(job_id,created_at);

CREATE TABLE IF NOT EXISTS mi_mundo.rule_evaluation (
  evaluation_id uuid PRIMARY KEY,
  job_id uuid NOT NULL REFERENCES mi_mundo.intake_job(job_id),
  rule_id uuid NOT NULL,
  rule_version integer NOT NULL,
  evaluated_at timestamptz NOT NULL DEFAULT now(),
  outcome text NOT NULL CHECK(outcome IN
    ('SUGGEST','NEEDS_CLARIFICATION','REQUIRES_APPROVAL','NO_MATCH','BLOCKED')),
  rationale_code text NOT NULL,
  context_fingerprint text NOT NULL CHECK(context_fingerprint ~ '^[0-9a-f]{64}$'),
  decision_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  FOREIGN KEY (rule_id,rule_version) REFERENCES mi_mundo.rule_version(rule_id,version),
  UNIQUE (job_id,rule_id,rule_version,context_fingerprint)
);
CREATE INDEX IF NOT EXISTS evaluation_job_idx ON mi_mundo.rule_evaluation(job_id,evaluated_at);

CREATE TABLE IF NOT EXISTS mi_mundo.preference_observation (
  observation_id uuid PRIMARY KEY,
  rule_id uuid NOT NULL,
  rule_version integer NOT NULL,
  job_id uuid REFERENCES mi_mundo.intake_job(job_id),
  confirmation_kind text NOT NULL CHECK(confirmation_kind IN
    ('EXPLICIT_CONFIRMATION','EXPLICIT_CORRECTION','CONTRADICTION')),
  source_message_id uuid,
  confirmed_by text NOT NULL,
  observed_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (rule_id,rule_version) REFERENCES mi_mundo.rule_version(rule_id,version)
);
CREATE INDEX IF NOT EXISTS preference_rule_idx ON mi_mundo.preference_observation(rule_id,observed_at);

CREATE TABLE IF NOT EXISTS mi_mundo.inbox_thread (
  thread_id uuid PRIMARY KEY,
  job_id uuid REFERENCES mi_mundo.intake_job(job_id),
  owner_principal text NOT NULL,
  subject text NOT NULL,
  privacy_class text NOT NULL CHECK(privacy_class IN
    ('GENERAL','BUSINESS_CONFIDENTIAL','FINANCIAL','HEALTH','HIGHLY_PRIVATE')),
  state text NOT NULL DEFAULT 'OPEN'
    CHECK(state IN ('OPEN','WAITING_USER','WAITING_DEPARTMENT','RESOLVED','ARCHIVED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS inbox_owner_state_idx ON mi_mundo.inbox_thread(owner_principal,state,updated_at DESC);

CREATE TABLE IF NOT EXISTS mi_mundo.inbox_message (
  message_id uuid PRIMARY KEY,
  thread_id uuid NOT NULL REFERENCES mi_mundo.inbox_thread(thread_id),
  sender_kind text NOT NULL CHECK(sender_kind IN ('USER','MI_MUNDO','DEPARTMENT','SYSTEM')),
  sender_reference text NOT NULL,
  body_text text,
  voice_evidence_id uuid REFERENCES mi_mundo.evidence(evidence_id),
  reply_to_message_id uuid REFERENCES mi_mundo.inbox_message(message_id),
  requires_response boolean NOT NULL DEFAULT false,
  message_state text NOT NULL DEFAULT 'RECORDED'
    CHECK(message_state IN ('RECORDED','DELIVERED','READ','ANSWERED','FAILED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (body_text IS NOT NULL OR voice_evidence_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS inbox_message_thread_idx ON mi_mundo.inbox_message(thread_id,created_at);

-- Notification outbox is NOT a second Post Office dispatch queue.
CREATE TABLE IF NOT EXISTS mi_mundo.notification_outbox (
  notification_id uuid PRIMARY KEY,
  message_id uuid NOT NULL REFERENCES mi_mundo.inbox_message(message_id),
  channel text NOT NULL CHECK(channel IN ('IN_APP','WEB_PUSH','EMAIL')),
  idempotency_key text NOT NULL UNIQUE,
  state text NOT NULL DEFAULT 'PENDING'
    CHECK(state IN ('PENDING','SENT','DELIVERED','FAILED','SUPPRESSED')),
  attempts integer NOT NULL DEFAULT 0 CHECK(attempts >= 0),
  next_attempt_at timestamptz,
  last_attempt_at timestamptz,
  last_error_code text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (message_id,channel)
);
CREATE INDEX IF NOT EXISTS notification_retry_idx
ON mi_mundo.notification_outbox(state,next_attempt_at)
WHERE state IN ('PENDING','FAILED');
COMMIT;
