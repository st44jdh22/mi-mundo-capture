import test from 'node:test';
import assert from 'node:assert/strict';
import {statusMessage,inboxProjection,INBOX_KINDS} from './inbox-status.mjs';
const base={jobId:'ee3cf53e-16a8-43d2-9097-bcfc617b22e2',updatedAt:'2026-10-18T00:00:00Z'};
test('offline queue visible but no send action',()=>{
 const m=statusMessage({...base,state:'QUEUED'},{online:false});
 assert.equal(m.kind,INBOX_KINDS.PENDING);assert.equal(m.primaryAction,null);
 assert.equal(m.durableVerified,false);assert.match(m.description,/No internet/);
});
test('online queued test offers explicit send',()=>{
 assert.equal(statusMessage({...base,state:'QUEUED'}).primaryAction,'SEND_TEST')
});
test('lost upload stays attention and retryable only online',()=>{
 const v={...base,state:'UNCONFIRMED',lastError:'timeout'};
 const off=statusMessage(v,{online:false}),on=statusMessage(v,{online:true});
 assert.equal(off.primaryAction,null);assert.equal(on.primaryAction,'RETRY_TEST');
 assert.match(on.description,/retained locally/);
});
test('test confirmation never claims durable cloud storage',()=>{
 const m=statusMessage({...base,state:'TEST_RECEIVED'});
 assert.equal(m.kind,INBOX_KINDS.TEST_ACK);
 assert.equal(m.remoteVerified,true);assert.equal(m.durableVerified,false);
 assert.match(m.description,/no permanent cloud archive/);
});
test('unknown state is not silently marked complete',()=>{
 const m=statusMessage({...base,state:'INVALID'});
 assert.equal(m.kind,INBOX_KINDS.UNKNOWN);assert.equal(m.durableVerified,false)
});
test('attention messages sort before test acknowledgments',()=>{
 const x=inboxProjection([{...base,state:'TEST_RECEIVED'},{...base,state:'UNCONFIRMED'}]);
 assert.equal(x[0].kind,INBOX_KINDS.ACTION)
});
test('error text does not carry out the injection',()=>{
 const x=statusMessage({...base,state:'UNCONFIRMED',lastError:'<script>alert(1)</script>'});
 assert.equal(x.description.includes('<script>'),true);
 // Actual DOM uses textContent, not innerHTML. This contract alone doesn't verify DOM.
 assert.equal(x.durableVerified,false)
});
