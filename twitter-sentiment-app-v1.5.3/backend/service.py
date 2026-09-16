"""Tradersecho v2. Run from project root: uvicorn backend.service:app."""
import os, sqlite3, secrets, hashlib, hmac, re, math, random, json, time
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager
from fastapi import FastAPI, Request, Response, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = os.getenv('TRADERSECHO_DB', str(ROOT / 'data' / 'tradersecho.sqlite'))
DEMO = os.getenv('DEMO_ENABLED', 'true').lower() == 'true'
SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
ORIGIN = os.getenv('APP_ORIGIN', 'http://127.0.0.1:8000').rstrip('/')
CATALOG = {'NVDA':('NVIDIA','Semiconductors'), 'TSLA':('Tesla','Automotive'), 'PLTR':('Palantir','Software'), 'AMD':('Advanced Micro Devices','Semiconductors'), 'AAPL':('Apple','Technology'), 'MSFT':('Microsoft','Software'), 'AMZN':('Amazon','Consumer'), 'META':('Meta Platforms','Technology'), 'GOOGL':('Alphabet','Technology'), 'COIN':('Coinbase','Financials'), 'RKLB':('Rocket Lab','Aerospace'), 'ASTS':('AST SpaceMobile','Telecom'), 'SOFI':('SoFi Technologies','Financials'), 'INTC':('Intel','Semiconductors'), 'MU':('Micron Technology','Semiconductors'), 'AVGO':('Broadcom','Semiconductors')}
app = FastAPI(title='Tradersecho', version='2.0.0')

@contextmanager
def db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

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
    if DEMO: seed_demo()

def seed_demo():
    with db() as c:
        if c.execute("SELECT 1 FROM meta WHERE key='demo_anchor'").fetchone(): return
        anchor = int(time.time())
        rng = random.Random(427)
        authors = ['signal_lab','growth_notes','chip_observer','market_journal','orbital_research','value_compass']
        phrases = {'bullish':['Demand looks strong. Watching the next earnings update.','Bullish on the long-term opportunity; execution is the key.','Breakout potential as revenue growth accelerates.'], 'bearish':['Valuation looks stretched. Risk of a pullback here.','Bearish near term: margins under pressure and guidance is weak.','The rally feels overextended. Watching downside risk.'], 'neutral':['Earnings on my watchlist. Waiting for the numbers.','Tracking the volume today; no position yet.','Interesting discussion, but the thesis needs more evidence.']}
        for day in range(61):
            for idx,ticker in enumerate(CATALOG):
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
    return dict(row) if row else None

def public_account(u):
    return {'email':u['email'],'plan':u['plan'],'demo':bool(u['demo'])}

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

@app.post('/api/auth/signup')
def signup(payload:Credentials,request:Request,response:Response):
    throttle(request)
    email=payload.email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): raise HTTPException(422,'Enter a valid email address.')
    uid=secrets.token_hex(16)
    with db() as c:
        try: c.execute('INSERT INTO accounts(id,email,password) VALUES(?,?,?)',(uid,email,password_hash(payload.password)))
        except sqlite3.IntegrityError: raise HTTPException(409,'An account with this email already exists.')
    session(response,uid)
    return {'email':email,'plan':'free','demo':False}

@app.post('/api/auth/login')
def login(payload:Credentials,request:Request,response:Response):
    throttle(request)
    with db() as c: u=c.execute('SELECT * FROM accounts WHERE email=? AND demo=0',(payload.email.strip().lower(),)).fetchone()
    stored=u['password'] if u else password_hash('unmatched-password')
    if not hmac.compare_digest(password_hash(payload.password,stored.split(':')[0]),stored) or not u:
        raise HTTPException(401,'Email or password is incorrect.')
    session(response,u['id'])
    return public_account(u)

@app.post('/api/auth/demo')
def demo_account(request:Request,response:Response,plan:str=Query('premium',pattern='^(free|premium)$')):
    if not DEMO: raise HTTPException(404)
    throttle(request)
    uid=secrets.token_hex(16)
    with db() as c:
        c.execute('INSERT INTO accounts(id,email,plan,demo) VALUES(?,?,?,1)',(uid,f'{plan}-preview-{uid[:6]}@demo.local',plan))
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
    if not u or u['plan']!='premium' or (u['demo'] and source!='demo'): raise HTTPException(403,'Premium membership is required for this feature.')

def reference(source,c):
    if source=='demo':
        if not DEMO: raise HTTPException(404,'Sample data is disabled.')
        return float(c.execute("SELECT value FROM meta WHERE key='demo_anchor'").fetchone()[0])
    return time.time()

@app.get('/api/status')
def status():
    with db() as c:
        row=c.execute("SELECT COUNT(*) n,MAX(ts) latest,MIN(ts) earliest FROM posts WHERE source='x'").fetchone()
        sync=c.execute("SELECT value FROM meta WHERE key='last_sync'").fetchone()
    return {'demo_enabled':DEMO,'x_configured':bool(os.getenv('X_BEARER_TOKEN')),'live_posts':row['n'],'latest_post':row['latest'],'earliest_post':row['earliest'],'last_sync':json.loads(sync[0]) if sync else None,'billing_configured':all(os.getenv(k) for k in ['STRIPE_SECRET_KEY','STRIPE_PRICE_ID','STRIPE_WEBHOOK_SECRET']),'catalog':[{'ticker':t,'name':v[0],'sector':v[1]} for t,v in CATALOG.items()]}

@app.get('/api/rankings')
def rankings(request:Request,window:int=Query(1,ge=1,le=30),source:str=Query('demo',pattern='^(demo|x)$')):
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
    rows.sort(key=lambda x:x['heat'],reverse=True)
    return {'rows':rows,'as_of':now,'source':source,'window':window,'comparison_complete':bool(earliest and earliest<=prev),'coverage_days':round((now-earliest)/86400,1) if earliest else 0}

@app.get('/api/posts')
def posts(request:Request,ticker:str='',window:int=Query(1,ge=1,le=30),source:str=Query('demo',pattern='^(demo|x)$'),tracked:bool=False,order:str=Query('latest',pattern='^(latest|engagement)$')):
    args=[source]; clauses=['p.source=?']
    with db() as c:
        now=reference(source,c)
        clauses+=['p.ts>?','p.ts<=?'];args += [now-window*86400,now]
        if ticker: clauses.append('m.ticker=?');args.append(ticker.upper())
        if tracked:
            u=account(request);premium(u,source)
            clauses.append('p.author IN (SELECT handle FROM handles WHERE user_id=?)');args.append(u['id'])
        ordering='p.likes DESC,p.ts DESC' if order=='engagement' else 'p.ts DESC'
        rows=c.execute('SELECT p.*,GROUP_CONCAT(DISTINCT m.ticker) tickers FROM posts p JOIN mentions m ON p.source=m.source AND p.id=m.post_id WHERE '+' AND '.join(clauses)+' GROUP BY p.source,p.id ORDER BY '+ordering+' LIMIT 50',args).fetchall()
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
    handle=payload.handle.lstrip('@').lower()
    if not re.fullmatch(r'[A-Za-z0-9_]{1,15}',handle): raise HTTPException(422,'Enter a valid X handle (letters, numbers, underscores).')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT COUNT(*) FROM handles WHERE user_id=?',(u['id'],)).fetchone()[0]>=25: raise HTTPException(403,'You can track up to 25 accounts.')
        c.execute('INSERT INTO handles VALUES(?,?,?) ON CONFLICT(user_id,handle) DO UPDATE SET note=excluded.note',(u['id'],handle,payload.note))
    return {'ok':True}

@app.delete('/api/handles/{handle}')
def remove_handle(handle:str,request:Request):
    u=account(request);premium(u)
    with db() as c: c.execute('DELETE FROM handles WHERE user_id=? AND handle=?',(u['id'],handle))
    return {'ok':True}

def admin(request):
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

def ingest(items):
    normalized=[]
    for item in items:
        pid=str(item.get('id',''));author=str(item.get('author','')).lstrip('@').lower();text=str(item.get('text',''))
        if not re.fullmatch(r'\d{1,30}',pid) or not re.fullmatch(r'[a-z0-9_]{1,15}',author) or not text or len(text)>25000: raise ValueError('Each post needs a numeric X id, valid author handle, text and UTC created_at.')
        ts=datetime.fromisoformat(str(item.get('created_at','')).replace('Z','+00:00'))
        if ts.tzinfo is None: raise ValueError('created_at must include a timezone.')
        ts=ts.timestamp()
        if ts>time.time()+60: raise ValueError('Posts cannot be dated in the future.')
        tickers=set(re.findall(r'\$([A-Za-z]{1,5}(?:\.[A-Za-z])?)\b',text.upper())) & set(CATALOG)
        sentiment=item.get('sentiment') or classify(text)
        if sentiment not in ['bullish','bearish','neutral']: raise ValueError('Invalid sentiment label.')
        likes=int(item.get('likes',0))
        if likes<0: raise ValueError('Likes must be nonnegative.')
        normalized.append((pid,author,text,ts,sentiment,likes,tickers))
    added=0; mentions=0
    with db() as c:
        for pid,author,text,ts,sentiment,likes,tickers in normalized:
            if not tickers: continue
            cur=c.execute('INSERT OR IGNORE INTO posts VALUES(?,?,?,?,?,?,?)',('x',pid,author,text,ts,sentiment,likes));added+=cur.rowcount
            for ticker in tickers: mentions+=c.execute('INSERT OR IGNORE INTO mentions VALUES(?,?,?)',('x',pid,ticker)).rowcount
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
        changed=c.execute('UPDATE accounts SET plan=? WHERE email=? AND demo=0',(payload['plan'],payload.get('email','').lower())).rowcount
    if not changed: raise HTTPException(404,'Account not found.')
    return {'ok':True}

@app.post('/api/billing/checkout')
async def checkout(request:Request):
    import httpx
    u=account(request)
    if u['demo']: raise HTTPException(400,'Create a real account before subscribing.')
    key=os.getenv('STRIPE_SECRET_KEY');price=os.getenv('STRIPE_PRICE_ID')
    if not key or not price or not os.getenv('STRIPE_WEBHOOK_SECRET'): raise HTTPException(503,'Subscriptions are not open yet. No payment has been taken.')
    async with httpx.AsyncClient(timeout=20) as client:
        r=await client.post('https://api.stripe.com/v1/checkout/sessions',auth=(key,''),data={'mode':'subscription','customer_email':u['email'],'client_reference_id':u['id'],'subscription_data[metadata][account_id]':u['id'],'line_items[0][price]':price,'line_items[0][quantity]':'1','success_url':ORIGIN+'/?billing=success','cancel_url':ORIGIN+'/?billing=cancelled'})
    if not r.is_success: raise HTTPException(502,'Checkout is unavailable. Please try again later.')
    return {'url':r.json()['url']}

@app.post('/api/billing/webhook')
async def webhook(request:Request):
    secret=os.getenv('STRIPE_WEBHOOK_SECRET','')
    if not secret: raise HTTPException(503)
    body=await request.body();parts=request.headers.get('stripe-signature','').split(',')
    stamps=[v[2:] for v in parts if v.startswith('t=')];signatures=[v[3:] for v in parts if v.startswith('v1=')]
    try: stamp=int(stamps[0])
    except (IndexError,ValueError): raise HTTPException(400,'Invalid signature')
    expected=hmac.new(secret.encode(),str(stamp).encode()+b'.'+body,hashlib.sha256).hexdigest()
    if abs(time.time()-stamp)>300 or not any(hmac.compare_digest(expected,s) for s in signatures): raise HTTPException(400,'Invalid signature')
    event=json.loads(body)
    if event['type'] in ['customer.subscription.created','customer.subscription.updated','customer.subscription.deleted']:
        # Fetch canonical status so out-of-order events cannot restore a cancelled plan.
        import httpx
        obj=event['data']['object']
        async with httpx.AsyncClient(timeout=20) as client:
            r=await client.get('https://api.stripe.com/v1/subscriptions/'+obj['id'],auth=(os.getenv('STRIPE_SECRET_KEY',''),''))
        if not r.is_success: raise HTTPException(502,'Unable to verify subscription')
        sub=r.json();uid=sub.get('metadata',{}).get('account_id')
        with db() as c:
            if not c.execute('SELECT 1 FROM webhook_events WHERE id=?',(event['id'],)).fetchone():
                c.execute('UPDATE accounts SET plan=?,stripe_customer=? WHERE id=? AND demo=0',('premium' if sub['status'] in ['active','trialing'] else 'free',sub['customer'],uid))
                c.execute('INSERT INTO webhook_events VALUES(?)',(event['id'],))
    return {'received':True}

init()
DIST=ROOT/'frontend'/'dist'
if DIST.exists():
    app.mount('/assets',StaticFiles(directory=DIST/'assets'),name='assets')
    @app.get('/favicon.svg')
    def favicon(): return FileResponse(DIST/'favicon.svg')
    @app.get('/')
    def index(): return FileResponse(DIST/'index.html')
