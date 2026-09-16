"""Budget-capped X recent search collector. See README before enabling paid access."""
import argparse, json, os, time, hashlib
from datetime import datetime, timezone
import httpx
from .service import db, ingest, CATALOG

def iso(ts): return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace('+00:00','Z')

def collect(max_pages=2, client=None):
    token=os.getenv('X_BEARER_TOKEN')
    if not token: raise RuntimeError('Set X_BEARER_TOKEN in the server environment before collection.')
    daily_budget=int(os.getenv('X_DAILY_REQUEST_LIMIT','24'))
    if daily_budget<1: raise RuntimeError('X_DAILY_REQUEST_LIMIT must be positive.')
    query='('+' OR '.join('$'+t for t in CATALOG)+') lang:en -is:retweet'
    key='cursor:'+hashlib.sha256(query.encode()).hexdigest()[:16]
    now=time.time();day=datetime.now(timezone.utc).date().isoformat()
    with db() as c:
        saved=c.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
        cursor=json.loads(saved[0]) if saved else {}
    if not cursor.get('next_token'):
        cursor={'start':max(cursor.get('end',now-86400)-60,now-7*86400+60),'end':now-30}
    if cursor['start']<now-7*86400:
        raise RuntimeError('Pending page is outside the recent-search window. Archive backfill is needed; checkpoint was retained.')
    if cursor['end']<=cursor['start']: return {'requests':0,'posts_added':0,'pending':False}
    total=0;requests=0
    owned=client is None
    client=client or httpx.Client(timeout=30)
    try:
        for _ in range(max_pages):
            # Reserve the request under a transaction, including failed requests.
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                row=c.execute('SELECT value FROM meta WHERE key=?',('requests:'+day,)).fetchone()
                used=int(row[0]) if row else 0
                if used>=daily_budget: raise RuntimeError('Daily request budget reached. No further X requests were sent.')
                c.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('requests:'+day,str(used+1)))
            params={'query':query,'max_results':100,'start_time':iso(cursor['start']),'end_time':iso(cursor['end']),'tweet.fields':'created_at,author_id,public_metrics','expansions':'author_id','user.fields':'username'}
            if cursor.get('next_token'): params['next_token']=cursor['next_token']
            r=client.get('https://api.x.com/2/tweets/search/recent',params=params,headers={'Authorization':'Bearer '+token})
            requests+=1
            if r.status_code==429: raise RuntimeError('X rate limit reached. Retry after the provider reset; checkpoint preserved.')
            if not r.is_success: raise RuntimeError(f'X returned HTTP {r.status_code}. Check API access and credits; checkpoint preserved.')
            result=r.json()
            if result.get('errors'): raise RuntimeError('X returned a partial response. Checkpoint retained to avoid silent gaps.')
            authors={u['id']:u['username'] for u in result.get('includes',{}).get('users',[])}
            items=[]
            for p in result.get('data',[]):
                if p['author_id'] not in authors: raise RuntimeError('Missing author expansion. Checkpoint retained.')
                items.append({'id':p['id'],'author':authors[p['author_id']],'text':p['text'],'created_at':p['created_at'],'likes':p.get('public_metrics',{}).get('like_count',0)})
            total+=ingest(items)['posts_added']
            cursor['next_token']=result.get('meta',{}).get('next_token')
            with db() as c:
                c.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(cursor)))
                c.execute("INSERT INTO meta VALUES('last_sync',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps({'at':time.time(),'pending':bool(cursor['next_token']),'posts_added':total,'window_end':cursor['end']}),))
            if not cursor['next_token']: break
    finally:
        if owned: client.close()
    return {'requests':requests,'posts_added':total,'pending':bool(cursor.get('next_token'))}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Collect actual X posts with daily request caps.')
    parser.add_argument('--loop',action='store_true')
    parser.add_argument('--interval',type=int,default=3600)
    parser.add_argument('--max-pages',type=int,default=2)
    args=parser.parse_args()
    if not 1<=args.max_pages<=10 or args.interval<300: parser.error('Use 1–10 pages and an interval of at least 300 seconds.')
    while True:
        try: print(json.dumps(collect(args.max_pages)),flush=True)
        except Exception as e:
            print(str(e),flush=True)
            if not args.loop: raise SystemExit(1)
        if not args.loop: break
        time.sleep(args.interval)
