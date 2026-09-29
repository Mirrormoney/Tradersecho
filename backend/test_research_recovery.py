import sqlite3
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
