"""Bounded, resumable daily X jobs. Shared by owner controls and cron runner."""
import hashlib, hmac, json, os, secrets, time
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, Request, HTTPException
from .community import core, staff, data_settings
from .collect_economy import iso, paid_request

router=APIRouter()

def plan_day():
    s=core();now=time.time();end=int(now//86400)*86400;day=iso(end)[:10]
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        settings=data_settings(c)
        if not settings['enabled']: raise RuntimeError('Collection is paused. Enable it in Administration after setting your X spending limit.')
        if not os.getenv('X_BEARER_TOKEN'): raise RuntimeError('X_BEARER_TOKEN is not configured. No paid call was sent.')
        if c.execute('SELECT 1 FROM meta WHERE key=?',('day_planned:'+day,)).fetchone(): return day,end,settings
        c.executemany('INSERT OR IGNORE INTO collection_jobs(day,kind,ticker,updated_at) VALUES(?,?,?,?)',[(day,'counts',ticker,now) for ticker in s.CATALOG])
        c.execute('INSERT INTO meta VALUES(?,?)',('day_planned:'+day,str(end)))
    return day,end,settings

def claim_job(day):
    s=core();now=time.time()
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute("SELECT * FROM collection_jobs WHERE day=? AND attempts<3 AND (status='pending' OR (status='running' AND lease_until<?) OR (status='error' AND next_attempt>0 AND next_attempt<=?)) ORDER BY CASE WHEN kind='counts' THEN 0 ELSE 1 END,id LIMIT 1",(day,now,now)).fetchone()
        if not row:return None
        c.execute("UPDATE collection_jobs SET status='running',attempts=attempts+1,lease_until=?,updated_at=? WHERE id=?",(now+300,now,row['id']))
        return dict(row)

def add_samples(day,end,settings):
    s=core()
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT 1 FROM collection_jobs WHERE day=? AND kind='counts' AND status!='done' LIMIT 1",(day,)).fetchone():return
        c.execute("INSERT INTO meta VALUES('completed_snapshot',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(end),))
        key='samples_planned:'+day
        if c.execute('SELECT 1 FROM meta WHERE key=?',(key,)).fetchone():return
        if settings['intraday_enabled']:
            c.execute('INSERT INTO meta VALUES(?,?)',(key,str(end)))
            return
        # Legacy daily-only mode; intraday sampling shares its own hourly queue.
        voices=[r[0] for r in c.execute("SELECT DISTINCT h.handle FROM handles h JOIN accounts a ON h.user_id=a.id WHERE a.demo=0 AND a.status='active' AND (a.plan='premium' OR a.role IN ('admin','owner')) ORDER BY h.handle")]
        voices=sorted(voices,key=lambda h:hashlib.sha256((day+h).encode()).hexdigest())[:min(2,settings['daily_post_limit']//10)]
        maximum=max(0,settings['daily_post_limit']//10-len(voices))
        rows=c.execute('SELECT ticker,SUM(n) n FROM x_counts WHERE start>=? AND end<=? GROUP BY ticker ORDER BY n DESC,ticker LIMIT ?',(end-86400,end,maximum)).fetchall()
        for r in rows:
            if r['n']>0:c.execute('INSERT OR IGNORE INTO collection_jobs(day,kind,ticker,updated_at) VALUES(?,?,?,?)',(day,'sample',r['ticker'],time.time()))
        for handle in voices:c.execute('INSERT OR IGNORE INTO collection_jobs(day,kind,ticker,updated_at) VALUES(?,?,?,?)',(day,'voice',handle,time.time()))
        if settings['daily_profile_limit']:
            c.execute('INSERT OR IGNORE INTO collection_jobs(day,kind,ticker,updated_at) VALUES(?,?,?,?)',(day,'profiles','profiles',time.time()))
        c.execute('INSERT INTO meta VALUES(?,?)',(key,str(end)))

def run_batch(max_jobs=10,client=None):
    day,end,settings=plan_day();s=core();owned=client is None;client=client or httpx.Client(timeout=12)
    token=os.environ['X_BEARER_TOKEN'];completed=0;errors=[];deadline=time.monotonic()+100
    try:
        add_samples(day,end,settings)
        while completed<max_jobs and time.monotonic()<deadline:
            job=claim_job(day)
            if not job:break
            try:
                ticker=job['ticker'];query=f'${ticker} lang:en -is:retweet' if job['kind']!='voice' else f'from:{ticker} has:cashtags lang:en -is:retweet'
                if job['kind']=='counts':
                    with s.db() as c:
                        # Intraday jobs may already contain today's hours. Daily jobs
                        # must resume inside their own midnight snapshot boundary.
                        last=c.execute('SELECT MAX(end) FROM x_counts WHERE ticker=? AND end<=?',(ticker,end)).fetchone()[0]
                    start=max(end-6*86400,(last-3600) if last else end-6*86400)
                    result=paid_request(client,'tweets/counts/recent',{'query':query,'start_time':iso(start),'end_time':iso(end),'granularity':'hour'},'counts',.005,token)
                    if result.get('meta',{}).get('next_token'):raise RuntimeError('Unexpected counts pagination; review this job before retrying.')
                    buckets=result.get('data',[])
                    expected=int((end-start)//3600)
                    parsed=[(datetime.fromisoformat(b['start'].replace('Z','+00:00')).timestamp(),datetime.fromisoformat(b['end'].replace('Z','+00:00')).timestamp(),int(b['tweet_count'])) for b in buckets]
                    if len(parsed)!=expected or sorted(a for a,b,n in parsed)!=list(range(int(start),end,3600)) or any(b-a!=3600 or n<0 for a,b,n in parsed):raise RuntimeError('Incomplete hourly counts; snapshot withheld.')
                    with s.db() as c:
                        c.executemany('INSERT INTO x_counts VALUES(?,?,?,?,?,?) ON CONFLICT(ticker,start) DO UPDATE SET n=excluded.n,end=excluded.end,query=excluded.query,fetched_at=excluded.fetched_at',[(ticker,a,b,n,query,time.time()) for a,b,n in parsed])
                elif job['kind']=='profiles':
                    with s.db() as c:
                        ids=[r[0] for r in c.execute('SELECT DISTINCT i.author_id FROM post_identity i JOIN posts p ON p.source=i.source AND p.id=i.post_id LEFT JOIN post_authors a ON a.id=i.author_id WHERE p.ts>? AND (a.id IS NULL OR a.fetched_at<?) ORDER BY i.author_id LIMIT ?',(end-86400,end-30*86400,settings['daily_profile_limit']))]
                    if ids:
                        result=paid_request(client,'users',{'ids':','.join(ids),'user.fields':'created_at,public_metrics,username'},'profiles',len(ids)*.01,token)
                        with s.db() as c:
                            for a in result.get('data',[]):
                                metrics=a.get('public_metrics',{});created=datetime.fromisoformat(a['created_at'].replace('Z','+00:00')).timestamp() if a.get('created_at') else None
                                c.execute('INSERT INTO post_authors VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET handle=excluded.handle,followers=excluded.followers,following=excluded.following,posts=excluded.posts,fetched_at=excluded.fetched_at',(a['id'],a['username'].lower(),created,metrics.get('followers_count',0),metrics.get('following_count',0),metrics.get('tweet_count',0),time.time()))
                                c.execute("UPDATE posts SET author=? WHERE source='x' AND id IN (SELECT post_id FROM post_identity WHERE author_id=?)",(a['username'].lower(),a['id']))
                else:
                    result=paid_request(client,'tweets/search/recent',{'query':query,'start_time':iso(end-86400),'end_time':iso(end),'max_results':10,'tweet.fields':'created_at,author_id,public_metrics'},'sample',.05,token)
                    items=[{'id':p['id'],'author':ticker if job['kind']=='voice' else 'id'+p['author_id'],'author_id':p['author_id'],'text':p['text'],'created_at':p['created_at'],'likes':p.get('public_metrics',{}).get('like_count',0)} for p in result.get('data',[])]
                    s.ingest(items)
                with s.db() as c:c.execute("UPDATE collection_jobs SET status='done',lease_until=0,error=NULL,updated_at=? WHERE id=?",(time.time(),job['id']))
                completed+=1
                add_samples(day,end,settings)
            except Exception as exc:
                # Never place provider response bodies or credentials into audit/UI errors.
                message=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__+': collection failed; check server logs.'
                transient=isinstance(exc,(httpx.TimeoutException,httpx.NetworkError)) or 'HTTP 429' in message or any('HTTP '+str(n) in message for n in range(500,600))
                with s.db() as c:c.execute("UPDATE collection_jobs SET status='error',lease_until=0,error=?,next_attempt=?,updated_at=? WHERE id=?",(message[:300],time.time()+900 if transient else 0,time.time(),job['id']))
                errors.append(message);break
        with s.db() as c:
            pending=c.execute("SELECT COUNT(*) FROM collection_jobs WHERE day=? AND status!='done'",(day,)).fetchone()[0]
            c.execute("INSERT INTO meta VALUES('last_sync',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps({'at':time.time(),'mode':'daily batched counts + screened samples','window_end':end,'pending':bool(pending)}),))
        return {'completed':completed,'errors':errors,'day':day}
    finally:
        if owned:client.close()

@router.get('/api/admin/collection')
def progress(request:Request):
    staff(request);s=core();day=datetime.now(timezone.utc).date().isoformat()
    with s.db() as c:
        counts=[dict(r) for r in c.execute('SELECT kind,status,COUNT(*) n FROM collection_jobs WHERE day=? GROUP BY kind,status',(day,))]
        errors=[dict(r) for r in c.execute("SELECT ticker,kind,error,attempts FROM collection_jobs WHERE day=? AND status='error' ORDER BY id LIMIT 20",(day,))]
    from .live_collection import status
    return {'day':day,'jobs':counts,'errors':errors,'configured':bool(os.getenv('X_BEARER_TOKEN')),**status()}

@router.post('/api/admin/collection/run')
def run_owner(request:Request):
    staff(request,owner=True)
    try:return run_batch()
    except RuntimeError as exc:raise HTTPException(409,str(exc))

@router.post('/api/admin/collection/retry')
def retry(request:Request):
    u=staff(request,owner=True);s=core();day=datetime.now(timezone.utc).date().isoformat()
    from .community import audit
    with s.db() as c:
        n=c.execute("UPDATE collection_jobs SET status='pending' WHERE day=? AND status='error' AND attempts<3",(day,)).rowcount
        audit(c,u,'collection_retry',detail=str(n))
    return {'retried':n}

@router.get('/api/cron/collect')
def cron(request:Request):
    expected=os.getenv('CRON_SECRET','')
    if not expected or not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+expected):raise HTTPException(401,'Unauthorized')
    from .live_collection import tick
    try:return tick(scheduled=True)
    except RuntimeError as exc:return {'paused':True,'reason':str(exc)}
