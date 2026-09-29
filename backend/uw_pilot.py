"""Owner-only UW observation pilot. Disabled until credentials and permission exist.

Raw net premium is NOT the proposed DTE/single-leg-filtered options indicator.
No provider data is returned through member or customer API routes.
"""
import os,time,json,secrets,hmac,ssl,math,statistics
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import httpx
from fastapi import APIRouter,Request,HTTPException,Response
from .community import core,staff

router=APIRouter()
NY=ZoneInfo('America/New_York')
PILOT=('NVDA','AMD','MU','AVGO','MSFT','META','AMZN','GOOGL','TSM','RMBS',
       'ORCL','NTAP','MRVL','ANET','DELL','STX','SMCI','INTC','SNDK','WDC')
KINDS={'candles':'ohlc/10m','net_premium':'net-prem-ticks'}
FOCUS=('NVDA','AMD','MU')
HISTORY_FOCUS=FOCUS+('AVGO','MSFT','META','AMZN','GOOGL','TSM','ANET','MRVL','ORCL','RMBS')

def fast_tickers(c,catalog,now):
    """Reuse saved X measurements; never buy extra X requests for prioritization."""
    cached=get(c,'fast_universe',{})
    if cached.get('slot')==int(now//600):
        return [t for t in cached.get('tickers',[]) if t in catalog][:20]
    try:
        from .live_collection import intraday_rows
        ranked=[r['ticker'] for r in intraday_rows(now) if r.get('state')=='measured' and r['ticker'] in catalog]
        source='intraday'
    except Exception:
        ranked=cached.get('tickers',[]);source='last_available'
    names=list(dict.fromkeys(t for t in ranked+list(PILOT) if t in catalog))[:20]
    put(c,'fast_universe',{'slot':int(now//600),'tickers':names,'source':source})
    return names

def collection_due(tickers,fast,latest,now):
    """Interleave active names, the wider universe and daily history fairly.

    Unfinished jobs remain due next tick. No fixed pilot membership excludes a
    covered stock, and fast-lane demand cannot starve background history.
    """
    lanes=[[],[],[]];fast=set(fast)
    midnight=datetime.fromtimestamp(now,NY).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
    for ticker in tickers:
        cadence=600 if ticker in fast else 3600
        for kind in (*KINDS,'filtered_options','history'):
            at=latest.get((ticker,kind),0)
            cutoff=midnight if kind=='history' else int(now//cadence)*cadence
            if at>=cutoff:continue
            lanes[2 if kind=='history' else 0 if ticker in fast else 1].append((ticker,kind))
    for lane in lanes:lane.sort(key=lambda job:(latest.get(job,0),list((*KINDS,'filtered_options','history')).index(job[1]),job[0]))
    result=[]
    while any(lanes):
        for lane,count in zip(lanes,(2,5,1)):
            result.extend(lane[:count]);del lane[:count]
    return result

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

def history_values(payload,now):
    rows=payload.get('data') if isinstance(payload,dict) else None
    if not isinstance(rows,list) or len(rows)>2500:raise ValueError('Unexpected history shape')
    values={};today=datetime.fromtimestamp(now,NY).date()
    for r in rows:
        if not isinstance(r,dict):continue
        at=timestamp(r.get('end_time'));start=timestamp(r.get('start_time'))
        if at is None or start is None or abs(at-start-600)>2 or not now-90*86400<at<now:continue
        dt=datetime.fromtimestamp(at,NY)
        if dt.date()>=today or not 570<dt.hour*60+dt.minute<=960:continue
        try:v=float(r['volume'])
        except (KeyError,TypeError,ValueError):continue
        if math.isfinite(v) and v>=0:
            values[at]={'at':at,'volume':v}
            try:
                close=float(r['close'])
                if math.isfinite(close) and close>0:values[at]['close']=close
            except (KeyError,TypeError,ValueError):pass
    return [values[t] for t in sorted(values)]

def filtered_trades(payload,ticker,now):
    rows=payload.get('data') if isinstance(payload,dict) else None
    if not isinstance(rows,list) or len(rows)>12000:raise ValueError('Unexpected options shape')
    accepted={};excluded=0
    for r in rows:
        if not isinstance(r,dict):excluded+=1;continue
        at=timestamp(r.get('executed_at'))
        try:
            expiry=datetime.fromisoformat(str(r['expiry']).replace('Z','+00:00')).date()
            dte=(expiry-datetime.fromtimestamp(at,NY).date()).days
            premium=float(r['premium'])
        except (KeyError,ValueError,TypeError,OverflowError):excluded+=1;continue
        tags=r.get('tags') or [];side='ask' if 'ask_side' in tags and 'bid_side' not in tags else 'bid' if 'bid_side' in tags and 'ask_side' not in tags else None
        # Endpoint enforces single-leg; reject OPRA multi-leg codes and unknown side.
        code=r.get('upstream_condition_detail')
        single=code in ('auto','isoi','slan','slai','slci','slcn','slft')
        typ=r.get('option_type');ident=r.get('id')
        if not (ident and r.get('underlying_symbol')==ticker and r.get('canceled') is False and
                not r.get('is_agg') and single and 7<=dte<=60 and now-3600<at<=now and
                side and typ in ('call','put') and math.isfinite(premium) and premium>0):
            excluded+=1;continue
        direction='bull' if (typ=='call' and side=='ask') or (typ=='put' and side=='bid') else 'bear'
        accepted[ident]={'at':at,'id':ident,'premium':premium,'direction':direction,'dte':dte}
    return {'at':now,'received':len(rows),'accepted':len(accepted),'excluded':excluded,
            'partial':payload.get('_partial',len(rows)>=500),'bull':sum(v['premium'] for v in accepted.values() if v['direction']=='bull'),
            'bear':sum(v['premium'] for v in accepted.values() if v['direction']=='bear'),
            'oldest':min((v['at'] for v in accepted.values()),default=None),
            'newest':max((v['at'] for v in accepted.values()),default=None)}

def volume_baseline(candles,history):
    tail=candles[-3:]
    result={'sessions':0,'required':20,'relative_volume':None,'median_shares':None,'persistence':None}
    if len(tail)!=3 or any(abs(b['at']-a['at']-600)>2 for a,b in zip(tail,tail[1:])):return result
    target=datetime.fromtimestamp(tail[-1]['at'],NY).date()
    slots=[datetime.fromtimestamp(r['at'],NY).strftime('%H:%M') for r in tail]
    days={}
    for r in history:
        dt=datetime.fromtimestamp(r['at'],NY)
        if dt.date()<target:days.setdefault(dt.date(),{})[dt.strftime('%H:%M')]=r['volume']
    # Require all of the most recent 20 observed sessions. Do not substitute older
    # sessions to hide missing same-time observations in more recent sessions.
    candidates=sorted(days,reverse=True)[:20]
    complete=[days[d] for d in candidates if all(slot in days[d] for slot in slots)]
    result['sessions']=len(complete)
    if len(complete)<20:return result
    median=statistics.median(sum(d[slot] for slot in slots) for d in complete)
    result['median_shares']=median
    if median<=0:return result
    result['relative_volume']=round(sum(r['volume'] for r in tail)/median,3)
    result['persistence']=sum(r['volume']>statistics.median(d[slot] for d in complete) for r,slot in zip(tail,slots))
    return result

def run(client=None,now=None):
    now=now or time.time();s=core();flags=configured()
    if not all(flags.values()):return {'state':'setup_required',**flags}
    if not session_open(now):return {'state':'outside_session'}
    # All active covered stocks are eligible, including future universe additions.
    tickers=sorted(s.CATALOG)
    token=secrets.token_hex(12)
    with s.db() as c:
        migrate(c)
        c.execute('BEGIN IMMEDIATE')
        if get(c,'cooldown',0)>now:return {'state':'provider_paused'}
        if get(c,'lease',{}).get('until',0)>now:return {'state':'already_running'}
        put(c,'lease',{'token':token,'until':now+240})
        latest={(r['ticker'],r['kind']):r['fetched_at'] for r in c.execute('SELECT ticker,kind,fetched_at FROM uw_pilot_latest')}
        fast=fast_tickers(c,s.CATALOG,now)
        put(c,'collection_scope',{'eligible_count':len(tickers),'fast_tickers':fast,'fast_seconds':600,'background_seconds':3600})
    due=collection_due(tickers,fast,latest,now)
    own=client is None
    started=time.monotonic();done=0;failures=0;state='complete';updated=set()
    try:
        if own:
            context=ssl.create_default_context();context.load_default_certs()
            client=httpx.Client(timeout=8,verify=context,headers={'Authorization':'Bearer '+os.environ['UW_API_KEY'],'Accept':'application/json'})
        for ticker,kind in due:
            if time.monotonic()-started>90:state='continued_next_tick';break
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
                url='https://api.unusualwhales.com/api/stock/'+ticker+'/'+KINDS.get(kind,'ohlc/10m')
                if kind=='history':params={'end_date':(datetime.fromtimestamp(now,NY).date()-timedelta(days=1)).isoformat(),'timeframe':'2M','limit':2500}
                if kind=='filtered_options':
                    url='https://api.unusualwhales.com/api/option-trades'
                    params={'ticker_symbol':ticker,'min_dte':7,'max_dte':60,'is_multi_leg':'false','canceled':'false','include_agg_trades':'false','newer_than':int(max(now-3600,datetime.fromtimestamp(now,NY).replace(hour=9,minute=30,second=0,microsecond=0).timestamp())),'older_than':int(now),'limit':500}
                response=client.get(url,params=params)
                http_status=response.status_code
                with s.db() as c:
                    for header,column in [('x-uw-daily-req-count','provider_count'),('x-uw-token-req-limit','provider_limit')]:
                        raw=response.headers.get(header,'')
                        if raw.isdigit():c.execute('UPDATE uw_pilot_usage SET '+column+'=? WHERE day=?',(int(raw),day))
                response.raise_for_status()
                if len(response.content)>2_000_000:raise ValueError('Response too large')
                body=response.json()
                if kind=='filtered_options':
                    gathered=[];seen=set();partial=False;cursor=now+1
                    for page in range(24):
                        batch=body.get('data') if isinstance(body,dict) else None
                        if not isinstance(batch,list) or len(batch)>500:raise ValueError('Unexpected options page')
                        fresh=[r for r in batch if isinstance(r,dict) and r.get('id') and r['id'] not in seen]
                        gathered.extend(fresh);seen.update(r['id'] for r in fresh)
                        if len(batch)<500:break
                        oldest=min((timestamp(r.get('executed_at')) or now for r in batch if isinstance(r,dict)),default=now)
                        if not fresh or oldest>=cursor or page==23 or time.monotonic()-started>80:
                            partial=True;break
                        # Overlap the boundary millisecond; dedup IDs so equal-time
                        # trades are not silently dropped by an exclusive cursor.
                        cursor=oldest
                        params['older_than']=datetime.fromtimestamp(oldest+.001,NY).isoformat()
                        with s.db() as c:
                            c.execute('BEGIN IMMEDIATE')
                            usage=c.execute('SELECT * FROM uw_pilot_usage WHERE day=?',(day,)).fetchone()
                            if max(usage['reserved'],usage['provider_count'])>=min(32000,usage['provider_limit']):
                                partial=True;state='daily_limit';break
                            c.execute('UPDATE uw_pilot_usage SET reserved=? WHERE day=?',(max(usage['reserved'],usage['provider_count'])+1,day))
                        time.sleep(1.05)
                        response=client.get(url,params=params);http_status=response.status_code
                        with s.db() as c:
                            for header,column in [('x-uw-daily-req-count','provider_count'),('x-uw-token-req-limit','provider_limit')]:
                                raw=response.headers.get(header,'')
                                if raw.isdigit():c.execute('UPDATE uw_pilot_usage SET '+column+'=? WHERE day=?',(int(raw),day))
                        response.raise_for_status()
                        if len(response.content)>2_000_000:raise ValueError('Options page too large')
                        body=response.json()
                    body={'data':gathered,'_partial':partial}
                values=history_values(body,now) if kind=='history' else [filtered_trades(body,ticker,now)] if kind=='filtered_options' else normalize(kind,body,now)
            except (httpx.HTTPError,ValueError,TypeError):
                error='http_'+str(http_status) if http_status and http_status>=400 else 'response_or_connection_error'
            data_at=values[-1]['at'] if values else None
            status='error' if error else 'empty' if not values else 'partial' if kind=='filtered_options' and values[0]['partial'] else 'ready' if kind=='history' else 'stale' if now-data_at>1200 else 'ready'
            with s.db() as c:
                if kind=='history' and values and not error:put(c,'history_price_v1_'+ticker,True)
                c.execute('INSERT INTO uw_pilot_latest(ticker,kind,fetched_at,data_at,state,error,payload) VALUES(?,?,?,?,?,?,?) ON CONFLICT(ticker,kind) DO UPDATE SET fetched_at=excluded.fetched_at,data_at=excluded.data_at,state=excluded.state,error=excluded.error,payload=excluded.payload',
                          (ticker,kind,now,data_at,status,error,json.dumps(values)))
                # Save each source interval once, not a copy of the whole day on
                # every poll. fetched_at preserves when we first knew this value.
                if values and kind in KINDS:c.executemany('INSERT OR IGNORE INTO uw_pilot_history VALUES(?,?,?,?,?,?)',
                    [(ticker,kind,int(v['at']),now,v['at'],json.dumps(v)) for v in values])
                if http_status in (401,403,429):
                    put(c,'cooldown',now+(3600 if http_status!=429 else 900));state='provider_paused'
            if error:failures+=1
            else:
                done+=1
                if values and kind in ('candles','history','filtered_options'):updated.add(ticker)
            if state=='provider_paused':break
            time.sleep(1.05) # At most about 57 calls/min, below the documented client default.
        with s.db() as c:
            c.execute('DELETE FROM uw_pilot_history WHERE fetched_at<?',(now-45*86400,))
            put(c,'last_run',{'at':now,'state':state,'completed':done,'failed':failures})
        if updated:
            # Independent evaluation failure must never stop collection or other workers.
            try:
                from .signal_lab import record
                with s.db() as c:
                    samples={}
                    selected=sorted(updated)
                    # Compact candles preserve sector peers across the universe;
                    # large historical/flow payloads are read only for scored names.
                    sql='SELECT ticker,kind,payload FROM uw_pilot_latest WHERE ticker IN ('+','.join('?' for _ in selected)+') OR kind=\'candles\''
                    for r in c.execute(sql,selected):
                        if r['ticker'] in s.CATALOG:samples.setdefault(r['ticker'],{})[r['kind']]=json.loads(r['payload'])
                    # Timestamp the decision after ingestion, not at worker start.
                    # X/research that arrived during collection was not known earlier.
                    record(c,samples,s.CATALOG,sorted(updated),time.time())
                    put(c,'scoring',{'at':now,'state':'ready'})
            except Exception as exc:
                with s.db() as c:put(c,'scoring',{'at':now,'state':'evaluation_error','error_type':type(exc).__name__})
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

def stock_measurements(ticker,datasets,now):
    """Raw observations only. Require contiguous regular-session windows."""
    def rows(kind):
        values=datasets.get(kind,[])
        return sorted([v for v in values if v['at']<=now and
            datetime.fromtimestamp(v['at'],NY).date()==datetime.fromtimestamp(now,NY).date() and
            570 < datetime.fromtimestamp(v['at'],NY).hour*60+datetime.fromtimestamp(v['at'],NY).minute <=960],key=lambda v:v['at'])
    candles=rows('candles');flow=rows('net_premium')
    def continuous(values,count,seconds):
        tail=values[-count:]
        return len(tail)==count and all(abs(b['at']-a['at']-seconds)<2 for a,b in zip(tail,tail[1:]))
    price_ready=continuous(candles,7,600)
    volume_ready=continuous(candles,3,600)
    flow_ready=continuous(flow,60,60)
    return {'ticker':ticker,'candles':candles,'flow':flow[-60:],
        'price_at':candles[-1]['at'] if candles else None,'flow_at':flow[-1]['at'] if flow else None,
        'return_60m':round((candles[-1]['close']/candles[-7]['close']-1)*100,3) if price_ready else None,
        'volume_30m':sum(v['volume'] for v in candles[-3:]) if volume_ready else None,
        'net_calls_60m':sum(v['net_call_premium'] for v in flow[-60:]) if flow_ready else None,
        'net_puts_60m':sum(v['net_put_premium'] for v in flow[-60:]) if flow_ready else None,
        'price_window_complete':price_ready,'volume_window_complete':volume_ready,'flow_window_complete':flow_ready,
        'price_fresh':bool(candles and now-candles[-1]['at']<=1200),
        'flow_fresh':bool(flow and now-flow[-1]['at']<=1200),
        'volume_baseline':volume_baseline(candles,datasets.get('history',[])),
        'filtered_options':(datasets.get('filtered_options') or [None])[-1]}

@router.get('/api/admin/uw-pilot')
def overview(request:Request):
    staff(request,owner=True);s=core();now=time.time()
    with s.db() as c:
        migrate(c)
        rows=[];samples={}
        for record in c.execute('SELECT * FROM uw_pilot_latest WHERE ticker IN ('+','.join('?' for _ in PILOT)+') ORDER BY ticker,kind',PILOT):
            item=dict(record);data=json.loads(item.pop('payload') or '[]')
            if item['ticker'] not in PILOT:continue
            if item['ticker'] in ('NVDA','AMD','MU'):samples.setdefault(item['ticker'],{})[item['kind']]=data
            item['observations']=len(data);item['latest']=data[-1] if data else None
            if item['kind']!='history' and item['state']=='ready' and now-(item['data_at'] or 0)>1200:item['state']='stale'
            rows.append(item)
        usage=c.execute('SELECT * FROM uw_pilot_usage WHERE day=?',(quota_day(now),)).fetchone()
        from .signal_lab import saved
        return {**configured(),'server_at':now,'session_open':session_open(now),'lab':saved(c),'scoring':get(c,'scoring'),'stocks':[stock_measurements(t,samples.get(t,{}),now) for t in ('NVDA','AMD','MU') if t in s.CATALOG],'rows':rows,'usage':dict(usage) if usage else None,'last_run':get(c,'last_run'),
                'tickers':sorted(s.CATALOG),'collection_scope':get(c,'collection_scope',{'eligible_count':len(s.CATALOG),'fast_seconds':600,'background_seconds':3600}),'local_daily_cap':32000,'scores_ready':False}


def home_preview_tickers(c,panels,now):
    from .pro_access import launched
    fallback=list(FOCUS)
    if not launched(now):return fallback
    known={p['ticker']:p for p in panels if p['ticker'] in core().CATALOG}
    previous=get(c,'home_preview_selection',[])
    previous=[t for t in previous if t in known]
    # Preserve the last selected session overnight; no paid fetch on page views.
    if len(previous)==3 and not session_open(now):return previous
    def eligible(p):
        axes=p.get('axes',[])
        return len(axes)==5 and axes[3].get('score') is not None and sum(a.get('score') is not None for a in axes)>=3
    candidates=sorted((p for p in known.values() if eligible(p)),key=lambda p:(-p['axes'][3]['score'],p['ticker']))
    if len(candidates)<3:return previous if len(previous)==3 else fallback
    chosen=[p['ticker'] for p in candidates[:3]]
    if chosen!=previous:put(c,'home_preview_selection',chosen)
    return chosen


@router.get('/api/signal-lab')
def public_signals(response:Response,request:Request,home:bool=False):
    """Owner approved public derived scores on 2026-09-25; never return provider records."""
    from .signal_lab import saved
    s=core();now=time.time()
    with s.db() as c:
        panels=saved(c)['stocks']
        selected=home_preview_tickers(c,panels,now) if home else list(FOCUS)
    rows=[]
    for panel in panels:
        if panel['ticker'] not in selected:continue
        axes=[{**{k:a.get(k) for k in ('name','score','strength','direction','state')},'as_of':a.get('details',{}).get('as_of')} for a in panel['axes']]
        rows.append(dict(ticker=panel['ticker'],name=s.CATALOG.get(panel['ticker'],(panel['ticker'],))[0],observed=panel['observed'],axes=axes,
            stale=now-panel['observed']>1200,activity=axes[3]['score']))
    rows.sort(key=lambda r:selected.index(r['ticker']) if home else (-(r['activity'] if r['activity'] is not None else -1),r['ticker']))
    u=s.account(request,False)
    full_preview=bool(u and (u['plan'] in ('premium','pro') or u['role'] in ('owner','admin')))
    rows=rows[:3 if full_preview else 1]
    response.headers['Cache-Control']='private, no-store'
    return dict(stocks=rows,scope='top-tile preview',server_at=now)


@router.get('/api/admin/signal-lab-overview')
def admin_signal_overview(request:Request,response:Response):
    staff(request,owner=True)
    return signal_overview_data(response)

def signal_overview_data(response):
    from .signal_lab import saved
    s=core();now=time.time()
    with s.db() as c:panels=saved(c)['stocks']
    rows=[]
    for panel in panels:
        if panel['ticker'] not in s.CATALOG:continue
        axes=[{k:a.get(k) for k in ('name','score','strength','direction','state','reason','as_of','stale')} for a in panel['axes']]
        rows.append(dict(ticker=panel['ticker'],name=s.CATALOG[panel['ticker']][0],candidate=panel.get('candidate'),axes=axes,observed=panel['observed'],stale=now-panel['observed']>1200))
    response.headers['Cache-Control']='private, no-store'
    return dict(stocks=rows,server_at=now)

@router.get('/api/admin/signal-lab-detail/{ticker}')
def admin_signal_detail(ticker:str,request:Request,response:Response):
    staff(request,owner=True)
    return signal_detail_data(ticker,response)

def signal_detail_data(ticker,response):
    s=core();ticker=ticker.upper()
    if ticker not in s.CATALOG:raise HTTPException(404,'Stock is not in the covered universe')
    from .signal_history import detail
    with s.db() as c:result=detail(c,ticker,time.time())
    if result is None:raise HTTPException(404,'No saved Signal Lab observations for this stock')
    response.headers['Cache-Control']='private, max-age=60'
    return {**result,'name':s.CATALOG[ticker][0]}

@router.get('/api/signal-lab/overview')
def member_signal_overview(request:Request,response:Response):
 from .pro_access import require_pro
 require_pro(request)
 return signal_overview_data(response)

@router.get('/api/signal-lab/detail/{ticker}')
def member_signal_detail(ticker:str,request:Request,response:Response):
 from .pro_access import require_pro
 require_pro(request)
 return signal_detail_data(ticker,response)
