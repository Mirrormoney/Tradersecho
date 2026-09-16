"""Count-first daily collection. Disabled until the owner opts in and a token exists."""
import argparse, json, os, time
from datetime import datetime, timezone
import httpx
from .service import db, CATALOG, ingest
from .community import data_settings

def iso(ts): return datetime.fromtimestamp(ts,timezone.utc).isoformat().replace('+00:00','Z')

def paid_request(client,path,params,kind,reserve,token):
    month=datetime.now(timezone.utc).strftime('%Y-%m')
    with db() as c:
        c.execute('BEGIN IMMEDIATE');settings=data_settings(c)
        if not settings['enabled']: raise RuntimeError('Collection is paused in Admin → Data budget.')
        spent=c.execute('SELECT COALESCE(SUM(COALESCE(actual_estimate,reserved)),0) FROM x_spend WHERE month=?',(month,)).fetchone()[0]
        if round(spent+reserve,6)>settings['monthly_budget']: raise RuntimeError('Local monthly cost ceiling reached; no request sent.')
        today=int(time.time()//86400)*86400
        if kind.startswith('sample') or kind=='profiles':
            category='sample%' if kind.startswith('sample') else 'profiles'
            limit=settings['daily_post_limit']*.005 if kind.startswith('sample') else settings['daily_profile_limit']*.01
            used=c.execute('SELECT COALESCE(SUM(reserved),0) FROM x_spend WHERE ts>=? AND kind LIKE ?',(today,category)).fetchone()[0]
            if round(used+reserve,6)>round(limit,6): raise RuntimeError('Daily sampling allowance reached; no request sent.')
        circuit=c.execute("SELECT value FROM meta WHERE key='x_retry_after'").fetchone()
        if circuit and float(circuit[0])>time.time(): raise RuntimeError('X cooldown active; no request sent.')
        rid=c.execute('INSERT INTO x_spend(month,kind,reserved,ts,status) VALUES(?,?,?,?,?)',(month,kind,reserve,time.time(),'reserved')).lastrowid
    # An uncertain or failed request keeps its full reservation: never refund a request that may have been billed.
    try:
        r=client.get('https://api.x.com/2/'+path,params=params,headers={'Authorization':'Bearer '+token})
        if not r.is_success:
            if r.status_code==429 or r.status_code>=500:
                try: reset=float(r.headers.get('x-rate-limit-reset',0))
                except ValueError: reset=0
                until=max(time.time()+900,min(reset,time.time()+3600))
                with db() as c:c.execute("INSERT INTO meta VALUES('x_retry_after',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(until),))
            raise RuntimeError(f'X returned HTTP {r.status_code}; reservation retained. Check access, balance or rate limits.')
        result=r.json()
        if result.get('errors'): raise RuntimeError('X returned a partial response; reservation retained.')
        estimate=.005 if kind.startswith('counts') else len(result.get('data',[]))*.01 if kind=='profiles' else len(result.get('data',[]))*.005+len(result.get('includes',{}).get('users',[]))*.01
        with db() as c: c.execute('UPDATE x_spend SET actual_estimate=?,status=? WHERE id=?',(round(estimate,4),'received',rid))
        return result
    except Exception:
        with db() as c: c.execute("UPDATE x_spend SET status='failed_or_uncertain' WHERE id=?",(rid,))
        raise

def collect(client=None):
    from .service import CATALOG
    token=os.getenv('X_BEARER_TOKEN')
    if not token: raise RuntimeError('X_BEARER_TOKEN is not configured. No paid requests sent.')
    day=datetime.now(timezone.utc).date().isoformat();end=int(time.time()//3600)*3600
    with db() as c:
        settings=data_settings(c)
        if not settings['enabled']: raise RuntimeError('Collection is paused in Admin → Data budget.')
        c.execute('BEGIN IMMEDIATE')
        lease=c.execute("SELECT value FROM meta WHERE key='economy_lease'").fetchone()
        if lease and float(lease[0])>time.time(): raise RuntimeError('Another collection run holds the lease.')
        c.execute("INSERT INTO meta VALUES('economy_lease',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(time.time()+1800),))
    owned=client is None;client=client or httpx.Client(timeout=30);added=0
    try:
        for ticker in CATALOG:
            key='economy-counts:'+day+':'+ticker
            with db() as c:
                if c.execute('SELECT 1 FROM meta WHERE key=?',(key,)).fetchone(): continue
            query=f'${ticker} lang:en -is:retweet'
            # Six days leaves a safe margin inside the rolling seven-day API limit.
            result=paid_request(client,'tweets/counts/recent',{'query':query,'start_time':iso(end-6*86400),'end_time':iso(end),'granularity':'hour'},'counts',.005,token)
            if result.get('meta',{}).get('next_token'): raise RuntimeError('Unexpected counts pagination; checkpoint not marked complete.')
            with db() as c:
                for b in result.get('data',[]):
                    start=datetime.fromisoformat(b['start'].replace('Z','+00:00')).timestamp();finish=datetime.fromisoformat(b['end'].replace('Z','+00:00')).timestamp()
                    c.execute('INSERT INTO x_counts VALUES(?,?,?,?,?,?) ON CONFLICT(ticker,start) DO UPDATE SET n=excluded.n,end=excluded.end,query=excluded.query,fetched_at=excluded.fetched_at',(ticker,start,finish,b['tweet_count'],query,time.time()))
                c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key,str(end)))
        with db() as c:
            # Freeze today's targets so reruns do not silently purchase additional samples.
            key='economy-targets:'+day
            saved=c.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
            targets=json.loads(saved[0]) if saved else [r['ticker'] for r in c.execute('SELECT ticker,SUM(n) n FROM x_counts WHERE start>=? AND end<=? GROUP BY ticker ORDER BY n DESC,ticker LIMIT ?',(end-86400,end,settings['sample_tickers']))]
            if not saved: c.execute('INSERT INTO meta VALUES(?,?)',(key,json.dumps(targets)))
        for ticker in targets:
            key='economy-sample:'+day+':'+ticker
            with db() as c:
                if c.execute('SELECT 1 FROM meta WHERE key=?',(key,)).fetchone(): continue
            result=paid_request(client,'tweets/search/recent',{'query':f'${ticker} lang:en -is:retweet','start_time':iso(end-86400),'end_time':iso(end),'max_results':settings['sample_size'],'tweet.fields':'created_at,author_id,public_metrics','expansions':'author_id','user.fields':'username'},'sample',settings['sample_size']*.015,token)
            authors={a['id']:a['username'] for a in result.get('includes',{}).get('users',[])}
            items=[]
            for p in result.get('data',[]):
                if p['author_id'] not in authors: raise RuntimeError('Missing author expansion; sample not marked complete.')
                items.append({'id':p['id'],'author':authors[p['author_id']],'text':p['text'],'created_at':p['created_at'],'likes':p.get('public_metrics',{}).get('like_count',0)})
            added+=ingest(items)['posts_added']
            with db() as c: c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key,str(end)))
        with db() as c: c.execute("INSERT INTO meta VALUES('last_sync',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps({'at':time.time(),'mode':'counts + sampled sentiment','window_end':end,'posts_added':added,'pending':False}),))
        return {'posts_added':added,'mode':'economy','window_end':end}
    finally:
        with db() as c: c.execute("DELETE FROM meta WHERE key='economy_lease'")
        if owned: client.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--loop',action='store_true');args=parser.parse_args()
    while True:
        try: print(json.dumps(collect()),flush=True)
        except Exception as exc: print(str(exc),flush=True)
        if not args.loop: break
        time.sleep(86400)
