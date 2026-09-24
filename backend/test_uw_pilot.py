import sqlite3,json
from contextlib import contextmanager
from types import SimpleNamespace
from datetime import datetime
import httpx,pytest
from . import uw_pilot as u

NOW=datetime(2026,9,24,11,0,tzinfo=u.NY).timestamp()

@pytest.fixture
def pilot(tmp_path,monkeypatch):
    path=tmp_path/'pilot.sqlite'
    @contextmanager
    def db():
        c=sqlite3.connect(path);c.row_factory=sqlite3.Row
        try:yield c;c.commit()
        finally:c.close()
    with db() as c:
        c.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)');u.migrate(c)
    s=SimpleNamespace(db=db,CATALOG={'NVDA':('NVIDIA','Semiconductors')})
    monkeypatch.setattr(u,'core',lambda:s);monkeypatch.setattr(u.time,'sleep',lambda n:None)
    for key in ['UW_API_KEY','UW_PILOT_ENABLED','UW_PRIVATE_EVALUATION_APPROVED']:monkeypatch.delenv(key,raising=False)
    return s

def enable(monkeypatch):
    monkeypatch.setenv('UW_API_KEY','test-only');monkeypatch.setenv('UW_PILOT_ENABLED','true');monkeypatch.setenv('UW_PRIVATE_EVALUATION_APPROVED','true')

def test_disabled_does_not_call_provider(pilot):
    assert u.run(now=NOW)['state']=='setup_required'

def test_partial_failure_continues_and_deduplicates_tick(pilot,monkeypatch):
    enable(monkeypatch);calls=[]
    def handler(request):
        calls.append(request.url.path)
        if 'ohlc' in request.url.path:return httpx.Response(500)
        return httpx.Response(200,json={'data':[{'tape_time':'2026-09-24T14:59:00Z','net_call_premium':'12','net_put_premium':'-4'}]},headers={'x-uw-daily-req-count':'2','x-uw-token-req-limit':'40000'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert u.run(client,NOW)=={'state':'complete','completed':1,'failed':1}
        assert u.run(client,NOW+60)['completed']==0
    assert len(calls)==2
    with pilot.db() as c:
        assert c.execute('SELECT COUNT(*) FROM uw_pilot_history').fetchone()[0]==1
        assert c.execute('SELECT reserved FROM uw_pilot_usage').fetchone()[0]==2

def test_rate_limit_pauses_without_retries(pilot,monkeypatch):
    enable(monkeypatch)
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(429))) as client:
        assert u.run(client,NOW)['state']=='provider_paused'
        assert u.run(client,NOW+60)['state']=='provider_paused'

def test_quota_stops_before_request(pilot,monkeypatch):
    enable(monkeypatch)
    with pilot.db() as c:c.execute('INSERT INTO uw_pilot_usage VALUES(?,?,?,?)',(u.quota_day(NOW),32000,0,40000))
    with httpx.Client(transport=httpx.MockTransport(lambda r:pytest.fail('quota bypass'))) as client:
        assert u.run(client,NOW)['state']=='daily_limit'

def test_empty_future_stale_and_invalid_values():
    assert u.normalize('candles',{'data':[]},NOW)==[]
    assert u.normalize('candles',{'data':[{'end_time':'2026-09-24T16:00:00Z','close':10,'volume':1}]},NOW)==[]
    assert u.normalize('candles',{'data':[{'end_time':'2026-09-24T14:50:00Z','close':'NaN','volume':1}]},NOW)==[]
    with pytest.raises(ValueError):u.normalize('candles',{'error':'wrong shape'},NOW)

def test_reset_and_session_dst():
    before=datetime(2026,9,24,19,59,tzinfo=u.NY).timestamp()
    after=datetime(2026,9,24,20,0,tzinfo=u.NY).timestamp()
    assert u.quota_day(before)=='2026-09-23' and u.quota_day(after)=='2026-09-24'
    assert u.session_open(NOW)
    assert not u.session_open(datetime(2026,9,26,11,tzinfo=u.NY).timestamp())

def test_owner_endpoint_checks_permission_first(monkeypatch):
    from fastapi import HTTPException
    def deny(*args,**kwargs):raise HTTPException(403,'Owner only')
    monkeypatch.setattr(u,'staff',deny)
    with pytest.raises(HTTPException) as e:u.overview(None)
    assert e.value.status_code==403
