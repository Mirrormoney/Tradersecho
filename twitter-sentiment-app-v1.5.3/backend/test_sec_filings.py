import time, httpx, pytest
from fastapi.testclient import TestClient
from .test_service import isolate_tests, s, make_account
from . import sec_filings as sec

@pytest.fixture(autouse=True)
def clear_sec():
    with s.db() as c:
        for table in ['sec_filings','sec_companies','sec_checks']:c.execute('DELETE FROM '+table)

def payload():
    from datetime import datetime,timezone
    now=datetime.now(timezone.utc)
    return {'filings':{'recent':{'accessionNumber':['0001045810-26-000123'],'form':['8-K/A'],'filingDate':[now.date().isoformat()],'acceptanceDateTime':[now.isoformat()],'primaryDocument':['report.htm'],'reportDate':['2026-09-01']}}}

def test_dates_links_and_amendments():
    rows=sec.parse_filings(payload(),'1045810',time.time())
    assert len(rows)==1 and rows[0][5]=='Company update · amendment'
    assert rows[0][6]=='https://www.sec.gov/Archives/edgar/data/1045810/000104581026000123/report.htm'
    p=payload();p['filings']['recent']['acceptanceDateTime']=['2001-01-01T12:00:00Z']
    assert sec.parse_filings(p,'1045810',time.time())==[]

def test_shared_dedup_and_read_auth(monkeypatch):
    monkeypatch.setenv('VERCEL_ENV','production');monkeypatch.setattr(sec.time,'sleep',lambda n:None)
    calls=[]
    def transport(req):
        calls.append(str(req.url))
        if 'company_tickers' in str(req.url):return httpx.Response(200,json={'0':{'ticker':'NVDA','cik_str':1045810}})
        return httpx.Response(200,json=payload())
    client=httpx.Client(transport=httpx.MockTransport(transport))
    assert sec.run(client)['new_filings']==1
    assert sec.run(client)['checked']==0
    with s.db() as c:c.execute('UPDATE sec_checks SET attempted_at=0')
    assert sec.run(client)['new_filings']==0
    assert len(calls)==3
    anon=TestClient(s.app)
    assert anon.get('/api/filings').status_code==401
    assert anon.get('/api/cron/sec').status_code==401
    member,_=make_account('sec-user@example.invalid')
    response=member.get('/api/filings?ticker=NVDA&kind=updates')
    assert response.status_code==200 and len(response.json()['rows'])==1
    assert member.get('/api/filings?kind=insiders').json()['rows']==[]
    assert member.get('/api/filings?ticker=INVALID').status_code==404

def test_sec_backoff_and_preview(monkeypatch):
    monkeypatch.setenv('VERCEL_ENV','preview')
    assert sec.run()['state']=='preview_disabled'
    monkeypatch.setenv('VERCEL_ENV','production')
    client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(429)))
    assert sec.run(client)['state']=='upstream_unavailable'
    assert sec.run(client)['state']=='cooldown'
    with s.db() as c:assert sec.getmeta(c,'lease')=={}

def test_alias_mapping_and_no_guessed_matches():
    with s.db() as c:
        sec.map_companies(c,{'0':{'ticker':'NVDA','cik_str':1045810},'1':{'ticker':'FAKE','cik_str':123}})
        assert [r[0] for r in c.execute('SELECT ticker FROM sec_companies')]==['NVDA']
