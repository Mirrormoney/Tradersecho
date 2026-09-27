import json,sqlite3
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from . import insight_worker as w
from .insight_updates import merge_updates

@pytest.fixture
def db(tmp_path,monkeypatch):
 @contextmanager
 def connect():
  c=sqlite3.connect(tmp_path/'insights.sqlite');c.row_factory=sqlite3.Row
  try:yield c;c.commit()
  finally:c.close()
 with connect() as c:
  w.migrate(c)
  c.executescript('''CREATE TABLE research_documents(id TEXT,text TEXT,result TEXT,status TEXT,received REAL);
  CREATE TABLE stocks(ticker TEXT,name TEXT,active INTEGER);
  CREATE TABLE ai_sentiment_spend(id TEXT,cache_key TEXT,month TEXT,reserved REAL,ts REAL,status TEXT,actual REAL,usage TEXT);''')
  c.execute("INSERT INTO research_documents VALUES(?,?,?,?,?)",('one','[Page 1]\nHBM4 qualification is expected in 2027.',json.dumps({'firm':'Broker','report_date':'2026-01-01'}),'no_match',1))
 monkeypatch.setattr(w,'core',lambda:SimpleNamespace(db=connect))
 monkeypatch.setenv('SENTIMENT_AI_MONTHLY_USD','20');monkeypatch.setenv('RESEARCH_AI_MONTHLY_USD','15')
 return connect

def test_budget_pause_makes_no_paid_call(db,monkeypatch):
 from datetime import datetime,timezone
 with db() as c:c.execute('INSERT INTO ai_sentiment_spend(id,cache_key,month,reserved) VALUES(?,?,?,?)',('spent','research:x',datetime.now(timezone.utc).strftime('%Y-%m'),15))
 monkeypatch.setattr(w.httpx,'post',lambda *a,**k:pytest.fail('Budget must prevent request'))
 assert w.analyze_one('test')['state']=='budget_paused'

def test_bad_document_is_skipped_once_without_blocking_next(db,monkeypatch):
 calls=[]
 def fail(*a,**k):calls.append(1);raise ValueError('Unreadable response')
 monkeypatch.setattr(w.httpx,'post',fail)
 assert w.analyze_one('test')['state']=='skipped'
 assert w.analyze_one('test')['state']=='idle'
 with db() as c:
  c.execute('INSERT INTO research_documents SELECT ?,text,result,status,received+1 FROM research_documents LIMIT 1',('two',))
 assert w.analyze_one('test')['state']=='skipped'
 assert len(calls)==2

def test_public_bad_article_does_not_block_good_one(db,monkeypatch):
 monkeypatch.setattr(w,'NEWSROOMS',[('Source','https://example.com/','/news/')])
 listing=SimpleNamespace(links=['/news/bad','/news/good','https://evil.example/news/no'])
 def fetch(url):
  if url.endswith('/bad'):raise ValueError('Unreadable')
  if url.endswith('/good'):return SimpleNamespace(day='2026-01-01',text=['HBM4 qualification is expected in 2027.'])
  return listing
 monkeypatch.setattr(w,'fetch',fetch)
 assert w.check_public()['added']==1
 assert w.check_public()['state']=='up_to_date'
 with db() as c:assert {r['status'] for r in c.execute('SELECT status FROM insight_sources')}=={'unreadable','queued'}

def test_old_backfill_cannot_replace_newer_beneficiary():
 base={'slug':'hbm','sources':[{'id':'new','date':'2026-09-20'}],'timeline':[],'beneficiaries':[{'ticker':'MU','source':'new','why':'New relationship'}]}
 row={'result':json.dumps({'firm':'Broker','report_date':'2026-01-01','exposures':[{'topic':'hbm','ticker':'MU','reason':'Old relationship','evidence':'Micron makes memory products.'}]})}
 result=merge_updates(base,[row])
 assert result['beneficiaries'][0]['why']=='New relationship'

def test_staff_run_cooldown_prevents_repeat_paid_work(db,monkeypatch):
 from fastapi import Request
 monkeypatch.setattr(w,'check_public',lambda:{'state':'checked'})
 calls=[]
 def analyze(token):calls.append(1);return {'state':'complete','developments':1}
 monkeypatch.setattr(w,'analyze_one',analyze)
 request=Request({'type':'http','headers':[]})
 assert len(w.run(request)['analysis'])==3
 assert w.run(request)=={'state':'cooldown'}
 assert len(calls)==3

def test_public_development_is_validated_saved_once_and_raw_text_discarded(db,monkeypatch):
 from .test_insight_updates import EVENT
 with db() as c:c.execute('INSERT INTO insight_sources VALUES(?,?,?,?,?,?)',('https://example.com/news','Source','2026-01-01',EVENT['evidence'],'queued',1))
 calls=[]
 def post(*a,**k):
  calls.append(1)
  return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'topic_developments':[EVENT],'exposures':[]})}}],'usage':{'cost':0.003}})
 monkeypatch.setattr(w.httpx,'post',post)
 assert w.analyze_one('test')=={'state':'complete','developments':1}
 with db() as c:
  assert c.execute('SELECT text FROM insight_sources').fetchone()[0]==''
  result=json.loads(c.execute("SELECT result FROM insight_analysis WHERE id LIKE 'public:%'").fetchone()[0])
  assert result['source_url']=='https://example.com/news'
  assert result['topic_developments']==[EVENT]
