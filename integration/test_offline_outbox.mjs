import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {LocalOutbox,STATES,canTransition,safeFailure} from './offline-outbox.mjs';

// Minimal evented IndexedDB fixture for deterministic Node contract tests.
// Real Safari IndexedDB/eviction behaviour requires separate on-device tests.
function fakeIndexedDB(){
 const tables=new Map();
 function db(){return {
  objectStoreNames:{contains:k=>tables.has(k)},
  createObjectStore(k){tables.set(k,new Map());return {createIndex(){}}},
  close(){},
  transaction(k){
   const values=tables.get(k);if(!values)throw Error('store missing');
   const tx={pending:0,aborted:false,abort(){this.aborted=true;setTimeout(()=>this.onabort?.(),0)}};
   function req(fn){
    const r={};tx.pending++;
    setTimeout(()=>{
     if(tx.aborted)return;
     try{r.result=fn();r.onsuccess?.()}
     catch(e){r.error=e;tx.aborted=true;r.onerror?.();tx.onerror?.()}
     tx.pending--;if(tx.pending===0)setTimeout(()=>{if(!tx.aborted)tx.oncomplete?.()},0);
    },0);
    return r;
   }
   const store={transaction:tx,
    get(key){return req(()=>values.get(key)&&structuredClone(values.get(key)))},
    add(item){return req(()=>{if(values.has(item.jobId))throw Error('duplicate');values.set(item.jobId,structuredClone(item))})},
    put(item){return req(()=>values.set(item.jobId,structuredClone(item)))},
    getAll(){return req(()=>[...values.values()].map(v=>structuredClone(v)))}
   };
   tx.objectStore=()=>store;return tx;
  }
 }}
 return {open(){const q={};setTimeout(()=>{q.result=db();q.onupgradeneeded?.();q.onsuccess?.()},0);return q}}
}
const id='ee3cf53e-16a8-43d2-9097-bcfc617b22e2';
const fixture=new Blob(['harmless synthetic test'],{type:'application/zip'});
async function setup(){return LocalOutbox.open({indexedDBImpl:fakeIndexedDB(),cryptoImpl:webcrypto})}
test('fail-closed state machine',()=>{
 assert.equal(canTransition(STATES.QUEUED,STATES.SENDING),true);
 assert.equal(canTransition(STATES.QUEUED,STATES.TEST_RECEIVED),false);
 assert.equal(canTransition(STATES.TEST_RECEIVED,STATES.QUEUED),false);
 assert.equal(safeFailure('foo\nbar'),'foo bar');
});
test('package survives write/readback',async()=>{
 const o=await setup(),x=await o.queue(id,fixture);
 assert.equal(x.state,STATES.QUEUED);
 assert.equal(await x.blob.text(),'harmless synthetic test');
 assert.equal((await o.get(id)).sha256,x.sha256);
 assert.equal((await o.list()).length,1);o.close();
});
test('same bytes idempotent, different bytes rejected',async()=>{
 const o=await setup();await o.queue(id,fixture);
 assert.equal((await o.queue(id,fixture)).attempts,0);
 await assert.rejects(o.queue(id,new Blob(['different'])),/different/);o.close();
});
test('offline leaves pending original',async()=>{
 const o=await setup();await o.queue(id,fixture);
 await assert.rejects(o.testSend(id,{transmit:async()=>{throw Error('offline')}}),/offline/);
 const x=await o.get(id);assert.equal(x.state,STATES.UNCONFIRMED);
 assert.equal(x.attempts,1);assert.equal(await x.blob.text(),'harmless synthetic test');
 assert.equal(x.lastError,'offline');o.close();
});
test('retry exact bytes and matching test receipt',async()=>{
 const o=await setup(),x=await o.queue(id,fixture);
 await assert.rejects(o.testSend(id,{transmit:async()=>{throw Error('timeout')}}));
 const r=await o.testSend(id,{transmit:async(j,b)=>{
   assert.equal(j,id);assert.equal(await b.text(),await fixture.text());
   return {job_id:j,package_sha256:x.sha256,status:'RECEIVED_TEST_ONLY',receipt_id:'fixture-receipt'};
 }});
 assert.equal(r.receipt_id,'fixture-receipt');
 const updated=await o.get(id);assert.equal(updated.state,STATES.TEST_RECEIVED);
 assert.equal(updated.attempts,2);o.close();
});
test('mismatched receipt never marks success',async()=>{
 const o=await setup();await o.queue(id,fixture);
 await assert.rejects(o.testSend(id,{transmit:async()=>({status:'RECEIVED_TEST_ONLY',job_id:'wrong'})}),/receipt/i);
 assert.equal((await o.get(id)).state,STATES.UNCONFIRMED);o.close();
});
test('crashed SENDING becomes UNCONFIRMED',async()=>{
 const o=await setup();await o.queue(id,fixture);await o.transition(id,STATES.SENDING);
 assert.equal((await o.recoverInterrupted()).length,1);
 assert.equal((await o.get(id)).state,STATES.UNCONFIRMED);o.close();
});
test('test receiver never triggers automatic deletion',async()=>{
 const o=await setup();assert.equal(typeof o.delete,'undefined');o.close();
});
