"""Account administration, owner bootstrap, privacy-light analytics and member room."""
import hashlib, hmac, json, re, secrets, time
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from .database import IntegrityError

router=APIRouter()

def core():
    from . import service
    return service

def available_default_name(c,uid,prefix='Trader'):
    candidate=prefix+'-'+uid[:6]
    while c.execute('SELECT 1 FROM accounts WHERE LOWER(TRIM(display_name))=?',(candidate.lower(),)).fetchone():
        candidate=prefix+'-'+secrets.token_hex(8)
    return candidate

def migrate(c):
    columns={r['name'] for r in c.execute('PRAGMA table_info(accounts)')}
    for name,kind in {'role':"TEXT NOT NULL DEFAULT 'member'",'status':"TEXT NOT NULL DEFAULT 'active'",'display_name':"TEXT NOT NULL DEFAULT ''",'created_at':'REAL','last_seen':'REAL','last_login':'REAL'}.items():
        if name not in columns: c.execute(f'ALTER TABLE accounts ADD COLUMN {name} {kind}')
    c.execute("UPDATE accounts SET display_name='Trader-'||substr(id,1,6) WHERE display_name=''")
    if not c.execute("SELECT 1 FROM meta WHERE key='unique_display_names_v1'").fetchone():
        for row in c.execute('SELECT id,display_name FROM accounts').fetchall():
            c.execute('UPDATE accounts SET display_name=? WHERE id=?',(' '.join(row['display_name'].split()),row['id']))
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS accounts_display_name_unique ON accounts(LOWER(TRIM(display_name)))')
        c.execute("INSERT INTO meta VALUES('unique_display_names_v1','1')")
    c.executescript('''
    CREATE TABLE IF NOT EXISTS owner_invites(hash TEXT PRIMARY KEY,email TEXT,expires REAL,used_by TEXT,created_at REAL);
    CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT,action TEXT,target TEXT,detail TEXT,ts REAL);
    CREATE TABLE IF NOT EXISTS traffic_events(id TEXT PRIMARY KEY,day TEXT,visitor TEXT,page TEXT,ts REAL);
    CREATE INDEX IF NOT EXISTS traffic_day ON traffic_events(day);
    CREATE TABLE IF NOT EXISTS chat_messages(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT REFERENCES accounts(id),body TEXT,ticker TEXT,ts REAL,hidden INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS chat_reports(message_id INTEGER REFERENCES chat_messages(id),user_id TEXT REFERENCES accounts(id),reason TEXT,ts REAL,resolved INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(message_id,user_id));
    CREATE TABLE IF NOT EXISTS x_counts(ticker TEXT,start REAL,end REAL,n INTEGER,query TEXT,fetched_at REAL,PRIMARY KEY(ticker,start));
    CREATE TABLE IF NOT EXISTS x_spend(id INTEGER PRIMARY KEY AUTOINCREMENT,month TEXT,kind TEXT,reserved REAL,actual_estimate REAL,ts REAL,status TEXT);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
    ''')

def audit(c,u,action,target='',detail=''):
    c.execute('INSERT INTO audit_log(actor,action,target,detail,ts) VALUES(?,?,?,?,?)',(u['id'],action,target,detail,time.time()))

def staff(request,owner=False):
    u=core().account(request)
    if u['demo'] or u['role'] not in (['owner'] if owner else ['owner','admin']): raise HTTPException(403,'Administrator access required.')
    return u

def create_owner_invite(email=None):
    """Local operator only. Never expose this as a public endpoint."""
    token=secrets.token_urlsafe(32)
    with core().db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT 1 FROM accounts WHERE role='owner'").fetchone(): raise ValueError('An owner already exists. Sign in with that account.')
        c.execute('DELETE FROM owner_invites WHERE used_by IS NULL')
        c.execute('INSERT INTO owner_invites VALUES(?,?,?,NULL,?)',(hashlib.sha256(token.encode()).hexdigest(),email.strip().lower() if email else None,time.time()+72*3600,time.time()))
    return token

def claim_owner(c,code,email,uid):
    invite=c.execute('SELECT * FROM owner_invites WHERE hash=?',(hashlib.sha256(code.encode()).hexdigest(),)).fetchone()
    if not invite or invite['used_by'] or invite['expires']<time.time() or (invite['email'] and invite['email']!=email): raise HTTPException(403,'Invalid or expired owner invitation.')
    if c.execute("SELECT 1 FROM accounts WHERE role='owner'").fetchone(): raise HTTPException(409,'The owner account has already been claimed.')
    c.execute("UPDATE accounts SET role='owner',plan='premium' WHERE id=? AND demo=0",(uid,))
    c.execute('UPDATE owner_invites SET used_by=? WHERE hash=?',(uid,invite['hash']))
    audit(c,{'id':uid},'owner_claimed',uid)

class Claim(BaseModel):
    code:str=Field(min_length=20,max_length=150)

@router.post('/api/owner/claim')
def claim(payload:Claim,request:Request):
    s=core();s.throttle(request);u=s.account(request)
    if u['demo']: raise HTTPException(403,'Create a real account to claim ownership.')
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE');claim_owner(c,payload.code,u['email'],u['id'])
    return s.public_account(s.account(request))

class Profile(BaseModel):
    display_name:str=Field(min_length=3,max_length=30)

class PasswordChange(BaseModel):
    current_password:str=Field(min_length=1,max_length=128)
    new_password:str=Field(min_length=10,max_length=128)

@router.post('/api/auth/change-password')
def change_password(payload:PasswordChange,request:Request,response:Response):
    s=core();u=s.account(request);s.throttle(request)
    if u['demo']:raise HTTPException(403,'Sample accounts cannot change passwords. Create your own account first.')
    token=secrets.token_urlsafe(32)
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        current=c.execute('SELECT password,status FROM accounts WHERE id=?',(u['id'],)).fetchone()
        if current['status']!='active':raise HTTPException(403,'This account is not active.')
        stored=current['password']
        if not stored or not hmac.compare_digest(s.password_hash(payload.current_password,stored.split(':')[0]),stored):
            raise HTTPException(400,'Your current password is incorrect.')
        if payload.current_password==payload.new_password:raise HTTPException(400,'Choose a different new password.')
        c.execute('UPDATE accounts SET password=? WHERE id=?',(s.password_hash(payload.new_password),u['id']))
        c.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],))
        c.execute('DELETE FROM account_tokens WHERE user_id=?',(u['id'],))
        c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),u['id'],time.time()+7*86400))
        audit(c,u,'password_changed',u['id'])
    response.set_cookie('te_session',token,httponly=True,secure=s.SECURE,samesite='lax',max_age=7*86400,path='/')
    return {'ok':True}

@router.put('/api/profile')
def profile(payload:Profile,request:Request):
    s=core();u=s.account(request);name=' '.join(payload.display_name.split())
    if not re.fullmatch(r'[A-Za-z0-9 _.-]{3,30}',name): raise HTTPException(422,'Use 3–30 letters, numbers, spaces, dots, dashes or underscores.')
    if not re.search(r'[A-Za-z0-9]',name):raise HTTPException(422,'Include at least one letter or number in your name.')
    try:
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT 1 FROM accounts WHERE LOWER(TRIM(display_name))=? AND id!=?',(name.lower(),u['id'])).fetchone():
                raise HTTPException(409,'That display name is already taken. Please choose another.')
            c.execute('UPDATE accounts SET display_name=? WHERE id=?',(name,u['id']))
    except IntegrityError:raise HTTPException(409,'That display name is already taken. Please choose another.')
    return s.public_account(s.account(request))

@router.get('/api/admin/users')
def users(request:Request,q:str=Query('',max_length=100),page:int=Query(1,ge=1),include_demo:bool=False):
    staff(request)
    clause='WHERE (email LIKE ? OR display_name LIKE ?)'+('' if include_demo else ' AND demo=0')
    with core().db() as c:
        args=['%'+q+'%']*2
        total=c.execute('SELECT COUNT(*) FROM accounts '+clause,args).fetchone()[0]
        rows=c.execute('SELECT id,email,display_name,role,status,plan,demo,created_at,last_seen,last_login FROM accounts '+clause+' ORDER BY COALESCE(created_at,0) DESC,id LIMIT 30 OFFSET ?',args+[(page-1)*30]).fetchall()
    return {'rows':[dict(r) for r in rows],'total':total,'page':page,'pages':max(1,(total+29)//30)}

class UserUpdate(BaseModel):
    plan:Literal['free','premium']|None=None
    status:Literal['active','suspended']|None=None
    role:Literal['member','admin']|None=None

@router.patch('/api/admin/users/{uid}')
def update_user(uid:str,payload:UserUpdate,request:Request):
    s=core();u=staff(request,owner=payload.role is not None)
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        target=c.execute('SELECT * FROM accounts WHERE id=?',(uid,)).fetchone()
        if not target: raise HTTPException(404,'Account not found.')
        if target['demo']: raise HTTPException(400,'Preview accounts cannot be administered.')
        if target['role']=='owner' or uid==u['id']: raise HTTPException(403,'Your account and the owner account are protected.')
        if target['role']=='admin' and u['role']!='owner': raise HTTPException(403,'Only the owner can manage administrators.')
        changes=payload.model_dump(exclude_none=True)
        for key,val in changes.items(): c.execute(f'UPDATE accounts SET {key}=? WHERE id=?',(val,uid))
        if payload.status=='suspended': c.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
        audit(c,u,'account_updated',uid,json.dumps(changes))
    return {'ok':True}

class Visit(BaseModel):
    event_id:str=Field(pattern=r'^[a-f0-9-]{32,36}$')
    visitor_id:str=Field(pattern=r'^[a-f0-9-]{32,36}$')
    page:Literal['home','market','briefing','watchlist','voices','data','community','admin','account','owner']

@router.post('/api/analytics/visit')
def visit(payload:Visit,request:Request):
    if request.headers.get('dnt')=='1' or request.headers.get('sec-gpc')=='1' or re.search(r'bot|crawler|spider',request.headers.get('user-agent',''),re.I): return {'counted':False}
    s=core();u=s.account(request,False)
    if u and (u['demo'] or u['role'] in ['owner','admin']): return {'counted':False}
    day=datetime.now(timezone.utc).date().isoformat()
    visitor=hashlib.sha256((day+':'+payload.visitor_id).encode()).hexdigest()
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('DELETE FROM traffic_events WHERE ts<?',(time.time()-30*86400,))
        n=c.execute('SELECT COUNT(*) FROM traffic_events WHERE day=? AND visitor=?',(day,visitor)).fetchone()[0]
        if n>=1000: return {'counted':False}
        c.execute('INSERT OR IGNORE INTO traffic_events VALUES(?,?,?,?,?)',(payload.event_id,day,visitor,payload.page,time.time()))
    return {'counted':True}

@router.get('/api/admin/overview')
def overview(request:Request):
    staff(request);now=time.time();today=datetime.now(timezone.utc).date().isoformat()
    with core().db() as c:
        totals=dict(c.execute("SELECT COUNT(*) users,SUM(plan='premium') premium,SUM(status='suspended') suspended,SUM(created_at>?) new_users FROM accounts WHERE demo=0",(now-30*86400,)).fetchone())
        traffic=[dict(r) for r in c.execute('SELECT day,COUNT(*) views,COUNT(DISTINCT visitor) visitors FROM traffic_events WHERE ts>? GROUP BY day ORDER BY day',(now-30*86400,))]
        pages=[dict(r) for r in c.execute('SELECT page,COUNT(*) views FROM traffic_events WHERE ts>? GROUP BY page ORDER BY views DESC',(now-30*86400,))]
        logs=[dict(r) for r in c.execute('SELECT action,target,detail,ts FROM audit_log ORDER BY id DESC LIMIT 15')]
    return {'accounts':totals,'traffic':traffic,'pages':pages,'audit':logs,'today':today,'views_30d':sum(x['views'] for x in traffic),'visitors_today':next((x['visitors'] for x in traffic if x['day']==today),0)}

def member(request):
    u=core().account(request);core().premium(u,'x')
    if u['demo']: raise HTTPException(403,'The community is for real Premium accounts. Preview accounts cannot enter.')
    return u

class Message(BaseModel):
    body:str=Field(min_length=1,max_length=1500)
    ticker:str=Field(default='',max_length=6)

@router.get('/api/community/messages')
def messages(request:Request,before:int|None=Query(None,ge=1),ticker:str=Query('',max_length=6)):
    member(request);args=[];clause='WHERE m.hidden=0'
    if before: clause+=' AND m.id<?';args.append(before)
    if ticker: clause+=' AND m.ticker=?';args.append(ticker.upper())
    with core().db() as c:
        rows=c.execute('SELECT m.id,m.body,m.ticker,m.ts,a.display_name,a.role,a.plan FROM chat_messages m JOIN accounts a ON m.user_id=a.id '+clause+' ORDER BY m.id DESC LIMIT 50',args).fetchall()
    return [dict(r) for r in reversed(rows)]

@router.post('/api/community/messages')
def send(payload:Message,request:Request):
    s=core();u=member(request);body=payload.body.strip();ticker=payload.ticker.upper()
    if not body: raise HTTPException(422,'Write an idea before posting.')
    if ticker and ticker not in s.CATALOG: raise HTTPException(422,'Choose a supported ticker or General.')
    now=time.time()
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        recent=c.execute('SELECT COUNT(*) FROM chat_messages WHERE user_id=? AND ts>?',(u['id'],now-60)).fetchone()[0]
        last=c.execute('SELECT ts FROM chat_messages WHERE user_id=? ORDER BY id DESC LIMIT 1',(u['id'],)).fetchone()
        if recent>=5 or (last and now-last[0]<3): raise HTTPException(429,'Please slow down. Maximum five messages per minute.')
        cur=c.execute('INSERT INTO chat_messages(user_id,body,ticker,ts) VALUES(?,?,?,?)',(u['id'],body,ticker,now))
    return {'id':cur.lastrowid}

class Report(BaseModel):
    reason:str=Field(min_length=3,max_length=300)

@router.post('/api/community/messages/{mid}/report')
def report(mid:int,payload:Report,request:Request):
    u=member(request)
    with core().db() as c:
        if not c.execute('SELECT 1 FROM chat_messages WHERE id=? AND hidden=0',(mid,)).fetchone(): raise HTTPException(404,'Message not found.')
        c.execute('INSERT OR IGNORE INTO chat_reports(message_id,user_id,reason,ts) VALUES(?,?,?,?)',(mid,u['id'],payload.reason,time.time()))
    return {'ok':True}

@router.get('/api/admin/reports')
def reports(request:Request):
    staff(request)
    with core().db() as c:
        return [dict(r) for r in c.execute('SELECT r.message_id,r.reason,r.ts,m.body,m.hidden,a.display_name FROM chat_reports r JOIN chat_messages m ON m.id=r.message_id JOIN accounts a ON a.id=m.user_id WHERE r.resolved=0 ORDER BY r.ts DESC LIMIT 100')]

class Moderate(BaseModel):
    hidden:bool

@router.patch('/api/admin/messages/{mid}')
def moderate(mid:int,payload:Moderate,request:Request):
    u=staff(request)
    with core().db() as c:
        if not c.execute('SELECT 1 FROM chat_messages WHERE id=?',(mid,)).fetchone(): raise HTTPException(404,'Message not found.')
        c.execute('UPDATE chat_messages SET hidden=? WHERE id=?',(int(payload.hidden),mid))
        c.execute('UPDATE chat_reports SET resolved=1 WHERE message_id=?',(mid,))
        audit(c,u,'message_hidden' if payload.hidden else 'message_restored',str(mid))
    return {'ok':True}

class DataSettings(BaseModel):
    intraday_enabled:bool=False
    hourly_top:int=Field(default=10,ge=1,le=10)
    on_demand_daily_limit:int=Field(default=30,ge=0,le=30)
    daily_post_limit:int=Field(default=120,ge=10,le=500)
    daily_profile_limit:int=Field(default=32,ge=0,le=100)
    enabled:bool=False
    monthly_budget:float=Field(default=185,ge=1,le=200)
    sample_tickers:int=Field(default=3,ge=1,le=5)
    sample_size:int=Field(default=10,ge=10,le=100)

def data_settings(c):
    row=c.execute("SELECT value FROM settings WHERE key='x_collection'").fetchone()
    return {**DataSettings().model_dump(),**(json.loads(row[0]) if row else {})}

@router.get('/api/admin/data-budget')
def data_budget(request:Request):
    staff(request);month=datetime.now(timezone.utc).strftime('%Y-%m')
    with core().db() as c:
        settings=data_settings(c)
        spent=c.execute('SELECT COALESCE(SUM(COALESCE(actual_estimate,reserved)),0) FROM x_spend WHERE month=?',(month,)).fetchone()[0]
        runs=[dict(r) for r in c.execute('SELECT kind,reserved,actual_estimate,ts,status FROM x_spend ORDER BY id DESC LIMIT 20')]
    extra=(24*settings['hourly_top']*.005+settings['on_demand_daily_limit']*.005) if settings['intraday_enabled'] else 0
    estimate=31*(len(core().CATALOG)*.005+settings['daily_post_limit']*.005+settings['daily_profile_limit']*.01+extra)
    return {**settings,'active_stocks':len(core().CATALOG),'estimated_monthly_cost':round(estimate,2),'budget_fits':estimate<=settings['monthly_budget'],'reserved_or_estimated_spend':round(spent,3),'month':month,'recent_requests':runs}

@router.put('/api/admin/data-budget')
def update_budget(payload:DataSettings,request:Request):
    u=staff(request,owner=True)
    with core().db() as c:
        c.execute("INSERT INTO settings VALUES('x_collection',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(payload.model_dump()),))
        audit(c,u,'data_budget_updated',detail=json.dumps(payload.model_dump()))
    return {'ok':True}
