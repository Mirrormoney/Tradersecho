from .test_service import s, isolate_tests
from fastapi.testclient import TestClient
from .supply_chain import group_rows

def test_groups_exclude_uncovered_and_distinguish_missing_from_zero():
    catalog={'A':('A','Compute'),'B':('B','Power'),'C':('C','Power')}
    rows=[{'ticker':'A','mentions':10,'heat':2,'coverage_hours':24},
          {'ticker':'B','mentions':0,'heat':0,'coverage_hours':2},
          {'ticker':'OUT','mentions':1000,'heat':50,'coverage_hours':24}]
    groups=group_rows(catalog,rows,24)
    assert groups[0]['share']==100
    assert groups[0]['complete']==1
    assert groups[1]['measured']==1 and groups[1]['stocks']==2
    assert groups[1]['complete']==0

def test_auth_and_free_drilldown_limits(monkeypatch):
    client=TestClient(s.app)
    assert client.get('/api/supply-chain').status_code==401
    monkeypatch.setenv('FREE_LAUNCH','false')
    monkeypatch.setattr(s,'account',lambda request: {'plan':'free','role':'member','demo':False})
    tickers=list(s.CATALOG)
    from . import count_metrics
    monkeypatch.setattr(count_metrics,'enrich',lambda *args:[{'ticker':t,'mentions':i+1,'heat':i,'coverage_hours':24} for i,t in enumerate(tickers)])
    for plan in ('free','premium','pro'):
        monkeypatch.setattr(s,'account',lambda request, plan=plan: {'plan':plan,'role':'member','demo':False})
        for window in (1,7,30):
            response=client.get(f'/api/supply-chain?window={window}')
            assert response.status_code==200
            data=response.json()
            assert data['locked'] is False
            assert sum(len(g['rows']) for g in data['groups'])==len(tickers)
    assert client.get('/api/supply-chain?window=2').status_code==422



def test_personal_voice_feed_is_private_and_premium(monkeypatch):
    import time
    client=TestClient(s.app)
    monkeypatch.setattr(s,'account',lambda *args: {'id':'voice-test','plan':'free','role':'member','demo':False})
    assert client.get('/api/posts?source=x&personal=true').status_code==403
    monkeypatch.setattr(s,'account',lambda *args: {'id':'voice-test','plan':'premium','role':'member','demo':False})
    with s.db() as c:
        c.execute("INSERT INTO posts VALUES('x','test-other','someoneelse','No access through personal feed',?,'neutral',0)",(time.time(),))
    assert client.get('/api/posts?source=x&personal=true').json()==[]
