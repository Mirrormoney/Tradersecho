"""Newsletter opt-out, provider-event verification and durable dispatch safeguards.
Subscriber sending is deliberately disabled until launch configuration is complete.
"""
import base64,hashlib,hmac,json,os,secrets,time
from html import escape
from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import HTMLResponse
from .community import core,staff
router=APIRouter()

def migrate(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS email_optouts(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,email TEXT NOT NULL,created_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS email_suppressions(email_hash TEXT PRIMARY KEY,reason TEXT NOT NULL,created_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS email_deliveries(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,email TEXT NOT NULL,window_end REAL NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,provider_id TEXT,created_at REAL NOT NULL,first_attempt REAL,lease_until REAL NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS email_events(id TEXT PRIMARY KEY,provider_id TEXT NOT NULL,kind TEXT NOT NULL,received_at REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS email_deliveries_provider ON email_deliveries(provider_id);
    ''')

def email_hash(email):return hashlib.sha256(email.strip().lower().encode()).hexdigest()
def valid_recipient(c,u):
    prefs=c.execute('SELECT frequency FROM digest_preferences WHERE user_id=?',(u['id'],)).fetchone()
    return bool(u['status']=='active' and not u['demo'] and u['email_verified'] and (u['plan']=='premium' or u['role'] in ('owner','admin')) and prefs and prefs['frequency']=='daily' and not c.execute('SELECT 1 FROM email_suppressions WHERE email_hash=?',(email_hash(u['email']),)).fetchone())

def optout_token(c,u):
    token=secrets.token_urlsafe(32)
    c.execute('INSERT INTO email_optouts VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),u['id'],u['email'],time.time()))
    return token

def unsubscribe(token):
    if not 30<=len(token)<=100:raise HTTPException(400,'Invalid unsubscribe link.')
    with core().db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM email_optouts WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if not row:raise HTTPException(400,'Invalid unsubscribe link.')
        # Suppress the original recipient even if their account email later changes.
        c.execute('INSERT INTO email_suppressions VALUES(?,?,?) ON CONFLICT(email_hash) DO NOTHING',(email_hash(row['email']),'unsubscribed',time.time()))
        c.execute("UPDATE digest_preferences SET frequency='off',updated_at=? WHERE user_id=? AND EXISTS(SELECT 1 FROM accounts WHERE id=? AND email=?)",(time.time(),row['user_id'],row['user_id'],row['email']))
        c.execute("UPDATE email_deliveries SET status='cancelled' WHERE email=? AND status IN ('pending','uncertain')",(row['email'],))

def page(body):
    return HTMLResponse('<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Traders Echo email preferences</title><body style="background:#102b24;color:#eff5e7;font:17px Arial;padding:40px;line-height:1.6"><main style="max-width:560px;margin:auto"><h1>Traders Echo</h1>'+body+'<p>Help: info@tradersecho.com</p></main></body></html>',headers={'Referrer-Policy':'no-referrer','Cache-Control':'no-store'})

@router.get('/api/newsletter/unsubscribe')
def unsubscribe_page(token:str=''):
    # GET never changes preferences: mail scanners commonly follow every link.
    if not 30<=len(token)<=100:raise HTTPException(400,'Invalid unsubscribe link.')
    return page('<h2>Stop newsletter emails?</h2><p>Your account and security emails will remain available.</p><form method="post"><input type="hidden" name="token" value="'+escape(token,quote=True)+'"><button style="padding:14px;background:#c4f27a;border:0" type="submit">Unsubscribe from newsletters</button></form>')

@router.post('/api/newsletter/unsubscribe')
async def unsubscribe_post(request:Request,token:str=''):
    from urllib.parse import parse_qs
    raw=await request.body()
    if len(raw)>2048:raise HTTPException(413,'Request too large')
    form=parse_qs(raw.decode('utf-8',errors='replace'))
    unsubscribe(token or form.get('token',[''])[0])
    return page('<h2>You’re unsubscribed.</h2><p>Newsletter delivery is off for this email address. No sign-in is needed.</p>')

def verify_event(raw,headers,secret,now=None):
    now=time.time() if now is None else now
    try:
        stamp=headers['svix-timestamp'];event_id=headers['svix-id']
        if not event_id or len(event_id)>200 or abs(now-int(stamp))>300:raise ValueError()
        key=base64.b64decode(secret.removeprefix('whsec_'),validate=True)
        if len(key)<16:raise ValueError()
        expected=base64.b64encode(hmac.new(key,event_id.encode()+b'.'+stamp.encode()+b'.'+raw,hashlib.sha256).digest()).decode()
        signatures=[x[3:] for x in headers['svix-signature'].split() if x.startswith('v1,')]
        if not any(hmac.compare_digest(expected,x) for x in signatures):raise ValueError()
        event=json.loads(raw)
        if not isinstance(event,dict):raise ValueError()
        return event_id,event
    except (KeyError,ValueError,TypeError):raise HTTPException(400,'Invalid webhook signature or payload')

@router.post('/api/newsletter/events')
async def delivery_event(request:Request):
    secret=os.getenv('RESEND_WEBHOOK_SECRET','')
    if not secret:raise HTTPException(503,'Delivery webhook is not configured')
    raw=await request.body()
    if len(raw)>100000:raise HTTPException(413,'Request too large')
    event_id,event=verify_event(raw,request.headers,secret)
    kind=event.get('type');data=event.get('data') or {}
    if not isinstance(data,dict):raise HTTPException(400,'Invalid event data')
    provider_id=data.get('email_id')
    if kind not in ('email.delivered','email.bounced','email.complained','email.suppressed'):return {'ignored':True}
    if not isinstance(provider_id,str):raise HTTPException(400,'Missing email id')
    recipients=data.get('to',[])
    if isinstance(recipients,str):recipients=[recipients]
    if not isinstance(recipients,list):raise HTTPException(400,'Invalid recipients')
    with core().db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM email_events WHERE id=?',(event_id,)).fetchone():return {'duplicate':True}
        c.execute('INSERT INTO email_events VALUES(?,?,?,?)',(event_id,provider_id,kind,time.time()))
        if kind!='email.delivered':
            stored=c.execute('SELECT email FROM email_deliveries WHERE provider_id=?',(provider_id,)).fetchall()
            recipients=recipients+[r['email'] for r in stored]
            for email in recipients[:50]:
                if isinstance(email,str):
                    c.execute('INSERT INTO email_suppressions VALUES(?,?,?) ON CONFLICT(email_hash) DO NOTHING',(email_hash(email),kind,time.time()))
            c.execute("UPDATE email_deliveries SET status='suppressed' WHERE provider_id=?",(provider_id,))
        else:c.execute("UPDATE email_deliveries SET status='delivered' WHERE provider_id=? AND status NOT IN ('suppressed','cancelled')",(provider_id,))
    return {'ok':True}

@router.get('/api/admin/newsletter/status')
def delivery_status(request:Request):
    staff(request)
    with core().db() as c:
        counts=[dict(r) for r in c.execute('SELECT status,COUNT(*) n FROM email_deliveries GROUP BY status')]
        verified=c.execute("SELECT COUNT(*) FROM accounts WHERE email_verified=1 AND status='active' AND demo=0").fetchone()[0]
        suppressed=c.execute('SELECT COUNT(*) FROM email_suppressions').fetchone()[0]
    return {'sending_enabled':False,'verified_accounts':verified,'suppressed_addresses':suppressed,'deliveries':counts,'webhook_configured':bool(os.getenv('RESEND_WEBHOOK_SECRET')),'note':'Private preparation only. Subscriber delivery is not activated.'}


def prepare_delivery(u):
    """Freeze one payload per recipient/day. Does not send or enable a scheduler."""
    from .newsletter import render
    from .digest import build,personalized
    # Never accept another user's pre-personalized report from a caller.
    report=personalized(build(),u)
    if not report.get('ready') or not 0<=time.time()-report['window_end']<=36*3600:raise ValueError('A fresh complete report is required')
    key=hashlib.sha256(('daily:'+str(report['window_end'])+':'+u['id']+':'+u['email']).encode()).hexdigest()
    with core().db() as c:
        c.execute('BEGIN IMMEDIATE')
        current=c.execute('SELECT * FROM accounts WHERE id=?',(u['id'],)).fetchone()
        if not current or current['email']!=u['email'] or not valid_recipient(c,current):raise ValueError('Recipient is not eligible')
        if c.execute('SELECT 1 FROM email_deliveries WHERE id=?',(key,)).fetchone():return key
        token=optout_token(c,current);url=core().ORIGIN+'/api/newsletter/unsubscribe?token='+token
        content=render(report,current['display_name'],core().ORIGIN)
        content['html']=content['html'].replace('Email preferences</a>', 'Email preferences</a> · <a href="'+escape(url,quote=True)+'">Unsubscribe</a>')
        content['text']+='\nUnsubscribe: '+url
        payload={'from':'Tradersecho <newsletter@tradersecho.com>','to':[current['email']],'reply_to':'info@tradersecho.com',**content,'headers':{'List-Unsubscribe':'<'+url+'>','List-Unsubscribe-Post':'List-Unsubscribe=One-Click'}}
        c.execute('INSERT INTO email_deliveries(id,user_id,email,window_end,payload,status,created_at) VALUES(?,?,?,?,?,?,?)',(key,current['id'],current['email'],report['window_end'],json.dumps(payload),'pending',time.time()))
    return key


def claim_delivery(key,now=None):
    """Atomic retry gate; the identical frozen payload/key must be used for every retry."""
    now=time.time() if now is None else now
    with core().db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM email_deliveries WHERE id=?',(key,)).fetchone()
        if not row or row['status'] not in ('pending','uncertain','sending') or row['lease_until']>now:return None
        u=c.execute('SELECT * FROM accounts WHERE id=?',(row['user_id'],)).fetchone()
        if not u or u['email']!=row['email'] or not valid_recipient(c,u):
            c.execute("UPDATE email_deliveries SET status='cancelled' WHERE id=?",(key,));return None
        if now-row['window_end']>36*3600 or row['first_attempt'] and now-row['first_attempt']>23*3600:
            c.execute("UPDATE email_deliveries SET status='manual_review' WHERE id=?",(key,));return None
        c.execute("UPDATE email_deliveries SET status='sending',first_attempt=COALESCE(first_attempt,?),lease_until=?,attempts=attempts+1 WHERE id=?",(now,now+120,key))
        return {'payload':json.loads(row['payload']),'idempotency_key':'newsletter-'+key}
