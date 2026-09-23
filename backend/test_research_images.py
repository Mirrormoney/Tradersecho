import io,json,sqlite3,time
from contextlib import contextmanager
from types import SimpleNamespace
from email.message import EmailMessage
from unittest.mock import MagicMock
import pytest,httpx
from PIL import Image
from . import research as r,research_images as im

TEXT='September 23, 2026\nBroker Research\nNVIDIA expects improving demand for AI products. Supply remains constrained and production capacity is expanding in response to customer orders.'

@pytest.fixture
def db(tmp_path,monkeypatch):
 @contextmanager
 def db():
  c=sqlite3.connect(tmp_path/'test.sqlite');c.row_factory=sqlite3.Row
  try:yield c;c.commit()
  finally:c.close()
 with db() as c:
  r.migrate(c)
  c.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
  c.execute('CREATE TABLE stocks(ticker TEXT,name TEXT,active INTEGER)')
  c.execute('CREATE TABLE ai_sentiment_spend(id TEXT PRIMARY KEY,cache_key TEXT,month TEXT,reserved REAL,actual REAL,ts REAL,status TEXT,usage TEXT,raw_response TEXT)')
 monkeypatch.setattr(r,'core',lambda:SimpleNamespace(db=db))
 monkeypatch.setenv('RESEARCH_IMAP_PASSWORD','test')
 monkeypatch.delenv('RESEARCH_DRIVE_PUBLISH_ENABLED',raising=False)
 return db

def mailbox(monkeypatch,msg):
 box=MagicMock();box.select.return_value=('OK',[]);box.response.return_value=('UIDVALIDITY',[b'1'])
 def uid(command,*args):
  if command=='search':return 'OK',[b'1']
  if args[1]=='(RFC822.SIZE)':return 'OK',[b'1 (RFC822.SIZE 1000)']
  return 'OK',[(b'1',msg.as_bytes())]
 box.uid.side_effect=uid;monkeypatch.setattr(r.imaplib,'IMAP4_SSL',lambda *a,**k:box)
 return box

def test_four_images_backfill_batch_and_duplicate(db,monkeypatch):
 msg=EmailMessage();msg.set_content('')
 for i in range(4):msg.add_attachment(str(i).encode(),maintype='image',subtype='png',filename=f'{i}.png')
 msg.add_attachment(b'0',maintype='image',subtype='png',filename='duplicate.png')
 box=mailbox(monkeypatch,msg);calls=[]
 monkeypatch.setattr(im,'extract',lambda raw,*a:(calls.append(raw) or ('[Page 1]\n'+TEXT,1)))
 with db() as c:c.execute("INSERT INTO research_messages VALUES('1:1','imported',?)",(time.time(),))
 assert r.import_mail()['images_deferred']==2
 assert r.import_mail()['imported']==2
 assert r.import_mail()['imported']==0
 assert len(calls)==4
 with db() as c:assert c.execute('SELECT count(*) FROM research_documents').fetchone()[0]==4
 box.store.assert_not_called()

def test_bad_image_and_deferred_budget_do_not_block_pdf(db,monkeypatch):
 msg=EmailMessage();msg.set_content('')
 for raw in (b'bad',b'budget'):msg.add_attachment(raw,maintype='image',subtype='png',filename='note.png')
 msg.add_attachment(b'pdf',maintype='application',subtype='pdf',filename='note.pdf')
 mailbox(monkeypatch,msg)
 def extract(raw,*args):
  if raw==b'bad':raise ValueError('Unreadable image')
  raise im.DeferredImage('budget')
 monkeypatch.setattr(im,'extract',extract);monkeypatch.setattr(r,'extract_pdf',lambda raw:('[Page 1]\n'+TEXT,1))
 assert r.import_mail()['images_deferred']==1
 with db() as c:
  assert c.execute("SELECT count(*) FROM research_documents WHERE status='awaiting_analysis'").fetchone()[0]==1
  assert c.execute('SELECT status FROM research_messages').fetchone()[0]=='images_pending'

def raw_image():
 out=io.BytesIO();Image.new('RGB',(500,800),'white').save(out,format='PNG');return out.getvalue()

def test_ocr_ledger_cache_and_budget(db,monkeypatch):
 payload={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'text':TEXT,'legible':True,'research':True})}}],'usage':{'cost':.002}}
 calls=[]
 def post(*a,**k):calls.append(k);return httpx.Response(200,json=payload)
 monkeypatch.setattr(im.httpx,'post',post)
 assert im.extract(raw_image(),'a','token')[1]==1
 assert im.extract(raw_image(),'a','token')[1]==1
 assert len(calls)==1
 with db() as c:
  assert c.execute('SELECT actual FROM ai_sentiment_spend').fetchone()[0]==.002
 monkeypatch.setenv('RESEARCH_AI_MONTHLY_USD','0.1')
 with pytest.raises(im.DeferredImage):im.extract(raw_image(),'b','token')
 assert len(calls)==1

def test_illegible_not_accepted():
 with pytest.raises(ValueError,match='reliably readable'):
  im.decode({'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'text':TEXT,'legible':False,'research':True})}}]})
 with pytest.raises(ValueError):im.prepare_image(b'broken')
