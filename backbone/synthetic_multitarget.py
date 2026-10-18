"""Synthetic-only Mi Mundo multi-target reconciliation proof.

No production Drive, medical records, external Post Office or sensitive sources.
A SQLite fixture checkpoint is NOT a replacement for PostgreSQL and the real Post Office.
"""
import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Target:
    key: str
    payload: dict[str, Any]
    privacy: str = 'GENERAL'

    @property
    def digest(self) -> str:
        encoded = json.dumps(self.payload, sort_keys=True, separators=(',', ':')).encode()
        return hashlib.sha256(encoded).hexdigest()


class FixtureDrive:
    """Deterministic fake authoritative targets, with late HTTP-timeout simulation."""
    def __init__(self):
        self.records: dict[str, dict[str, Any]] = {}
        self.write_count: dict[str, int] = {}
        self.lose_reply_once: set[str] = set()
        self.block_once: set[str] = set()

    def read(self, key: str):
        return self.records.get(key)

    def put(self, key: str, payload: dict, digest: str):
        if key in self.block_once:
            self.block_once.remove(key)
            raise ConnectionError('synthetic temporary remote failure')
        before = self.records.get(key)
        if before is not None and before['digest'] != digest:
            raise ValueError('existing authoritative record conflict')
        if before is None:
            self.records[key] = {'payload': payload, 'digest': digest}
            self.write_count[key] = self.write_count.get(key, 0) + 1
        if key in self.lose_reply_once:
            self.lose_reply_once.remove(key)
            raise TimeoutError('synthetic ACK lost after target commit')
        return True


class SyntheticReconciler:
    """Per-target durable fixture checkpoints, full readback, no double writes.

    The local DB persists to a caller-selected sqlite file for repeat-run tests.
    No automatic department routing: all targets are caller-approved fixtures.
    """
    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path)
        self.db.execute('''CREATE TABLE IF NOT EXISTS target_operations (
          intake_id TEXT NOT NULL, target_key TEXT NOT NULL,
          payload_sha256 TEXT NOT NULL,
          state TEXT NOT NULL CHECK(state IN ('PENDING','UNCONFIRMED','VERIFIED','CONFLICT')),
          privacy_class TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
          duration_ms REAL NOT NULL DEFAULT 0, last_error TEXT,
          PRIMARY KEY (intake_id,target_key))''')
        self.db.commit()

    def close(self):
        self.db.close()

    def record(self, intake_id: str, target: Target) -> None:
        with self.db:
            row = self.db.execute('''SELECT payload_sha256 FROM target_operations
              WHERE intake_id=? AND target_key=?''', (intake_id, target.key)).fetchone()
            if row and row[0] != target.digest:
                raise ValueError('same intake target changed content; new reviewed version required')
            if row is None:
                self.db.execute('''INSERT INTO target_operations
                  (intake_id,target_key,payload_sha256,state,privacy_class)
                  VALUES (?,?,?,'PENDING',?)''',
                  (intake_id, target.key, target.digest, target.privacy))

    def _mark(self, intake_id: str, target: Target, state: str, elapsed_ms: float,
              error: str | None, attempted: bool) -> None:
        with self.db:
            self.db.execute('''UPDATE target_operations SET state=?,duration_ms=duration_ms+?,
              last_error=?,attempts=attempts+? WHERE intake_id=? AND target_key=?''',
              (state, elapsed_ms, error, int(attempted), intake_id, target.key))

    def apply(self, intake_id: str, target: Target, fixture: FixtureDrive,
              *, original_verified: bool) -> dict:
        if not original_verified:
            raise RuntimeError('source original not preserved: block target write')
        self.record(intake_id, target)
        start = time.perf_counter_ns()
        attempted = False
        error = None
        try:
            existing = fixture.read(target.key)  # GET-first reconciliation, even after timeout
            if existing and existing['digest'] == target.digest:
                state = 'VERIFIED'
            elif existing:
                state = 'CONFLICT'
                error = 'authoritative record has different digest'
            else:
                attempted = True
                fixture.put(target.key, target.payload, target.digest)
                observed = fixture.read(target.key)
                if not observed or observed['digest'] != target.digest:
                    state, error = 'UNCONFIRMED', 'readback does not match expected digest'
                else:
                    state = 'VERIFIED'
        except (TimeoutError, ConnectionError) as exc:
            # A timeout after write is not proof of a failed write.
            state, error = 'UNCONFIRMED', type(exc).__name__
        except ValueError:
            state, error = 'CONFLICT', 'non-idempotent target conflict'
        elapsed = (time.perf_counter_ns() - start) / 1_000_000
        self._mark(intake_id, target, state, elapsed, error, attempted)
        return dict(key=target.key, status=state, duration_ms=round(elapsed, 3), error=error)

    def run(self, intake_id: str, targets: list[Target], fixture: FixtureDrive,
            *, original_verified: bool) -> dict:
        start = time.perf_counter_ns()
        keys = [t.key for t in targets]
        if len(keys) != len(set(keys)):
            raise ValueError('duplicate target key')
        outcomes = [self.apply(intake_id, x, fixture, original_verified=original_verified)
                    for x in targets]
        rows = self.db.execute('''SELECT state,COUNT(*) FROM target_operations
          WHERE intake_id=? GROUP BY state''', (intake_id,)).fetchall()
        return {'intake_id': intake_id, 'targets': outcomes,
                'counts': dict(rows),
                'total_ms': round((time.perf_counter_ns() - start) / 1_000_000, 3),
                'all_verified': all(x['status'] == 'VERIFIED' for x in outcomes),
                'post_office_acknowledged': False}
