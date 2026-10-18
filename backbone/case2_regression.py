"""Synthetic Mi Mundo intake Case 2 regression. No Google or personal data."""
import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import date

@dataclass(frozen=True)
class Event:
    event_key: str
    event_date: str
    payload: dict

    @property
    def digest(self):
        return hashlib.sha256(json.dumps(self.payload, sort_keys=True).encode()).hexdigest()


def choose_current_event(events, requested_date):
    selected = [e for e in events if e.event_date == requested_date]
    if len(selected) != 1:
        raise ValueError('date match requires clarification')
    return selected[0]


def correct_shake(raw, correction):
    result = dict(raw)
    if correction.get('yoghurt_fat') is not None:
        result['yoghurt_fat'] = correction['yoghurt_fat']
    if correction.get('milk_fat') is not None:
        result['milk_fat'] = correction['milk_fat']
    result['whole_shake_fat_free'] = result.get('yoghurt_fat') == '0%' and result.get('milk_fat') == '0%'
    result['portion_size'] = None
    return result

class Case2Fixture:
    def __init__(self, filename):
        self.db=sqlite3.connect(filename)
        self.db.execute('CREATE TABLE IF NOT EXISTS targets(job TEXT, destination TEXT, event_key TEXT, digest TEXT, state TEXT, attempts INTEGER DEFAULT 0, PRIMARY KEY(job,destination))')
        self.db.commit()
        self.remote={}
        self.calls={}
        self.denied=set()
        self.lost_ack=set()

    def close(self): self.db.close()

    def apply(self,job,destination,event):
        beginning=time.perf_counter_ns()
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO targets(job,destination,event_key,digest,state) VALUES(?,?,?,?,?)",(job,destination,event.event_key,event.digest,'PENDING'))
        row=self.db.execute('SELECT event_key,digest,state FROM targets WHERE job=? AND destination=?',(job,destination)).fetchone()
        if row[:2]!=(event.event_key,event.digest):
            return 'CONFLICT', (time.perf_counter_ns()-beginning)/1e6
        if row[2] in ('POLICY_BLOCKED','VERIFIED'):
            return row[2], (time.perf_counter_ns()-beginning)/1e6
        key=(destination,event.event_key)
        if key in self.remote:
            state='VERIFIED' if self.remote[key]==event.digest else 'CONFLICT'
        elif destination in self.denied:
            state='POLICY_BLOCKED'
        else:
            self.remote[key]=event.digest
            self.calls[key]=self.calls.get(key,0)+1
            state='UNCONFIRMED' if destination in self.lost_ack else 'VERIFIED'
            self.lost_ack.discard(destination)
        with self.db:
            self.db.execute('UPDATE targets SET state=?,attempts=attempts+1 WHERE job=? AND destination=?',(state,job,destination))
        return state,(time.perf_counter_ns()-beginning)/1e6

    def release(self,job,destination,approved,policy_permits):
        if not approved or not policy_permits:
            raise PermissionError('no policy-compliant approval')
        if destination in self.denied:
            raise PermissionError('external policy remains blocked')
        with self.db:
            if self.db.execute('SELECT state FROM targets WHERE job=? AND destination=?',(job,destination)).fetchone() != ('POLICY_BLOCKED',):
                raise ValueError('not held')
            self.db.execute("UPDATE targets SET state='PENDING' WHERE job=? AND destination=?",(job,destination))

    def summary(self,job):
        rows=self.db.execute('SELECT destination,state FROM targets WHERE job=? ORDER BY destination',(job,)).fetchall()
        return {'targets':dict(rows),'complete':bool(rows) and all(state=='VERIFIED' for _,state in rows), 'post_office_acknowledged':False}