"""Owner-only UW observation pilot. Disabled until credentials and permission exist.

Raw net premium is NOT the proposed DTE/single-leg-filtered options indicator.
No provider data is returned through member or customer API routes.
"""
import os,time,json,secrets,hmac,ssl,math
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import httpx
from fastapi import APIRouter,Request,HTTPException
from .community import core,staff

router=APIRouter()
NY=ZoneInfo('America/New_York')
PILOT=('NVDA','AMD','MU','AVGO','MSFT','META','AMZN','GOOGL','TSLA','PLTR',
       'ORCL','ARM','MRVL','ANET','DELL','HPE','SMCI','INTC','CRWV','NBIS')
KINDS={'candles':'ohlc/10m','net_premium':'net-prem-ticks'}

def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS uw_pilot_latest(ticker TEXT,kind TEXT,fetched_at REAL,data_at REAL,state TEXT,error TEXT,payload TEXT,PRIMARY KEY(ticker,kind));
    CREATE TABLE IF NOT EXISTS uw_pilot_history(ticker TEXT,kind TEXT,slot INTEGER,fetched_at REAL,data_at REAL,payload TEXT,PRIMARY KEY(ticker,kind,slot));
    CREATE TABLE IF NOT EXISTS uw_pilot_usage(day TEXT PRIMARY KEY,reserved INTEGER DEFAULT 0,provider_count INTEGER DEFAULT 0,provider_limit INTEGER DEFAULT 40000);
    ''')

def get(c,key,default=None):
    row=c.execute('SELECT value FROM meta WHERE key=?',('uw_pilot_'+key,)).fetchone()
    return json.loads(row[0]) if row else default

def put(c,key,value):
    c.execute('INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)',('uw_pilot_'+key,json.dumps(value)))

def quota_day(now):
    return (datetime.fromtimestamp(now,NY)-timedelta(hours=20)).date().isoformat()

def session_open(now):
    local=datetime.fromtimestamp(now,NY)
    return local.weekday()<5 and 570<=local.hour*60+local.minute<960

def configured():
    return {'key_saved':bool(os.getenv('UW_API_KEY')),
            'evaluation_approved':os.getenv('UW_PRIVATE_EVALUATION_APPROVED','false').lower()=='true',
            'enabled':os.getenv('UW_PILOT_ENABLED','false').lower()=='true'}

def timestamp(value):
    try:return datetime.fromisoformat(str(value).replace('Z','+00:00')).timestamp()
    except (ValueError,TypeError):return None

def normalize(kind,payload,now):
    rows=payload.get('data') if isinstance(payload,dict) else None
    if isinstance(rows,dict):rows=rows.get('data')
    if not isinstance(rows,list):raise ValueError('Unexpected response shape')
    if len(rows)>2500:raise ValueError('Response exceeds pilot limit')
    result={}
    fields=['open','high','low','close','volume'] if kind=='candles' else ['net_call_premium','net_put_premium','call_volume','put_volume']
    for row in rows:
        if not isinstance(row,dict):continue
        at=timestamp(row.get('end_time') if kind=='candles' else row.get('tape_time'))
        # Only completed, recent observations; old fallback sessions are not fresh.
        if at is None or not now-86400<=at<=now:continue
        values={}
        for key in fields:
            try:value=float(row[key])
            except (KeyError,ValueError,TypeError):continue
            if math.isfinite(value):values[key]=value
        required=['close','volume'] if kind=='candles' else ['net_call_premium','net_put_premium']
        if not all(k in values for k in required):continue
        if kind=='candles' and (values['close']<=0 or values['volume']<0):continue
        result[at]={'at':at,**values}
    return [result[t] for t in sorted(result)][-400:]

def run(client=None,now=None):
    now=now or time.time();s=core();flags=configured()
    if not all(flags.values()):return {'state':'setup_required',**flags}
    if not session_open(now):return {'state':'outside_session'}
    # Basic pilot limited to twenty in-universe stocks. Expand only after validation.
    tickers=[t for t in PILOT if t in s.CATALOG]
    token=secrets.token_hex(12)
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        if get(c,'cooldown',0)>now:return {'state':'provider_paused'}
        if get(c,'lease',{}).get('until',0)>now:return {'state':'already_running'}
        put(c,'lease',{'token':token,'until':now+180})
        latest={(r['ticker'],r['kind']):r['fetched_at'] for r in c.execute('SELECT ticker,kind,fetched_at FROM uw_pilot_latest')}
    due=sorted([(t,k) for t in tickers for k in KINDS if latest.get((t,k),0)<=now-600],key=lambda x:latest.get(x,0))[:40]
    own=client is None
    started=time.monotonic();done=0;failures=0;state='complete'
    try:
        if own:
            context=ssl.create_default_context();context.load_default_certs()
            client=httpx.Client(timeout=8,verify=context,headers={'Authorization':'Bearer '+os.environ['UW_API_KEY'],'Accept':'application/json'})
        for ticker,kind in due:
            if time.monotonic()-started>60:state='continued_next_tick';break
            with s.db() as c:
                c.execute('BEGIN IMMEDIATE')
                day=quota_day(now)
                c.execute('INSERT OR IGNORE INTO uw_pilot_usage(day) VALUES(?)',(day,))
                usage=c.execute('SELECT * FROM uw_pilot_usage WHERE day=?',(day,)).fetchone()
                if max(usage['reserved'],usage['provider_count'])>=min(32000,usage['provider_limit']):state='daily_limit';break
                c.execute('UPDATE uw_pilot_usage SET reserved=? WHERE day=?',(max(usage['reserved'],usage['provider_count'])+1,day))
            values=[];error=None;http_status=None
            try:
                params={'date':datetime.fromtimestamp(now,NY).date().isoformat()}
                if kind=='candles':params['limit']=100
                response=client.get('https://api.unusualwhales.com/api/stock/'+ticker+'/'+KINDS[kind],params=params)
                http_status=response.status_code
                with s.db() as c:
                    for header,column in [('x-uw-daily-req-count','provider_count'),('x-uw-token-req-limit','provider_limit')]:
                        raw=response.headers.get(header,'')
                        if raw.isdigit():c.execute('UPDATE uw_pilot_usage SET '+column+'=? WHERE day=?',(int(raw),day))
                response.raise_for_status()
                if len(response.content)>2_000_000:raise ValueError('Response too large')
                values=normalize(kind,response.json(),now)
            except (httpx.HTTPError,ValueError,TypeError):
                error='http_'+str(http_status) if http_status and http_status>=400 else 'response_or_connection_error'
            data_at=values[-1]['at'] if values else None
            status='error' if error else 'empty' if not values else 'stale' if now-data_at>1200 else 'ready'
            with s.db() as c:
                c.execute('INSERT INTO uw_pilot_latest(ticker,kind,fetched_at,data_at,state,error,payload) VALUES(?,?,?,?,?,?,?) ON CONFLICT(ticker,kind) DO UPDATE SET fetched_at=excluded.fetched_at,data_at=excluded.data_at,state=excluded.state,error=excluded.error,payload=excluded.payload',
                          (ticker,kind,now,data_at,status,error,json.dumps(values)))
                # Save each source interval once, not a copy of the whole day on
                # every poll. fetched_at preserves when we first knew this value.
                if values:c.executemany('INSERT OR IGNORE INTO uw_pilot_history VALUES(?,?,?,?,?,?)',
                    [(ticker,kind,int(v['at']),now,v['at'],json.dumps(v)) for v in values])
                if http_status in (401,403,429):
                    put(c,'cooldown',now+(3600 if http_status!=429 else 900));state='provider_paused'
            if error:failures+=1
            else:done+=1
            if state=='provider_paused':break
            time.sleep(1.05) # At most about 57 calls/min, below the documented client default.
        with s.db() as c:
            c.execute('DELETE FROM uw_pilot_history WHERE fetched_at<?',(now-45*86400,))
            put(c,'last_run',{'at':now,'state':state,'completed':done,'failed':failures})
        return {'state':state,'completed':done,'failed':failures}
    finally:
        if own and client is not None:client.close()
        with s.db() as c:
            if get(c,'lease',{}).get('token')==token:put(c,'lease',{})

@router.get('/api/cron/uw-pilot')
def cron(request:Request):
    secret=os.getenv('CRON_SECRET','')
    if not secret or not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+secret):raise HTTPException(401,'Unauthorized')
    return run()

@router.get('/api/admin/uw-pilot')
def overview(request:Request):
    staff(request,owner=True);s=core();now=time.time()
    with s.db() as c:
        rows=[]
        for record in c.execute('SELECT * FROM uw_pilot_latest ORDER BY ticker,kind'):
            item=dict(record);data=json.loads(item.pop('payload') or '[]')
            item['observations']=len(data);item['latest']=data[-1] if data else None
            if item['state']=='ready' and now-(item['data_at'] or 0)>1200:item['state']='stale'
            rows.append(item)
        usage=c.execute('SELECT * FROM uw_pilot_usage WHERE day=?',(quota_day(now),)).fetchone()
        return {**configured(),'rows':rows,'usage':dict(usage) if usage else None,'last_run':get(c,'last_run'),
                'tickers':[t for t in PILOT if t in s.CATALOG],'local_daily_cap':32000,'scores_ready':False}
