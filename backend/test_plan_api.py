import sqlite3, time, hashlib
from types import SimpleNamespace
from contextlib import contextmanager
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from . import customer_api as api
from .plan_limits import limits

@pytest.fixture
def database(monkeypatch):
    c=sqlite3.connect(':memory:',check_same_thread=False);c.row_factory=sqlite3.Row
    c.executescript('CREATE TABLE accounts(id TEXT PRIMARY KEY,plan TEXT,role TEXT,status TEXT,demo INTEGER,stripe_customer TEXT); CREATE TABLE billing_entitlements(id TEXT,user_id TEXT,tier TEXT,active INTEGER);')
    c.execute("INSERT INTO accounts VALUES('u','premium','member','active',0,'cus_test')")
    api.migrate(c);c.commit()
    @contextmanager
    def db():
        try:yield c;c.commit()
        except Exception:c.rollback();raise
    monkeypatch.setattr(api,'core',lambda:SimpleNamespace(db=db))
    yield c
    c.close()

def test_plan_limits_founder_and_free(database):
    u={'id':'u','plan':'premium','role':'member'}
    assert limits(database,u)=={'saved_stocks':25,'personal_voices':3,'ticker_refreshes':3}
    database.execute("INSERT INTO billing_entitlements VALUES('f','u','founder',1)")
    assert limits(database,u)=={'saved_stocks':50,'personal_voices':5,'ticker_refreshes':5}
    database.execute('UPDATE billing_entitlements SET active=0')
    assert limits(database,{**u,'plan':'free'})=={'saved_stocks':5,'personal_voices':3,'ticker_refreshes':0}

def test_quota_limits_and_reset(database):
    now=1780000020
    for i in range(10):assert api.consume(database,'u',now)==9999-i
    with pytest.raises(HTTPException) as exc:api.consume(database,'u',now)
    assert exc.value.status_code==429 and exc.value.headers['Retry-After']
    assert api.consume(database,'u',now+60)==9989
    database.execute('UPDATE customer_api_usage SET monthly_used=10000')
    with pytest.raises(HTTPException):api.consume(database,'u',now+120)
    assert api.consume(database,'u',now+32*86400)==9999

def test_api_fails_closed_and_entitlements(database,monkeypatch):
    app=FastAPI();app.include_router(api.router);client=TestClient(app)
    monkeypatch.delenv('CUSTOMER_API_ENABLED',raising=False)
    assert client.get('/api/v1/snapshot').status_code==503
    assert client.post('/api/customer-api/checkout').status_code==503
    monkeypatch.setenv('CUSTOMER_API_ENABLED','true');monkeypatch.setenv('CUSTOMER_API_RIGHTS_APPROVED','true')
    assert client.get('/api/v1/snapshot').status_code==401
    token='te_live_test';database.execute('INSERT INTO customer_api_keys VALUES(?,?,?)',('u',hashlib.sha256(token.encode()).hexdigest(),time.time()));database.commit()
    headers={'Authorization':'Bearer '+token}
    assert client.get('/api/v1/snapshot',headers=headers).status_code==403
    database.execute("INSERT INTO customer_api_subscriptions VALUES('sub','u',1,0)");database.commit()
    monkeypatch.setattr(api,'snapshot',lambda days:{'window_days':days,'rankings':[]})
    r=client.get('/api/v1/snapshot?window=7',headers=headers)
    assert r.status_code==200 and r.json()['window_days']==7 and r.headers['x-ratelimit-monthly-remaining']=='9999'
    assert client.get('/api/v1/snapshot?window=2',headers=headers).status_code==422
    database.execute("UPDATE accounts SET plan='free'");database.commit()
    assert client.get('/api/v1/snapshot',headers=headers).status_code==403

def test_api_billing_is_separate_and_price_checked(database,monkeypatch):
    monkeypatch.setenv('STRIPE_PRICE_API','price_api')
    obj={'id':'sub','metadata':{'tier':'api','account_id':'u'},'customer':'cus_test','status':'active','items':{'data':[{'price':{'id':'price_api','currency':'usd','unit_amount':500,'recurring':{'interval':'month','interval_count':1}}}]}}
    assert api.sync(database,obj)
    assert api.subscribed(database,'u')
    assert database.execute('SELECT COUNT(*) FROM billing_entitlements').fetchone()[0]==0
    obj['status']='canceled';api.sync(database,obj)
    assert not api.subscribed(database,'u')
    obj['items']['data'][0]['price']['unit_amount']=50
    assert not api.valid_price(obj['items']['data'][0]['price'])


def test_sentiment_only_aggregate_never_leaks_source_fields():
    rows=[]
    for i,label in enumerate(['bullish','bullish','bearish','neutral','unclear']):
        rows.append({'source':'x','id':str(i),'text':'PRIVATE source text','author':'PRIVATE author','url':'PRIVATE link','sentiment_status':'done','sentiment_analyzed_at':100+i,'ticker_sentiments':[{'ticker':'MU','label':label,'evidence':'PRIVATE quote','reason':'PRIVATE explanation'},{'ticker':'OUTSIDE','label':'bullish'}]})
    rows += [rows[0],{**rows[0],'id':'pending','sentiment_status':'pending'}]
    result=api.sentiment_rows(rows,{'MU':('Micron','Semiconductors')})
    assert len(result)==1
    r=result[0]
    assert r['score']==25 and r['bullish_pct']==40 and r['bearish_pct']==20
    assert r['sentiment']=='bullish' and r['analyzed_at']==104
    assert set(r)=={'ticker','sentiment','score','bullish_pct','bearish_pct','neutral_pct','mixed_pct','unclear_pct','analyzed_at'}
    assert 'PRIVATE' not in str(result) and 'OUTSIDE' not in str(result)
    assert api.sentiment_rows(rows[:4],{'MU':()})==[]
    unclear=[{**p,'ticker_sentiments':[{'ticker':'MU','label':'unclear'}]} for p in rows[:5]]
    assert api.sentiment_rows(unclear,{'MU':()})[0]['score'] is None
    crypto=[{**p,'text':'$AI token on solana','ticker_sentiments':[{'ticker':'AI','label':'bullish'}]} for p in rows[:5]]
    assert api.sentiment_rows(crypto,{'AI':()})==[]


def test_api_runtime_modules_are_deployment_allowlisted():
    from pathlib import Path
    config=(Path(__file__).parents[1]/'.vercelignore').read_text()
    for name in ('customer_api','plan_limits'):
        assert '!backend/'+name+'.py' in config
