import sqlite3,time
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock
from email.message import EmailMessage
import pytest
from . import research as r

@pytest.mark.parametrize('failure',['fetch','parse','pdf','mime'])
def test_failed_email_or_attachment_does_not_block_next(tmp_path,monkeypatch,failure):
 @contextmanager
 def db():
  c=sqlite3.connect(tmp_path/'mail.sqlite');c.row_factory=sqlite3.Row
  try:yield c;c.commit()
  finally:c.close()
 monkeypatch.setattr(r,'core',lambda:SimpleNamespace(db=db))
 with db() as c:
  r.migrate(c);c.execute('CREATE TABLE stocks(ticker TEXT,name TEXT,active INTEGER)');c.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
 monkeypatch.setenv('RESEARCH_IMAP_PASSWORD','test');monkeypatch.delenv('RESEARCH_DRIVE_PUBLISH_ENABLED',raising=False)
 def message(raw):
  if raw==b'bad' and failure=='parse':raise ValueError('malformed MIME')
  msg=EmailMessage();msg['From']='test@example.com';msg.set_content('')
  if raw==b'bad':msg.add_attachment(b'broken',maintype='application',subtype='pdf',filename='bad.pdf')
  msg.add_attachment(b'valid'+raw,maintype='application',subtype='pdf',filename='valid.pdf')
  if raw==b'bad' and failure=='mime':
   parts=list(msg.walk());bad=MagicMock();bad.get_filename.side_effect=ValueError('bad filename encoding')
   msg.walk=lambda:iter([bad]+parts)
  return msg
 monkeypatch.setattr(r.email,'message_from_bytes',lambda raw,**kwargs:message(raw))
 def extract(raw):
  if raw==b'broken':raise RuntimeError('unexpected parser failure')
  return ('[Page 1]\nNVIDIA demand is growing.',1)
 monkeypatch.setattr(r,'extract_pdf',extract)
 imap=MagicMock();imap.select.return_value=('OK',[]);imap.response.return_value=('UIDVALIDITY',[b'123'])
 def uid(command,*args):
  if command=='search':return 'OK',[b'1 2']
  if args[1]=='(RFC822.SIZE)':return 'OK',[b'1 (RFC822.SIZE 1000)']
  if args[0]==b'1' and failure=='fetch':return 'NO',[None]
  return 'OK',[(b'1',b'bad' if args[0]==b'1' else b'good')]
 imap.uid.side_effect=uid;monkeypatch.setattr(r.imaplib,'IMAP4_SSL',lambda *a,**k:imap)
 assert r.import_mail()['state']=='ok'
 with db() as c:
  assert c.execute("SELECT COUNT(*) FROM research_documents WHERE status='awaiting_analysis'").fetchone()[0]>=1
  assert c.execute("SELECT status FROM research_messages WHERE id='123:2'").fetchone()[0]=='imported'
 assert r.import_mail()['imported']==0
 imap.store.assert_not_called()

def test_parser_timeout_is_a_skippable_document_failure(monkeypatch):
 import subprocess
 def timeout(*a,**kw):
  assert kw['timeout']==20
  raise subprocess.TimeoutExpired(a[0],20)
 monkeypatch.setattr(subprocess,'run',timeout)
 with pytest.raises(ValueError,match='20 seconds'):r.extract_pdf(b'%PDF')
