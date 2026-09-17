"""Single-use email verification and password recovery. Raw tokens never enter storage/logs."""
import hashlib,os,secrets,time
import httpx
from fastapi import APIRouter,Request,HTTPException
from pydantic import BaseModel,Field
router=APIRouter()

def core():
    from . import service
    return service

def migrate(c):
    columns={r['name'] for r in c.execute('PRAGMA table_info(accounts)')}
    if 'email_verified' not in columns:c.execute('ALTER TABLE accounts ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0')
    for name in ['trial_started_at','trial_ends_at']:
        if name not in columns:c.execute('ALTER TABLE accounts ADD COLUMN '+name+' REAL')
    c.executescript('''CREATE TABLE IF NOT EXISTS account_tokens(hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,purpose TEXT NOT NULL,email TEXT NOT NULL,expires REAL NOT NULL,used INTEGER NOT NULL DEFAULT 0);
    CREATE INDEX IF NOT EXISTS account_tokens_user ON account_tokens(user_id,purpose);''')

def configured():
    return bool(os.getenv('RESEND_API_KEY')) and os.getenv('ACCOUNT_EMAIL_ENABLED','false').lower()=='true'

def trial_account(user,now=None):
    u=dict(user);now=time.time() if now is None else now
    u['trial_active']=bool(not u['demo'] and u['status']=='active' and u['email_verified'] and u['plan']=='free' and (u.get('trial_ends_at') or 0)>now)
    if u['trial_active']:u['plan']='premium'
    return u

def start_trial(c,uid):
    u=c.execute('SELECT * FROM accounts WHERE id=?',(uid,)).fetchone()
    if not u or u['demo'] or u['status']!='active' or not u['email_verified'] or u['plan']!='free' or u['role']!='member' or u['trial_started_at']:
        return False
    if c.execute('SELECT 1 FROM billing_entitlements WHERE user_id=?',(uid,)).fetchone():return False
    now=time.time()
    c.execute('UPDATE accounts SET trial_started_at=?,trial_ends_at=? WHERE id=? AND trial_started_at IS NULL',(now,now+7*86400,uid))
    return True

@router.post('/api/auth/start-trial')
def activate_trial(request:Request):
    s=core();u=s.account(request);s.throttle(request)
    if not u['email_verified']:raise HTTPException(403,'Verify your email to start your seven-day trial.')
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        if not start_trial(c,u['id']):raise HTTPException(409,'This account is not eligible for another trial.')
    return s.public_account(s.account(request))

def send_email(email,purpose,token):
    s=core();kind='reset' if purpose=='reset' else 'verify'
    link=s.ORIGIN+'/#'+kind+'='+token
    subject='Reset your Tradersecho password' if kind=='reset' else 'Verify your Tradersecho email'
    text=subject+'\n\nOpen this link and confirm the action:\n'+link+'\n\nThis link expires '+('in one hour.' if kind=='reset' else 'in 24 hours.')+' If you did not request it, ignore this email.\n\nHelp: info@tradersecho.com'
    from .email_brand import message
    from html import escape
    branded=message(subject,text,'<p style="line-height:1.8">'+escape(text).replace(escape(link),'<a href="'+escape(link,quote=True)+'">Open your secure link</a>').replace('\n','<br>')+'</p>')
    try:
        with httpx.Client(timeout=15) as client:
            r=client.post('https://api.resend.com/emails',headers={'Authorization':'Bearer '+os.environ['RESEND_API_KEY'],'Idempotency-Key':'account-'+hashlib.sha256(token.encode()).hexdigest()},json={'from':os.getenv('ACCOUNT_EMAIL_FROM','Tradersecho <info@tradersecho.com>'),'to':[email],'reply_to':'info@tradersecho.com',**branded})
        if not r.is_success:raise RuntimeError('Email provider rejected delivery')
    except (httpx.HTTPError,RuntimeError):raise HTTPException(503,'Account email is temporarily unavailable. Please retry later or contact info@tradersecho.com.')

def issue(email,purpose):
    s=core();now=time.time();token=secrets.token_urlsafe(32);digest=hashlib.sha256(token.encode()).hexdigest()
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        gate='account-email:'+hashlib.sha256(email.encode()).hexdigest()
        recent=c.execute('SELECT reset FROM attempts WHERE key=?',(gate,)).fetchone()
        if recent and recent['reset']>now:return
        c.execute('INSERT INTO attempts VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET reset=excluded.reset',(gate,now+60))
        u=c.execute("SELECT id,email,email_verified FROM accounts WHERE email=? AND demo=0 AND status='active'",(email,)).fetchone()
        if not u or purpose=='verify' and u['email_verified']:return
        c.execute('DELETE FROM account_tokens WHERE expires<?',(now,))
        c.execute('INSERT INTO account_tokens VALUES(?,?,?,?,?,0)',(digest,u['id'],purpose,email,now+(3600 if purpose=='reset' else 86400)))
    try:send_email(email,purpose,token)
    except HTTPException:
        with s.db() as c:c.execute('DELETE FROM account_tokens WHERE hash=?',(digest,))
        raise

class Email(BaseModel):
    email:str=Field(min_length=3,max_length=254)
class Token(BaseModel):
    token:str=Field(min_length=30,max_length=150)
class Reset(Token):
    new_password:str=Field(min_length=10,max_length=128)

@router.post('/api/auth/forgot-password')
def forgot(payload:Email,request:Request):
    core().throttle(request)
    if not configured():raise HTTPException(503,'Account email is not available. Contact info@tradersecho.com.')
    # Identical public response for registered, unregistered and delivery failures.
    try:issue(payload.email.strip().lower(),'reset')
    except HTTPException:pass
    return {'message':'If this email has an active account, a reset link will arrive shortly. Check spam or contact info@tradersecho.com if it does not arrive.'}

@router.post('/api/auth/send-verification')
def send_verification(request:Request):
    s=core();u=s.account(request);s.throttle(request)
    if u['demo']:raise HTTPException(403,'Sample accounts cannot verify email.')
    if not configured():raise HTTPException(503,'Account email is temporarily unavailable. Contact info@tradersecho.com.')
    issue(u['email'],'verify')
    return {'message':'Check your inbox for a verification link. You can request another in one minute.'}

def consume(c,token,purpose):
    hashed=hashlib.sha256(token.encode()).hexdigest()
    row=c.execute("SELECT t.*,a.status FROM account_tokens t JOIN accounts a ON a.id=t.user_id AND a.email=t.email WHERE t.hash=? AND t.purpose=? AND t.used=0 AND t.expires>?",(hashed,purpose,time.time())).fetchone()
    if not row or row['status']!='active':raise HTTPException(400,'This link is invalid or expired. Request a new one.')
    c.execute('UPDATE account_tokens SET used=1 WHERE hash=?',(hashed,))
    return row

@router.post('/api/auth/reset-password')
def reset(payload:Reset,request:Request):
    s=core();s.throttle(request)
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE');row=consume(c,payload.token,'reset')
        c.execute('UPDATE accounts SET password=?,email_verified=1 WHERE id=?',(s.password_hash(payload.new_password),row['user_id']))
        c.execute('DELETE FROM sessions WHERE user_id=?',(row['user_id'],))
        c.execute('DELETE FROM account_tokens WHERE user_id=?',(row['user_id'],))
    return {'message':'Password reset. Sign in with your new password. All previous sessions have been signed out.'}

@router.post('/api/auth/verify-email')
def verify(payload:Token,request:Request):
    s=core();s.throttle(request)
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE');row=consume(c,payload.token,'verify')
        c.execute('UPDATE accounts SET email_verified=1 WHERE id=?',(row['user_id'],))
        started=start_trial(c,row['user_id'])
        c.execute("DELETE FROM account_tokens WHERE user_id=? AND purpose='verify'",(row['user_id'],))
    return {'message':'Email verified. Your seven-day Premium trial has started. No card required and no automatic charges.' if started else 'Email verified. You can return to your account.'}
