"""Mi Mundo P0 recovery queue — synthetic, single-worker SQLite reference.

No real Google, Post Office, private source content, or background scheduler.
Store only non-sensitive metadata; a private immutable evidence service is a
separate prerequisite. This code cannot circumvent platform safety decisions.
"""
import sqlite3
from dataclasses import dataclass


class PolicyDenied(Exception):
    """Upstream tool-level safety or policy denial; do not automatically retry."""


class AuthDenied(Exception):
    """Credentials/permission failure; owner review required."""


@dataclass(frozen=True)
class Destination:
    key: str
    digest: str
    privacy_class: str = 'GENERAL'


STATES = ('PENDING', 'RETRY_WAIT', 'POLICY_BLOCKED', 'AUTH_BLOCKED',
          'CONFLICT', 'VERIFIED')


class RecoveryQueue:
    """Durable single-process reference. Multi-worker claiming needs PostgreSQL."""

    def __init__(self, filename):
        self.db = sqlite3.connect(filename)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS recovery_jobs(
          job_id TEXT PRIMARY KEY, source_digest TEXT NOT NULL,
          private_evidence_ref TEXT NOT NULL, opened_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS recovery_targets(
          job_id TEXT NOT NULL, target_key TEXT NOT NULL, payload_digest TEXT NOT NULL,
          privacy_class TEXT NOT NULL,
          state TEXT NOT NULL CHECK(state IN
            ('PENDING','RETRY_WAIT','POLICY_BLOCKED','AUTH_BLOCKED','CONFLICT','VERIFIED')),
          attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at INTEGER NOT NULL DEFAULT 0,
          updated_at INTEGER NOT NULL, last_error_code TEXT,
          PRIMARY KEY(job_id,target_key),
          FOREIGN KEY(job_id) REFERENCES recovery_jobs(job_id));
        CREATE TABLE IF NOT EXISTS recovery_inbox_outbox(
          event_key TEXT PRIMARY KEY, job_id TEXT NOT NULL,
          event_type TEXT NOT NULL, generic_text TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'QUEUED', created_at INTEGER NOT NULL,
          FOREIGN KEY(job_id) REFERENCES recovery_jobs(job_id));
        ''')

    def close(self):
        self.db.close()

    def start(self, job_id, source_digest, evidence_ref, destinations, *,
              original_verified, now):
        if not original_verified or not evidence_ref:
            raise ValueError('verified private source evidence required')
        if not job_id or not source_digest or not destinations:
            raise ValueError('incomplete recovery job')
        keys = [d.key for d in destinations]
        if len(keys) != len(set(keys)):
            raise ValueError('duplicate destination')
        with self.db:
            current = self.db.execute('SELECT * FROM recovery_jobs WHERE job_id=?',
                                      (job_id,)).fetchone()
            if current and (current['source_digest'] != source_digest or
                            current['private_evidence_ref'] != evidence_ref):
                raise ValueError('job source changed; cannot replay')
            if current is None:
                self.db.execute('INSERT INTO recovery_jobs VALUES(?,?,?,?)',
                                (job_id, source_digest, evidence_ref, now))
            for d in destinations:
                if not d.key or not d.digest or d.privacy_class not in (
                    'GENERAL', 'BUSINESS_CONFIDENTIAL', 'FINANCIAL', 'HEALTH',
                    'HIGHLY_PRIVATE'):
                    raise ValueError('invalid target')
                target = self.target(job_id, d.key)
                if target and (target['payload_digest'] != d.digest or
                               target['privacy_class'] != d.privacy_class):
                    raise ValueError('target changed; reviewed version required')
                if not target:
                    self.db.execute('''INSERT INTO recovery_targets
                       (job_id,target_key,payload_digest,privacy_class,state,updated_at)
                       VALUES (?,?,?,?,'PENDING',?)''',
                       (job_id, d.key, d.digest, d.privacy_class, now))

    def target(self, job_id, key):
        row = self.db.execute('''SELECT * FROM recovery_targets
          WHERE job_id=? AND target_key=?''', (job_id, key)).fetchone()
        return dict(row) if row else None

    def _event(self, job_id, event_key, event_type, message, now):
        # This is only an unsent delivery outbox, not a push notification.
        self.db.execute('''INSERT OR IGNORE INTO recovery_inbox_outbox
          (event_key,job_id,event_type,generic_text,created_at)
          VALUES (?,?,?,?,?)''', (event_key, job_id, event_type, message, now))

    def _set(self, job_id, key, state, now, error=None, next_time=0,
             increment_attempt=False):
        self.db.execute('''UPDATE recovery_targets SET state=?,updated_at=?,
          last_error_code=?,next_attempt_at=?,attempts=attempts+?
          WHERE job_id=? AND target_key=?''',
          (state, now, error, next_time, int(increment_attempt), job_id, key))

    def run_once(self, job_id, backend, *, now):
        """One explicitly invoked iteration; no timers or worker installed.

        backend.read(key) -> digest or None
        backend.write(key,digest) -> None; raises PolicyDenied/AuthDenied/etc.
        """
        rows = self.db.execute('''SELECT * FROM recovery_targets WHERE job_id=?
          ORDER BY target_key''', (job_id,)).fetchall()
        if not rows:
            raise ValueError('unknown or empty job')
        for item in rows:
            row = dict(item)
            key = row['target_key']
            if row['state'] not in ('PENDING', 'RETRY_WAIT'):
                continue
            if row['state'] == 'RETRY_WAIT' and now < row['next_attempt_at']:
                continue
            attempted = False
            try:
                existing = backend.read(key)  # reconcile remote before any write
                if existing == row['payload_digest']:
                    with self.db:
                        self._set(job_id, key, 'VERIFIED', now)
                    continue
                if existing is not None:
                    with self.db:
                        self._set(job_id, key, 'CONFLICT', now, 'remote_conflict')
                        self._event(job_id, f'{job_id}:{key}:CONFLICT', 'ATTENTION',
                                    'An update needs review; no existing entry was overwritten.', now)
                    continue
                attempted = True
                backend.write(key, row['payload_digest'])
                if backend.read(key) != row['payload_digest']:
                    raise TimeoutError('readback unconfirmed')
                with self.db:
                    self._set(job_id, key, 'VERIFIED', now, increment_attempt=True)
            except PolicyDenied:
                with self.db:
                    self._set(job_id, key, 'POLICY_BLOCKED', now,
                              'platform_safety_block', increment_attempt=attempted)
                    self._event(job_id, f'{job_id}:{key}:POLICY', 'ATTENTION',
                                'An update is on hold for safe review.', now)
            except AuthDenied:
                with self.db:
                    self._set(job_id, key, 'AUTH_BLOCKED', now,
                              'permission_or_authentication', increment_attempt=attempted)
                    self._event(job_id, f'{job_id}:{key}:AUTH', 'ATTENTION',
                                'An update needs authorised access review.', now)
            except (TimeoutError, ConnectionError):
                attempts = row['attempts'] + int(attempted)
                wait = min(900, 30 * (2 ** min(5, max(0, attempts - 1))))
                with self.db:
                    self._set(job_id, key, 'RETRY_WAIT', now, 'transient_or_unknown',
                              next_time=now + wait, increment_attempt=attempted)
            except Exception:
                # Unknown failures require review, not a blind repeated write.
                with self.db:
                    self._set(job_id, key, 'AUTH_BLOCKED', now,
                              'unknown_error_needs_review', increment_attempt=attempted)
                    self._event(job_id, f'{job_id}:{key}:UNKNOWN', 'ATTENTION',
                                'An update needs engineering review.', now)
        self._reconcile_job_notice(job_id, now)
        return self.status(job_id)

    def _reconcile_job_notice(self, job_id, now):
        rows = self.db.execute('SELECT state FROM recovery_targets WHERE job_id=?',
                               (job_id,)).fetchall()
        if rows and all(r['state'] == 'VERIFIED' for r in rows):
            with self.db:
                self._event(job_id, f'{job_id}:RESOLVED', 'RESOLVED',
                            'All requested destinations have been verified.', now)

    def attention_due(self, job_id, *, now, threshold_seconds=900):
        """Run when the app/worker wakes; this is not a 15-minute timer."""
        opened = self.db.execute('SELECT opened_at FROM recovery_jobs WHERE job_id=?',
                                 (job_id,)).fetchone()
        if not opened or now - opened['opened_at'] < threshold_seconds:
            return False
        count = self.db.execute('''SELECT COUNT(*) FROM recovery_targets
             WHERE job_id=? AND state IN ('PENDING','RETRY_WAIT')''', (job_id,)).fetchone()[0]
        if count:
            with self.db:
                self._event(job_id, f'{job_id}:STILL_PENDING', 'ATTENTION',
                            'An upload remains pending; the original is held safely.', now)
        return bool(count)

    def release_after_review(self, job_id, key, *, authorised, policy_permits, reason, now):
        row = self.target(job_id, key)
        if not row or row['state'] not in ('POLICY_BLOCKED','AUTH_BLOCKED'):
            raise ValueError('no blocked destination')
        if not authorised or not policy_permits or not reason or not reason.strip():
            raise PermissionError('separate compliant approval and access needed')
        with self.db:
            self._set(job_id, key, 'PENDING', now)
        # No write occurs here. The next ordinary iteration must still pass
        # the external policy guard and independent remote readback.

    def status(self, job_id):
        rows = self.db.execute('''SELECT target_key,state,attempts,next_attempt_at,
          last_error_code FROM recovery_targets WHERE job_id=? ORDER BY target_key''',
          (job_id,)).fetchall()
        if not rows:
            raise ValueError('unknown job')
        counts = {state: sum(r['state'] == state for r in rows) for state in STATES}
        return {'job_id': job_id, 'destinations': [dict(r) for r in rows],
                'counts': counts, 'complete': counts['VERIFIED'] == len(rows)}

    def notices(self, job_id):
        return [dict(r) for r in self.db.execute('''SELECT event_key,event_type,
          generic_text,status FROM recovery_inbox_outbox WHERE job_id=?
          ORDER BY created_at,event_key''', (job_id,)).fetchall()]