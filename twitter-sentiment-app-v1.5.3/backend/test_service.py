import os, tempfile, time, json, hmac, hashlib
from datetime import datetime, timezone
os.environ['TRADERSECHO_DB']=tempfile.mktemp(suffix='.sqlite')
os.environ['ADMIN_TOKEN']='test-only-admin-token'
from fastapi.testclient import TestClient
from . import service as s
from .collect_x import collect
import httpx
import pytest

@pytest.fixture(autouse=True)
def isolate_tests():
    with s.db() as c:
        for table in ['watchlist','handles','sessions','accounts','attempts','webhook_events']:
            c.execute('DELETE FROM '+table)
        c.execute("DELETE FROM posts WHERE source='x'")
        c.execute("DELETE FROM meta WHERE key!='demo_anchor'")
    yield

def test_rankings_windows_and_separation():
    c=TestClient(s.app)
    day=c.get('/api/rankings?window=1').json()
    week=c.get('/api/rankings?window=7').json()
    month=c.get('/api/rankings?window=30').json()
    assert len(day['rows'])==16
    assert sum(r['mentions'] for r in day['rows'])<sum(r['mentions'] for r in week['rows'])<sum(r['mentions'] for r in month['rows'])
    assert all(r['bullish']+r['bearish']+r['neutral']==r['mentions'] for r in month['rows'])
    assert c.get('/api/rankings?window=2').status_code==422
    assert c.get('/api/rankings?source=x').json()['rows']==[]

def test_accounts_isolation_limits_and_logout():
    c=TestClient(s.app); other=TestClient(s.app)
    assert c.get('/api/watchlist').status_code==401
    assert c.post('/api/auth/signup',json={'email':'first@example.com','password':'long-test-password'}).status_code==200
    assert c.cookies.get('te_session')
    assert c.get('/api/handles').status_code==403
    for ticker in list(s.CATALOG)[:5]: assert c.put('/api/watchlist/'+ticker).status_code==200
    assert c.put('/api/watchlist/AMZN').status_code==403
    assert c.put('/api/watchlist/NVDA').status_code==200
    other.post('/api/auth/signup',json={'email':'second@example.com','password':'long-test-password'})
    assert other.get('/api/watchlist').json()==[]
    assert c.delete('/api/watchlist/NVDA').status_code==200
    assert len(c.get('/api/watchlist').json())==4
    assert c.post('/api/admin/plan',json={'email':'first@example.com','plan':'premium'}).status_code==403
    assert c.post('/api/admin/plan',headers={'x-admin-token':os.environ['ADMIN_TOKEN']},json={'email':'first@example.com','plan':'premium'}).status_code==200
    assert c.post('/api/handles',json={'handle':'@Investor','note':'Research'}).status_code==200
    assert c.get('/api/handles').json()[0]['handle']=='investor'
    assert c.post('/api/handles',json={'handle':'bad/handle'}).status_code==422
    c.post('/api/auth/logout')
    assert c.get('/api/watchlist').status_code==401
    assert c.post('/api/auth/login',json={'email':'first@example.com','password':'wrong-password'}).status_code==401
    assert c.post('/api/auth/login',json={'email':'first@example.com','password':'long-test-password'}).status_code==200
    assert len(c.get('/api/watchlist').json())==4

def test_demo_premium_does_not_unlock_live():
    c=TestClient(s.app)
    assert c.post('/api/auth/demo?plan=premium').status_code==200
    assert c.get('/api/posts?tracked=true&source=demo').status_code==200
    assert c.get('/api/posts?tracked=true&source=x').status_code==403
    assert c.post('/api/billing/checkout').status_code==400

def test_import_dedup_multiticker_validation_and_tracked():
    c=TestClient(s.app); headers={'x-admin-token':os.environ['ADMIN_TOKEN']}
    post={'id':'123456789','author':'investor','text':'Bullish $NVDA $AMD $NVDA','created_at':datetime.now(timezone.utc).isoformat()}
    assert c.post('/api/admin/import',json={'posts':[post]}).status_code==403
    first=c.post('/api/admin/import',headers=headers,json={'posts':[post]}).json()
    assert first['posts_added']==1 and first['mentions_added']==2
    assert c.post('/api/admin/import',headers=headers,json={'posts':[post]}).json()['posts_added']==0
    rows=c.get('/api/rankings?source=x').json()['rows']
    assert len(rows)==2 and all(r['mentions']==1 for r in rows)
    assert c.post('/api/admin/import',headers=headers,json={'posts':[{**post,'id':'2'}, {**post,'id':'bad'}]}).status_code==422
    with s.db() as conn: assert not conn.execute("SELECT 1 FROM posts WHERE id='2'").fetchone()
    c.post('/api/auth/signup',json={'email':'importer@example.com','password':'long-test-password'})
    c.post('/api/admin/plan',headers=headers,json={'email':'importer@example.com','plan':'premium'})
    c.post('/api/handles',json={'handle':'investor'})
    assert c.get('/api/posts?tracked=true&source=x').json()[0]['id']==post['id']

def test_security_and_classifier():
    c=TestClient(s.app)
    assert c.post('/api/auth/demo',headers={'Origin':'https://evil.example'}).status_code==403
    assert s.classify('not bullish on this')=='bearish'
    assert s.classify('strong growth and upside')=='bullish'
    assert c.get('/api/me').headers['cache-control']=='no-store'
    os.environ['STRIPE_WEBHOOK_SECRET']='test'
    assert c.post('/api/billing/webhook',content='{}').status_code==400
    del os.environ['STRIPE_WEBHOOK_SECRET']

def test_collector_pagination_checkpoint_budget_and_retry():
    os.environ['X_BEARER_TOKEN']='fake-test-token';os.environ['X_DAILY_REQUEST_LIMIT']='3'
    calls=[]
    def handler(request):
        calls.append(dict(request.url.params))
        next_page=request.url.params.get('next_token')
        return httpx.Response(200,json={'data':[{'id':'987654322' if next_page else '987654321','author_id':'42','text':'$NVDA bullish','created_at':datetime.now(timezone.utc).isoformat()}], 'includes':{'users':[{'id':'42','username':'collector_test'}]},'meta':{} if next_page else {'next_token':'page2'}})
    client=httpx.Client(transport=httpx.MockTransport(handler))
    first=collect(1,client); assert first['pending']
    second=collect(1,client);assert not second['pending']
    assert calls[1]['next_token']=='page2' and calls[0]['end_time']==calls[1]['end_time']
    # Network failure must not erase a completed checkpoint.
    def fail(request): return httpx.Response(429)
    try: collect(1,httpx.Client(transport=httpx.MockTransport(fail)))
    except RuntimeError as e: assert 'rate limit' in str(e)
    else: assert False
    try: collect(1,client)
    except RuntimeError as e: assert 'budget' in str(e)
    else: assert False
    del os.environ['X_BEARER_TOKEN']; del os.environ['X_DAILY_REQUEST_LIMIT']
