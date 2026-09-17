"""Hourly, shared collection with bounded spend, deduplication and visible freshness."""
import json, os, time, secrets
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, Request, HTTPException
from .community import core, staff, data_settings
from .voices import shared_handles
from .collect_economy import paid_request, iso, CollectionDeferred

router=APIRouter()

def enqueue(c, slot, kind, ticker, end, query):
    c.execute('INSERT OR IGNORE INTO collection_jobs(day,kind,ticker,updated_at,window_end,query) VALUES(?,?,?,?,?,?)', (slot,kind,ticker,time.time(),end,query))

def plan_hour():
    s=core(); end=int(time.time()//3600)*3600;slot=iso(end)[:13]
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE');settings=data_settings(c)
        if not settings['enabled'] or not settings['intraday_enabled']: return
        if c.execute('SELECT 1 FROM meta WHERE key=?',('hour_planned:'+slot,)).fetchone(): return
        snapshot=c.execute("SELECT value FROM meta WHERE key='completed_snapshot'").fetchone()
        if not snapshot:return  # Do not turn partial first-backfill counts into a top-ten list.
        cutoff=float(snapshot[0])
        top=[r[0] for r in c.execute('SELECT ticker FROM x_counts WHERE start>=? AND end<=? GROUP BY ticker ORDER BY SUM(n) DESC,ticker LIMIT ?',(cutoff-86400,cutoff,settings['hourly_top'])) if r[0] in s.CATALOG]
        for ticker in top:enqueue(c,slot,'hour_counts',ticker,end,f'${ticker} lang:en -is:retweet')
        # A bounded discovery queue shares the existing daily on-demand count allowance.
        recent=[r[0] for r in c.execute("SELECT m.ticker FROM mentions m JOIN posts p ON p.source=m.source AND p.id=m.post_id JOIN admin_voices a ON a.handle=LOWER(p.author) WHERE p.source='x' AND p.ts>? GROUP BY m.ticker ORDER BY MAX(p.ts) DESC,m.ticker",(end-6*3600,)) if r[0] in s.CATALOG and r[0] not in top]
        used=c.execute("SELECT COUNT(*) FROM collection_jobs WHERE day LIKE ? AND kind='request_counts'",(slot[:10]+'%',)).fetchone()[0]
        for ticker in recent[:min(5,max(0,settings['on_demand_daily_limit']-used))]:
            if not c.execute("SELECT 1 FROM collection_jobs WHERE day=? AND ticker=? AND kind IN ('request_counts','hour_counts')",(slot,ticker)).fetchone():
                enqueue(c,slot,'request_counts',ticker,end,f'${ticker} lang:en -is:retweet')

        # One rotating popular-stock sample and shared account groups/hour.
        # All readers, retries and demand requests share the same daily allowance.
        if top:
            ticker=top[int(end//3600)%len(top)]
            enqueue(c,slot,'hour_sample',ticker,end,f'${ticker} lang:en -is:retweet')
        voices=shared_handles(c)
        if voices:
            checkpoints={r['handle']:max(end-86400,int(r['window_end'])) for r in c.execute('SELECT handle,window_end FROM voice_checkpoints')}
            eligible=[h for h in voices if checkpoints.get(h,end-86400)<end]
            admin={r[0] for r in c.execute('SELECT handle FROM admin_voices')}
            # Individual jobs stop a busy author crowding others out of a shared response.
            # Oldest coverage first within each priority class.
            for handle in sorted(eligible,key=lambda h:(h not in admin,checkpoints.get(h,0),h)):
                enqueue(c,slot,'hour_voice',handle,end,'from:'+handle+' -is:retweet -is:reply')
        c.execute('INSERT INTO meta VALUES(?,?)',('hour_planned:'+slot,str(end)))

def perform(job,client):
    s=core();end=int(job['window_end']);ticker=job['ticker'];kind=job['kind'];query=job['query'];token=os.environ['X_BEARER_TOKEN']
    if kind in ('hour_counts','request_counts'):
        start=end-86400
        result=paid_request(client,'tweets/counts/recent',{'query':query,'start_time':iso(start),'end_time':iso(end),'granularity':'hour'},'counts_live',.005,token)
        parsed=[(int(datetime.fromisoformat(b['start'].replace('Z','+00:00')).timestamp()),int(datetime.fromisoformat(b['end'].replace('Z','+00:00')).timestamp()),int(b['tweet_count'])) for b in result.get('data',[])]
        if result.get('meta',{}).get('next_token') or sorted(a for a,b,n in parsed)!=list(range(start,end,3600)) or any(b-a!=3600 or n<0 for a,b,n in parsed):raise RuntimeError('Incomplete hourly counts; previous values retained.')
        with s.db() as c:c.executemany('INSERT INTO x_counts VALUES(?,?,?,?,?,?) ON CONFLICT(ticker,start) DO UPDATE SET n=excluded.n,end=excluded.end,query=excluded.query,fetched_at=excluded.fetched_at',[(ticker,a,b,n,query,time.time()) for a,b,n in parsed])
    else:
        # Resolve tracked handles as a bounded shared lookup, then match every
        # returned post by stable author ID (even without a cashtag).
        with s.db() as c:
            author_map={r['id']:r['handle'] for r in c.execute('SELECT id,handle FROM post_authors')}
        if kind=='hour_voice':
            handles=ticker.split(',')
            with s.db() as c:
                checkpoints={r['handle']:int(r['window_end']) for r in c.execute('SELECT handle,window_end FROM voice_checkpoints')}
            if all(checkpoints.get(h,0)>=end for h in handles):return {'data':[]}
            with s.db() as c:
                cached=[dict(r) for r in c.execute('SELECT id,handle,fetched_at FROM post_authors')]
            author_map={r['id']:r['handle'] for r in cached}
            known={r['handle'] for r in cached if r['fetched_at']>time.time()-30*86400}
            missing=[h for h in handles if h not in known]
            if missing:
                result=paid_request(client,'users/by',{'usernames':','.join(missing)},'profiles_tracked',len(missing)*.01,token)
                with s.db() as c:
                    for a in result.get('data',[]):
                        author_map[a['id']]=a['username'].lower()
                        c.execute('INSERT INTO post_authors(id,handle,fetched_at) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET handle=excluded.handle,fetched_at=excluded.fetched_at',(a['id'],a['username'].lower(),time.time()))
        with s.db() as c:
            previous=c.execute("SELECT MAX(window_end) FROM collection_jobs WHERE kind=? AND ticker=? AND status='done'",(kind,ticker)).fetchone()[0]
        # Initial sample covers 24h; subsequent scans overlap a minute. A cap is
        # explicitly a sample, never a claim to have read the entire account.
        start=max(end-86400,int(previous)-60 if previous else end-86400)
        if kind=='hour_voice':
            with s.db() as c:
                checkpoints={r['handle']:int(r['window_end']) for r in c.execute('SELECT handle,window_end FROM voice_checkpoints')}
            if all(checkpoints.get(h,0)>=end for h in handles):return {'data':[]}
            start=max(end-86400,min(checkpoints.get(h,end-86400) for h in handles)-60)
        with s.db() as c:
            admin=kind=='hour_voice' and ',' not in ticker and bool(c.execute('SELECT 1 FROM admin_voices WHERE handle=?',(ticker,)).fetchone())
        size=20 if admin else 10
        spend_kind='sample_admin:'+ticker if admin else 'sample_live'
        result=paid_request(client,'tweets/search/recent',{'query':query,'start_time':iso(start),'end_time':iso(end),'max_results':size,'tweet.fields':'created_at,author_id,public_metrics,note_tweet'},spend_kind,size*.005,token)
        items=[{'id':p['id'],'author':author_map.get(p['author_id'],'id'+p['author_id']),'author_id':p['author_id'],'text':(p.get('note_tweet') or {}).get('text') or p['text'],'created_at':p['created_at'],'likes':p.get('public_metrics',{}).get('like_count',0)} for p in result.get('data',[])]
        s.ingest(items,include_unmatched=kind=='hour_voice')
        with s.db() as c:
            truncated=int(bool(result.get('meta',{}).get('next_token')))
            c.execute('UPDATE collection_jobs SET truncated=? WHERE id=?',(truncated,job['id']))
            if kind=='hour_voice':
                for handle in handles:
                    c.execute('INSERT INTO voice_checkpoints VALUES(?,?,?,?) ON CONFLICT(handle) DO UPDATE SET window_end=excluded.window_end,checked_at=excluded.checked_at,truncated=excluded.truncated WHERE excluded.window_end>voice_checkpoints.window_end',(handle,end,time.time(),truncated))
    return result

def profiles(client):
    s=core();end=int(time.time()//86400)*86400
    with s.db() as c:
        settings=data_settings(c)
        used=c.execute("SELECT COALESCE(SUM(COALESCE(actual_estimate,reserved)),0) FROM x_spend WHERE kind LIKE 'profiles%' AND ts>=?",(end,)).fetchone()[0]
        known={r[0] for r in c.execute('SELECT handle FROM post_authors WHERE fetched_at>?',(time.time()-30*86400,))}
        unresolved=len(set(shared_handles(c))-known)
        remaining=max(0,settings['daily_profile_limit']-round(used/.01)-unresolved)
        c.execute("UPDATE posts SET author=(SELECT a.handle FROM post_identity i JOIN post_authors a ON a.id=i.author_id WHERE i.source=posts.source AND i.post_id=posts.id) WHERE source='x' AND EXISTS(SELECT 1 FROM post_identity i JOIN post_authors a ON a.id=i.author_id WHERE i.source=posts.source AND i.post_id=posts.id)")
        if not remaining:return
        # Author IDs remain stable even before their handles are resolved.
        ids=[r[0] for r in c.execute('SELECT i.author_id FROM post_identity i JOIN posts p ON p.source=i.source AND p.id=i.post_id LEFT JOIN post_authors a ON a.id=i.author_id WHERE p.ts>? AND (a.id IS NULL OR a.fetched_at<?) GROUP BY i.author_id ORDER BY MAX(p.ts) DESC LIMIT ?',(end-31*86400,end-30*86400,remaining))]
    if not ids:return
    result=paid_request(client,'users',{'ids':','.join(ids),'user.fields':'username,created_at,public_metrics'},'profiles',len(ids)*.01,os.environ['X_BEARER_TOKEN'])
    with s.db() as c:
        for a in result.get('data',[]):
            m=a.get('public_metrics',{});created=datetime.fromisoformat(a['created_at'].replace('Z','+00:00')).timestamp() if a.get('created_at') else None
            c.execute('INSERT INTO post_authors VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET handle=excluded.handle,followers=excluded.followers,following=excluded.following,posts=excluded.posts,fetched_at=excluded.fetched_at',(a['id'],a['username'].lower(),created,m.get('followers_count',0),m.get('following_count',0),m.get('tweet_count',0),time.time()))
        # Apply cached handles also to newly ingested posts without buying profiles again.
        c.execute("UPDATE posts SET author=(SELECT a.handle FROM post_identity i JOIN post_authors a ON a.id=i.author_id WHERE i.source=posts.source AND i.post_id=posts.id) WHERE source='x' AND EXISTS(SELECT 1 FROM post_identity i JOIN post_authors a ON a.id=i.author_id WHERE i.source=posts.source AND i.post_id=posts.id)")

def tick(scheduled=False,client=None):
    s=core();now=time.time();lease=secrets.token_hex(16);owned=client is None
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE');settings=data_settings(c)
        if scheduled:c.execute("INSERT INTO meta VALUES('scheduler_seen',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(now),))
        if not settings['enabled']:return {'paused':True,'reason':'Collection paused','completed':0}
        if not os.getenv('X_BEARER_TOKEN'):raise RuntimeError('X credential missing.')
        cooldown=c.execute("SELECT value FROM meta WHERE key='x_retry_after'").fetchone()
        if cooldown and float(cooldown[0])>now:return {'completed':0,'deferred':True,'retry_after':float(cooldown[0])}
        active=c.execute("SELECT value FROM meta WHERE key='worker_lease'").fetchone()
        if active and json.loads(active[0])['until']>now:return {'completed':0,'busy':True}
        c.execute("INSERT INTO meta VALUES('worker_lease',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps({'token':lease,'until':now+300}),))

    client=client or httpx.Client(timeout=12);completed=0;errors=[];deferred=None
    try:
        with s.db() as c:
            day=iso(now)[:10];marker=c.execute("SELECT value FROM meta WHERE key='maintenance_day'").fetchone()
            if not marker or marker[0]!=day:
                c.execute('DELETE FROM sessions WHERE expires<?',(now,))
                c.execute('DELETE FROM attempts WHERE reset<?',(now,))
                c.execute("DELETE FROM collection_jobs WHERE updated_at<? AND status NOT IN ('pending','running')",(now-90*86400,))
                c.execute("INSERT INTO meta VALUES('maintenance_day',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(day,))
        plan_hour()
        deadline=time.monotonic()+65
        # Prioritize current hourly/demand jobs. Past hourly slots are not bought
        # retroactively after an outage; the next scan catches recent posts.
        with s.db() as c:
            c.execute("UPDATE collection_jobs SET status='expired' WHERE kind IN ('hour_counts','hour_sample','hour_voice','request_counts','request_sample') AND status='pending' AND window_end<?",(now-7200,))
            rows=[dict(r) for r in c.execute("SELECT * FROM collection_jobs WHERE kind IN ('hour_counts','hour_sample','hour_voice','request_counts','request_sample') AND (status='pending' OR (status='running' AND lease_until<?) OR (status='error' AND next_attempt>0 AND next_attempt<=?)) AND attempts<3 ORDER BY CASE WHEN kind='hour_voice' THEN 0 WHEN kind='hour_sample' THEN 1 ELSE 2 END,id LIMIT 15",(now,now))]
        for job in rows:
            if time.monotonic()>deadline:break
            with s.db() as c:c.execute("UPDATE collection_jobs SET status='running',attempts=attempts+1,lease_until=?,lease_token=? WHERE id=?",(time.time()+180,lease,job['id']))
            try:
                perform(job,client)
                with s.db() as c:c.execute("UPDATE collection_jobs SET status='done',error=NULL,lease_until=0,next_attempt=0,updated_at=? WHERE id=? AND lease_token=?",(time.time(),job['id'],lease))
                completed+=1
            except CollectionDeferred as exc:
                deferred=exc.until
                with s.db() as c:c.execute("UPDATE collection_jobs SET status='pending',attempts=attempts-1,lease_until=0,error=NULL,next_attempt=0,updated_at=? WHERE id=? AND lease_token=?",(time.time(),job['id'],lease))
                break
            except Exception as exc:
                message=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__+': request failed'
                transient=isinstance(exc,(httpx.TimeoutException,httpx.NetworkError)) or 'HTTP 429' in message or any('HTTP '+str(n) in message for n in range(500,600))
                quota='allowance reached' in message or 'ceiling reached' in message
                with s.db() as c:c.execute("UPDATE collection_jobs SET status=?,error=?,next_attempt=?,lease_until=0,updated_at=? WHERE id=? AND lease_token=?",('skipped' if quota else 'error',message[:300],time.time()+900 if transient else 0,time.time(),job['id'],lease))
                if not quota:errors.append(message);break
        from .collection import run_batch
        if not errors and not deferred:
            result=run_batch(30,client);completed+=result['completed'];errors+=result['errors']
            deferred=result.get('retry_after') if result.get('deferred') else None
        if not errors and not deferred:
            try:profiles(client)
            except CollectionDeferred as exc:deferred=exc.until
            except RuntimeError as exc:
                if 'allowance reached' not in str(exc) and 'ceiling reached' not in str(exc):errors.append(str(exc))
        with s.db() as c:
            c.execute("INSERT INTO meta VALUES('worker_result',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps({'at':time.time(),'completed':completed,'errors':errors,'duration_seconds':round(time.time()-now,1),'deferred':bool(deferred),'retry_after':deferred}),))
        if not errors:
            from .digest import build
            build()
        return {'completed':completed,'errors':errors,**({'deferred':True,'retry_after':deferred} if deferred else {})}
    finally:
        if owned:client.close()
        with s.db() as c:
            row=c.execute("SELECT value FROM meta WHERE key='worker_lease'").fetchone()
            if row and json.loads(row[0])['token']==lease:c.execute("DELETE FROM meta WHERE key='worker_lease'")

def status():
    now=time.time();s=core()
    with s.db() as c:
        cooldown=c.execute("SELECT value FROM meta WHERE key='x_retry_after'").fetchone()
        seen=c.execute("SELECT value FROM meta WHERE key='scheduler_seen'").fetchone()
        result=c.execute("SELECT value FROM meta WHERE key='worker_result'").fetchone()
        jobs=[dict(r) for r in c.execute("SELECT kind,status,COUNT(*) n FROM collection_jobs WHERE updated_at>? AND kind!='counts' GROUP BY kind,status",(now-86400,))]
        errors=[dict(r) for r in c.execute("SELECT ticker,kind,error,attempts,next_attempt FROM collection_jobs WHERE status='error' ORDER BY updated_at DESC LIMIT 10")]
    last=float(seen[0]) if seen else None
    return {'automatic_preview':bool(last and now-last<5400),'scheduler_last_seen':last,'retry_after':float(cooldown[0]) if cooldown and float(cooldown[0])>now else None,'last_result':json.loads(result[0]) if result else None,'live_jobs':jobs,'live_errors':errors}

@router.post('/api/admin/collection/tick')
def manual_tick(request:Request):
    staff(request,owner=True)
    try:return tick()
    except RuntimeError as exc:raise HTTPException(409,str(exc))

@router.post('/api/refresh/{ticker}')
def request_refresh(ticker:str,request:Request):
    s=core();u=s.account(request);s.premium(u,'x');ticker=ticker.upper()
    if ticker not in s.CATALOG:raise HTTPException(404,'Unknown ticker.')
    now=time.time();end=int(now//3600)*3600;slot=iso(end)[:13];day=iso(end)[:10]
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE');settings=data_settings(c)
        if not settings['enabled'] or not settings['intraday_enabled']:raise HTTPException(409,'Live updates are paused.')
        latest=c.execute('SELECT MAX(end) FROM x_counts WHERE ticker=?',(ticker,)).fetchone()[0]
        if latest and latest>=end:return {'state':'fresh','message':'Latest completed hour is already cached.'}
        if c.execute("SELECT 1 FROM collection_jobs WHERE day=? AND ticker=? AND kind IN ('hour_counts','request_counts') AND status IN ('pending','running','done')",(slot,ticker)).fetchone():return {'state':'queued','message':'A shared refresh already exists for this hour.'}
        daily=c.execute("SELECT COUNT(*) FROM collection_jobs WHERE day LIKE ? AND kind='request_counts'",(day+'%',)).fetchone()[0]
        key='demand:'+day+':'+u['id'];row=c.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone();used=int(row[0]) if row else 0
        if daily>=settings['on_demand_daily_limit'] or used>=5:raise HTTPException(429,'Refresh allowance reached. Scheduled updates continue.')
        enqueue(c,slot,'request_counts',ticker,end,f'${ticker} lang:en -is:retweet')
        enqueue(c,slot,'request_sample',ticker,end,f'${ticker} lang:en -is:retweet')
        c.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,str(used+1)))
    return {'state':'queued','message':'Queued for the next scheduled run. All members share this refresh.'}

@router.get('/api/live/{ticker}')
def live_ticker(ticker:str,request:Request):
    s=core();s.account(request);ticker=ticker.upper()
    if ticker not in s.CATALOG:raise HTTPException(404,'Unknown ticker.')
    with s.db() as c:
        end=c.execute('SELECT MAX(end) FROM x_counts WHERE ticker=?',(ticker,)).fetchone()[0]
        counts=c.execute('SELECT SUM(n),COUNT(*) FROM x_counts WHERE ticker=? AND start>=? AND end<=?',(ticker,(end or 0)-86400,end or 0)).fetchone()
        latest=c.execute("SELECT MAX(p.ts) FROM posts p JOIN mentions m ON m.source=p.source AND m.post_id=p.id WHERE p.source='x' AND m.ticker=?",(ticker,)).fetchone()[0]
        queued=c.execute("SELECT COUNT(*) FROM collection_jobs WHERE ticker=? AND kind IN ('hour_counts','request_counts') AND status IN ('pending','running')",(ticker,)).fetchone()[0]
    return {'ticker':ticker,'as_of':end,'mentions_24h':counts[0] or 0,'coverage_hours':counts[1],'latest_sample':latest,'queued':bool(queued),'stale':not end or time.time()-end>7200}


@router.get('/api/intraday')
def intraday(request:Request):
    import math
    s=core();u=s.account(request,False);now=time.time();rows=[]
    with s.db() as c:
        posts=[dict(r) for r in c.execute("SELECT p.id,p.author,p.text,p.ts,m.ticker FROM posts p JOIN mentions m ON m.source=p.source AND m.post_id=p.id JOIN admin_voices a ON a.handle=LOWER(p.author) WHERE p.source='x' AND p.ts>? AND p.ts<=? ORDER BY p.ts DESC,p.id DESC LIMIT 500",(now-6*3600,now))]
        context={}
        for post in posts:
            if post['ticker'] in s.CATALOG and len(context.setdefault(post['ticker'],[]))<2:context[post['ticker']].append(post)
        ends={r['ticker']:r['end'] for r in c.execute('SELECT ticker,MAX(end) AS end FROM x_counts WHERE end>? AND end<=? GROUP BY ticker',(now-7200,now)) if r['ticker'] in s.CATALOG}
        for ticker in set(ends)|set(context):
            end=ends.get(ticker);current=[];prior=[]
            if end:
                buckets=[dict(r) for r in c.execute('SELECT start,end,n FROM x_counts WHERE ticker=? AND start>=? AND end<=? ORDER BY start',(ticker,end-21600,end))]
                current=[r for r in buckets if r['start']>=end-10800];prior=[r for r in buckets if r['start']<end-10800]
            complete=bool(end and [r['start'] for r in current]==[end-10800+i*3600 for i in range(3)] and [r['start'] for r in prior]==[end-21600+i*3600 for i in range(3)] and all(r['end']-r['start']==3600 for r in current+prior))
            n=sum(r['n'] for r in current) if complete else None;old=sum(r['n'] for r in prior) if complete else None
            heat=round(10*math.log1p(n)*(1+max(0,math.log2((n+5)/(old+5)))),1) if complete else None
            rows.append({'ticker':ticker,'name':s.CATALOG[ticker][0],'mentions':n,'previous':old,'change':round((n/old-1)*100,1) if old else None,'heat':heat,'as_of':end if complete else None,'posts':context.get(ticker,[]),'state':'measured' if complete else 'awaiting_counts'})
    rows.sort(key=lambda r:(r['heat'] is None,-(r['heat'] or 0),r['ticker']))
    full=bool(u and (u['plan']=='premium' or u['role'] in ('owner','admin') or os.getenv('FREE_LAUNCH','false').lower()=='true') and not u['demo'])
    return {'rows':rows if full else rows[:5 if u else 2],'total':len(rows),'locked':not full,'as_of':now,'comparison_hours':3,'disclosure':'Latest three completed hours versus the preceding three. Selected hourly leaders and recent admin-voice discoveries; not a full-market scan. Fresh posts provide context, not proof of a catalyst.'}
