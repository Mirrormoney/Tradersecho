"""Clearly labelled, deterministic conversation starters from saved data only."""
import os,time,hmac,json
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter,Request,HTTPException
from pydantic import BaseModel
router=APIRouter()
def core():
 from . import service
 return service

def migrate(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS echo_posts(event_key TEXT PRIMARY KEY,message_id INTEGER REFERENCES chat_messages(id) ON DELETE SET NULL,ticker TEXT NOT NULL,ts REAL NOT NULL);
 CREATE INDEX IF NOT EXISTS echo_posts_time ON echo_posts(ts);''')

def enabled(c):
 r=c.execute("SELECT value FROM settings WHERE key='echo_assistant'").fetchone()
 return bool(r and r[0]=='enabled')

@router.get('/api/admin/echo-assistant')
def status(request:Request):
 from .community import staff
 staff(request)
 with core().db() as c:return {'enabled':enabled(c)}
class Setting(BaseModel):
 enabled:bool
@router.put('/api/admin/echo-assistant')
def setting(body:Setting,request:Request):
 from .community import staff,audit
 u=staff(request)
 with core().db() as c:
  c.execute("INSERT INTO settings(key,value) VALUES('echo_assistant',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",('enabled' if body.enabled else 'paused',))
  audit(c,u,'echo_assistant','', 'enabled' if body.enabled else 'paused')
 return {'enabled':body.enabled}

def candidates(now):
 from .live_collection import intraday_rows
 from .post_quality import research_text
 from .screening import stock_context
 s=core();result=[]
 for r in intraday_rows(now):
  if r['state']!='measured' or r['mentions']<20 or r['previous']<10 or (r['change'] or 0)<25:continue
  if not any(now-6*3600<=p['ts']<=now and research_text(p['text']) and stock_context(p['text'],r['ticker']) for p in r.get('posts',[])):continue
  stamp=datetime.fromtimestamp(r['as_of'],ZoneInfo('America/New_York')).strftime('%I:%M %p %Z').lstrip('0')
  fact=f"${r['ticker']} recorded {r['mentions']:,} X mentions in the latest three completed hours, up {r['change']:g}% versus the preceding three (through {stamp})."
  result.append((r['ticker'],f"attention:{r['ticker']}:{r['as_of']}",fact,'Attention is not a price signal. What context would you check before drawing a conclusion?'))
 with s.db() as c:
  rows=c.execute("SELECT f.accession,f.form,f.accepted,m.ticker FROM sec_filings f JOIN sec_companies m ON m.cik=f.cik JOIN stocks s ON s.ticker=m.ticker WHERE s.active=1 AND f.accepted>? AND f.accepted<=? ORDER BY f.accepted DESC LIMIT 20",(now-6*3600,now)).fetchall()
 for r in rows:
  if r['ticker'] in s.CATALOG and r['form'] in ('8-K','10-Q','10-K','6-K'):
   result.append((r['ticker'],'sec:'+r['accession'],f"${r['ticker']} has a new {r['form']} filing in our SEC feed.",'Open the ticker details to read the original filing. Which disclosure is worth a closer look?'))
 return result

def run(now=None):
 now=time.time() if now is None else now;s=core();local=datetime.fromtimestamp(now,ZoneInfo('America/New_York'));minute=local.hour*60+local.minute
 # Weekday US-session window; no catch-up posts outside that window.
 if local.weekday()>=5 or not 570<=minute<960:return {'state':'outside_window'}
 with s.db() as c:
  if not enabled(c):return {'state':'paused'}
 options=candidates(now)
 start=local.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
 with s.db() as c:
  c.execute('BEGIN IMMEDIATE')
  if not enabled(c):return {'state':'paused'}
  today=c.execute('SELECT ticker,ts FROM echo_posts WHERE ts>=?',(start,)).fetchall()
  if len(today)>=4:return {'state':'daily_cap'}
  last=c.execute('SELECT MAX(ts) FROM echo_posts').fetchone()[0]
  if last and now-last< (90+int(datetime.fromtimestamp(last,ZoneInfo('America/New_York')).strftime('%d'))%7*5)*60:return {'state':'cooldown'}
  if c.execute('SELECT 1 FROM chat_messages WHERE user_id IS NOT NULL AND hidden=0 AND ts>? LIMIT 1',(now-30*60,)).fetchone():return {'state':'room_active'}
  used={r['ticker'] for r in today}
  for ticker,key,fact,question in options:
   if ticker in used or c.execute('SELECT 1 FROM echo_posts WHERE event_key=?',(key,)).fetchone():continue
   intros=['Worth a closer look:','A conversation starter:','On the research list:','One to discuss:']
   body=intros[len(today)%4]+' '+fact+'\n\n'+question
   mid=c.execute('INSERT INTO chat_messages(user_id,body,ticker,ts) VALUES(NULL,?,?,?)',(body,ticker,now)).lastrowid
   c.execute('INSERT INTO echo_posts VALUES(?,?,?,?)',(key,mid,ticker,now))
   return {'state':'posted','message_id':mid}
 return {'state':'no_fresh_evidence'}

@router.get('/api/cron/echo')
def cron(request:Request):
 secret=os.getenv('CRON_SECRET','')
 if not secret or not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+secret):raise HTTPException(401,'Unauthorized')
 if os.getenv('VERCEL_ENV') not in (None,'production') or os.getenv('BILLING_SANDBOX','false').lower()=='true':return {'state':'non_production'}
 return run()
