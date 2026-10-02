import sqlite3
import json
from backend import research as r
from backend.research_health import snapshot

def connection():
 c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
 c.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)');r.migrate(c)
 return c

def test_failed_notes_stay_skipped_without_paid_retry():
 c=connection()
 for did,error in [('retry','Evidence not present in source'),('skip','PDF parsing failed; manual review required')]:
  c.execute('INSERT INTO research_documents VALUES(?,?,?,?,?,?,?,?,?,?,?)',(did,'x.pdf','',100,'x'*200,1,'needs_review',error,None,None,100))
 r.retry_failed_analyses(c,101)
 assert c.execute("SELECT status FROM research_documents WHERE id='retry'").fetchone()[0]=='needs_review'
 assert c.execute("SELECT status FROM research_documents WHERE id='skip'").fetchone()[0]=='needs_review'
 c.execute("UPDATE research_documents SET status='needs_review' WHERE id='retry'")
 r.retry_failed_analyses(c,102)
 assert c.execute("SELECT status FROM research_documents WHERE id='retry'").fetchone()[0]=='needs_review'

def test_cached_recovery_is_bounded_idempotent_and_never_calls_provider(monkeypatch):
 from backend.test_research import REPORT,TEXT
 c=connection();now=200000
 c.execute('CREATE TABLE stocks(ticker TEXT,name TEXT,active INTEGER)')
 c.execute("INSERT INTO stocks VALUES('NVDA','NVIDIA',1)")
 c.execute('CREATE TABLE ai_sentiment_spend(cache_key TEXT,raw_response TEXT,ts REAL)')
 for i in range(3):
  c.execute('INSERT INTO research_documents VALUES(?,?,?,?,?,?,?,?,?,?,?)',(str(i),'x.pdf','',now-i,TEXT+'\nAdditional industry discussion provides detailed context for the company outlook.',2,'needs_review','Evidence not present in source',None,None,now))
  content=json.dumps(REPORT)
  if i==1: content=content[:content.rfind(']')]+', {"ticker":'
  payload={'choices':[{'finish_reason':'length' if i==1 else 'stop','message':{'content':content}}]}
  c.execute('INSERT INTO ai_sentiment_spend VALUES(?,?,?)',('research:'+str(i),json.dumps(payload),now))
 monkeypatch.setattr(r.httpx,'post',lambda *a,**k:(_ for _ in ()).throw(AssertionError('No paid retries')))
 assert r.recover_cached_analyses(c,now,limit=2)==2
 assert c.execute("SELECT count(*) FROM research_documents WHERE status='draft'").fetchone()[0]==2
 assert r.recover_cached_analyses(c,now,limit=2)==1
 assert r.recover_cached_analyses(c,now,limit=2)==0
 assert c.execute('SELECT count(*) FROM research_links').fetchone()[0]==3

def test_cached_invalid_response_marked_once_without_blocking_next():
 c=connection();now=200000
 c.execute('CREATE TABLE stocks(ticker TEXT,name TEXT,active INTEGER)')
 c.execute('CREATE TABLE ai_sentiment_spend(cache_key TEXT,raw_response TEXT,ts REAL)')
 c.execute('INSERT INTO research_documents VALUES(?,?,?,?,?,?,?,?,?,?,?)',('bad','x.pdf','',now,'text',1,'needs_review','error',None,None,now))
 c.execute("INSERT INTO ai_sentiment_spend VALUES('research:bad','not json',?)",(now,))
 assert r.recover_cached_analyses(c,now)==0
 assert r.meta(c,'cached_recovery_v2:bad')['state']=='unresolved'
 assert r.recover_cached_analyses(c,now+1)==0

def test_mail_failures_back_off_and_stop_after_three_attempts(monkeypatch):
 c=connection();monkeypatch.setattr(r.time,'time',lambda:1000)
 r.record_mail_failure(c,'transient','fetch_needs_review')
 assert r.meta(c,'mail_retry:transient')['next']==1300
 r.record_mail_failure(c,'transient','fetch_needs_review')
 assert r.meta(c,'mail_retry:transient')['next']==2800
 r.record_mail_failure(c,'transient','fetch_needs_review')
 assert r.meta(c,'mail_retry:transient')['next'] is None
 r.record_mail_failure(c,'oversize','oversize_or_unavailable',permanent=True)
 assert r.meta(c,'mail_retry:oversize')['next'] is None

def test_repeated_validation_failure_and_unpublished_valid_notes_alert(monkeypatch):
 import time
 from datetime import datetime,timezone
 c=connection();now=time.time()
 for key in ['worker','drive_worker']:r.put(c,key,{'at':now,'state':'ok'})
 for i in range(3):c.execute('INSERT INTO research_documents VALUES(?,?,?,?,?,?,?,?,?,?,?)',(str(i),'x.pdf','',now,'text',1,'needs_review','Evidence not present in source',None,None,now))
 assert any('Repeated research validation' in v for v in snapshot(c,now)['operational_issues'])
 c.execute('CREATE TABLE research_publications(document_id TEXT PRIMARY KEY,published REAL)')
 v={'report_date':datetime.fromtimestamp(now,timezone.utc).date().isoformat(),'date_evidence':'date','findings':[{'ticker':'APH'}]}
 c.execute('INSERT INTO research_documents VALUES(?,?,?,?,?,?,?,?,?,?,?)',('waiting','x.pdf','',now,'text',1,'draft',None,json.dumps(v),None,now-1900))
 monkeypatch.setenv('RESEARCH_DRIVE_PUBLISH_ENABLED','true')
 assert any('not reached publication' in v for v in snapshot(c,now)['operational_issues'])

def test_old_queue_with_progress_is_not_an_outage():
 c=connection();now=100000
 for key in ['worker','drive_worker']:r.put(c,key,{'at':now,'state':'ok'})
 for did,status,updated in [('waiting','queued',now-10000),('done','draft',now-100)]:
  c.execute('INSERT INTO research_documents VALUES(?,?,?,?,?,?,?,?,?,?,?)',(did,'x.pdf','',now,'x'*200,1,status,None,None,None,updated))
 assert snapshot(c,now)['operational_issues']==[]
 c.execute("UPDATE research_documents SET updated=? WHERE id='done'",(now-3600,))
 assert any('two hours' in x for x in snapshot(c,now)['operational_issues'])


def test_drive_pending_watchdog_tracks_progress_not_heartbeat():
 c=connection();now=100000
 c.execute('CREATE TABLE research_drive_files(id TEXT,status TEXT)')
 c.execute("INSERT INTO research_drive_files VALUES('waiting','pending')")
 for key in ['worker','drive_worker']:r.put(c,key,{'at':now,'state':'ok'})
 assert snapshot(c,now)['operational_issues']==[]
 later=now+3700
 for key in ['worker','drive_worker']:r.put(c,key,{'at':later,'state':'ok'})
 assert any('no import progress' in x for x in snapshot(c,later)['operational_issues'])
 r.put(c,'drive_last_progress',later)
 assert snapshot(c,later)['operational_issues']==[]
 c.execute('DELETE FROM research_drive_files')
 snapshot(c,later)
 assert r.meta(c,'drive_pending_observed')==0


def test_release_holds_preserves_charges_unknowns_and_live_work():
 c=connection()
 c.execute('CREATE TABLE ai_sentiment_spend(id TEXT,cache_key TEXT,reserved REAL,actual REAL,status TEXT,ts REAL)')
 for row in [('failed','research:a',.25,None,'reserved',100),('paid','research:b',.25,.012,'received',100),('live','research:c',.25,None,'reserved',1999),('other','sentiment:d',.03,None,'reserved',100)]:
  c.execute('INSERT INTO ai_sentiment_spend VALUES(?,?,?,?,?,?)',row)
 assert r.release_research_reservations(c,2000)==2
 assert tuple(c.execute("SELECT reserved,actual FROM ai_sentiment_spend WHERE id='failed'").fetchone())==(0,None)
 assert tuple(c.execute("SELECT reserved,actual FROM ai_sentiment_spend WHERE id='paid'").fetchone())==(0,.012)
 assert c.execute("SELECT reserved FROM ai_sentiment_spend WHERE id='live'").fetchone()[0]==.25
 assert c.execute("SELECT reserved FROM ai_sentiment_spend WHERE id='other'").fetchone()[0]==.03
 assert r.meta(c,'unreconciled_cost:failed')['provider_charge']=='unknown'
 assert r.release_research_reservations(c,2000)==0
 r.release_research_reservations(c,2000,'live')
 assert c.execute("SELECT reserved FROM ai_sentiment_spend WHERE id='live'").fetchone()[0]==0
