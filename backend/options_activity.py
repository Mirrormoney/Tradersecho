"""Private, bounded UW alert experiment. Never contributes to member scores."""
import hashlib,hmac,json,math,os,secrets,time
from datetime import datetime
import httpx
from fastapi import APIRouter,Request,Response,HTTPException
from .community import core,staff
from . import uw_pilot as uw
router=APIRouter()

def migrate(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS options_activity_events(id TEXT PRIMARY KEY,ticker TEXT,at REAL,premium REAL,payload TEXT);
 CREATE INDEX IF NOT EXISTS options_activity_time ON options_activity_events(at);
 CREATE TABLE IF NOT EXISTS options_activity_usage(day TEXT PRIMARY KEY,n INTEGER DEFAULT 0);''')

def get(c,key,default=None):return uw.get(c,'activity_'+key,default)
def put(c,key,value):uw.put(c,'activity_'+key,value)

def event(row,catalog,now):
 try:
  ticker=row['ticker'];at=uw.timestamp(row['created_at']);premium=float(row['total_premium'])
  if ticker not in catalog or at is None or not now-30*86400<at<=now or not math.isfinite(premium) or premium<100000:return None
  typ=row['type']
  if typ not in ('call','put'):return None
  ask=float(row.get('total_ask_side_prem') or 0);bid=float(row.get('total_bid_side_prem') or 0)
  if not all(math.isfinite(v) and 0<=v<=premium for v in (ask,bid)):return None
  multi=bool(row.get('has_multileg'))
  side='complex' if multi else 'ask' if ask/premium>=.7 else 'bid' if bid/premium>=.7 else 'mixed'
  # Stable identity excludes mutable premium totals; later updates replace the event.
  identity=str(row.get('id') or '|'.join(str(row.get(k,'')) for k in ('ticker','option_chain','created_at','alert_rule')))
  return {'id':hashlib.sha256(identity.encode()).hexdigest(),'ticker':ticker,'at':at,'premium':premium,
   'type':typ,'strike':str(row.get('strike',''))[:32],'expiry':str(row.get('expiry',''))[:10],
   'side':side,'ask_pct':round(100*ask/premium),'bid_pct':round(100*bid/premium),
   'sweep':bool(row.get('has_sweep')),'rule':str(row.get('alert_rule',''))[:80],
   'size':str(row.get('total_size',''))[:30],'open_interest':str(row.get('open_interest',''))[:30]}
 except (KeyError,ValueError,TypeError):return None

def reserve(c,now):
 day=uw.quota_day(now);c.execute('BEGIN IMMEDIATE')
 c.execute('INSERT OR IGNORE INTO uw_pilot_usage(day) VALUES(?)',(day,))
 c.execute('INSERT OR IGNORE INTO options_activity_usage(day) VALUES(?)',(day,))
 u=c.execute('SELECT * FROM uw_pilot_usage WHERE day=?',(day,)).fetchone()
 n=c.execute('SELECT n FROM options_activity_usage WHERE day=?',(day,)).fetchone()[0]
 if n>=500 or max(u['reserved'],u['provider_count'])>=min(32000,u['provider_limit']):return False
 c.execute('UPDATE uw_pilot_usage SET reserved=? WHERE day=?',(max(u['reserved'],u['provider_count'])+1,day))
 c.execute('UPDATE options_activity_usage SET n=n+1 WHERE day=?',(day,));return True

def run(now=None,client=None):
 now=now or time.time()
 if os.getenv('VERCEL_ENV')!='production':return {'state':'preview_disabled'}
 if not all(uw.configured().values()):return {'state':'setup_required'}
 if not uw.session_open(now):return {'state':'outside_session'}
 s=core();catalog=set(s.CATALOG);token=secrets.token_hex(12)
 with s.db() as c:
  migrate(c);c.execute('BEGIN IMMEDIATE')
  if get(c,'lease',{}).get('until',0)>now:return {'state':'busy'}
  if max(get(c,'cooldown',0),uw.get(c,'cooldown',0))>now:return {'state':'provider_paused'}
  if get(c,'last',{}).get('at',0)>now-540:return {'state':'not_due'}
  put(c,'lease',{'token':token,'until':now+120})
  start=datetime.fromtimestamp(now,uw.NY).replace(hour=9,minute=30,second=0,microsecond=0).timestamp()
  pending=get(c,'pending',None)
  if pending and pending['start']<start:pending=None
  window=pending or {'start':max(start,get(c,'through',now-600)-1),'end':now,'cursor':now}
 own=client is None;result={'state':'partial','at':now,'pages':0,'matched':0};started=time.monotonic()
 try:
  if own:client=httpx.Client(timeout=12,headers={'Authorization':'Bearer '+os.environ['UW_API_KEY']})
  for _ in range(5):
   with s.db() as c:
    if not reserve(c,now):result['state']='budget_paused';break
   response=client.get('https://api.unusualwhales.com/api/option-trades/flow-alerts',params={'min_premium':100000,'limit':200,'newer_than':window['start'],'older_than':window['cursor']})
   result['pages']+=1
   with s.db() as c:
    for header,col in [('x-uw-daily-req-count','provider_count'),('x-uw-token-req-limit','provider_limit')]:
     value=response.headers.get(header,'')
     if value.isdigit():c.execute('UPDATE uw_pilot_usage SET '+col+'=? WHERE day=?',(int(value),uw.quota_day(now)))
   if response.status_code in (401,403,429):
    with s.db() as c:put(c,'cooldown',now+(900 if response.status_code==429 else 3600))
   response.raise_for_status()
   if len(response.content)>2000000:raise ValueError('response_size')
   rows=response.json().get('data')
   if not isinstance(rows,list) or len(rows)>200:raise ValueError('response_shape')
   events=[v for r in rows if isinstance(r,dict) and (v:=event(r,catalog,now))]
   with s.db() as c:
    for v in events:c.execute('INSERT INTO options_activity_events VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET premium=excluded.premium,payload=excluded.payload',(v['id'],v['ticker'],v['at'],v['premium'],json.dumps(v)))
   result['matched']+=len(events)
   if len(rows)<200:
    result['state']='complete'
    with s.db() as c:put(c,'through',window['end']);put(c,'pending',None)
    break
   times=[uw.timestamp(r.get('created_at')) for r in rows if isinstance(r,dict)]
   oldest=min((t for t in times if t is not None),default=window['cursor'])
   # Overlap the boundary and deduplicate. Never silently skip equal-time overflow.
   cursor=oldest+.000001
   if cursor>=window['cursor']:result['state']='cursor_stalled';break
   window['cursor']=cursor
   with s.db() as c:put(c,'pending',window)
   if time.monotonic()-started>70:break
   time.sleep(1.1)
 except (httpx.HTTPError,ValueError,TypeError) as exc:
  result['state']='provider_error';result['error_type']=type(exc).__name__
  if isinstance(exc,httpx.HTTPStatusError):result['http_status']=exc.response.status_code
 finally:
  if own and client:client.close()
  with s.db() as c:
   if result['state']!='complete':put(c,'pending',window)
   put(c,'last',result)
   if get(c,'lease',{}).get('token')==token:put(c,'lease',{})
   c.execute('DELETE FROM options_activity_events WHERE at<?',(now-30*86400,))
 return result

@router.get('/api/admin/options-activity')
def overview(request:Request,response:Response):
 staff(request);s=core();now=time.time()
 with s.db() as c:
  migrate(c)
  rows=c.execute('SELECT payload FROM options_activity_events WHERE at>? ORDER BY at DESC LIMIT 200',(now-7*86400,)).fetchall()
  last=get(c,'last',{});through=get(c,'through');pending=get(c,'pending');u=c.execute('SELECT n FROM options_activity_usage WHERE day=?',(uw.quota_day(now),)).fetchone()
 response.headers['Cache-Control']='private, no-store'
 return {'events':[json.loads(r[0]) for r in rows],'worker':last,'through':through,'pending':bool(pending),'session_open':uw.session_open(now),'universe':len(s.CATALOG),'requests_today':u[0] if u else 0,'daily_cap':500}

@router.get('/api/cron/options-activity')
def cron(request:Request):
 secret=os.getenv('CRON_SECRET','')
 if not secret or not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+secret):raise HTTPException(401,'Unauthorized')
 return run()

@router.post('/api/admin/options-activity/sample')
def sample(request:Request):
 staff(request)
 if os.getenv('VERCEL_ENV')!='production':raise HTTPException(409,'Sample only available in production')
 if not all(uw.configured().values()):raise HTTPException(409,'UW is not configured')
 s=core();now=time.time();day=uw.quota_day(now)
 with s.db() as c:
  migrate(c);c.execute('BEGIN IMMEDIATE')
  if get(c,'sample_day')==day:raise HTTPException(409,'Sample already checked this quota day')
  if max(get(c,'cooldown',0),uw.get(c,'cooldown',0))>now:raise HTTPException(409,'Provider cooldown is active')
  put(c,'sample_day',day)
 with s.db() as c:
  if not reserve(c,now):raise HTTPException(429,'Request budget paused')
 try:
  with httpx.Client(timeout=15) as client:
   r=client.get('https://api.unusualwhales.com/api/option-trades/flow-alerts',headers={'Authorization':'Bearer '+os.environ['UW_API_KEY']},params={'min_premium':100000,'limit':200})
  r.raise_for_status();rows=r.json().get('data')
  if not isinstance(rows,list) or len(rows)>200:raise ValueError('response_shape')
  events=[v for row in rows if isinstance(row,dict) and (v:=event(row,set(s.CATALOG),now))]
  with s.db() as c:
   for v in events:c.execute('INSERT INTO options_activity_events VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET premium=excluded.premium,payload=excluded.payload',(v['id'],v['ticker'],v['at'],v['premium'],json.dumps(v)))
   put(c,'sample',{'at':now,'state':'latest_provider_sample','matched':len(events)})
  return {'matched':len(events)}
 except (httpx.HTTPError,ValueError) as exc:
  raise HTTPException(502,'Provider sample failed: '+(str(exc.response.status_code) if isinstance(exc,httpx.HTTPStatusError) else type(exc).__name__)) from None
