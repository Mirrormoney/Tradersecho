"""Read-only customer API. Launch remains disabled until redistribution is approved."""
import hashlib, os, secrets, time, threading
from datetime import datetime, timezone
from urllib.parse import quote
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse

router=APIRouter()
MONTHLY_LIMIT=10000
MINUTE_LIMIT=10
_cache={}
_lock=threading.Lock()

def core():
    from . import service
    return service

def enabled():
    return os.getenv('CUSTOMER_API_ENABLED','false').lower()=='true' and os.getenv('CUSTOMER_API_RIGHTS_APPROVED','false').lower()=='true'

def require_enabled():
    if not enabled():raise HTTPException(503,'API access is not open for purchase or use yet.')

def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS customer_api_subscriptions(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,active INTEGER NOT NULL,updated_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS customer_api_keys(user_id TEXT PRIMARY KEY,key_hash TEXT NOT NULL UNIQUE,created_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS customer_api_usage(user_id TEXT PRIMARY KEY,month TEXT NOT NULL,monthly_used INTEGER NOT NULL,minute INTEGER NOT NULL,minute_used INTEGER NOT NULL);
    ''')

def paid_member(c,uid):
    row=c.execute("SELECT plan,role,status,demo FROM accounts WHERE id=?",(uid,)).fetchone()
    return bool(row and row['status']=='active' and not row['demo'] and (row['plan']=='premium' or row['role'] in ('owner','admin')))

def subscribed(c,uid):
    return bool(c.execute('SELECT 1 FROM customer_api_subscriptions WHERE user_id=? AND active=1',(uid,)).fetchone())

@router.get('/api/customer-api/status')
def status(request:Request):
    u=core().account(request)
    with core().db() as c:
        migrate(c)
        key=c.execute('SELECT created_at FROM customer_api_keys WHERE user_id=?',(u['id'],)).fetchone()
        usage=c.execute('SELECT month,monthly_used FROM customer_api_usage WHERE user_id=?',(u['id'],)).fetchone()
        month=datetime.now(timezone.utc).strftime('%Y-%m')
        return {'enabled':enabled(),'eligible':paid_member(c,u['id']),'subscribed':subscribed(c,u['id']),'has_key':bool(key),'used':usage['monthly_used'] if usage and usage['month']==month else 0,'limit':MONTHLY_LIMIT,'month':month}

@router.post('/api/customer-api/key')
def create_key(request:Request):
    require_enabled();s=core();u=s.account(request);s.throttle(request)
    token='te_live_'+secrets.token_urlsafe(32)
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE');migrate(c)
        if not paid_member(c,u['id']) or not subscribed(c,u['id']):raise HTTPException(403,'An active paid membership and API subscription are required.')
        c.execute('INSERT INTO customer_api_keys VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET key_hash=excluded.key_hash,created_at=excluded.created_at',(u['id'],hashlib.sha256(token.encode()).hexdigest(),time.time()))
    return JSONResponse({'key':token,'message':'Shown once. Creating a new key revokes the previous key.'},headers={'Cache-Control':'no-store'})

@router.delete('/api/customer-api/key')
def revoke_key(request:Request):
    u=core().account(request)
    with core().db() as c:
        migrate(c);c.execute('DELETE FROM customer_api_keys WHERE user_id=?',(u['id'],))
    return {'revoked':True}

def consume(c,uid,now):
    month=datetime.fromtimestamp(now,timezone.utc).strftime('%Y-%m');minute=int(now//60)
    # Caller holds the cross-instance transaction lock. Quotas are per account, not per key.
    old=c.execute('SELECT * FROM customer_api_usage WHERE user_id=?',(uid,)).fetchone()
    monthly=old['monthly_used'] if old and old['month']==month else 0
    recent=old['minute_used'] if old and old['minute']==minute else 0
    if monthly>=MONTHLY_LIMIT:raise HTTPException(429,'Monthly API allowance reached. Resets on the first day of next month (UTC).')
    if recent>=MINUTE_LIMIT:raise HTTPException(429,'Minute API allowance reached.',headers={'Retry-After':str(60-int(now%60))})
    c.execute('INSERT INTO customer_api_usage VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET month=excluded.month,monthly_used=excluded.monthly_used,minute=excluded.minute,minute_used=excluded.minute_used',(uid,month,monthly+1,minute,recent+1))
    return MONTHLY_LIMIT-monthly-1

def authenticate(request):
    require_enabled()
    scheme,_,token=request.headers.get('authorization','').partition(' ')
    if scheme.lower()!='bearer' or not token.startswith('te_live_') or len(token)>100:raise HTTPException(401,'Supply your API key using Authorization: Bearer.',headers={'WWW-Authenticate':'Bearer'})
    with core().db() as c:
        c.execute('BEGIN IMMEDIATE');migrate(c)
        row=c.execute('SELECT user_id FROM customer_api_keys WHERE key_hash=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if not row:raise HTTPException(401,'Invalid or revoked API key.')
        uid=row['user_id']
        if not paid_member(c,uid) or not subscribed(c,uid):raise HTTPException(403,'Active membership and API subscription required.')
        return consume(c,uid,time.time())

def snapshot(days):
    with _lock:
        old=_cache.get(days)
        if old and time.monotonic()-old[0]<60:return old[1]
        from .count_metrics import enrich
        from .supply_chain import group_rows
        s=core()
        with s.db() as c:
            stamp=s.reference('x',c);rows=enrich(c,[],stamp,days)
        ranked=sorted(rows,key=lambda r:(-r['heat'],r['ticker']))[:20]
        fields=('ticker','name','sector','mentions','change','heat')
        result={'window_days':days,'as_of':stamp,'stale':time.time()-stamp>36*3600,'rankings':[{**{k:r.get(k) for k in fields},'rank':i+1} for i,r in enumerate(ranked)],'sectors':[{k:g[k] for k in ('sector','stocks','mentions','share')} for g in group_rows(s.CATALOG,rows,days*24)]}
        _cache[days]=(time.monotonic(),result);return result

@router.get('/api/v1/snapshot')
def get_snapshot(request:Request,window:int=Query(1)):
    if window not in (1,7,30):raise HTTPException(422,'Choose window=1, 7 or 30.')
    remaining=authenticate(request)
    return JSONResponse(snapshot(window),headers={'Cache-Control':'private, no-store','X-RateLimit-Monthly-Remaining':str(remaining)})

@router.post('/api/customer-api/checkout')
def checkout(request:Request):
    require_enabled()
    from . import payments as p
    u=core().account(request);core().throttle(request)
    if not p.environment_valid() or os.getenv('BILLING_ENABLED','false').lower()!='true':raise HTTPException(503,'Billing unavailable.')
    with core().db() as c:
        c.execute('BEGIN IMMEDIATE');migrate(c)
        if not paid_member(c,u['id']):raise HTTPException(403,'Choose a paid Premium or Founder membership first.')
        if subscribed(c,u['id']):raise HTTPException(409,'API subscription already active. Use Manage billing.')
        user=c.execute('SELECT stripe_customer FROM accounts WHERE id=?',(u['id'],)).fetchone()
        if not user['stripe_customer']:raise HTTPException(409,'A paid billing account is required.')
        price_id=os.getenv('STRIPE_PRICE_API','')
        if not price_id:raise HTTPException(503,'API billing is not configured.')
        price=p.stripe('GET','prices/'+quote(price_id,safe=''))
        if not valid_price(price):raise HTTPException(503,'API price needs review. No payment was taken.')
        old=c.execute("SELECT * FROM billing_checkouts WHERE user_id=? AND tier='api' ORDER BY created_at DESC LIMIT 1",(u['id'],)).fetchone()
        if old:
            session=p.stripe('GET','checkout/sessions/'+quote(old['id'],safe=''))
            if session['status']=='open':return {'url':session['url']}
            if session['status']=='complete':raise HTTPException(409,'Use Manage billing for your API subscription.')
        data={'mode':'subscription','customer':user['stripe_customer'],'client_reference_id':u['id'],'line_items[0][price]':price_id,'line_items[0][quantity]':'1','metadata[tier]':'api','metadata[account_id]':u['id'],'subscription_data[metadata][tier]':'api','subscription_data[metadata][account_id]':u['id'],'success_url':core().ORIGIN+'/plans?api=success','cancel_url':core().ORIGIN+'/plans','billing_address_collection':'required'}
        if os.getenv('STRIPE_AUTOMATIC_TAX','false').lower()=='true':data.update({'automatic_tax[enabled]':'true','customer_update[address]':'auto'})
        session=p.stripe('POST','checkout/sessions',data,'api-checkout-'+u['id']+'-'+str(int(time.time()//1800)))
        c.execute('INSERT OR IGNORE INTO billing_checkouts VALUES(?,?,?,?)',(session['id'],u['id'],'api',time.time()))
        return {'url':session['url']}

def valid_price(price):
    recurring=price.get('recurring') or {}
    return price.get('id')==os.getenv('STRIPE_PRICE_API') and price.get('currency')=='usd' and price.get('unit_amount')==500 and recurring.get('interval')=='month' and recurring.get('interval_count')==1

def sync(c,obj):
    if obj.get('metadata',{}).get('tier')!='api':return False
    migrate(c);uid=obj.get('metadata',{}).get('account_id')
    user=c.execute('SELECT id FROM accounts WHERE id=? AND stripe_customer=? AND demo=0',(uid,obj.get('customer'))).fetchone()
    items=obj.get('items',{}).get('data',[])
    if user and len(items)==1 and valid_price(items[0]['price']):
        c.execute('INSERT INTO customer_api_subscriptions VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET active=excluded.active,updated_at=excluded.updated_at',(obj['id'],uid,int(obj['status']=='active'),time.time()))
    return True
