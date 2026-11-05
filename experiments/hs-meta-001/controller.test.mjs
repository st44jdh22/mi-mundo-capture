import test from 'node:test';
import assert from 'node:assert/strict';
import {CaptureController,MODES} from './controller.mjs';
const photo=()=>({id:'synthetic-photo-001',kind:'photo',mimeType:'application/x-test',bytes:12});

test('supports exactly the three commissioned options',()=>assert.deepEqual([...MODES],['photo','video','audio']));
test('unavailable native camera never claims a capture',async()=>{
  const c=new CaptureController(null); await c.choose('photo');
  assert.equal(c.state,'BLOCKED');assert.equal(c.capture,null);
});
test('cannot send without original',async()=>{
  const c=new CaptureController({});await c.send();assert.equal(c.state,'BLOCKED');
});
test('retains original if transport fails',async()=>{
  const bridge={capture:async()=>photo(),transmit:async()=>{throw Error('network unavailable')},verifyReceipt:async()=>false};
  const c=new CaptureController(bridge);await c.choose('photo');await c.send();
  assert.equal(c.state,'UNCONFIRMED');assert.equal(c.capture.id,photo().id);
});
test('does not accept a PUT response without independent readback',async()=>{
  const bridge={capture:async()=>photo(),transmit:async()=>({status:'RECEIVED_TEST_ONLY'}),verifyReceipt:async()=>false};
  const c=new CaptureController(bridge);await c.choose('photo');await c.send();
  assert.equal(c.state,'UNCONFIRMED');
});
test('accepts only test receipts when independently read back',async()=>{
  let checks=0;
  const bridge={capture:async()=>photo(),transmit:async()=>({status:'RECEIVED_TEST_ONLY'}),verifyReceipt:async()=>{checks++;return true}};
  const c=new CaptureController(bridge);await c.choose('photo');await c.send();
  assert.equal(c.state,'RECEIVED_TEST_ONLY');assert.equal(checks,1);
});
test('cannot overwrite unsent capture by changing mode',async()=>{
  const bridge={capture:async(kind)=>({...photo(),kind})};
  const c=new CaptureController(bridge);await c.choose('photo');await c.choose('video');
  assert.equal(c.capture.kind,'photo');assert.equal(c.state,'RETAINED');
});
test('refuses false production receipt even after boolean readback',async()=>{
  const c=new CaptureController({capture:async()=>photo(),transmit:async()=>({status:'RECEIVED'}),verifyReceipt:async()=>true});
  await c.choose('photo');await c.send();assert.equal(c.state,'UNCONFIRMED');
});
