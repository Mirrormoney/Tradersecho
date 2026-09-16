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
def isolate_tests(monkeypatch):
    monkeypatch.setattr(s,'CATALOG',dict(s.DEMO_CATALOG))
    with s.db() as c:
        for table in ['post_identity','post_authors','collection_jobs','chat_reports','chat_messages','owner_invites','audit_log','traffic_events','x_counts','x_spend','settings','watchlist','handles','sessions','accounts','attempts','webhook_events']:
            c.execute('DELETE FROM '+table)
        c.execute("DELETE FROM posts WHERE source='x'")
        c.execute("DELETE FROM meta WHERE key!='demo_anchor'")
    yield

def test_rankings_windows_and_separation():
    c=TestClient(s.app)
    c.post('/api/auth/demo?plan=free')
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
    with s.db() as conn: conn.execute("INSERT INTO settings VALUES('x_collection',?)",(json.dumps({'enabled':True,'monthly_budget':25,'sample_tickers':3,'sample_size':10}),))
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
    except RuntimeError as e: assert '429' in str(e)
    else: assert False
    try: collect(1,client)
    except RuntimeError as e: assert 'budget' in str(e)
    else: assert False
    del os.environ['X_BEARER_TOKEN']; del os.environ['X_DAILY_REQUEST_LIMIT']

def make_account(email,code=''):
    client=TestClient(s.app)
    response=client.post('/api/auth/signup',json={'email':email,'password':'long-test-password','owner_code':code})
    assert response.status_code==200,response.text
    return client,response.json()


def test_public_gate_owner_invitation_and_admin_controls():
    from .community import create_owner_invite
    guest=TestClient(s.app)
    assert len(guest.get('/api/rankings').json()['rows'])==3
    assert guest.get('/api/rankings?window=7').status_code==401
    assert guest.get('/api/posts').status_code==401
    assert guest.get('/api/admin/users').status_code==401
    code=create_owner_invite('Owner@example.com')
    assert guest.post('/api/auth/signup',json={'email':'wrong@example.com','password':'long-test-password','owner_code':code}).status_code==403
    with s.db() as conn: assert not conn.execute("SELECT 1 FROM accounts WHERE email='wrong@example.com'").fetchone()
    owner,o=make_account('OWNER@example.com',code)
    assert o['role']=='owner' and o['plan']=='premium'
    assert owner.post('/api/owner/claim',json={'code':code}).status_code==403
    member,m=make_account('member@example.com')
    assert m['role']=='member' and m['plan']=='free'
    assert len(member.get('/api/rankings').json()['rows'])==16
    assert member.get('/api/admin/users').status_code==403
    assert 'password' not in owner.get('/api/admin/users').text
    assert owner.patch('/api/admin/users/'+o['id'],json={'status':'suspended'}).status_code==403
    assert owner.patch('/api/admin/users/'+m['id'],json={'role':'admin'}).status_code==200
    assert member.get('/api/admin/users').status_code==200
    assert member.patch('/api/admin/users/'+o['id'],json={'plan':'free'}).status_code==403
    assert member.put('/api/admin/data-budget',json={'enabled':True}).status_code==403
    assert owner.patch('/api/admin/users/'+m['id'],json={'status':'suspended'}).status_code==200
    assert member.get('/api/watchlist').status_code==401
    assert member.post('/api/auth/login',json={'email':m['email'],'password':'long-test-password'}).status_code==403


def test_premium_room_privacy_rate_limits_reports_and_moderation():
    from .community import create_owner_invite
    owner,_=make_account('owner@example.com',create_owner_invite('owner@example.com'))
    free,f=make_account('free@example.com')
    assert free.get('/api/community/messages').status_code==403
    assert free.post('/api/community/messages',json={'body':'Denied'}).status_code==403
    demo=TestClient(s.app);demo.post('/api/auth/demo')
    assert demo.get('/api/community/messages').status_code==403
    owner.patch('/api/admin/users/'+f['id'],json={'plan':'premium'})
    free.put('/api/profile',json={'display_name':'Test Trader'})
    message=free.post('/api/community/messages',json={'body':'My thesis for $NVDA <script>bad()</script>','ticker':'NVDA'})
    assert message.status_code==200
    mid=message.json()['id']
    assert free.post('/api/community/messages',json={'body':'Spam'}).status_code==429
    feed=owner.get('/api/community/messages?ticker=NVDA').json()
    assert len(feed)==1 and feed[0]['display_name']=='Test Trader' and 'email' not in feed[0]
    assert owner.get('/api/community/messages?ticker=AMD').json()==[]
    assert free.post(f'/api/community/messages/{mid}/report',json={'reason':'Test report'}).status_code==200
    assert len(owner.get('/api/admin/reports').json())==1
    assert owner.patch(f'/api/admin/messages/{mid}',json={'hidden':True}).status_code==200
    assert free.get('/api/community/messages').json()==[]
    assert owner.get('/api/admin/reports').json()==[]
    owner.patch('/api/admin/users/'+f['id'],json={'plan':'free'})
    assert free.get('/api/community/messages').status_code==403


def test_traffic_is_deduplicated_and_excludes_staff_and_optouts():
    from .community import create_owner_invite
    import uuid
    owner,_=make_account('owner@example.com',create_owner_invite('owner@example.com'))
    guest=TestClient(s.app)
    payload={'event_id':str(uuid.uuid4()),'visitor_id':str(uuid.uuid4()),'page':'home'}
    guest.post('/api/analytics/visit',json=payload);guest.post('/api/analytics/visit',json=payload)
    for headers in [{'DNT':'1'},{'Sec-GPC':'1'},{'User-Agent':'SearchBot'}]:
        assert not guest.post('/api/analytics/visit',json={**payload,'event_id':str(uuid.uuid4())},headers=headers).json()['counted']
    assert not owner.post('/api/analytics/visit',json=payload).json()['counted']
    overview=owner.get('/api/admin/overview').json()
    assert overview['views_30d']==1 and overview['visitors_today']==1


def test_economy_counts_sampling_retries_and_currency_ceiling(monkeypatch):
    from . import collect_economy as economy
    from .community import create_owner_invite
    monkeypatch.setenv('X_BEARER_TOKEN','mock-only')
    owner,_=make_account('owner@example.com',create_owner_invite('owner@example.com'))
    calls=[];end=int(time.time()//3600)*3600
    def handler(request):
        calls.append(request)
        if 'counts' in request.url.path:
            return httpx.Response(200,json={'data':[{'start':economy.iso(end-i*3600),'end':economy.iso(end-(i-1)*3600),'tweet_count':i%4+1} for i in range(1,145)]})
        return httpx.Response(200,json={'data':[{'id':str(12345670+len(calls)),'author_id':'1','text':request.url.params['query'].split()[0]+' bullish','created_at':economy.iso(end-60)}],'includes':{'users':[{'id':'1','username':'sample_author'}]}})
    client=httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError,match='paused'): economy.collect(client)
    assert not calls
    owner.put('/api/admin/data-budget',json={'enabled':True,'monthly_budget':1,'sample_tickers':3,'sample_size':10})
    assert economy.collect(client)['posts_added']==3
    assert len(calls)==19
    economy.collect(client)
    assert len(calls)==19
    rows=owner.get('/api/rankings?source=x').json()
    assert len(rows['rows'])==16 and all(r['mentions']==60 for r in rows['rows'])
    assert all(r['comparison_complete'] for r in rows['rows'])
    assert sum(r['sample_mentions'] for r in rows['rows'])==3
    week=owner.get('/api/rankings?source=x&window=7').json()['rows']
    assert all(r['change'] is None and r['coverage_hours']==144 for r in week)
    with pytest.raises(RuntimeError,match='ceiling'): economy.paid_request(client,'tweets/search/recent',{},'sample',1,'mock')
    assert len(calls)==19
    assert owner.get('/api/admin/data-budget').json()['reserved_or_estimated_spend']==.125

def test_batched_collection_resumes_and_refuses_duplicate_purchases(monkeypatch):
    from . import collection as jobs
    from .community import create_owner_invite
    monkeypatch.setenv('X_BEARER_TOKEN','mock-only')
    monkeypatch.setattr(s,'CATALOG',{'NVDA':('NVIDIA','Chips'),'AMD':('AMD','Chips')})
    owner,_=make_account('owner@example.com',create_owner_invite('owner@example.com'))
    owner.put('/api/admin/data-budget',json={'enabled':True,'monthly_budget':1,'daily_post_limit':10,'daily_profile_limit':0})
    calls=[]
    def handler(request):
        calls.append(request)
        start=datetime.fromisoformat(request.url.params['start_time'].replace('Z','+00:00')).timestamp()
        end=datetime.fromisoformat(request.url.params['end_time'].replace('Z','+00:00')).timestamp()
        if 'counts' in request.url.path:
            return httpx.Response(200,json={'data':[{'start':jobs.iso(t),'end':jobs.iso(t+3600),'tweet_count':3} for t in range(int(start),int(end),3600)]})
        return httpx.Response(200,json={'data':[{'id':'55577','author_id':'6677889990011223344','text':'Bullish $NVDA','created_at':jobs.iso(end-30)}]})
    client=httpx.Client(transport=httpx.MockTransport(handler))
    assert jobs.run_batch(1,client)['completed']==1
    assert jobs.run_batch(10,client)['completed']==2
    assert len(calls)==3
    assert jobs.run_batch(10,client)['completed']==0
    assert len(calls)==3
    with s.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM collection_jobs WHERE status='done'").fetchone()[0]==3
        assert conn.execute("SELECT value FROM meta WHERE key='completed_snapshot'").fetchone()
    assert owner.get('/api/rankings?source=x').json()['rows'][0]['quality']['sufficient'] is False


def test_sample_screening_limits_authors_and_copy_templates():
    from .screening import screen,ticker_sentiment
    posts=[{'id':str(i),'author':'bot','text':'Buy $NVDA now!','ts':1000+i} for i in range(100)]
    result=screen(posts,s.classify,'NVDA')
    assert result['screened_posts']==1 and result['repeat_author_posts']==99
    assert not result['sufficient']
    for i in range(5):posts.append({'id':'x'+str(i),'author':'copy'+str(i),'text':'Buy $NVDA now!','ts':1100+i})
    result=screen(posts,s.classify,'NVDA')
    assert result['duplicate_posts']==5 and result['independent_authors']==1
    assert ticker_sentiment('Bullish $NVDA but bearish $TSLA','NVDA',s.classify)=='bullish'
    assert ticker_sentiment('Bullish $NVDA but bearish $TSLA','TSLA',s.classify)=='bearish'
    assert ticker_sentiment('Long $NVDA short $TSLA','NVDA',s.classify)=='neutral'


def test_cron_requires_secret_and_owner_signup_is_reserved(monkeypatch):
    from .community import create_owner_invite
    monkeypatch.setenv('CRON_SECRET','private-test-secret')
    c=TestClient(s.app)
    assert c.get('/api/cron/collect').status_code==401
    assert c.get('/api/cron/collect',headers={'Authorization':'Bearer wrong'}).status_code==401
    assert c.get('/api/cron/collect',headers={'Authorization':'Bearer private-test-secret'}).json()['paused']
    create_owner_invite('reserved@example.com')
    assert c.post('/api/auth/signup',json={'email':'reserved@example.com','password':'long-test-password'}).status_code==403
