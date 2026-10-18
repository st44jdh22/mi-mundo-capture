/**
 * Mi Mundo local-first outbox, SYNTHETIC REVIEW ONLY.
 * Keep the same ZIP bytes across retries. IndexedDB is best-effort browser storage;
 * never confuse TEST_RECEIVED with permanent production evidence preservation.
 * No tokens, real evidence or Post Office execution permissions here.
 */
export const STATES=Object.freeze({
 QUEUED:'QUEUED',SENDING:'SENDING',UNCONFIRMED:'UNCONFIRMED',
 TEST_RECEIVED:'TEST_RECEIVED',NEEDS_REVIEW:'NEEDS_REVIEW'
});
const NEXT={QUEUED:['SENDING','NEEDS_REVIEW'],SENDING:['UNCONFIRMED','TEST_RECEIVED'],
 UNCONFIRMED:['SENDING','NEEDS_REVIEW'],NEEDS_REVIEW:['SENDING'],TEST_RECEIVED:[]};
const ID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function canTransition(a,b){return (NEXT[a]||[]).includes(b)}
export function safeFailure(v){return String(v||'Unverified send').replace(/\s+/g,' ').slice(0,180)}
function checkId(id){if(typeof id!=='string'||!ID.test(id))throw Error('Invalid job id')}
function hex(b){return [...new Uint8Array(b)].map(x=>x.toString(16).padStart(2,'0')).join('')}
function openDB(api){return new Promise((ok,no)=>{
 if(!api){no(Error('Local storage unavailable'));return}
 const q=api.open('mi-mundo-local-outbox-v1',1);
 q.onupgradeneeded=()=>{if(!q.result.objectStoreNames.contains('outbox'))
   q.result.createObjectStore('outbox',{keyPath:'jobId'})};
 q.onsuccess=()=>ok(q.result);q.onerror=()=>no(q.error||Error('Storage open failed'));
 q.onblocked=()=>no(Error('Local storage locked by another tab'));
})}
function transact(db,mode,fn){return new Promise((ok,no)=>{
 const tx=db.transaction('outbox',mode),store=tx.objectStore('outbox');
 let value;try{fn(store,(x)=>value=x)}catch(e){tx.abort();no(e);return}
 tx.oncomplete=()=>ok(value);tx.onerror=()=>no(tx.error||Error('Storage failed'));
 tx.onabort=()=>no(tx.error||Error('Storage transaction aborted'));
})}
function read(db,id){return transact(db,'readonly',(s,done)=>{
 const req=s.get(id);req.onsuccess=()=>done(req.result)
})}
export class LocalOutbox {
 constructor(db,cryptoImpl){this.db=db;this.cryptoImpl=cryptoImpl}
 static async open({indexedDBImpl=globalThis.indexedDB,cryptoImpl=globalThis.crypto}={}){
  return new LocalOutbox(await openDB(indexedDBImpl),cryptoImpl)
 }
 async get(id){checkId(id);return (await read(this.db,id))||null}
 async list(){return transact(this.db,'readonly',(s,done)=>{
  const q=s.getAll();q.onsuccess=()=>done(q.result.sort((a,b)=>b.updatedAt.localeCompare(a.updatedAt)))
 })}
 // Calling code MUST construct the archive ONCE before calling queue.
 async queue(jobId,blob,{kind='SYNTHETIC_TEST'}={}){
  checkId(jobId);if(kind!=='SYNTHETIC_TEST')throw Error('Real records forbidden in test outbox');
  if(!(blob instanceof Blob)||!blob.size||blob.size>100*1024*1024)throw Error('Invalid synthetic package');
  const sha256=hex(await this.cryptoImpl.subtle.digest('SHA-256',await blob.arrayBuffer()));
  const prior=await this.get(jobId);
  if(prior){if(prior.sha256!==sha256)throw Error('Job ID already holds different package bytes');return prior}
  const now=new Date().toISOString();
  const item={jobId,blob,sha256,byteLength:blob.size,kind,state:STATES.QUEUED,
    createdAt:now,updatedAt:now,attempts:0,lastError:null,testReceiptId:null};
  await transact(this.db,'readwrite',s=>s.add(item));
  const actual=await this.get(jobId);
  if(!actual||actual.sha256!==sha256||actual.blob.size!==blob.size||
      hex(await this.cryptoImpl.subtle.digest('SHA-256',await actual.blob.arrayBuffer()))!==sha256)
     throw Error('Local package readback failed; keep source file');
  return actual;
 }
 async transition(jobId,to,{lastError=null,testReceiptId=null}={}){
  checkId(jobId);if(!Object.values(STATES).includes(to))throw Error('Unknown job status');
  await transact(this.db,'readwrite',s=>{
   const r=s.get(jobId);r.onsuccess=()=>{
     const x=r.result;if(!x||!canTransition(x.state,to)){s.transaction.abort();return}
     x.state=to;x.updatedAt=new Date().toISOString();
     if(to===STATES.SENDING)x.attempts++;
     x.lastError=[STATES.UNCONFIRMED,STATES.NEEDS_REVIEW].includes(to)?safeFailure(lastError):null;
     if(to===STATES.TEST_RECEIVED)x.testReceiptId=testReceiptId;
     s.put(x)
   }
  });
  const value=await this.get(jobId);
  if(!value||value.state!==to)throw Error('Status update readback failed');
  return value;
 }
 async recoverInterrupted(){
  const found=await this.list(),pending=[];
  for(const x of found)if(x.state===STATES.SENDING)
   pending.push(await this.transition(x.jobId,STATES.UNCONFIRMED,
    {lastError:'App closed during send; receipt must be checked before retry'}));
  return pending;
 }
 async testSend(jobId,client){
  const x=await this.get(jobId);
  if(!x)throw Error('Local item missing');
  if(![STATES.QUEUED,STATES.UNCONFIRMED,STATES.NEEDS_REVIEW].includes(x.state))
    throw Error('Item unavailable for transmission');
  await this.transition(jobId,STATES.SENDING);
  try{
   // Client must GET previous receipt before deciding to retry PUT.
   const receipt=await client.transmit(jobId,x.blob);
   if(receipt.job_id!==jobId||receipt.package_sha256!==x.sha256||
     receipt.status!=='RECEIVED_TEST_ONLY'||!receipt.receipt_id)
     throw Error('Receipt verification failed');
   await this.transition(jobId,STATES.TEST_RECEIVED,{testReceiptId:receipt.receipt_id});
   return receipt;
  }catch(err){
   const current=await this.get(jobId);
   if(current?.state===STATES.SENDING)
      await this.transition(jobId,STATES.UNCONFIRMED,{lastError:err?.message});
   throw err;
  }
 }
 // Intentionally NO auto-delete: synthetic server receipt is ephemeral.
 close(){this.db.close()}
}
