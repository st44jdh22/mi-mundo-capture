"""Mi Mundo FOOD-CHEF synthetic threaded conversation service.
Isolated single-owner fixture ONLY. No real sources, model calls or Post Office writes.
"""
from __future__ import annotations
import hashlib, hmac, os, time, uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, Body
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (MetaData, Table, Column, String, Integer, ForeignKeyConstraint,
                        create_engine, insert, select, update, func)
from sqlalchemy.exc import IntegrityError

metadata=MetaData()
threads=Table('mm_chef_demo_threads',metadata,
 Column('thread_id',String(36),primary_key=True),Column('owner_id',String(40),nullable=False),
 Column('department',String(24),nullable=False),Column('created_at',Integer,nullable=False))
messages=Table('mm_chef_demo_messages',metadata,
 Column('message_id',String(36),primary_key=True),Column('thread_id',String(36),nullable=False),
 Column('owner_id',String(40),nullable=False), Column('source_id',String(36),nullable=False),
 Column('idempotency_key',String(72),nullable=False),Column('sender',String(24),nullable=False),
 Column('body',String(1000),nullable=False),Column('reply_to',String(36)),
 Column('delivery_state',String(64),nullable=False),Column('created_at',Integer,nullable=False),
 ForeignKeyConstraint(['thread_id'],['mm_chef_demo_threads.thread_id']))
# Unique stable acceptance: prevent source turn replay, including client network failure.
from sqlalchemy import UniqueConstraint
messages.append_constraint(UniqueConstraint('thread_id','source_id',name='unique_chef_source'))

class MessageInput(BaseModel):
 model_config=ConfigDict(extra='forbid')
 source_id:uuid.UUID
 body:str=Field(min_length=1,max_length=1000)

class StageBody(BaseModel):
 model_config=ConfigDict(extra='forbid')
 origin_id:uuid.UUID
 user_message_id:uuid.UUID

class SignedBody(BaseModel):
 model_config=ConfigDict(extra='forbid')
 delivery_id:uuid.UUID
 envelope:dict

class Store:
 def __init__(self,url):
  if url.startswith('postgresql://'): url='postgresql+psycopg://'+url.split('://',1)[1]
  self.engine=create_engine(url,pool_pre_ping=True,connect_args={'check_same_thread':False} if url.startswith('sqlite:') else {})
  metadata.create_all(self.engine)
 def close(self):self.engine.dispose()
 def new_thread(self,owner='synthetic-owner'):
  tid=str(uuid.uuid4());now=int(time.time())
  with self.engine.begin() as c:c.execute(insert(threads).values(thread_id=tid,owner_id=owner,department='FOOD-CHEF',created_at=now))
  return tid
 def get_thread(self,tid,owner='synthetic-owner'):
  with self.engine.connect() as c:
   row=c.execute(select(threads).where(threads.c.thread_id==tid,threads.c.owner_id==owner)).mappings().first()
   if row is None:raise KeyError('thread not found')
   values=c.execute(select(messages).where(messages.c.thread_id==tid,messages.c.owner_id==owner).order_by(messages.c.created_at,messages.c.message_id)).mappings().all()
  return {'thread_id':tid,'department':'FOOD-CHEF','mode':'SYNTHETIC_SCRIPTED_REVIEW','messages':[{'message_id':m['message_id'],'source_id':m['source_id'],'sender':m['sender'],'body':m['body'],'reply_to':m['reply_to'],'delivery_state':m['delivery_state']} for m in values]}
 def send(self,tid,source_id,body,owner='synthetic-owner'):
  sid=str(source_id);digest=hashlib.sha256(body.encode()).hexdigest();now=int(time.time())
  with self.engine.begin() as c:
   if c.execute(select(threads.c.thread_id).where(threads.c.thread_id==tid,threads.c.owner_id==owner)).first() is None:raise KeyError('thread not found')
   exists=c.execute(select(messages).where(messages.c.thread_id==tid,messages.c.source_id==sid)).mappings().first()
   if exists:
    if exists['idempotency_key']!=digest:raise ValueError('source id was reused with altered message')
    return self.get_thread(tid,owner)
   c.execute(insert(messages).values(message_id=str(uuid.uuid4()),thread_id=tid,owner_id=owner,source_id=sid,idempotency_key=digest,sender='USER',body=body,delivery_state='QUEUED_SYNTHETIC',created_at=now))
  return self.get_thread(tid,owner)
 def respond_synthetic(self,tid,owner='synthetic-owner'):
  with self.engine.begin() as c:
   if c.execute(select(threads.c.thread_id).where(threads.c.thread_id==tid,threads.c.owner_id==owner)).first() is None:raise KeyError('thread not found')
   rows=c.execute(select(messages).where(messages.c.thread_id==tid,messages.c.owner_id==owner).order_by(messages.c.created_at,messages.c.message_id)).mappings().all()
   pending=[m for m in rows if m['sender']=='USER' and m['delivery_state']=='QUEUED_SYNTHETIC']
   for m in pending:
    reply_exists=c.execute(select(messages.c.message_id).where(messages.c.thread_id==tid,messages.c.reply_to==m['message_id'])).first()
    if reply_exists is None:
     answer=('Happy to help with the barbecue. Do you have dietary requirements, and would you prefer a Mediterranean or traditional menu?' if len([x for x in rows if x['sender']=='USER'])==1 else 'Got it. Synthetic draft: Mediterranean barbecue menu and shopping list are proposed for review. No real document has been filed.')
     c.execute(insert(messages).values(message_id=str(uuid.uuid4()),thread_id=tid,owner_id=owner,source_id=str(uuid.uuid4()),idempotency_key=hashlib.sha256(answer.encode()).hexdigest(),sender='CHEF_SIMULATOR',body=answer,reply_to=m['message_id'],delivery_state='SIMULATED_REPLY',created_at=int(time.time())))
    c.execute(update(messages).where(messages.c.message_id==m['message_id']).values(delivery_state='SIMULATED_DELIVERY'))
  return self.get_thread(tid,owner)

TOKEN_MIN=32
def create_app(url,token,*,actor_key=None,actor_token=None):
 if len(token)<TOKEN_MIN:raise ValueError('pilot token missing')
 if (actor_key is None) != (actor_token is None):raise ValueError('both signed fixture actor key and actor token are required')
 if actor_key is not None and (len(actor_key)<32 or len(actor_token)<32 or actor_token==token):
  raise ValueError('signed fixture actor must have separate strong credentials')
 store=Store(url)
 bridge=None
 if actor_key is not None:
  from chef_signed_bridge import SignedChefBridge
  bridge=SignedChefBridge(store,metadata,threads,messages,actor_key)

 @asynccontextmanager
 async def lifecycle(app):
  yield
  store.close()
 app=FastAPI(title='Mi Mundo synthetic Chef messages',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifecycle)
 def auth(authorization):
  if not authorization or not hmac.compare_digest(authorization,'Bearer '+token):raise HTTPException(status_code=401,detail='Unauthorised')
 @app.get('/healthz')
 def health():return {'status':'SYNTHETIC_ONLY','post_office_connected':False,'real_chef_connected':False,'original_media_archived':False,'signed_fixture_adapter':bridge is not None}
 @app.get('/chef-demo')
 def page():return HTMLResponse((Path(__file__).parent/'chef_demo.html').read_text(encoding='utf8'))
 @app.post('/v1/chef-demo/threads',status_code=201)
 def new(authorization:str|None=Header(default=None)):
  auth(authorization);return store.get_thread(store.new_thread())
 @app.get('/v1/chef-demo/threads/{tid}')
 def get(tid:str,authorization:str|None=Header(default=None)):
  auth(authorization)
  try:return store.get_thread(tid)
  except KeyError:raise HTTPException(404,'Thread not found')
 @app.post('/v1/chef-demo/threads/{tid}/messages')
 def send(tid:str,body:MessageInput,authorization:str|None=Header(default=None)):
  auth(authorization)
  try:return store.send(tid,body.source_id,body.body)
  except KeyError:raise HTTPException(404,'Thread not found')
  except ValueError:raise HTTPException(409,'Conflicting idempotency key')
 @app.post('/v1/chef-demo/threads/{tid}/simulate-response')
 def respond(tid:str,authorization:str|None=Header(default=None)):
  auth(authorization)
  try:return store.respond_synthetic(tid)
  except KeyError:raise HTTPException(404,'Thread not found')
 if bridge is not None:
  def actor_auth(authorization):
   if not authorization or not hmac.compare_digest(authorization,'Bearer '+actor_token):
    raise HTTPException(status_code=401,detail='Signed fixture actor credential required')
  @app.post('/v1/chef-demo/threads/{tid}/bridge/stage')
  def stage(tid:str,body:StageBody=Body(...),authorization:str|None=Header(default=None)):
   auth(authorization)
   try:return bridge.stage(tid,str(body.origin_id),str(body.user_message_id))
   except KeyError:raise HTTPException(404,'Demo thread or source message not found')
   except PermissionError:raise HTTPException(403,'Synthetic messages only')
   except ValueError:raise HTTPException(409,'Immutable source conflict')
  @app.get('/v1/chef-demo/threads/{tid}/bridge')
  def staged(tid:str,authorization:str|None=Header(default=None)):
   auth(authorization)
   try:return {'deliveries':bridge.thread_deliveries(tid),
               'institutional_post_office_connected':False,
               'signed_actor_fixture_only':True}
   except KeyError:raise HTTPException(404,'Demo thread not found')
  @app.post('/v1/chef-fixture/actor/receipt')
  def actor_receipt(body:SignedBody=Body(...),authorization:str|None=Header(default=None)):
   actor_auth(authorization)
   try:
    kind=body.envelope.get('receipt',{}).get('kind')
    return bridge.receive(str(body.delivery_id),body.envelope,kind,int(time.time()))
   except KeyError:raise HTTPException(404,'Fixture delivery not found')
   except PermissionError:raise HTTPException(403,'Signed fixture receipt denied')
   except (ValueError,TypeError):raise HTTPException(409,'Signed fixture receipt conflict')
 return app

if __name__=='__main__':
 import uvicorn
 uvicorn.run(create_app(os.environ.get('MI_MUNDO_DATABASE_URL','sqlite:///chef_demo.sqlite'),os.environ['MI_MUNDO_TEST_TOKEN']),host='127.0.0.1',port=8078)