import sqlite3
from backend import research as r
from backend.research_health import snapshot

def connection():
 c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
 c.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)');r.migrate(c)
 return c

def test_retry_is_once_and_skips_unreadable_sources():
 c=connection()
 for did,error in [('retry','Evidence not present in source'),('skip','PDF parsing failed; manual review required')]:
  c.execute('INSERT INTO research_documents VALUES(?,?,?,?,?,?,?,?,?,?,?)',(did,'x.pdf','',100,'x'*200,1,'needs_review',error,None,None,100))
 r.retry_failed_analyses(c,101)
 assert c.execute("SELECT status FROM research_documents WHERE id='retry'").fetchone()[0]=='queued'
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
