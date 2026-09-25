import sqlite3,time
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from . import research as r

@pytest.mark.parametrize('state,complete,delete',[('draft',True,True),('no_match',True,True),('screened_out',True,True),('queued',True,False),('needs_review',True,False),('analyzing',True,False),('draft',False,False)])
def test_cleanup_only_complete_mail(tmp_path,monkeypatch,state,complete,delete):
 @contextmanager
 def db():
  c=sqlite3.connect(tmp_path/'cleanup.sqlite');c.row_factory=sqlite3.Row
  try:yield c;c.commit()
  finally:c.close()
 monkeypatch.setattr(r,'core',lambda:SimpleNamespace(db=db))
 with db() as c:
  r.migrate(c);c.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
  c.execute('INSERT INTO research_documents VALUES(?,?,?,?,?,?,?,?,?,?,?)',('doc','a.pdf','',0,'',1,state,None,None,None,0))
  r.put(c,'mail_documents:123:1',{'ids':['doc'],'complete':complete})
 imap=MagicMock();imap.capabilities=(b'IMAP4rev1',b'UIDPLUS');imap.select.return_value=('OK',[]);imap.response.return_value=('UIDVALIDITY',[b'123'])
 imap.uid.side_effect=lambda command,*args: ('OK',[b'1 2']) if command=='search' else ('OK',[])
 assert r.cleanup_mail(imap,'123')['deleted']==int(delete)
 calls=[call.args for call in imap.uid.call_args_list]
 assert ('expunge',b'1') in calls if delete else not any(c[0]=='store' for c in calls)
 imap.expunge.assert_not_called()
 assert all(c[1]!=b'2' for c in calls if c[0]=='store')
 imap.capabilities=(b'IMAP4rev1',)
 assert r.cleanup_mail(imap,'123')['state']=='uid_expunge_unavailable'
