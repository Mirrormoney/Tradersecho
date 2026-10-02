import json,sqlite3,time
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from . import industry_radar as r

@pytest.fixture
def db(tmp_path,monkeypatch):
 @contextmanager
 def connect():
  c=sqlite3.connect(tmp_path/'radar.sqlite');c.row_factory=sqlite3.Row
  try:yield c;c.commit()
  finally:c.close()
 with connect() as c:
  r.migrate(c)
  c.executescript("CREATE TABLE stocks(ticker TEXT,name TEXT,active INTEGER); CREATE TABLE research_documents(id TEXT,result TEXT,text TEXT,status TEXT,received REAL);")
  c.execute("INSERT INTO stocks VALUES('MU','Micron',1)")
 monkeypatch.setattr(r,'core',lambda:SimpleNamespace(db=connect))
 return connect

TEXT='Micron supplies HBM memory to customers and expects capacity growth in 2027. '+('Supporting HBM industry discussion. '*12)

def analysis():
 return dict(headline='Memory capacity expectation',topic='hbm',kind='expectation',summary='Micron expects capacity growth.',evidence=TEXT[:73],timing='2027',novelty='unclear',compared_to=[],what_changed='No comparable previous evidence supplied.',readthroughs=[dict(ticker='MU',relationship='direct',direction='mixed',reason='Capacity could support sales if demand holds.',basis_source='current',basis_quote='Micron supplies HBM memory to customers',caveat='Capacity alone does not establish profitability.')],next_check='Check shipment confirmation.',uncertainty='Forecast, not an accomplished event.')

def test_access_and_cron_auth(monkeypatch):
 def denied(req):raise HTTPException(403)
 monkeypatch.setattr(r,'staff',denied)
 req=Request({'type':'http','headers':[]})
 for f in (r.status,r.manual):
  with pytest.raises(HTTPException):f(req)
 monkeypatch.setenv('CRON_SECRET','test')
 with pytest.raises(HTTPException):r.cron(req)

def test_scope():
 assert r.allowed('https://www.trendforce.com/news/a','https://www.trendforce.com/news/','/news/')
 for u in ('http://www.trendforce.com/news/a','https://evil.com/news/a','https://www.trendforce.com.evil.com/news/a','https://www.trendforce.com/private'):
  assert not r.allowed(u,'https://www.trendforce.com/news/','/news/')

def test_evidence_and_relationships():
 d=analysis();assert r.check_analysis(d,TEXT,[],{'MU':'Micron'})['readthroughs']
 d['readthroughs'][0]['basis_quote']='NVIDIA supplies imaginary parts'
 with pytest.raises(ValueError):r.check_analysis(d,TEXT,[],{'MU':'Micron'})
 d=analysis();d['readthroughs'][0]['ticker']='NVDA'
 with pytest.raises(ValueError):r.check_analysis(d,TEXT,[],{'MU':'Micron'})

def test_dedup_and_no_ai_on_status(db,monkeypatch):
 with db() as c:
  assert r.save_item(c,'1','web','Test',None,None,'HBM',TEXT)=='queued'
  assert r.save_item(c,'2','web','Test',None,None,'HBM',TEXT)=='duplicate'
 monkeypatch.setattr(r,'staff',lambda q:None)
 monkeypatch.setattr(r,'call_ai',lambda *a:pytest.fail('status cannot generate AI'))
 assert r.status(Request({'type':'http','headers':[]}))['budget']['limit']==20

def test_success_two_calls_settled_and_no_retries(db,monkeypatch):
 with db() as c:r.save_item(c,'one','web','Test',None,'2026-10-01','HBM',TEXT)
 calls=[]
 def ai(token,schema,system,content,costs):
  calls.append(1);costs.append(.002)
  return analysis() if len(calls)==1 else {'approved':True,'reason':'Source supported'}
 monkeypatch.setattr(r,'call_ai',ai)
 assert r.analyze('test')['state']=='complete'
 assert r.analyze('test')['state']=='idle'
 with db() as c:
  row=c.execute('SELECT * FROM radar_spend').fetchone();assert row['actual']==.004;assert row['accounted']==.004
  assert c.execute('SELECT text FROM radar_items').fetchone()[0]==''
 assert len(calls)==2

def test_failed_validation_skips_and_moves_on(db,monkeypatch):
 with db() as c:
  r.save_item(c,'one','web','Test',None,None,'HBM',TEXT)
  r.save_item(c,'two','web','Test',None,None,'HBM',TEXT+' New detail.')
 def ai(token,schema,system,content,costs):
  costs.append(.001);d=analysis();d['evidence']='A fake quotation that never appeared in this document.';return d
 monkeypatch.setattr(r,'call_ai',ai)
 assert r.analyze('test')['state']=='skipped'
 assert r.analyze('test')['state']=='skipped'
 with db() as c:
  assert c.execute('SELECT SUM(accounted) FROM radar_spend').fetchone()[0]==.002
  assert c.execute("SELECT COUNT(*) FROM radar_items WHERE status='queued'").fetchone()[0]==0

def test_budget_and_atomic_claim(db,monkeypatch):
 with db() as c:
  r.save_item(c,'one','web','Test',None,None,'HBM',TEXT)
  c.execute('INSERT INTO radar_spend VALUES(?,?,?,?,?,?)',('spent',r.month(),19.9,19.9,'settled',time.time()))
 monkeypatch.setattr(r,'call_ai',lambda *a:pytest.fail('budget must block'))
 assert r.analyze('test')['state']=='budget_paused'
 with db() as c:assert c.execute('SELECT status FROM radar_items').fetchone()[0]=='queued'

def test_preview_does_not_collect(monkeypatch):
 monkeypatch.setenv('VERCEL_ENV','preview')
 monkeypatch.setattr(r,'discover',lambda:pytest.fail('No preview collection'))
 assert r.run(Request({'type':'http','headers':[]}))['state']=='preview_read_only'


def test_typography_normalization_does_not_change_words():
 assert r.normal("Micron’s HBM—growth") == r.normal("Micron's HBM-growth")
 assert r.normal('growth 10%') != r.normal('growth 100%')
