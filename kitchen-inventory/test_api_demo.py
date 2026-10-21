from fastapi.testclient import TestClient
from api_demo import app
client=TestClient(app)
R={'X-Demo-Token':'test-read-only'}
W={'X-Demo-Token':'test-kitchen-writer','Idempotency-Key':'test:coffee-1'}

def test_roles():
    assert client.get('/v1/kitchen/current-stock').status_code==403
    assert client.get('/v1/kitchen/current-stock',headers=R).status_code==200
    assert client.post('/v1/kitchen/stock-events',headers=R,json={}).status_code==403

def test_exact_once_and_direct_read():
    payload={'source':'test:conversation-1','kind':'CONSUME','movements':[{'product':'coffee','location':'pantry','delta':'-1','unit':'count'}]}
    first=client.post('/v1/kitchen/stock-events',headers=W,json=payload)
    assert first.status_code==200,first.text
    assert first.json()['replayed'] is False
    replay=client.post('/v1/kitchen/stock-events',headers=W,json=payload)
    assert replay.status_code==200 and replay.json()['replayed'] is True
    rows=client.get('/v1/kitchen/current-stock?location=pantry',headers=R).json()['items']
    assert next(r for r in rows if r['product']=='coffee')['quantity']=='19'
    changed={**payload,'movements':[{'product':'coffee','location':'pantry','delta':'-2','unit':'count'}]}
    assert client.post('/v1/kitchen/stock-events',headers=W,json=changed).status_code==409

def test_unknown_stock_and_threshold():
    rows=client.get('/v1/kitchen/current-stock?location=fridge',headers=R).json()['items']
    assert next(r for r in rows if r['product']=='yoghurt')['state']=='UNKNOWN'
    needs=client.get('/v1/kitchen/shopping-needs',headers=R).json()['items']
    assert any(x['product']=='coffee' for x in needs)
