import pytest,httpx
from datetime import date
from . import research_drive as d

def client(nodes):
 def handler(req):
  name=req.url.path.rsplit('/',1)[-1]
  return httpx.Response(200,json=nodes.get(name,{'parents':[]}))
 return httpx.Client(transport=httpx.MockTransport(handler))

def test_descendant_allowed():
 with client({'pdf':{'parents':['broker']},'broker':{'parents':[d.ROOT]}}) as c:assert d.under_root(c,'pdf')
def test_unrelated_denied():
 with client({'pdf':{'parents':['other']}}) as c:assert not d.under_root(c,'pdf')
def test_trashed_denied():
 with client({'pdf':{'parents':[d.ROOT],'trashed':True}}) as c:assert not d.under_root(c,'pdf')
def test_cycle_bounded():
 with client({'a':{'parents':['b']},'b':{'parents':['a']}}) as c:assert not d.under_root(c,'a')
def test_query_injection_rejected():
 with pytest.raises(ValueError):d.safe_id("x' or trashed=false")
def test_cipher_not_plaintext(monkeypatch):
 monkeypatch.setenv('GOOGLE_DRIVE_CLIENT_SECRET','test-only')
 token=d.cipher().encrypt(b'example-token')
 assert b'example-token' not in token
 assert d.cipher().decrypt(token)==b'example-token'
def test_preview_never_runs(monkeypatch):
 monkeypatch.setenv('VERCEL_ENV','preview');monkeypatch.setenv('RESEARCH_DRIVE_ENABLED','true')
 assert d.run()=={'state':'disabled'}

def test_report_date_candidate_screen():
 today=date(2026,9,20)
 for text in ['September 18, 2026','18 September 2026','2026-09-18','9/18/2026','18 Sep 2026']:
  assert d.recent_date_candidate(text,today)
  for text in ['September 18, 2025','October 18, 2026','undated report']:
   assert not d.recent_date_candidate(text,today)

def test_filename_and_whole_first_page_dates():
 today=date(2026,9,20)
 assert d.recent_date_candidate('no date',today,'GS_9.18.26.pdf')
 assert d.recent_date_candidate('[Page 1]\n'+'x'*4000+' September 18, 2026\n[Page 2]\n',today)
 assert not d.recent_date_candidate('[Page 1]\nundated\n[Page 2]\nSeptember 18, 2026',today)
 assert len(d.date_candidates('Report_09.10.2026.pdf'))==2

def test_ancestry_deadline():
 with client({}) as c:
  with pytest.raises(TimeoutError):d.under_root(c,'pdf',0)

def test_pending_prioritizes_recent_filename_over_discovery_time():
 today=date.today().isoformat()
 recent={'id':'recent','name':today+'.pdf','seen':1}
 unknown={'id':'unknown','name':'note.pdf','seen':2}
 old={'id':'old','name':'2000-01-01.pdf','seen':3}
 assert sorted([old,unknown,recent],key=d.pending_priority)==[recent,unknown,old]

def test_only_recent_dated_findings_publish(monkeypatch,tmp_path):
 import sqlite3,json,time
 from contextlib import contextmanager
 from types import SimpleNamespace
 @contextmanager
 def db():
  c=sqlite3.connect(tmp_path/'drive.sqlite');c.row_factory=sqlite3.Row
  c.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT)")
  try:yield c;c.commit()
  finally:c.close()
 monkeypatch.setattr(d,'core',lambda:SimpleNamespace(db=db))
 with db() as c:
  d.migrate(c)
  for identifier,report_date,evidence,findings in [('recent',date.today().isoformat(),'dated source',[{'ticker':'NVDA'}]),('undated',None,'',[{'ticker':'NVDA'}]),('old','2000-01-01','dated source',[{'ticker':'NVDA'}]),('empty',date.today().isoformat(),'dated source',[])]:
   result=json.dumps(dict(report_date=report_date,date_evidence=evidence,findings=findings))
   c.execute('INSERT INTO research_documents(id,filename,sender,received,text,pages,status,result,updated) VALUES(?,?,?,?,?,?,?,?,?)',(identifier,'private.pdf','test',time.time(),'source',1,'draft',result,time.time()))
   c.execute('INSERT INTO research_drive_files(id,version,name,size,status,document_id,seen) VALUES(?,?,?,?,?,?,?)',(identifier,'1','private.pdf',100,'imported',identifier,time.time()))
 d.publish_validated();d.publish_validated()
 with db() as c:assert [r[0] for r in c.execute('SELECT document_id FROM research_publications')]==['recent']


def test_parser_typeerror_does_not_block_next_pdf(monkeypatch,tmp_path):
 import sqlite3,time
 from contextlib import contextmanager
 from types import SimpleNamespace
 @contextmanager
 def db():
  c=sqlite3.connect(tmp_path/'isolated.sqlite');c.row_factory=sqlite3.Row
  c.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT)")
  try:yield c;c.commit()
  finally:c.close()
 monkeypatch.setattr(d,'core',lambda:SimpleNamespace(db=db))
 with db() as c:
  d.migrate(c);c.execute('CREATE TABLE stocks(ticker TEXT,name TEXT,active INTEGER)')
  c.execute("INSERT INTO stocks VALUES('NVDA','Nvidia',1)")
  for fid in ['a','b']:c.execute('INSERT INTO research_drive_files(id,parent,version,name,size,status,seen) VALUES(?,?,?,?,?,?,?)',(fid,d.ROOT,'1',date.today().isoformat()+'.pdf',100,'pending',1))
 with db() as c:c.execute('UPDATE research_drive_files SET modified_at=?',(time.time(),))
 monkeypatch.setattr(d,'under_root',lambda *a:True)
 def extract(raw):
  if raw==b'a':raise RuntimeError('unexpected malformed font parser failure')
  return ('[Page 1] valid body.',1)
 monkeypatch.setattr(d.research,'extract_pdf',extract)
 monkeypatch.setattr(d.research,'prescreen',lambda *a:{'skip':False})
 with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,content=req.url.path.rsplit('/',1)[-1].encode()))) as c:d.import_files(c,time.monotonic()+30)
 with db() as c:
  rows=c.execute('SELECT id,status FROM research_drive_files ORDER BY id').fetchall()
  assert [tuple(r) for r in rows]==[('a','needs_review'),('b','imported')]


def test_scan_filters_pdf_date_not_folder_date(monkeypatch,tmp_path):
 import sqlite3,time
 from contextlib import contextmanager
 from types import SimpleNamespace
 from datetime import datetime,timezone,timedelta
 @contextmanager
 def db():
  c=sqlite3.connect(tmp_path/'metadata.sqlite');c.row_factory=sqlite3.Row
  c.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT)")
  try:yield c;c.commit()
  finally:c.close()
 monkeypatch.setattr(d,'core',lambda:SimpleNamespace(db=db))
 with db() as c:d.migrate(c)
 now=datetime.now(timezone.utc)
 files=[{'id':'oldfolder','name':'folder','mimeType':d.FOLDER,'modifiedTime':'2000-01-01T00:00:00Z'}]
 for fid,stamp in [('recent',(now-timedelta(days=2)).isoformat()),('old',(now-timedelta(days=8)).isoformat()),('missing',None)]:
  files.append({'id':fid,'name':fid+'.pdf','mimeType':'application/pdf','size':'100','modifiedTime':stamp,'md5Checksum':fid})
 monkeypatch.setattr(d,'under_root',lambda *a:True)
 with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'files':files}))) as c:d.scan(c,time.monotonic()+30)
 with db() as c:
  assert dict(c.execute('SELECT id,status FROM research_drive_files'))=={'recent':'pending','old':'outside_modified_window','missing':'needs_review'}
  assert c.execute("SELECT id FROM research_drive_folders WHERE id='oldfolder'").fetchone()
  c.execute("UPDATE research_drive_files SET modified_at=? WHERE id='recent'",(time.time()-8*86400,))
 with httpx.Client(transport=httpx.MockTransport(lambda req:pytest.fail('Old files must not be downloaded'))) as c:d.import_files(c,time.monotonic()+30)
 with db() as c:assert c.execute("SELECT status FROM research_drive_files WHERE id='recent'").fetchone()[0]=='outside_modified_window'

def test_missing_file_date_never_uses_discovery_time():
 assert d.file_modified_at(None) is None
 assert d.file_modified_at('2026-09-21') is None
 assert d.file_modified_at('2026-09-21T05:00:00Z') is not None


def test_backlog_migration_requires_file_metadata_once(monkeypatch,tmp_path):
 import sqlite3
 from contextlib import contextmanager
 from types import SimpleNamespace
 @contextmanager
 def db():
  c=sqlite3.connect(tmp_path/'legacy.sqlite');c.row_factory=sqlite3.Row
  try:yield c;c.commit()
  finally:c.close()
 monkeypatch.setattr(d,'core',lambda:SimpleNamespace(db=db))
 with db() as c:
  c.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
  c.execute('CREATE TABLE research_drive_files(id TEXT PRIMARY KEY,parent TEXT,version TEXT,name TEXT,size INTEGER,status TEXT,document_id TEXT,seen REAL,error TEXT)')
  c.execute("INSERT INTO research_drive_files(id,version,name,size,status,seen) VALUES('legacy','1','note.pdf',100,'pending',9999999999)")
  d.migrate(c)
  assert c.execute("SELECT status FROM research_drive_files WHERE id='legacy'").fetchone()[0]=='archived_discovery'
  c.execute("UPDATE research_drive_folders SET checked=123")
  d.migrate(c)
  assert c.execute('SELECT checked FROM research_drive_folders').fetchone()[0]==123


def test_server_query_filters_only_pdf_modified_time():
 from datetime import datetime,timezone
 query=d.discovery_query(d.ROOT,datetime(2026,9,21,tzinfo=timezone.utc).timestamp())
 assert "modifiedTime >= '2026-09-14T00:00:00Z'" in query
 assert "(mimeType='application/vnd.google-apps.folder' or (mimeType='application/pdf' and modifiedTime" in query
 assert "trashed=false" in query
