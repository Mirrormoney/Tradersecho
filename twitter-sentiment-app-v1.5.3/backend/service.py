"""Tradersecho v2. Run from project root: uvicorn backend.service:app."""
import os, sqlite3, secrets, hashlib, hmac, re, math, random, json, time
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager
from fastapi import FastAPI, Request, Response, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .community import router as community_router, migrate, claim_owner, available_default_name
from .database import connect, IntegrityError

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = os.getenv('TRADERSECHO_DB', str(ROOT / 'data' / 'tradersecho.sqlite'))
DEMO = os.getenv('DEMO_ENABLED', 'true').lower() == 'true'
SECURE = os.getenv('COOKIE_SECURE', 'true' if os.getenv('VERCEL') else 'false').lower() == 'true'
ORIGIN = os.getenv('APP_ORIGIN', 'http://127.0.0.1:8000').rstrip('/')
DEMO_CATALOG = {'NVDA':('NVIDIA','Semiconductors'), 'TSLA':('Tesla','Automotive'), 'PLTR':('Palantir','Software'), 'AMD':('Advanced Micro Devices','Semiconductors'), 'AAPL':('Apple','Technology'), 'MSFT':('Microsoft','Software'), 'AMZN':('Amazon','Consumer'), 'META':('Meta Platforms','Technology'), 'GOOGL':('Alphabet','Technology'), 'COIN':('Coinbase','Financials'), 'RKLB':('Rocket Lab','Aerospace'), 'ASTS':('AST SpaceMobile','Telecom'), 'SOFI':('SoFi Technologies','Financials'), 'INTC':('Intel','Semiconductors'), 'MU':('Micron Technology','Semiconductors'), 'AVGO':('Broadcom','Semiconductors')}
from .stocks import Catalog, router as stocks_router, migrate as migrate_stocks
CATALOG=Catalog()
app = FastAPI(title='Tradersecho', version='2.0.0')
app.include_router(community_router)
app.include_router(stocks_router)
from .digest import router as digest_router, migrate as migrate_digest
app.include_router(digest_router)
from .voices import router as voices_router, migrate as migrate_voices, normalize as normalize_handle
app.include_router(voices_router)

def db():
    return connect(DB_PATH)

def init():
    with db() as c:
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,email TEXT UNIQUE,password TEXT,plan TEXT NOT NULL DEFAULT 'free',demo INTEGER NOT NULL DEFAULT 0,stripe_customer TEXT);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT REFERENCES accounts(id) ON DELETE CASCADE,expires REAL);
        CREATE TABLE IF NOT EXISTS watchlist(user_id TEXT REFERENCES accounts(id),ticker TEXT,PRIMARY KEY(user_id,ticker));
        CREATE TABLE IF NOT EXISTS handles(user_id TEXT REFERENCES accounts(id),handle TEXT,note TEXT,PRIMARY KEY(user_id,handle));
        CREATE TABLE IF NOT EXISTS posts(source TEXT,id TEXT,author TEXT,text TEXT,ts REAL,sentiment TEXT,likes INTEGER DEFAULT 0,PRIMARY KEY(source,id));
        CREATE TABLE IF NOT EXISTS mentions(source TEXT,post_id TEXT,ticker TEXT,PRIMARY KEY(source,post_id,ticker),FOREIGN KEY(source,post_id) REFERENCES posts(source,id) ON DELETE CASCADE);
        CREATE INDEX IF NOT EXISTS posts_ts ON posts(source,ts);
        CREATE INDEX IF NOT EXISTS mentions_ticker ON mentions(ticker,source);
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY,count INTEGER,reset REAL);
        CREATE TABLE IF NOT EXISTS webhook_events(id TEXT PRIMARY KEY);
        ''')
        migrate(c)
        from .payments import migrate as migrate_payments
        migrate_payments(c)
        migrate_stocks(c)
        migrate_digest(c)
        migrate_voices(c)
        c.execute('CREATE TABLE IF NOT EXISTS post_identity(source TEXT,post_id TEXT,author_id TEXT,PRIMARY KEY(source,post_id))')
    if DEMO: seed_demo()

def seed_demo():
    with db() as c:
        if c.execute("SELECT 1 FROM meta WHERE key='demo_anchor'").fetchone(): return
        anchor = int(time.time())
        rng = random.Random(427)
        authors = ['signal_lab','growth_notes','chip_observer','market_journal','orbital_research','value_compass']
        phrases = {'bullish':['Demand looks strong. Watching the next earnings update.','Bullish on the long-term opportunity; execution is the key.','Breakout potential as revenue growth accelerates.'], 'bearish':['Valuation looks stretched. Risk of a pullback here.','Bearish near term: margins under pressure and guidance is weak.','The rally feels overextended. Watching downside risk.'], 'neutral':['Earnings on my watchlist. Waiting for the numbers.','Tracking the volume today; no position yet.','Interesting discussion, but the thesis needs more evidence.']}
        for day in range(61):
            for idx,ticker in enumerate(DEMO_CATALOG):
                base = 25 - idx
                boost = (4.7 if idx==0 else 3.3 if idx==2 else 1.8 if idx==1 else 1) if day<1 else (1.8 if idx in [3,10] and day<7 else 1)
                count = max(3, int(base*boost*rng.uniform(.7,1.3)))
                for n in range(count):
                    pid = f'{day}-{ticker}-{n}'
                    sentiment = rng.choices(['bullish','bearish','neutral'],[.62 if idx%3 else .72,.2,.2])[0]
                    ts = anchor - day*86400 - rng.randrange(86400)
                    author = authors[(n+idx)%len(authors)]
                    c.execute('INSERT INTO posts VALUES(?,?,?,?,?,?,?)',('demo',pid,author,f'${ticker} '+rng.choice(phrases[sentiment]),ts,sentiment,rng.randrange(8,900)))
                    c.execute('INSERT INTO mentions VALUES(?,?,?)',('demo',pid,ticker))
        c.execute('INSERT INTO meta VALUES(?,?)',('demo_anchor',str(anchor)))

@app.middleware('http')
async def security(request, call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin = request.headers.get('origin')
        allowed = {ORIGIN,'http://127.0.0.1:5173','http://localhost:5173'} if not SECURE else {ORIGIN}
        for key in ['VERCEL_URL','VERCEL_BRANCH_URL','VERCEL_PROJECT_PRODUCTION_URL']:
            if os.getenv(key): allowed.add('https://'+os.environ[key])
        if origin and origin not in allowed:
            return Response('Origin rejected',status_code=403)
        try:
            length=int(request.headers.get('content-length','0') or 0)
        except ValueError:
            return Response('Invalid content length',status_code=400)
        if length>2_000_000:
            return Response('Request too large',status_code=413)
    response = await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['X-Frame-Options']='DENY'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    return response

def account(request, required=True):
    raw = request.cookies.get('te_session','')
    with db() as c:
        row=c.execute('SELECT a.* FROM accounts a JOIN sessions s ON a.id=s.user_id WHERE s.token=? AND s.expires>?',(hashlib.sha256(raw.encode()).hexdigest(),time.time())).fetchone()
    if not row and required: raise HTTPException(401,'Sign in to continue.')
    if row and row['status']!='active': raise HTTPException(403,'This account is suspended. Contact the site owner.')
    if row and (not row['last_seen'] or row['last_seen']<time.time()-300):
        with db() as c: c.execute('UPDATE accounts SET last_seen=? WHERE id=?',(time.time(),row['id']))
    return dict(row) if row else None

def public_account(u):
    from .payments import account_details
    return {k:u[k] for k in ['id','email','plan','role','status','display_name']} | {'demo':bool(u['demo'])} | account_details(u)

def session(response, uid):
    token=secrets.token_urlsafe(32)
    with db() as c:
        c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
        c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,time.time()+7*86400))
    response.set_cookie('te_session',token,httponly=True,secure=SECURE,samesite='lax',max_age=7*86400,path='/')

def throttle(request):
    key=request.client.host if request.client else 'unknown'
    now=time.time()
    with db() as c:
        c.execute('DELETE FROM attempts WHERE reset<?',(now,))
        c.execute('INSERT INTO attempts VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1',(key,now+900))
        count=c.execute('SELECT count FROM attempts WHERE key=?',(key,)).fetchone()[0]
    if count>30: raise HTTPException(429,'Too many attempts. Try again in 15 minutes.')

def password_hash(p,salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+':'+hashlib.scrypt(p.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()

class Credentials(BaseModel):
    email:str=Field(min_length=3,max_length=254)
    password:str=Field(min_length=10,max_length=128)
    owner_code:str=Field(default='',max_length=150)

@app.post('/api/auth/signup')
def signup(payload:Credentials,request:Request,response:Response):
    throttle(request)
    email=payload.email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): raise HTTPException(422,'Enter a valid email address.')
    uid=secrets.token_hex(16)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        reserved=c.execute('SELECT 1 FROM owner_invites WHERE email=? AND used_by IS NULL AND expires>?',(email,time.time())).fetchone()
        if reserved and not payload.owner_code: raise HTTPException(403,'This email is reserved. Use Owner setup with your private invitation.')
        name=available_default_name(c,uid)
        try: c.execute('INSERT INTO accounts(id,email,password,display_name,created_at,last_login) VALUES(?,?,?,?,?,?)',(uid,email,password_hash(payload.password),name,time.time(),time.time()))
        except IntegrityError: raise HTTPException(409,'An account with this email already exists.')
        if payload.owner_code: claim_owner(c,payload.owner_code,email,uid)
        u=c.execute('SELECT * FROM accounts WHERE id=?',(uid,)).fetchone()
    session(response,uid)
    return public_account(u)

@app.post('/api/auth/login')
def login(payload:Credentials,request:Request,response:Response):
    throttle(request)
    with db() as c: u=c.execute('SELECT * FROM accounts WHERE email=? AND demo=0',(payload.email.strip().lower(),)).fetchone()
    stored=u['password'] if u else password_hash('unmatched-password')
    if not hmac.compare_digest(password_hash(payload.password,stored.split(':')[0]),stored) or not u:
        raise HTTPException(401,'Email or password is incorrect.')
    if u['status']!='active': raise HTTPException(403,'This account is suspended. Contact the site owner.')
    with db() as c: c.execute('UPDATE accounts SET last_login=? WHERE id=?',(time.time(),u['id']))
    session(response,u['id'])
    return public_account(u)

@app.post('/api/auth/demo')
def demo_account(request:Request,response:Response,plan:str=Query('premium',pattern='^(free|premium)$')):
    if not DEMO: raise HTTPException(404)
    throttle(request)
    uid=secrets.token_hex(16)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        name=available_default_name(c,uid,'Preview')
        c.execute('INSERT INTO accounts(id,email,plan,demo,display_name,created_at) VALUES(?,?,?,1,?,?)',(uid,f'{plan}-preview-{uid[:6]}@demo.local',plan,name,time.time()))
        for t in ['NVDA','PLTR','RKLB']: c.execute('INSERT INTO watchlist VALUES(?,?)',(uid,t))
        c.execute('INSERT INTO handles VALUES(?,?,?)',(uid,'signal_lab','Fictional analyst in the sample dataset'))
        u=c.execute('SELECT * FROM accounts WHERE id=?',(uid,)).fetchone()
    session(response,uid)
    return public_account(u)

@app.post('/api/auth/logout')
def logout(request:Request,response:Response):
    with db() as c: c.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(request.cookies.get('te_session','').encode()).hexdigest(),))
    response.delete_cookie('te_session',path='/')
    return {'ok':True}

@app.get('/api/me')
def me(request:Request):
    u=account(request,False)
    return public_account(u) if u else None

def premium(u,source='demo'):
    if not u or (u['plan']!='premium' and u['role'] not in ['owner','admin']) or (u['demo'] and source!='demo'): raise HTTPException(403,'Premium membership is required for this feature.')

def reference(source,c):
    if source=='demo':
        if not DEMO: raise HTTPException(404,'Sample data is disabled.')
        return float(c.execute("SELECT value FROM meta WHERE key='demo_anchor'").fetchone()[0])
    latest=c.execute("SELECT value FROM meta WHERE key='completed_snapshot'").fetchone()
    if latest: return float(latest[0])
    totals=c.execute('SELECT ticker,MAX(end) latest FROM x_counts GROUP BY ticker').fetchall()
    if len(totals)==len(CATALOG): return min(r['latest'] for r in totals)
    return time.time()

@app.get('/api/status')
def status():
    with db() as c:
        row=c.execute("SELECT COUNT(*) n,MAX(ts) latest,MIN(ts) earliest FROM posts WHERE source='x'").fetchone()
        sync=c.execute("SELECT value FROM meta WHERE key='last_sync'").fetchone()
    return {'demo_enabled':DEMO,'x_configured':bool(os.getenv('X_BEARER_TOKEN')),'live_posts':row['n'],'latest_post':row['latest'],'earliest_post':row['earliest'],'last_sync':json.loads(sync[0]) if sync else None,'billing_sandbox':billing_sandbox(),'billing_configured':any(billing_options().values()),'billing_options':billing_options(),'catalog':[{'ticker':t,'name':v[0],'sector':v[1]} for t,v in CATALOG.items()]}

@app.get('/api/rankings')
def rankings(request:Request,window:int=Query(1,ge=1,le=30),source:str=Query('demo',pattern='^(demo|x)$'),scope:str=Query('market',pattern='^(market|watchlist)$')):
    u=account(request,False)
    if not u and window!=1: raise HTTPException(401,'Create a free account to explore weekly and monthly rankings.')
    if window not in [1,7,30]: raise HTTPException(422,'Choose 1, 7 or 30 days.')
    with db() as c:
        now=reference(source,c); start=now-window*86400; prev=start-window*86400
        data=c.execute('''SELECT m.ticker,COUNT(*) mentions,COUNT(DISTINCT p.author) authors,
        SUM(p.sentiment='bullish') bullish,SUM(p.sentiment='bearish') bearish,SUM(p.sentiment='neutral') neutral
        FROM posts p JOIN mentions m ON p.source=m.source AND p.id=m.post_id WHERE p.source=? AND p.ts>? AND p.ts<=? GROUP BY m.ticker''',(source,start,now)).fetchall()
        previous={r['ticker']:r['n'] for r in c.execute('SELECT ticker,COUNT(*) n FROM mentions m JOIN posts p ON m.source=p.source AND m.post_id=p.id WHERE p.source=? AND p.ts>? AND p.ts<=? GROUP BY ticker',(source,prev,start))}
        buckets={}
        for r in c.execute('SELECT ticker,MIN(13,CAST((p.ts-?)/? AS INTEGER)) bucket,COUNT(*) n FROM mentions m JOIN posts p ON m.source=p.source AND m.post_id=p.id WHERE p.source=? AND p.ts>? AND p.ts<=? GROUP BY ticker,bucket',(start,window*86400/14,source,start,now)):
            buckets.setdefault(r['ticker'],[0]*14)[r['bucket']]=r['n']
        earliest=c.execute('SELECT MIN(ts) FROM posts WHERE source=?',(source,)).fetchone()[0]
    rows=[]
    for r in data:
        row=dict(r); old=previous.get(row['ticker'],0)
        row.update(name=CATALOG.get(row['ticker'],(row['ticker'],'Other'))[0],sector=CATALOG.get(row['ticker'],('','Other'))[1],previous=old,change=round((row['mentions']/old-1)*100,1) if old else None,spark=buckets.get(row['ticker'],[0]*14))
        row['sentiment']=round((row['bullish']-row['bearish'])/row['mentions']*100)
        row['heat']=round(math.log1p(row['mentions'])*(1+max(0,math.log2((row['mentions']+5)/(old+5))))*10,1)
        rows.append(row)
    if source=='x':
        from .count_metrics import enrich
        with db() as c:
            rows=enrich(c,rows,now,window)
            from .screening import enrich as screen_rows
            rows=screen_rows(c,rows,time.time(),window,classify)
    rows.sort(key=lambda x:x['heat'],reverse=True)
    total=len(rows)
    comparison=bool(earliest and earliest<=prev)
    if source=='x' and any(r.get('volume_source') for r in rows):
        comparison=all(r.get('comparison_complete',False) for r in rows)
        with db() as c:
            earliest=c.execute('SELECT MIN(start) FROM x_counts').fetchone()[0]
    full=bool(u and (u['plan']=='premium' or u['role'] in ('owner','admin')) and (not u['demo'] or source=='demo'))
    total_mentions=sum(r['mentions'] for r in rows)
    if scope=='watchlist':
        if not u:raise HTTPException(401,'Sign in to view your watchlist.')
        with db() as c:watched={r[0] for r in c.execute('SELECT ticker FROM watchlist WHERE user_id=? ORDER BY ticker LIMIT ?',(u['id'],50 if full else 5))}
        rows=[r for r in rows if r['ticker'] in watched]
    visible=rows if full else rows[:5 if u else 3]
    return {'rows':visible,'total_tickers':total,'total_mentions':total_mentions,'ranking_locked':bool(u and not full and scope=='market'),'preview_limit':None if full else 5 if u else 3,'preview':not bool(u),'as_of':now,'sample_as_of':time.time() if source=='x' else now,'source':source,'window':window,'comparison_complete':comparison,'coverage_days':round((now-earliest)/86400,1) if earliest else 0}

@app.get('/api/posts')
def posts(request:Request,ticker:str='',window:int=Query(1,ge=1,le=30),source:str=Query('demo',pattern='^(demo|x)$'),tracked:bool=False,order:str=Query('latest',pattern='^(latest|engagement)$')):
    account(request)
    args=[source]; clauses=['p.source=?']
    with db() as c:
        now=time.time() if source=='x' else reference(source,c)
        clauses+=['p.ts>?','p.ts<=?'];args += [now-window*86400,now]
        if ticker: clauses.append('m.ticker=?');args.append(ticker.upper())
        if tracked:
            u=account(request)
            if u['demo'] and source!='demo':raise HTTPException(403,'Sign in with a real account to view live voices.')
            if u['plan']=='premium' or u['role'] in ('owner','admin'):
                clauses.append('p.author IN (SELECT handle FROM handles WHERE user_id=? UNION SELECT handle FROM admin_voices)');args.append(u['id'])
            else:clauses.append('p.author IN (SELECT handle FROM admin_voices)')
        ordering='p.likes DESC,p.ts DESC' if order=='engagement' else 'p.ts DESC'
        rows=c.execute('SELECT p.*,GROUP_CONCAT(DISTINCT m.ticker) tickers FROM posts p LEFT JOIN mentions m ON p.source=m.source AND p.id=m.post_id WHERE '+' AND '.join(clauses)+' GROUP BY p.source,p.id ORDER BY '+ordering+' LIMIT 50',args).fetchall()
    return [dict(r) for r in rows]

@app.get('/api/watchlist')
def watchlist(request:Request):
    u=account(request)
    with db() as c: return [r[0] for r in c.execute('SELECT ticker FROM watchlist WHERE user_id=? ORDER BY ticker',(u['id'],))]

@app.put('/api/watchlist/{ticker}')
def watch(request:Request,ticker:str):
    u=account(request);ticker=ticker.upper()
    if ticker not in CATALOG: raise HTTPException(422,'Choose a ticker from the tracked universe.')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        count=c.execute('SELECT COUNT(*) FROM watchlist WHERE user_id=?',(u['id'],)).fetchone()[0]
        exists=c.execute('SELECT 1 FROM watchlist WHERE user_id=? AND ticker=?',(u['id'],ticker)).fetchone()
        if count>=(50 if u['plan']=='premium' else 5) and not exists: raise HTTPException(403,'Free accounts can save 5 tickers. Upgrade for more.')
        c.execute('INSERT OR IGNORE INTO watchlist VALUES(?,?)',(u['id'],ticker))
    return {'ok':True}

@app.delete('/api/watchlist/{ticker}')
def unwatch(request:Request,ticker:str):
    u=account(request)
    with db() as c: c.execute('DELETE FROM watchlist WHERE user_id=? AND ticker=?',(u['id'],ticker.upper()))
    return {'ok':True}

class Handle(BaseModel):
    handle:str=Field(min_length=1,max_length=16)
    note:str=Field(default='',max_length=250)

@app.get('/api/handles')
def handles(request:Request):
    u=account(request);premium(u)
    with db() as c: return [dict(r) for r in c.execute('SELECT handle,note FROM handles WHERE user_id=? ORDER BY handle',(u['id'],))]

@app.post('/api/handles')
def add_handle(payload:Handle,request:Request):
    u=account(request);premium(u)
    handle=normalize_handle(payload.handle)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM admin_voices WHERE handle=?',(handle,)).fetchone():
            return {'ok':True,'already_curated':True,'message':'Already included in Tradersecho voices. Its posts are in your feed; no personal slot was used and no private note was saved.'}
        existing=c.execute('SELECT 1 FROM handles WHERE user_id=? AND handle=?',(u['id'],handle)).fetchone()
        if not existing and c.execute('SELECT COUNT(*) FROM handles WHERE user_id=?',(u['id'],)).fetchone()[0]>=5: raise HTTPException(403,'You can add up to 5 personal accounts. Remove one before adding another.')
        c.execute('INSERT INTO handles VALUES(?,?,?) ON CONFLICT(user_id,handle) DO UPDATE SET note=excluded.note',(u['id'],handle,payload.note))
    return {'ok':True}

@app.delete('/api/handles/{handle}')
def remove_handle(handle:str,request:Request):
    u=account(request);premium(u)
    with db() as c: c.execute('DELETE FROM handles WHERE user_id=? AND handle=?',(u['id'],normalize_handle(handle)))
    return {'ok':True}

def admin(request):
    u=account(request,False)
    if u and not u['demo'] and u['role'] in ['admin','owner']: return
    expected=os.getenv('ADMIN_TOKEN','')
    if not expected or not hmac.compare_digest(request.headers.get('x-admin-token',''),expected): raise HTTPException(403,'Administrator access required.')

def classify(text):
    words=re.findall(r'[a-z]+',text.lower())
    positive={'bullish','buy','buying','breakout','strong','growth','beat','upside','long'}
    negative={'bearish','sell','selling','weak','miss','downside','short','overvalued','pullback'}
    score=0
    for i,w in enumerate(words):
        v=int(w in positive)-int(w in negative)
        if any(x in {'not','no','never'} for x in words[max(0,i-3):i]): v=-v
        score+=v
    return 'bullish' if score>0 else 'bearish' if score<0 else 'neutral'

def ingest(items,include_unmatched=False):
    normalized=[]
    for item in items:
        pid=str(item.get('id',''));author=str(item.get('author','')).lstrip('@').lower();text=str(item.get('text',''))
        if not re.fullmatch(r'\d{1,30}',pid) or not re.fullmatch(r'(?:[a-z0-9_]{1,15}|id[0-9]{1,20})',author) or not text or len(text)>25000: raise ValueError('Each post needs a numeric X id, valid author handle, text and UTC created_at.')
        ts=datetime.fromisoformat(str(item.get('created_at','')).replace('Z','+00:00'))
        if ts.tzinfo is None: raise ValueError('created_at must include a timezone.')
        ts=ts.timestamp()
        if ts>time.time()+60: raise ValueError('Posts cannot be dated in the future.')
        tickers=set(re.findall(r'\$([A-Za-z]{1,5}(?:\.[A-Za-z])?)\b',text.upper())) & set(CATALOG)
        sentiment=item.get('sentiment') or classify(text)
        if sentiment not in ['bullish','bearish','neutral']: raise ValueError('Invalid sentiment label.')
        likes=int(item.get('likes',0))
        if likes<0: raise ValueError('Likes must be nonnegative.')
        normalized.append((pid,author,text,ts,sentiment,likes,tickers,str(item.get('author_id',''))))
    normalized=[r for r in normalized if r[6] or include_unmatched]
    with db() as c:
        added=c.executemany('INSERT OR IGNORE INTO posts VALUES(?,?,?,?,?,?,?)',[('x',pid,author,text,ts,sentiment,likes) for pid,author,text,ts,sentiment,likes,tickers,aid in normalized]).rowcount
        c.executemany('INSERT OR IGNORE INTO post_identity VALUES(?,?,?)',[('x',r[0],r[7]) for r in normalized if r[7]])
        mentions=c.executemany('INSERT OR IGNORE INTO mentions VALUES(?,?,?)',[('x',r[0],ticker) for r in normalized for ticker in r[6]]).rowcount
    return {'posts_added':added,'mentions_added':mentions,'received':len(items)}

class ImportPayload(BaseModel):
    posts:list[dict]=Field(max_length=1000)

@app.post('/api/admin/import')
def import_posts(payload:ImportPayload,request:Request):
    admin(request)
    try: return ingest(payload.posts)
    except (ValueError,TypeError,OverflowError) as e: raise HTTPException(422,str(e))

@app.post('/api/admin/plan')
async def set_plan(request:Request):
    admin(request);payload=await request.json()
    if payload.get('plan') not in ['free','premium']: raise HTTPException(422,'Invalid plan.')
    with db() as c:
        changed=c.execute("UPDATE accounts SET plan=? WHERE email=? AND demo=0 AND role='member'",(payload['plan'],payload.get('email','').lower())).rowcount
    if not changed: raise HTTPException(404,'Account not found.')
    return {'ok':True}

from .payments import router as payments_router, options as billing_options, sandbox as billing_sandbox
app.include_router(payments_router)

from .collection import router as collection_router
app.include_router(collection_router)
from .live_collection import router as live_router
app.include_router(live_router)

@app.get('/api/health')
def health():
    try:
        with db() as c:
            c.execute('SELECT 1').fetchone()
            c.execute('SELECT id FROM billing_checkouts LIMIT 0')
            c.execute('SELECT id FROM billing_entitlements LIMIT 0')
        return {'ok':True,'storage':'postgres' if os.getenv('APP_DATABASE_URL') or os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL') else 'sqlite','universe':len(CATALOG)}
    except Exception as exc:
        import logging
        logging.exception('Database health check failed')
        return Response(json.dumps({'ok':False,'error':type(exc).__name__}),status_code=503,media_type='application/json')

if not os.getenv('VERCEL'): init()
DIST=ROOT/'frontend'/'dist'
if DIST.exists():
    app.mount('/assets',StaticFiles(directory=DIST/'assets'),name='assets')
    @app.get('/favicon.svg')
    def favicon(): return FileResponse(DIST/'favicon.svg')
    @app.get('/')
    def index(): return FileResponse(DIST/'index.html')
