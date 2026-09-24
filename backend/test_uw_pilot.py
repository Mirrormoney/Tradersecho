import sqlite3,json
from contextlib import contextmanager
from types import SimpleNamespace
from datetime import datetime
import httpx,pytest
from . import uw_pilot as u

NOW=datetime(2026,9,24,11,0,tzinfo=u.NY).timestamp()

@pytest.fixture
def pilot(tmp_path,monkeypatch):
    monkeypatch.setattr(u,'FOCUS',())
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

def test_measurements_require_contiguous_windows():
    candles=[{'at':NOW-i*600,'close':106-i,'volume':100} for i in range(7)]
    flow=[{'at':NOW-i*60,'net_call_premium':10,'net_put_premium':-2} for i in range(60)]
    result=u.stock_measurements('NVDA',{'candles':candles,'net_premium':flow},NOW)
    assert result['return_60m']==6
    assert result['volume_30m']==300
    assert result['net_calls_60m']==600 and result['net_puts_60m']==-120
    assert result['price_fresh'] and result['flow_fresh']
    result=u.stock_measurements('NVDA',{'candles':candles[:3]+candles[4:],'net_premium':flow[:15]+flow[16:]},NOW)
    assert result['return_60m'] is None and result['net_calls_60m'] is None
    assert result['volume_30m']==300

def test_measurements_do_not_mix_previous_day_or_future():
    sample={'at':NOW-86400,'close':10,'volume':100}
    future={'at':NOW+600,'close':11,'volume':100}
    result=u.stock_measurements('MU',{'candles':[sample,future]},NOW)
    assert result['candles']==[] and result['return_60m'] is None
    assert not result['price_fresh']

def test_measurements_label_stale_separately():
    result=u.stock_measurements('AMD',{'candles':[{'at':NOW-1800,'close':100,'volume':50}]},NOW)
    assert result['price_at']==NOW-1800 and not result['price_fresh']

def test_history_and_baseline_20_sessions_no_current_day_leak():
    candles=[{'at':NOW-i*600,'close':100,'volume':200} for i in reversed(range(3))]
    history=[]
    for day in range(1,21):
        history.extend({'at':r['at']-day*86400,'volume':100} for r in candles)
    b=u.volume_baseline(candles,history)
    assert b['sessions']==20 and b['relative_volume']==2 and b['persistence']==3
    assert u.volume_baseline(candles,history[:-1])['relative_volume'] is None
    assert u.volume_baseline(candles,[{'at':r['at'],'volume':1} for r in candles])['sessions']==0

def test_options_excludes_wrong_ticker_multi_ambiguous_and_deduplicates():
    r={'id':'a','executed_at':'2026-09-24T14:55:00Z','expiry':'2026-10-16','premium':'1000','tags':['ask_side'],'underlying_symbol':'NVDA','canceled':False,'upstream_condition_detail':'auto','option_type':'call'}
    result=u.filtered_trades({'data':[r,r,{**r,'id':'b','underlying_symbol':'AMD'},{**r,'id':'c','upstream_condition_detail':'mlet'},{**r,'id':'d','tags':['mid_side']},{**r,'id':'e','option_type':'put'}]},'NVDA',NOW)
    assert result['accepted']==2 and result['bull']==1000 and result['bear']==1000 and not result['partial']
    assert u.filtered_trades({'data':[r]*500},'NVDA',NOW)['partial']

def test_extra_datasets_use_shared_budget_and_once_daily_history(pilot,monkeypatch):
    enable(monkeypatch);monkeypatch.setattr(u,'FOCUS',('NVDA',));calls=[]
    def handler(r):
        calls.append(str(r.url));return httpx.Response(200,json={'data':[]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert u.run(client,NOW)['completed']==4
        assert u.run(client,NOW+600)['completed']==3
    assert sum('timeframe=2M' in url for url in calls)==1
    assert sum('/api/option-trades?' in url for url in calls)==2
    with pilot.db() as c:assert c.execute('SELECT reserved FROM uw_pilot_usage').fetchone()[0]==7

def test_options_pagination_overlaps_boundary_and_counts_requests(pilot,monkeypatch):
    enable(monkeypatch);monkeypatch.setattr(u,'FOCUS',('NVDA',));pages=[]
    def trade(i):return {'id':str(i),'executed_at':datetime.fromtimestamp(NOW-i,u.NY).isoformat(),'expiry':'2026-10-16','premium':1,'tags':['ask_side'],'underlying_symbol':'NVDA','canceled':False,'upstream_condition_detail':'auto','option_type':'call'}
    def handler(r):
        if r.url.path!='/api/option-trades':return httpx.Response(200,json={'data':[]})
        pages.append(r.url.params.get('older_than'))
        return httpx.Response(200,json={'data':[trade(i) for i in range(500)] if len(pages)==1 else [trade(499),trade(500)]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:assert u.run(client,NOW)['failed']==0
    with pilot.db() as c:
        row=json.loads(c.execute("SELECT payload FROM uw_pilot_latest WHERE kind='filtered_options'").fetchone()[0])[0]
        assert row['accepted']==501 and row['bull']==501 and not row['partial']
        assert c.execute('SELECT reserved FROM uw_pilot_usage').fetchone()[0]==5
    assert len(pages)==2
