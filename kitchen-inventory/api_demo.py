"""Synthetic-only inventory API. NOT authenticated or production-safe."""
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Literal
import sqlite3, json, hashlib, uuid
from decimal import Decimal
from threading import RLock

app=FastAPI(title="Casa Hullock synthetic kitchen inventory")
lock=RLock()
db=sqlite3.connect(":memory:",check_same_thread=False,isolation_level=None)
db.executescript("""
CREATE TABLE balance(product TEXT,location TEXT,quantity TEXT,state TEXT,unit TEXT,version INT DEFAULT 0,PRIMARY KEY(product,location));
CREATE TABLE tx(id TEXT PRIMARY KEY,key TEXT UNIQUE,digest TEXT);
CREATE TABLE event(id TEXT PRIMARY KEY,tx TEXT,product TEXT,location TEXT,delta TEXT,result TEXT);
CREATE TABLE threshold(product TEXT,location TEXT,amount TEXT,PRIMARY KEY(product,location));
CREATE TABLE outbox(id TEXT PRIMARY KEY,tx TEXT,product TEXT,location TEXT,status TEXT);
""")
for p,l,q,s,u in [('milk','fridge','1000','CONFIRMED','ml'),('milk','freezer','0','CONFIRMED','ml'),
 ('powder','pantry','500','CONFIRMED','g'),('cherries','freezer','300','CONFIRMED','g'),
 ('shake','fridge','0','CONFIRMED','count'),('yoghurt','fridge',None,'UNKNOWN','g'),
 ('coffee','pantry','20','CONFIRMED','count')]:
    db.execute('INSERT INTO balance(product,location,quantity,state,unit) VALUES(?,?,?,?,?)',(p,l,q,s,u))
db.execute("INSERT INTO threshold VALUES('coffee','pantry','19')")

class Movement(BaseModel):
    product:str
    location:str
    delta:str
    unit:Literal['g','ml','count']
class Instruction(BaseModel):
    source:str
    kind:Literal['PURCHASE','CONSUME','TRANSFER','PREPARE','CORRECTION']
    movements:list[Movement]

def auth(token,write=False):
    if token != ('test-kitchen-writer' if write else token) or token not in (('test-kitchen-writer',) if write else ('test-read-only','test-kitchen-writer')):
        raise HTTPException(403,'Synthetic test token required')

@app.get('/v1/kitchen/current-stock')
def current_stock(location:str|None=None,x_demo_token:str|None=Header(default=None)):
    auth(x_demo_token)
    with lock:
        rows=db.execute("SELECT product,location,quantity,state,unit,version FROM balance"+(" WHERE location=?" if location else ""),((location,) if location else ())).fetchall()
    return {'authority':'SYNTHETIC_ONLY','items':[dict(zip(('product','location','quantity','state','unit','version'),r)) for r in rows]}

@app.get('/v1/kitchen/shopping-needs')
def shopping_needs(x_demo_token:str|None=Header(default=None)):
    auth(x_demo_token)
    with lock:
        rows=db.execute("SELECT b.product,b.location,b.quantity,t.amount FROM balance b JOIN threshold t ON b.product=t.product AND b.location=t.location WHERE b.state='CONFIRMED'").fetchall()
    return {'items':[dict(product=p,location=l,quantity=q,threshold=t) for p,l,q,t in rows if Decimal(q)<=Decimal(t)]}

@app.post('/v1/kitchen/stock-events')
def stock_events(data:Instruction,x_demo_token:str|None=Header(default=None),idempotency_key:str|None=Header(default=None)):
    auth(x_demo_token,True)
    if not idempotency_key or len(idempotency_key)>200 or not data.movements:
        raise HTTPException(422,'Idempotency-Key and movements required')
    body=data.model_dump()
    digest=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
    with lock:
        db.execute('BEGIN IMMEDIATE')
        try:
            found=db.execute('SELECT id,digest FROM tx WHERE key=?',(idempotency_key,)).fetchone()
            if found:
                if found[1]!=digest: raise HTTPException(409,'Idempotency key payload mismatch')
                db.execute('COMMIT')
                return {'transaction_id':found[0],'replayed':True}
            movements=[]
            keys=set()
            for m in data.movements:
                k=(m.product,m.location)
                if k in keys: raise HTTPException(422,'Duplicate product/location')
                keys.add(k)
                row=db.execute('SELECT quantity,state,unit FROM balance WHERE product=? AND location=?',k).fetchone()
                if row is None or row[1]!='CONFIRMED':raise HTTPException(422,'Unconfirmed stock')
                if row[2]!=m.unit: raise HTTPException(422,'Unit mismatch')
                delta=Decimal(m.delta)
                if not delta.is_finite():raise HTTPException(422,'Invalid quantity')
                current=Decimal(row[0]); target=current+delta
                if target<0:raise HTTPException(422,'Insufficient stock')
                movements.append((m,delta,current,target))
            if data.kind=='TRANSFER' and (len(movements)!=2 or movements[0][0].product!=movements[1][0].product or sum((v[1] for v in movements),Decimal(0))!=0):
                raise HTTPException(422,'Unbalanced transfer')
            tid=str(uuid.uuid4())
            db.execute('INSERT INTO tx VALUES(?,?,?)',(tid,idempotency_key,digest))
            for m,delta,old,new in movements:
                db.execute('UPDATE balance SET quantity=?,version=version+1 WHERE product=? AND location=?',(str(new),m.product,m.location))
                db.execute('INSERT INTO event VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),tid,m.product,m.location,str(delta),str(new)))
                t=db.execute('SELECT amount FROM threshold WHERE product=? AND location=?',(m.product,m.location)).fetchone()
                if t and old>Decimal(t[0]) and new<=Decimal(t[0]):
                    db.execute('INSERT INTO outbox VALUES(?,?,?,?,?)',(str(uuid.uuid4()),tid,m.product,m.location,'QUEUED'))
            db.execute('COMMIT')
            return {'transaction_id':tid,'replayed':False}
        except Exception:
            db.execute('ROLLBACK')
            raise
