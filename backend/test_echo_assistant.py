from .test_service import s,isolate_tests
from . import echo_assistant as e
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi.testclient import TestClient

def moment(hour=10,minute=0):return datetime(2026,9,22,hour,minute,tzinfo=ZoneInfo('America/New_York')).timestamp()
def prep(monkeypatch):
 with s.db() as c:
  c.execute('DELETE FROM echo_posts');c.execute("INSERT INTO settings VALUES('echo_assistant','enabled')")
 monkeypatch.setattr(e,'candidates',lambda now:[(t,'e:'+t,'$'+t+' has fresh data.','What would you check?') for t in ['NVDA','AMD','MU','INTC','TSLA']])
def test_gates_dedup_and_label(monkeypatch):
 prep(monkeypatch)
 assert e.run(moment(8))['state']=='outside_window'
 assert e.run(moment())['state']=='posted'
 assert e.run(moment())['state']=='cooldown'
 assert e.run(moment(12))['state']=='posted'
 assert e.run(moment(14))['state']=='posted'
 assert e.run(moment(15,55))['state']=='posted'
 assert e.run(moment(15,56))['state']=='daily_cap'
 with s.db() as c:
  rows=c.execute('SELECT * FROM echo_posts').fetchall();assert len({r['ticker'] for r in rows})==4
  c.execute('DELETE FROM chat_messages WHERE id=?',(rows[0]['message_id'],))
  assert c.execute('SELECT COUNT(*) FROM echo_posts').fetchone()[0]==4
 c=TestClient(s.app);assert c.get('/api/cron/echo').status_code==401
 c.post('/api/auth/signup',json={'display_name':'echotest','email':'echo@example.com','password':'test-password-long'})
 with s.db() as db:db.execute("UPDATE accounts SET plan='premium' WHERE email='echo@example.com'")
 messages=c.get('/api/community/messages');assert messages.status_code==200,messages.text
 bot=[r for r in messages.json() if r['display_name']=='Echo Assistant'];assert len(bot)==3 and all(r['role']=='Automated' for r in bot)
 assert c.put('/api/admin/echo-assistant',json={'enabled':False}).status_code==403

def test_active_room_pause_and_empty(monkeypatch):
 prep(monkeypatch)
 with s.db() as c:
  c.execute("INSERT INTO accounts(id,email,display_name) VALUES('member','member@example.com','Human Member')")
  c.execute("INSERT INTO chat_messages(user_id,body,ticker,ts) VALUES('member','Hello','',?)",(moment()-60,))
 assert e.run(moment())['state']=='room_active'
 monkeypatch.setattr(e,'candidates',lambda now:[])
 assert e.run(moment(11))['state']=='no_fresh_evidence'
 with s.db() as c:c.execute("UPDATE settings SET value='paused' WHERE key='echo_assistant'")
 assert e.run(moment(12))['state']=='paused'
