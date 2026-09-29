import sqlite3,json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock
import httpx,pytest
from fastapi import HTTPException,Response
from . import options_activity as a

NOW=1790686800
def row():return {'ticker':'NVDA','created_at':'2026-09-29T12:59:00Z','total_premium':'1200000','total_ask_side_prem':'1000000','total_bid_side_prem':'100000','type':'call','strike':'200','expiry':'2026-10-16','option_chain':'NVDA-C','alert_rule':'RepeatedHits'}

def test_event_validation_and_identity():
 r=row();v=a.event(r,{'NVDA'},NOW)
 assert v['side']=='ask' and v['premium']==1200000
 assert a.event(r,{'MU'},NOW) is None
 assert a.event({**r,'total_premium':'NaN'},{'NVDA'},NOW) is None
 assert a.event({**r,'has_multileg':True},{'NVDA'},NOW)['side']=='complex'
 assert a.event({**r,'total_premium':'1500000'},{'NVDA'},NOW)['id']==v['id']

@pytest.fixture
def setup(tmp_path,monkeypatch):
 @contextmanager
 def db():
  c=sqlite3.connect(tmp_path/'db');c.row_factory=sqlite3.Row
  try:yield c;c.commit()
  finally:c.close()
 with db() as c:c.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)');a.uw.migrate(c);a.migrate(c)
 monkeypatch.setattr(a,'core',lambda:SimpleNamespace(db=db,CATALOG={'NVDA':('NVIDIA',)}))
 monkeypatch.setattr(a.uw,'session_open',lambda now:True)
 monkeypatch.setattr(a.uw,'configured',lambda:{'enabled':True})
 monkeypatch.setenv('VERCEL_ENV','production');monkeypatch.setattr(a.time,'sleep',lambda _:None)
 return db

def test_scan_deduplicates_and_shares_quota(setup):
 client=httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'data':[row(),row()]})))
 assert a.run(NOW,client)['state']=='complete'
 with setup() as c:
  assert c.execute('SELECT count(*) FROM options_activity_events').fetchone()[0]==1
  assert c.execute('SELECT reserved FROM uw_pilot_usage').fetchone()[0]==1
 assert a.run(NOW+10,client)['state']=='not_due'

def test_provider_denial_and_limit(setup):
 client=httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(403,json={})))
 assert a.run(NOW,client)['http_status']==403
 assert a.run(NOW+600,client)['state']=='provider_paused'
 with setup() as c:
  a.put(c,'cooldown',0);c.execute('UPDATE uw_pilot_usage SET reserved=32000')
 assert a.run(NOW+600,client)['state']=='budget_paused'

def test_admin_denied_before_read(monkeypatch):
 def deny(req):raise HTTPException(403)
 monkeypatch.setattr(a,'staff',deny)
 with pytest.raises(HTTPException):a.overview(None,Response())

def test_preview_never_collects(setup,monkeypatch):
 monkeypatch.setenv('VERCEL_ENV','preview');client=MagicMock()
 assert a.run(NOW,client)['state']=='preview_disabled';client.get.assert_not_called()

def test_deployment_includes_module():
 from pathlib import Path
 assert '!backend/options_activity.py' in (Path(__file__).resolve().parents[1]/'.vercelignore').read_text()

def test_sample_is_staff_only(monkeypatch):
 def deny(req):raise HTTPException(403)
 monkeypatch.setattr(a,'staff',deny)
 with pytest.raises(HTTPException):a.sample(None)

def test_full_page_cursor_stall_keeps_window(setup):
 client=httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'data':[row()]*200})))
 result=a.run(NOW,client)
 assert result['state']=='cursor_stalled'
 with setup() as c:assert a.get(c,'pending') and a.get(c,'through') is None
