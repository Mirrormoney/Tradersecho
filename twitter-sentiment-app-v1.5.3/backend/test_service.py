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
    monkeypatch.setenv('BILLING_SANDBOX','true')
    monkeypatch.setenv('TRADERSECHO_SCHEMA','billing_sandbox_tests')
    monkeypatch.setattr(s,'CATALOG',dict(s.DEMO_CATALOG))
    with s.db() as c:
        for table in ['ai_sentiment','ai_sentiment_spend','email_events','email_deliveries','email_optouts','email_suppressions','account_tokens','billing_checkouts','billing_entitlements','admin_voices','voice_checkpoints','digest_preferences','daily_briefings','post_identity','post_authors','collection_jobs','chat_reports','chat_messages','owner_invites','audit_log','traffic_events','x_counts','x_spend','settings','watchlist','handles','sessions','accounts','attempts','webhook_events']:
            c.execute('DELETE FROM '+table)
        c.execute("DELETE FROM posts WHERE source='x'")
        c.execute("DELETE FROM meta WHERE key!='demo_anchor'")
    yield

def test_custom_domain_login_and_origin_rejection(monkeypatch):
    monkeypatch.setattr(s,'SECURE',True)
    monkeypatch.setattr(s,'ORIGIN','https://tradersecho.com')
    monkeypatch.setenv('APP_ADDITIONAL_ORIGINS','https://tradersecho-preview-sven-mais-projects.vercel.app')
    c=TestClient(s.app,base_url='https://tradersecho.com')
    body={'email':'domain-test@example.com','password':'long-test-password'}
    assert c.post('/api/auth/signup',json=body,headers={'origin':s.ORIGIN}).status_code==200
    assert c.post('/api/auth/login',json=body,headers={'origin':s.ORIGIN}).status_code==200
    assert c.get('/api/me').status_code==200
    assert c.post('/api/auth/login',json=body,headers={'origin':'https://tradersecho-preview-sven-mais-projects.vercel.app'}).status_code==200
    rejected=c.post('/api/auth/login',json=body,headers={'origin':'https://tradersecho.com.attacker.example'})
    assert rejected.status_code==403
    assert 'website address' in rejected.json()['detail']


def test_rankings_windows_and_separation():
    c=TestClient(s.app)
    c.post('/api/auth/demo?plan=premium')
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
    assert len(member.get('/api/rankings').json()['rows'])==5
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


def test_daily_counts_ignore_newer_intraday_buckets(monkeypatch):
    from . import collection as jobs
    from .community import create_owner_invite
    monkeypatch.setenv('X_BEARER_TOKEN','mock-only')
    monkeypatch.setattr(s,'CATALOG',{'AAPL':('Apple','Chips')})
    owner,_=make_account('owner@example.com',create_owner_invite('owner@example.com'))
    owner.put('/api/admin/data-budget',json={'enabled':True,'monthly_budget':1,'intraday_enabled':True})
    end=int(time.time()//86400)*86400
    with s.db() as c:
        c.executemany('INSERT INTO x_counts VALUES(?,?,?,?,?,?)',[
            ('AAPL',t,t+3600,3,'test',time.time()) for t in range(end-6*86400,end+3*3600,3600)])
    calls=[]
    def handler(request):
        start=datetime.fromisoformat(request.url.params['start_time'].replace('Z','+00:00')).timestamp()
        finish=datetime.fromisoformat(request.url.params['end_time'].replace('Z','+00:00')).timestamp()
        assert start==end-3600 and finish==end
        calls.append(request)
        return httpx.Response(200,json={'data':[{'start':jobs.iso(start),'end':jobs.iso(finish),'tweet_count':5}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert jobs.run_batch(10,client)['errors']==[]
        assert jobs.run_batch(10,client)['completed']==0
    assert len(calls)==1
    with s.db() as c:
        assert float(c.execute("SELECT value FROM meta WHERE key='completed_snapshot'").fetchone()[0])==end
        assert c.execute('SELECT n FROM x_counts WHERE ticker=? AND start=?',('AAPL',end+7200)).fetchone()[0]==3


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
    assert ticker_sentiment('Long $NVDA short $TSLA','NVDA',s.classify)=='unclear'


def test_cron_requires_secret_and_owner_signup_is_reserved(monkeypatch):
    from .community import create_owner_invite
    monkeypatch.setenv('CRON_SECRET','private-test-secret')
    c=TestClient(s.app)
    assert c.get('/api/cron/collect').status_code==401
    assert c.get('/api/cron/collect',headers={'Authorization':'Bearer wrong'}).status_code==401
    assert c.get('/api/cron/collect',headers={'Authorization':'Bearer private-test-secret'}).json()['paused']
    create_owner_invite('reserved@example.com')
    assert c.post('/api/auth/signup',json={'email':'reserved@example.com','password':'long-test-password'}).status_code==403

def test_hourly_planning_budget_and_shared_demand(monkeypatch):
    from . import live_collection as live
    from .community import create_owner_invite
    monkeypatch.setenv('X_BEARER_TOKEN','mock-only')
    monkeypatch.setattr(s,'CATALOG',{'NVDA':('NVIDIA','Chips'),'AMD':('AMD','Chips')})
    owner,u=make_account('hourly@example.com',create_owner_invite('hourly@example.com'))
    owner.put('/api/admin/data-budget',json={'enabled':True,'intraday_enabled':True,'monthly_budget':5,'daily_post_limit':20,'daily_profile_limit':0})
    end=int(time.time()//3600)*3600
    with s.db() as c:
        c.execute("INSERT INTO meta VALUES('completed_snapshot',?)",(str(end-86400),))
        c.executemany('INSERT INTO x_counts VALUES(?,?,?,?,?,?)',[('NVDA',end-172800+i*3600,end-172800+(i+1)*3600,3,'mock',time.time()) for i in range(24)])
    live.plan_hour();live.plan_hour()
    with s.db() as c:
        assert c.execute("SELECT COUNT(*) FROM collection_jobs WHERE kind='hour_counts'").fetchone()[0]==1
        assert c.execute("SELECT COUNT(*) FROM collection_jobs WHERE kind='hour_sample'").fetchone()[0]==1
    a=owner.post('/api/refresh/AMD');b=owner.post('/api/refresh/AMD')
    assert a.status_code==b.status_code==200
    with s.db() as c:assert c.execute("SELECT COUNT(*) FROM collection_jobs WHERE kind='request_counts'").fetchone()[0]==1
    guest=TestClient(s.app)
    assert guest.post('/api/refresh/AMD').status_code==401
    free,_=make_account('free-hourly@example.com')
    assert free.post('/api/refresh/AMD').status_code==403
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={'data':[]})
    client=httpx.Client(transport=httpx.MockTransport(handler))
    from .collect_economy import paid_request
    paid_request(client,'tweets/search/recent',{},'sample_live',.05,'mock')
    paid_request(client,'tweets/search/recent',{},'sample_live',.05,'mock')
    with pytest.raises(RuntimeError,match='allowance'):paid_request(client,'tweets/search/recent',{},'sample_live',.05,'mock')
    assert len(calls)==2


def test_shared_voices_limits_privacy_and_collection(monkeypatch):
    from . import live_collection as live
    from .voices import shared_handles
    from .community import create_owner_invite
    monkeypatch.setenv('X_BEARER_TOKEN','mock-only')
    owner,_=make_account('voice-owner@example.com',create_owner_invite('voice-owner@example.com'))
    members=[]
    for i in range(5):
        member,u=make_account(f'voice{i}@example.com')
        owner.patch('/api/admin/users/'+u['id'],json={'plan':'premium'})
        assert member.post('/api/handles',json={'handle':'@SharedVoice','note':f'private{i}'}).status_code==200
        members.append((member,u))
    a,u=members[0]
    for i in range(4):assert a.post('/api/handles',json={'handle':f'extra{i}'}).status_code==200
    assert a.post('/api/handles',json={'handle':'sixth'}).status_code==403
    assert a.post('/api/handles',json={'handle':'SHAREDVOICE','note':'updated private'}).status_code==200
    assert len(a.get('/api/handles').json())==5
    assert members[1][0].get('/api/handles').json()[0]['note']=='private1'
    assert a.post('/api/admin/voices',json={'handle':'forbidden'}).status_code==403
    free,_=make_account('voice-free@example.com')
    assert free.get('/api/voices/curated').status_code==200
    assert owner.post('/api/admin/voices',json={'handle':'@SHAREDVOICE','note':'public note'}).status_code==200
    duplicate=a.post('/api/handles',json={'handle':'@SHAREDVOICE','note':'must not overwrite'})
    assert duplicate.status_code==200 and duplicate.json()['already_curated']
    assert len(a.get('/api/handles').json())==5
    assert next(r for r in a.get('/api/handles').json() if r['handle']=='sharedvoice')['note']=='updated private'
    fresh=members[1][0].post('/api/handles',json={'handle':'sharedvoice'})
    assert fresh.json()['already_curated']
    for i in range(4):a.delete('/api/handles/'+f'extra{i}')
    registry=owner.get('/api/admin/voices').json()
    assert registry['unique_accounts']==1 and registry['rows'][0]['followers']==5
    assert 'private' not in json.dumps(registry)
    owner.put('/api/admin/data-budget',json={'enabled':True,'intraday_enabled':True,'monthly_budget':5})
    end=int(time.time()//3600)*3600
    with s.db() as c:c.execute("INSERT INTO meta VALUES('completed_snapshot',?)",(str(end-86400),))
    live.plan_hour();live.plan_hour()
    with s.db() as c:
        jobs=[dict(r) for r in c.execute("SELECT * FROM collection_jobs WHERE kind='hour_voice'")]
    assert len(jobs)==1 and jobs[0]['query'].count('from:sharedvoice')==1
    calls=[]
    def handler(request):
        calls.append(request)
        if '/users/' in request.url.path:return httpx.Response(200,json={'data':[{'id':'73','username':'SharedVoice'}]})
        return httpx.Response(200,json={'data':[{'id':'987321001','author_id':'73','text':'Watching $NVDA','created_at':live.iso(end-20)}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        live.perform(jobs[0],client)
        live.perform(jobs[0],client)
    assert len(calls)==2  # one shared profile lookup + one shared post search, including retry
    for member,_ in members:assert len(member.get('/api/posts?source=x&tracked=true').json())==1
    assert len(owner.get('/api/posts?source=x&tracked=true').json())==1  # curated, no personal follow
    assert len(free.get('/api/posts?source=x&tracked=true').json())==1
    assert a.delete('/api/handles/@SharedVoice').status_code==200
    assert len(a.get('/api/posts?source=x&tracked=true').json())==1  # still curated
    owner.delete('/api/admin/voices/sharedvoice')
    with s.db() as c:assert shared_handles(c)==['sharedvoice']  # other subscribers retain it
    assert a.get('/api/posts?source=x&tracked=true').json()==[]
    for _,u in members[1:]:owner.patch('/api/admin/users/'+u['id'],json={'status':'suspended'})
    with s.db() as c:assert shared_handles(c)==[]
    for i in range(8):assert owner.post('/api/admin/voices',json={'handle':f'curated{i}'}).status_code==200
    assert len(owner.get('/api/admin/voices').json()['rows'])==8
    assert a.post('/api/handles',json={'handle':'CURATED0'}).json()['already_curated']
    assert a.get('/api/handles').json()==[]


def test_blocked_new_voice_does_not_starve_cached_voices(monkeypatch):
    from . import live_collection as live
    from .community import create_owner_invite
    owner,_=make_account('queue-owner@example.com',create_owner_invite('queue-owner@example.com'))
    owner.put('/api/admin/data-budget',json={'enabled':True,'intraday_enabled':True,'monthly_budget':10,'daily_profile_limit':0})
    monkeypatch.setenv('X_BEARER_TOKEN','mock-only')
    end=int(time.time()//3600)*3600
    with s.db() as c:
        c.execute("INSERT INTO meta VALUES('completed_snapshot',?)",(str(end-86400),))
        for handle in ['blocked','cached']:
            c.execute('INSERT INTO admin_voices VALUES(?,?,?)',(handle,'',time.time()))
        c.execute('INSERT INTO voice_checkpoints VALUES(?,?,?,0)',('cached',end-3600,time.time()))
        c.execute('INSERT INTO post_authors(id,handle,fetched_at) VALUES(?,?,?)',('42','cached',time.time()))
    live.plan_hour();live.plan_hour()
    with s.db() as c:jobs=[dict(r) for r in c.execute("SELECT * FROM collection_jobs WHERE kind='hour_voice' ORDER BY id")]
    assert len(jobs)==2
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={'data':[]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError,match='profile lookup allowance'):live.perform(jobs[0],client)
        live.perform(jobs[1],client)
    assert len(calls)==1 and 'from:cached' in calls[0].url.params['query']
    with s.db() as c:assert c.execute("SELECT window_end FROM voice_checkpoints WHERE handle='cached'").fetchone()[0]==end


def test_rate_pacing_and_provider_reset(monkeypatch):
    from .collect_economy import paid_request,CollectionDeferred
    from .community import create_owner_invite
    owner,_=make_account('pacing@example.com',create_owner_invite('pacing@example.com'))
    owner.put('/api/admin/data-budget',json={'enabled':True,'monthly_budget':5})
    now=time.time();month=datetime.now(timezone.utc).strftime('%Y-%m');calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,headers={'x-rate-limit-remaining':'0','x-rate-limit-reset':str(now+7200)},json={'data':[]})
    client=httpx.Client(transport=httpx.MockTransport(handler))
    with s.db() as c:c.executemany('INSERT INTO x_spend(month,kind,reserved,ts,status) VALUES(?,?,?,?,?)',[(month,'counts_live',.005,now-30,'received')]*240)
    with pytest.raises(CollectionDeferred):paid_request(client,'tweets/counts/recent',{},'counts',.005,'mock')
    assert not calls
    with s.db() as c:
        assert c.execute('SELECT COUNT(*) FROM x_spend').fetchone()[0]==240
        c.execute('UPDATE x_spend SET ts=?',(now-1000,))
    paid_request(client,'tweets/counts/recent',{},'counts',.005,'mock')
    with pytest.raises(CollectionDeferred) as pause:paid_request(client,'tweets/counts/recent',{},'counts',.005,'mock')
    assert pause.value.until>=now+7200 and len(calls)==1


def test_worker_lease_cooldown_and_tracked_posts(monkeypatch):
    from . import live_collection as live
    from .community import create_owner_invite
    from .collect_economy import paid_request
    monkeypatch.setenv('X_BEARER_TOKEN','mock-only')
    owner,u=make_account('worker@example.com',create_owner_invite('worker@example.com'))
    owner.put('/api/admin/data-budget',json={'enabled':True,'intraday_enabled':True,'monthly_budget':5})
    with s.db() as c:c.execute("INSERT INTO meta VALUES('worker_lease',?)",(json.dumps({'token':'other','until':time.time()+90}),))
    assert live.tick()['busy']
    with s.db() as c:c.execute("DELETE FROM meta WHERE key='worker_lease'")
    calls=[]
    def handler(request):
        calls.append(request);return httpx.Response(429,json={'title':'rate limit'})
    client=httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError,match='429'):paid_request(client,'tweets/counts/recent',{},'counts_live',.005,'mock')
    with pytest.raises(RuntimeError,match='cooldown'):paid_request(client,'tweets/counts/recent',{},'counts_live',.005,'mock')
    assert live.tick(scheduled=True,client=client)['deferred']
    with s.db() as c:
        assert c.execute("SELECT COUNT(*) FROM collection_jobs").fetchone()[0]==0
        assert c.execute("SELECT value FROM meta WHERE key='scheduler_seen'").fetchone()
    assert len(calls)==1
    owner.post('/api/handles',json={'handle':'researcher','note':'test'})
    result=s.ingest([{'id':'883322','author':'researcher','author_id':'77','text':'A useful general discussion without a cashtag','created_at':datetime.now(timezone.utc).isoformat()}],include_unmatched=True)
    assert result['posts_added']==1 and result['mentions_added']==0
    rows=owner.get('/api/posts?source=x&tracked=true').json()
    assert len(rows)==1 and rows[0]['author']=='researcher'


def test_bulk_history_and_live_freshness(monkeypatch):
    from .live_collection import perform
    from .community import create_owner_invite
    monkeypatch.setenv('X_BEARER_TOKEN','mock-only')
    owner,u=make_account('bulk@example.com',create_owner_invite('bulk@example.com'))
    owner.put('/api/admin/data-budget',json={'enabled':True,'intraday_enabled':True,'monthly_budget':5})
    end=int(time.time()//3600)*3600
    def handler(request):
        from .collect_economy import iso
        return httpx.Response(200,json={'data':[{'start':iso(t),'end':iso(t+3600),'tweet_count':7} for t in range(end-86400,end,3600)]})
    client=httpx.Client(transport=httpx.MockTransport(handler))
    perform({'kind':'hour_counts','ticker':'NVDA','window_end':end,'query':'$NVDA'},client)
    data=owner.get('/api/live/NVDA').json()
    assert data['mentions_24h']==168 and data['coverage_hours']==24 and not data['stale']
    assert owner.post('/api/refresh/NVDA').json()['state']=='fresh'

def test_digest_coverage_personalization_and_preferences(monkeypatch):
    from . import digest
    monkeypatch.setattr(s,'CATALOG',{'INTC':('Intel','Chips'),'MU':('Micron','Memory')})
    member,u=make_account('digest@example.com')
    other,v=make_account('other-digest@example.com')
    assert TestClient(s.app).get('/api/digest').status_code==401
    assert not member.get('/api/digest').json()['ready']
    assert member.put('/api/digest/preferences',json={'frequency':'daily'}).status_code==403
    assert member.put('/api/digest/preferences',json={'frequency':'weekly'}).status_code==200
    assert other.get('/api/digest/preferences').json()['frequency']=='off'
    end=int(time.time()//86400)*86400
    with s.db() as c:
        c.execute("INSERT INTO meta VALUES('completed_snapshot',?)",(str(end),))
        for ticker in ['INTC','MU']:
            c.executemany('INSERT INTO x_counts VALUES(?,?,?,?,?,?)',[(ticker,start,start+3600,4 if start>=end-86400 else 2,'test',time.time()) for start in range(end-172800,end,3600)])
        c.execute('DELETE FROM x_counts WHERE ticker=? AND start=?',('MU',end-3600))
    assert not digest.build()['ready']
    with s.db() as c:c.execute('INSERT INTO x_counts VALUES(?,?,?,?,?,?)',('MU',end-3600,end,4,'test',time.time()))
    result=digest.build()
    assert result['ready'] and result['rows'][0]['mentions']==96 and result['rows'][0]['change']==100
    assert len(result['x_draft'])<=280
    with s.db() as c:
        c.execute('UPDATE x_counts SET n=99')
        c.execute("UPDATE accounts SET plan='premium' WHERE id=?",(u['id'],))
    assert digest.build()==result  # An issued report is immutable.
    member.put('/api/watchlist/INTC')
    member.post('/api/handles',json={'handle':'scroogecap'})
    s.ingest([{'id':'887766','author':'scroogecap','text':'$INTC buying','created_at':datetime.fromtimestamp(end,timezone.utc).isoformat()}])
    assert member.put('/api/digest/preferences',json={'frequency':'daily','watchlist_only':True}).status_code==200
    personal=member.get('/api/digest').json()
    assert [r['ticker'] for r in personal['rows']]==['INTC'] and len(personal['posts'])==1
    assert other.get('/api/digest').json()['posts']==[]
    assert member.get('/api/admin/digest').status_code==403
    assert not digest.build(now=end+37*3600)['ready']
    member.put('/api/digest/preferences',json={'frequency':'off'})
    assert member.get('/api/digest/preferences').json()['frequency']=='off'


def test_daily_plan_picks_up_new_stocks(monkeypatch):
    from .collection import plan_day
    from .community import create_owner_invite
    monkeypatch.setenv('X_BEARER_TOKEN','mock-only')
    owner,_=make_account('reconcile@example.com',create_owner_invite('reconcile@example.com'))
    owner.put('/api/admin/data-budget',json={'enabled':True,'monthly_budget':5})
    monkeypatch.setattr(s,'CATALOG',{'INTC':('Intel','Chips')})
    day,_,_=plan_day()
    monkeypatch.setattr(s,'CATALOG',{'INTC':('Intel','Chips'),'CAT':('Caterpillar','Infrastructure')})
    plan_day();plan_day()
    with s.db() as c:
        assert [r[0] for r in c.execute("SELECT ticker FROM collection_jobs WHERE day=? AND kind='counts' ORDER BY ticker",(day,))]==['CAT','INTC']


def test_display_names_unique_and_chat_identity_updates():
    from .community import create_owner_invite,available_default_name
    from .database import IntegrityError
    owner,_=make_account('identity-owner@example.com',create_owner_invite('identity-owner@example.com'))
    a,u=make_account('identity-a@example.com');b,v=make_account('identity-b@example.com')
    assert a.put('/api/profile',json={'display_name':'  Sven   Mai  '}).json()['display_name']=='Sven Mai'
    response=b.put('/api/profile',json={'display_name':'sVEN  mAI'})
    assert response.status_code==409 and 'already taken' in response.json()['detail']
    assert b.get('/api/me').json()['display_name']==v['display_name']
    assert a.put('/api/profile',json={'display_name':'SVEN MAI'}).status_code==200
    assert a.put('/api/profile',json={'display_name':'---'}).status_code==422
    with pytest.raises(IntegrityError):
        with s.db() as c:c.execute('UPDATE accounts SET display_name=? WHERE id=?',('sven mai',v['id']))
    owner.patch('/api/admin/users/'+u['id'],json={'plan':'premium'})
    assert a.post('/api/community/messages',json={'body':'A research idea'}).status_code==200
    assert a.put('/api/profile',json={'display_name':'New Researcher'}).status_code==200
    post=owner.get('/api/community/messages').json()[0]
    assert post['display_name']=='New Researcher' and post['plan']=='premium' and 'email' not in post
    owner.patch('/api/admin/users/'+u['id'],json={'plan':'free'})
    assert owner.get('/api/community/messages').json()[0]['plan']=='free'
    assert b.put('/api/profile',json={'display_name':'Sven Mai'}).status_code==200
    assert a.put('/api/profile',json={'display_name':'Trader-abcdef'}).status_code==200
    with s.db() as c:assert available_default_name(c,'abcdef0000')!='Trader-abcdef'


def test_free_rankings_are_server_limited_and_watchlist_survives():
    from .community import create_owner_invite
    guest=TestClient(s.app)
    assert len(guest.get('/api/rankings').json()['rows'])==3
    free,u=make_account('ranking-free@example.com')
    owner,_=make_account('ranking-owner@example.com',create_owner_invite('ranking-owner@example.com'))
    full=owner.get('/api/rankings').json()
    for window in (1,7,30):
        preview=free.get(f'/api/rankings?window={window}').json()
        assert len(preview['rows'])==5 and preview['ranking_locked']
        assert preview['total_tickers']==16
    outside=full['rows'][-1]['ticker']
    assert free.put('/api/watchlist/'+outside).status_code==200
    watched=free.get('/api/rankings?scope=watchlist').json()
    assert [r['ticker'] for r in watched['rows']]==[outside]
    assert len(free.get('/api/rankings?scope=market&limit=1000').json()['rows'])==5
    assert guest.get('/api/rankings?scope=watchlist').status_code==401
    owner.patch('/api/admin/users/'+u['id'],json={'plan':'premium'})
    upgraded=free.get('/api/rankings').json()
    assert len(upgraded['rows'])==16 and not upgraded['ranking_locked']

def test_checkout_tiers_reuse_and_account_binding(monkeypatch):
    from . import payments as p
    c=TestClient(s.app)
    uid=c.post('/api/auth/signup',json={'email':'billing@example.com','password':'long-test-password'}).json()['id']
    assert c.post('/api/billing/checkout',json={'tier':'invalid'}).status_code==422
    assert c.post('/api/billing/checkout',json={'tier':'yearly'}).status_code==503
    for k,v in {'BILLING_ENABLED':'true','STRIPE_SECRET_KEY':'sk_test_test','STRIPE_WEBHOOK_SECRET':'test','STRIPE_PRICE_MONTHLY':'price_monthly','STRIPE_PRICE_YEARLY':'price_yearly','STRIPE_PRICE_FOUNDER':'price_founder'}.items():monkeypatch.setenv(k,v)
    calls=[];sessions={};counter=[0]
    def stripe(method,path,data=None,idempotency=None):
        calls.append((method,path,data,idempotency))
        if path.startswith('prices/'):
            tier=path.split('_')[-1];_,amount,interval=p.TIERS[tier]
            return {'id':'price_'+tier,'currency':'usd','unit_amount':amount,'recurring':{'interval':interval,'interval_count':1} if interval else None}
        if path=='customers':return {'id':'cus_own'}
        if path=='checkout/sessions':
            counter[0]+=1;sid='cs_'+str(counter[0]);sessions[sid]={'id':sid,'status':'open','url':'https://checkout.stripe.com/test/'+sid};return sessions[sid]
        if path.endswith('/expire'):
            sessions[path.split('/')[2]]['status']='expired';return {}
        if path.startswith('checkout/sessions/'):return sessions[path.split('/')[-1]]
        if path=='billing_portal/sessions':return {'url':'https://billing.stripe.com/test'}
        raise AssertionError(path)
    monkeypatch.setattr(p,'stripe',stripe)
    first=c.post('/api/billing/checkout',json={'tier':'yearly','customer':'cus_attacker','price':'fake'});assert first.status_code==200
    data=[x[2] for x in calls if x[1]=='checkout/sessions'][-1]
    assert data['customer']=='cus_own' and data['client_reference_id']==uid and data['line_items[0][price]']=='price_yearly'
    assert c.post('/api/billing/checkout',json={'tier':'yearly'}).json()==first.json() and counter[0]==1
    assert c.post('/api/billing/checkout',json={'tier':'founder'}).status_code==200
    assert sessions['cs_1']['status']=='expired'
    assert [x[2] for x in calls if x[1]=='checkout/sessions'][-1]['mode']=='payment'
    assert c.post('/api/billing/portal',json={'customer':'cus_attacker'}).status_code==200
    assert calls[-1][2]['customer']=='cus_own'
    with s.db() as db:db.execute("UPDATE accounts SET plan='premium' WHERE id=?",(uid,))
    assert c.post('/api/billing/checkout',json={'tier':'monthly'}).status_code==409


def test_billing_webhooks_canonical_state_replay_and_founder(monkeypatch):
    from . import payments as p
    c=TestClient(s.app);uid=c.post('/api/auth/signup',json={'email':'payer@example.com','password':'long-test-password'}).json()['id']
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_test_test');monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','test');monkeypatch.setenv('STRIPE_PRICE_MONTHLY','price_monthly')
    with s.db() as db:
        db.execute('UPDATE accounts SET stripe_customer=? WHERE id=?',('cus_own',uid))
        db.execute('INSERT INTO billing_checkouts VALUES(?,?,?,?)',('cs_founder',uid,'founder',time.time()))
    sub={'id':'sub_1','customer':'cus_own','metadata':{'account_id':uid,'tier':'monthly'},'status':'active','items':{'data':[{'price':{'id':'price_monthly','currency':'usd','unit_amount':1900,'recurring':{'interval':'month','interval_count':1}}}]}}
    pi={'id':'pi_1','customer':'cus_own','metadata':{'account_id':uid,'tier':'founder'},'currency':'usd','amount':99900,'status':'succeeded','latest_charge':{'refunded':False,'disputed':False}}
    calls=[]
    def stripe(method,path,data=None,idempotency=None):
        calls.append(path)
        if path=='subscriptions/sub_1':return sub
        if path=='payment_intents/pi_1':return pi
        if path=='checkout/sessions/cs_founder':return {'client_reference_id':uid,'payment_status':'paid','payment_intent':'pi_1'}
        raise AssertionError(path)
    monkeypatch.setattr(p,'stripe',stripe)
    def event(eid,kind,obj,live=False):
        body=json.dumps({'id':eid,'type':kind,'livemode':live,'data':{'object':obj}}).encode();stamp=str(int(time.time()))
        sig=hmac.new(b'test',stamp.encode()+b'.'+body,hashlib.sha256).hexdigest()
        return c.post('/api/billing/webhook',content=body,headers={'stripe-signature':'t='+stamp+',v1='+sig})
    assert event('evt_1','customer.subscription.created',{'id':'sub_1'}).status_code==200
    assert c.get('/api/me').json()['plan']=='premium'
    n=len(calls);assert event('evt_1','customer.subscription.created',{'id':'sub_1'}).status_code==200;assert len(calls)==n
    sub['status']='canceled'
    assert event('evt_2','customer.subscription.updated',{'id':'sub_1','status':'active'}).status_code==200
    assert c.get('/api/me').json()['plan']=='free'
    assert event('evt_3','checkout.session.completed',{'id':'cs_founder'}).status_code==200
    assert c.get('/api/me').json()['billing_tier']=='founder'
    assert event('evt_4','customer.subscription.deleted',{'id':'sub_1'}).status_code==200
    assert c.get('/api/me').json()['plan']=='premium'
    pi['latest_charge']['refunded']=True
    assert event('evt_5','charge.refunded',{'payment_intent':'pi_1'}).status_code==200
    assert c.get('/api/me').json()['plan']=='free'
    pi['customer']='cus_other'
    assert event('evt_6','checkout.session.completed',{'id':'cs_founder'}).status_code==200
    assert c.get('/api/me').json()['plan']=='free'
    assert event('evt_7','customer.subscription.created',{'id':'sub_1'},live=True).status_code==400


def test_billing_price_mismatch_is_rejected():
    from .payments import validate_price
    from fastapi import HTTPException
    with pytest.raises(HTTPException):validate_price({'currency':'usd','unit_amount':190,'recurring':{'interval':'year','interval_count':1}},'yearly')


def test_sandbox_cannot_unlock_main_members(monkeypatch):
    from . import payments as p
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_test_test')
    monkeypatch.setenv('BILLING_ENABLED','true')
    monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','test')
    monkeypatch.setenv('STRIPE_PRICE_MONTHLY','price_test')
    monkeypatch.setenv('TRADERSECHO_SCHEMA','public')
    assert not any(p.options().values())
    from fastapi import HTTPException
    with pytest.raises(HTTPException):p.process_event('evt_unsafe','customer.subscription.created',{'id':'sub_test'})
    monkeypatch.setenv('TRADERSECHO_SCHEMA','billing_sandbox_tests')
    assert p.options()['monthly']
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_live_test')
    assert not any(p.options().values())

def test_live_key_override_is_isolated_from_sandbox(monkeypatch):
    from . import payments as p
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_test_marketplace')
    monkeypatch.setenv('STRIPE_LIVE_SECRET_KEY','sk_live_production')
    monkeypatch.setenv('BILLING_SANDBOX','false')
    monkeypatch.setenv('TRADERSECHO_SCHEMA','public')
    assert p.secret_key()=='sk_live_production'
    assert p.environment_valid()
    monkeypatch.setenv('BILLING_SANDBOX','true')
    monkeypatch.setenv('TRADERSECHO_SCHEMA','billing_sandbox_tests')
    assert p.secret_key()=='sk_test_marketplace'
    assert p.environment_valid()
    monkeypatch.delenv('STRIPE_LIVE_SECRET_KEY')
    monkeypatch.setenv('BILLING_SANDBOX','false')
    assert not p.environment_valid()


def test_founder_dispute_resolution_and_payment_confirmation(monkeypatch):
    from . import payments as p
    c=TestClient(s.app)
    uid=c.post('/api/auth/signup',json={'email':'founder-dispute@example.com','password':'long-test-password'}).json()['id']
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_test_test')
    with s.db() as db:db.execute('UPDATE accounts SET stripe_customer=? WHERE id=?',('cus_dispute',uid))
    pi={'id':'pi_dispute','customer':'cus_dispute','metadata':{'account_id':uid,'tier':'founder'},'currency':'usd','amount':99900,'status':'succeeded','latest_charge':{'id':'ch_dispute','refunded':False,'disputed':True}}
    disputes={'data':[{'status':'under_review'}],'has_more':False}
    def stripe(method,path,data=None,idempotency=None):
        if path=='payment_intents/pi_dispute':return pi
        if path=='disputes':return disputes
        raise AssertionError(path)
    monkeypatch.setattr(p,'stripe',stripe)
    p.process_event('evt_founder_confirmation','payment_intent.succeeded',{'id':'pi_dispute'})
    assert c.get('/api/me').json()['plan']=='free'
    disputes['data'][0]['status']='won'
    with s.db() as db:p.sync_entitlement(db,'payment','pi_dispute')
    assert c.get('/api/me').json()['billing_tier']=='founder'
    pi['latest_charge']['refunded']=True
    with s.db() as db:p.sync_entitlement(db,'payment','pi_dispute')
    assert c.get('/api/me').json()['plan']=='free'

def test_change_password_rotates_sessions_and_rejects_bad_input():
    first=TestClient(s.app);second=TestClient(s.app);other=TestClient(s.app)
    creds={'email':'password-test@example.com','password':'old-long-password'}
    uid=first.post('/api/auth/signup',json=creds).json()['id'];second.post('/api/auth/login',json=creds)
    other.post('/api/auth/signup',json={'email':'unrelated@example.com','password':'other-long-password'})
    old_cookie=first.cookies.get('te_session')
    assert first.post('/api/auth/change-password',json={'current_password':'wrong','new_password':'new-long-password'}).status_code==400
    assert first.post('/api/auth/change-password',json={'current_password':creds['password'],'new_password':creds['password']}).status_code==400
    assert first.post('/api/auth/change-password',json={'current_password':creds['password'],'new_password':'short'}).status_code==422
    assert second.get('/api/me').json()['id']==uid
    response=first.post('/api/auth/change-password',json={'current_password':creds['password'],'new_password':'new-long-password'})
    assert response.status_code==200
    assert first.cookies.get('te_session')!=old_cookie
    assert first.get('/api/me').json()['id']==uid
    assert second.get('/api/me').json() is None
    assert other.get('/api/me').json()['email']=='unrelated@example.com'
    assert second.post('/api/auth/login',json=creds).status_code==401
    assert second.post('/api/auth/login',json={**creds,'password':'new-long-password'}).status_code==200
    with s.db() as db:
        row=db.execute('SELECT password FROM accounts WHERE id=?',(uid,)).fetchone()
        assert row[0]!='new-long-password'
        audit=db.execute("SELECT detail FROM audit_log WHERE action='password_changed' AND target=?",(uid,)).fetchone()
        assert audit and not audit[0]
    anonymous=TestClient(s.app)
    assert anonymous.post('/api/auth/change-password',json={'current_password':'old-long-password','new_password':'new-long-password'}).status_code==401
    anonymous.post('/api/auth/demo')
    assert anonymous.post('/api/auth/change-password',json={'current_password':'old-long-password','new_password':'new-long-password'}).status_code==403


def test_login_session_refuses_outdated_password_hash():
    from fastapi import Response,HTTPException
    c=TestClient(s.app);uid=c.post('/api/auth/signup',json={'email':'race@example.com','password':'original-password'}).json()['id']
    with s.db() as db:old=db.execute('SELECT password FROM accounts WHERE id=?',(uid,)).fetchone()[0]
    c.post('/api/auth/change-password',json={'current_password':'original-password','new_password':'replacement-password'})
    with pytest.raises(HTTPException):s.session(Response(),uid,old)

def test_recovery_single_use_scope_expiry_sessions_and_provider_failure(monkeypatch):
    from . import account_security as security
    from fastapi import HTTPException
    sent=[]
    monkeypatch.setenv('ACCOUNT_EMAIL_ENABLED','true')
    monkeypatch.setenv('RESEND_API_KEY','mock-only')
    monkeypatch.setattr(security,'send_email',lambda email,purpose,token:sent.append((email,purpose,token)))
    c=TestClient(s.app)
    c.post('/api/auth/signup',json={'email':'recover@example.com','password':'old-password-for-test'})
    assert c.post('/api/auth/send-verification').status_code==200
    verification=sent[-1][2]
    assert c.post('/api/auth/reset-password',json={'token':verification,'new_password':'new-password-for-test'}).status_code==400
    assert c.post('/api/auth/verify-email',json={'token':verification}).status_code==200
    assert c.get('/api/me').json()['email_verified']
    assert c.post('/api/auth/verify-email',json={'token':verification}).status_code==400
    with s.db() as conn:conn.execute("DELETE FROM attempts")
    response=c.post('/api/auth/forgot-password',json={'email':'recover@example.com'})
    token=sent[-1][2]
    assert c.post('/api/auth/forgot-password',json={'email':'unknown@example.com'}).json()==response.json()
    with s.db() as conn:
        assert not conn.execute('SELECT 1 FROM account_tokens WHERE hash=?',(token,)).fetchone()
        conn.execute('UPDATE account_tokens SET expires=?',(time.time()-1,))
    assert c.post('/api/auth/reset-password',json={'token':token,'new_password':'new-password-for-test'}).status_code==400
    with s.db() as conn:conn.execute('DELETE FROM attempts')
    c.post('/api/auth/forgot-password',json={'email':'recover@example.com'})
    token=sent[-1][2]
    assert c.post('/api/auth/reset-password',json={'token':token,'new_password':'new-password-for-test'}).status_code==200
    assert c.get('/api/me').json() is None
    assert c.post('/api/auth/reset-password',json={'token':token,'new_password':'new-password-for-test'}).status_code==400
    assert c.post('/api/auth/login',json={'email':'recover@example.com','password':'old-password-for-test'}).status_code==401
    assert c.post('/api/auth/login',json={'email':'recover@example.com','password':'new-password-for-test'}).status_code==200
    with s.db() as conn:conn.execute('DELETE FROM attempts')
    def fail(*args):raise HTTPException(503,'unavailable')
    monkeypatch.setattr(security,'send_email',fail)
    assert c.post('/api/auth/forgot-password',json={'email':'recover@example.com'}).json()==response.json()
    with s.db() as conn:assert conn.execute('SELECT COUNT(*) FROM account_tokens').fetchone()[0]==0


def test_full_text_refresh_links_and_conservative_language(monkeypatch):
    from .post_quality import language_label,research_text
    post={'id':'987654321','author':'researcher','text':'Bullish $NVDA','created_at':datetime.now(timezone.utc).isoformat()}
    assert s.ingest([post])['mentions_added']==1
    assert s.ingest([post])['mentions_added']==0
    full={**post,'text':'Bullish $NVDA but bearish $MU. This is the full research text.'}
    assert s.ingest([full])['mentions_added']==1
    s.ingest([post])
    with s.db() as conn:
        assert conn.execute("SELECT text FROM posts WHERE id=?",(post['id'],)).fetchone()[0]==full['text']
        assert conn.execute("SELECT COUNT(*) FROM mentions WHERE post_id=?",(post['id'],)).fetchone()[0]==2
    assert language_label(full['text'],'MU')=='bearish'
    assert language_label('Memory technology is advancing. $MU','MU')=='unclear'
    assert language_label('Not bullish $NVDA','NVDA')=='bearish'
    assert not research_text('Join our stock trading group today $NVDA https://t.me/free')


def test_free_launch_rankings_and_checkout_disabled(monkeypatch):
    from . import payments
    monkeypatch.setenv('FREE_LAUNCH','true')
    monkeypatch.setenv('BILLING_ENABLED','true')
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_test_mock')
    monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','whsec_mock')
    monkeypatch.setenv('STRIPE_PRICE_MONTHLY','price_mock')
    c=TestClient(s.app)
    assert c.post('/api/auth/signup',json={'email':'launch@example.com','password':'long-test-password'}).status_code==200
    assert len(c.get('/api/rankings?source=demo').json()['rows'])==16
    assert not any(payments.options().values())
    assert c.post('/api/billing/checkout',json={'tier':'monthly'}).status_code==503
    assert c.get('/api/status').json()['free_launch']

def test_newsletter_personalization_safe_html_and_inline_logo():
    from .newsletter import render,LOGO
    import base64
    report={'ready':True,'date':'2026-09-16','tracked_stocks':357,'rows':[{'ticker':'MU','name':'Micron <script>bad</script>','mentions':900,'previous':600,'change':50}], 'watchlist_only':True,'watchlist':[],'posts':[{'id':'123','author':'researcher','text':'Watching $MU & <img src=x onerror=alert(1)>'}],'disclosure':'Sampled posts, not investment advice.'}
    result=render(report,'<Sven>','https://example.com',preview=True)
    assert '&lt;Sven&gt;' in result['html'] and '<script>' not in result['html']
    assert '&lt;img' in result['html'] and 'src="data:image/png;base64,' in result['html']
    assert '$MU leads your watchlist' in result['html']
    assert 'view=market&amp;ticker=MU' in result['html'] and 'view=account' in result['text']
    assert 'Automatic newsletter delivery is off' in result['html']
    actual=render(report,'Sven','https://example.com')
    assert 'src="cid:tradersecho-pulse"' in actual['html']
    assert actual['attachments'][0]['content_id']=='tradersecho-pulse'
    assert base64.b64decode(LOGO).startswith(b'\x89PNG')
    assert len(actual['html'].encode())<90000
    with pytest.raises(ValueError):render({'ready':False})
    with pytest.raises(ValueError):render(report,origin='javascript:alert(1)')
    empty=render({**report,'rows':[],'posts':[]})
    assert 'No matching watchlist stocks' in empty['html'] and '$MU' not in empty['html']


def test_newsletter_signature_and_timestamp():
    from .email_delivery import verify_event
    from fastapi import HTTPException
    raw=b'{"event_type":"ping","data":{"success":true}}'
    headers={'svix-id':'msg_loFOjxBNrRLzqYUf','svix-timestamp':'1731705121','svix-signature':'v1,rAvfW3dJ/X/qxhsaXPOyyCGmRKsaKWcsNccKXlIktD0='}
    secret='whsec_plJ3nmyCDGBKInavdOK15jsl'
    assert verify_event(raw,headers,secret,1731705121)[1]['event_type']=='ping'
    with pytest.raises(HTTPException):verify_event(raw+b' ',headers,secret,1731705121)
    with pytest.raises(HTTPException):verify_event(raw,headers,secret,1731705422)


def test_research_feed_excludes_group_promotions_and_ticker_stuffing():
    from .post_quality import research_text,prepare_feed
    spam="I've created a dedicated WhatsApp group for $NVDA $TSLA $AAPL shareholders. Click this link to join."
    stuffed='$QQQ easy 50% gains! $SPY $TSLA $NVDA $MSFT $AAPL $GOOGL $META $AMZN $AMD'
    assert not research_text(spam) and not research_text(stuffed)
    assert not research_text('Our analyst on fire $NVDA +33%. Copy Trading doing its thing!')
    assert research_text('$MU buying')
    assert research_text('$NVDA and $TSM depend on continued data center investment and manufacturing capacity.')
    rows=[{'id':'1','text':spam,'author':'promo','likes':0,'ts':time.time()}]
    assert prepare_feed(rows,'NVDA',set(),'research','latest')==[]
    assert len(prepare_feed(rows,'NVDA',set(),'all','latest'))==1


def test_newsletter_optout_scanner_and_retry_gate(monkeypatch):
    from . import email_delivery as d,digest
    client,u=make_account('newsletter@example.com')
    other,v=make_account('different@example.com')
    end=int(time.time()//86400)*86400
    report={'ready':True,'window_start':end-86400,'window_end':end,'date':'2026-09-17','tracked_stocks':1,'rows':[{'ticker':'MU','name':'Micron','mentions':20,'previous':10,'change':100}]}
    monkeypatch.setattr(digest,'build',lambda:report)
    with s.db() as c:
        c.execute("UPDATE accounts SET plan='premium',email_verified=1 WHERE id=?",(u['id'],))
        c.execute('INSERT INTO digest_preferences VALUES(?,?,?,?)',(u['id'],'daily',0,time.time()))
    with pytest.raises(ValueError):d.prepare_delivery(v)
    key=d.prepare_delivery(u)
    assert d.prepare_delivery(u)==key
    claim=d.claim_delivery(key)
    assert claim and d.claim_delivery(key) is None
    assert claim['payload']['to']==['newsletter@example.com']
    assert d.claim_delivery(key,now=time.time()+121)==claim
    url=claim['payload']['headers']['List-Unsubscribe'][1:-1]
    from urllib.parse import urlsplit,parse_qs
    token=parse_qs(urlsplit(url).query)['token'][0]
    anonymous=TestClient(s.app)
    response=anonymous.get('/api/newsletter/unsubscribe',params={'token':token})
    assert response.status_code==200 and response.headers['referrer-policy']=='no-referrer'
    assert client.get('/api/digest/preferences').json()['frequency']=='daily'
    assert anonymous.post('/api/newsletter/unsubscribe',params={'token':token},data={'List-Unsubscribe':'One-Click'}).status_code==200
    assert client.get('/api/digest/preferences').json()['frequency']=='off'
    assert other.get('/api/digest/preferences').json()['frequency']=='off'
    assert d.claim_delivery(key,now=time.time()+250) is None
    with pytest.raises(ValueError):d.prepare_delivery(u)


def test_newsletter_webhook_suppression_and_replay(monkeypatch):
    import base64
    from . import email_delivery as d
    secret='whsec_'+base64.b64encode(b'unit-test-webhook-key-32-bytes!!').decode()
    monkeypatch.setenv('RESEND_WEBHOOK_SECRET',secret)
    client=TestClient(s.app)
    def send(kind,event_id='event-one',data=None):
        raw=json.dumps({'type':kind,'data':data if data is not None else {'email_id':'provider-one','to':['bounced@example.com']}}).encode()
        stamp=str(int(time.time()))
        sig=base64.b64encode(hmac.new(base64.b64decode(secret[6:]),event_id.encode()+b'.'+stamp.encode()+b'.'+raw,hashlib.sha256).digest()).decode()
        return client.post('/api/newsletter/events',content=raw,headers={'svix-id':event_id,'svix-timestamp':stamp,'svix-signature':'v1,'+sig})
    assert client.post('/api/newsletter/events',json={}).status_code==400
    assert send('email.bounced').status_code==200
    assert send('email.bounced').json()['duplicate']
    assert send('email.delivered','event-two').status_code==200
    assert send('email.bounced','event-three',data=['bad']).status_code==400
    with s.db() as c:
        assert c.execute('SELECT COUNT(*) FROM email_events').fetchone()[0]==2
        assert c.execute('SELECT reason FROM email_suppressions WHERE email_hash=?',(d.email_hash('bounced@example.com'),)).fetchone()[0]=='email.bounced'
