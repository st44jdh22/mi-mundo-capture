import {test} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {createHash} from 'node:crypto';
import {CaptureClient} from './capture-client.mjs';

const id = 'a54e5f03-da6c-44fa-834a-9a613d323fee';
const body = new Blob(['synthetic package']);
const digest = createHash('sha256').update('synthetic package').digest('hex');
const receipt = {job_id:id, package_sha256:digest, receipt_id:'test-receipt', status:'RECEIVED_TEST_ONLY',
  routed:false, departmental_updates:false, production_evidence_filed:false};
const token = 'test-only-random-token-with-32-characters';

async function fixture(handler, run) {
  const calls = [];
  const server = http.createServer(async (req, res) => {
    let bytes = Buffer.alloc(0);
    for await (const part of req) bytes = Buffer.concat([bytes, part]);
    calls.push(req.method);
    assert.equal(req.headers.authorization, 'Bearer ' + token);
    assert.equal(req.url, '/v1/jobs/' + id);
    await handler(req, res, calls, bytes);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const endpoint = 'http://127.0.0.1:' + server.address().port;
  const client = new CaptureClient({endpoint, token, testLoopback:true});
  try { await run(client, calls); }
  finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
}

function send(res, code, value) { res.writeHead(code, {'Content-Type':'application/json'}); res.end(JSON.stringify(value)); }

test('uploads once, reads back and reconciles a repeat', async () => {
  let stored = false;
  await fixture((req,res,_,bytes) => {
    if(req.method === 'PUT') { assert.equal(bytes.toString(), 'synthetic package'); stored=true; send(res,201,receipt); }
    else send(res, stored ? 200 : 404, stored ? receipt : {});
  }, async (client,calls) => {
    assert.deepEqual(await client.transmit(id,body),receipt);
    assert.deepEqual(await client.transmit(id,body),receipt);
    assert.deepEqual(calls,['GET','PUT','GET','GET']);
    await assert.rejects(client.transmit(id,new Blob(['changed'])),/Job changed/);
  });
});

test('lost upload response resolves by lookup without second PUT', async () => {
  let stored = false;
  await fixture((req,res) => {
    if(req.method==='PUT') {stored=true;res.destroy();}
    else send(res,stored?200:404,stored?receipt:{});
  }, async (client,calls) => {
    assert.deepEqual(await client.transmit(id,body),receipt);
    assert.deepEqual(calls,['GET','PUT','GET']);
  });
});

test('failed lookup never attempts upload', async () => {
  await fixture((_,res)=>send(res,503,{}),async(client,calls)=>{
    await assert.rejects(client.transmit(id,body),/lookup failed/);
    assert.deepEqual(calls,['GET']);
  });
});

test('wrong checksum cannot be shown as successful receipt', async () => {
  await fixture((_,res)=>send(res,200,{...receipt,package_sha256:'wrong'}),async(client)=>{
    await assert.rejects(client.transmit(id,body),/does not match/);
  });
});

test('successful upload without subsequent readback stays uncertain', async () => {
  await fixture((req,res)=>send(res,req.method==='PUT'?201:404,req.method==='PUT'?receipt:{}),async(client)=>{
    await assert.rejects(client.transmit(id,body),/not independently readable/);
  });
});

test('rejects unsafe endpoint configuration and invalid token', () => {
  for(const endpoint of ['http://example.com','https://example.com/path','https://user:pass@example.com',
    'https://example.com/?token=secret','https://example.com/#secret']) {
    assert.throws(()=>new CaptureClient({endpoint,token}));
  }
  assert.throws(()=>new CaptureClient({endpoint:'https://example.com',token:'short'}));
});

test('rejects credential redirect rather than following it', async () => {
  await fixture((_,res)=>{res.writeHead(302,{Location:'http://127.0.0.1:1/'});res.end();},async(client)=>{
    await assert.rejects(client.transmit(id,body));
  });
});
