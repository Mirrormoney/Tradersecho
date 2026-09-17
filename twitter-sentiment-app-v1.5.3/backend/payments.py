"""Account-bound Stripe hosted checkout. Prices and activation are server controlled."""
import hashlib, hmac, json, os, time
from urllib.parse import quote
import httpx
from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

router=APIRouter()
TIERS={'monthly':('STRIPE_PRICE_MONTHLY',1900,'month'), 'yearly':('STRIPE_PRICE_YEARLY',19000,'year'), 'founder':('STRIPE_PRICE_FOUNDER',99900,None)}

def core():
    from . import service
    return service

def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS billing_checkouts(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES accounts(id),tier TEXT NOT NULL,created_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS billing_entitlements(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES accounts(id),tier TEXT NOT NULL,active INTEGER NOT NULL,updated_at REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS billing_checkouts_user ON billing_checkouts(user_id);
    ''')

def options():
    enabled=os.getenv('FREE_LAUNCH','false').lower()!='true' and environment_valid() and os.getenv('BILLING_ENABLED','false').lower()=='true' and all(os.getenv(k) for k in ['STRIPE_SECRET_KEY','STRIPE_WEBHOOK_SECRET'])
    return {tier:bool(enabled and os.getenv(config[0])) for tier,config in TIERS.items()}

def sandbox():
    return os.getenv('BILLING_SANDBOX','false').lower()=='true'

def environment_valid():
    key=os.getenv('STRIPE_SECRET_KEY','')
    if key.startswith(('sk_test_','rk_test_')):
        return sandbox() and os.getenv('TRADERSECHO_SCHEMA','').startswith('billing_sandbox_')
    return key.startswith(('sk_live_','rk_live_')) and not sandbox()

def stripe(method,path,data=None,idempotency=None):
    key=os.getenv('STRIPE_SECRET_KEY','')
    if not key: raise HTTPException(503,'Billing is not connected yet.')
    headers={'Stripe-Version':'2025-02-24.acacia'}
    if idempotency: headers['Idempotency-Key']=idempotency
    try:
        with httpx.Client(timeout=20) as client:
            r=client.request(method,'https://api.stripe.com/v1/'+path,auth=(key,''),data=data if method!='GET' else None,params=data if method=='GET' else None,headers=headers)
        if not r.is_success: raise HTTPException(502,'Stripe could not complete this request. Please try again later.')
        return r.json()
    except httpx.HTTPError: raise HTTPException(502,'Billing is temporarily unavailable. Please retry.')

def account_details(u):
    u=dict(u)
    with core().db() as c:
        founder=c.execute("SELECT 1 FROM billing_entitlements WHERE user_id=? AND tier='founder' AND active=1",(u['id'],)).fetchone()
    return {'billing_tier':'founder' if founder else u['plan'],'billing_customer':bool(u.get('stripe_customer'))}

def validate_price(price,tier):
    _,amount,interval=TIERS[tier]
    recurring=price.get('recurring') or {}
    if price.get('currency')!='usd' or price.get('unit_amount')!=amount or recurring.get('interval')!=interval or (interval and recurring.get('interval_count')!=1):
        raise HTTPException(503,'The configured price needs review. No payment has been taken.')

@router.post('/api/billing/checkout')
async def checkout(request:Request):
    s=core();u=s.account(request)
    if u['demo']: raise HTTPException(400,'Create a real account before subscribing.')
    s.throttle(request)
    try: payload=await request.json()
    except (ValueError,TypeError): payload={}
    tier=payload.get('tier','monthly') if isinstance(payload,dict) else None
    if tier not in TIERS: raise HTTPException(422,'Choose monthly, yearly or founder.')
    if not options()[tier]: raise HTTPException(503,'Payments are not open yet. No payment has been taken.')
    return await run_in_threadpool(create_checkout,u,tier)

def create_checkout(u,tier):
    if not environment_valid():raise HTTPException(503,'Payment environment is not configured safely.')
    s=core()
    # Serialize checkout creation and entitlement changes across instances.
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        u=dict(c.execute('SELECT * FROM accounts WHERE id=?',(u['id'],)).fetchone())
        if u['plan']=='premium' or u['role'] in ['owner','admin']:
            raise HTTPException(409,'You already have Premium access. Use Manage billing for an existing subscription.')
        existing=c.execute('SELECT * FROM billing_checkouts WHERE user_id=? ORDER BY created_at DESC LIMIT 1',(u['id'],)).fetchone()
        if existing:
            session=stripe('GET','checkout/sessions/'+quote(existing['id'],safe=''))
            if session['status']=='complete' and not c.execute('SELECT 1 FROM billing_entitlements WHERE user_id=?',(u['id'],)).fetchone():
                raise HTTPException(409,'Your payment is being confirmed. Please refresh your account shortly.')
            if session['status']=='open':
                if existing['tier']==tier:return {'url':session['url']}
                stripe('POST','checkout/sessions/'+quote(existing['id'],safe='')+'/expire')
        price_id=os.environ[TIERS[tier][0]]
        validate_price(stripe('GET','prices/'+quote(price_id,safe='')),tier)
        nonce=f"{u['id']}-{tier}-{existing['id'] if existing else 'initial'}-{int(time.time()//1800)}"
        if not u['stripe_customer']:
            customer=stripe('POST','customers',{'email':u['email'],'metadata[account_id]':u['id']},'customer-'+u['id'])
            u['stripe_customer']=customer['id']
            c.execute('UPDATE accounts SET stripe_customer=? WHERE id=?',(customer['id'],u['id']))
        data={'mode':'payment' if tier=='founder' else 'subscription','customer':u['stripe_customer'],'client_reference_id':u['id'],
              'line_items[0][price]':price_id,'line_items[0][quantity]':'1','payment_method_types[0]':'card',
              'metadata[account_id]':u['id'],'metadata[tier]':tier,'success_url':s.ORIGIN+'/?billing=success',
              'cancel_url':s.ORIGIN+'/?billing=cancelled','billing_address_collection':'required'}
        prefix='payment_intent_data' if tier=='founder' else 'subscription_data'
        data[prefix+'[metadata][account_id]']=u['id'];data[prefix+'[metadata][tier]']=tier
        if os.getenv('STRIPE_AUTOMATIC_TAX','false').lower()=='true':
            data['automatic_tax[enabled]']='true';data['customer_update[address]']='auto'
        session=stripe('POST','checkout/sessions',data,'checkout-'+nonce)
        c.execute('INSERT OR IGNORE INTO billing_checkouts VALUES(?,?,?,?)',(session['id'],u['id'],tier,time.time()))
        return {'url':session['url']}

@router.post('/api/billing/portal')
def portal(request:Request):
    s=core();u=s.account(request);s.throttle(request)
    if u['demo'] or not u['stripe_customer']:raise HTTPException(400,'No billing account is connected to this membership.')
    result=stripe('POST','billing_portal/sessions',{'customer':u['stripe_customer'],'return_url':s.ORIGIN+'/?billing=portal'})
    return {'url':result['url']}

def sync_entitlement(c,kind,object_id):
    if not environment_valid():raise HTTPException(503,'Payment environment is not configured safely.')
    obj=stripe('GET',('subscriptions/' if kind=='subscription' else 'payment_intents/')+quote(object_id,safe=''),None if kind=='subscription' else {'expand[0]':'latest_charge'})
    uid=obj.get('metadata',{}).get('account_id');tier=obj.get('metadata',{}).get('tier')
    if tier not in TIERS or (kind=='subscription')==(tier=='founder'): return
    u=c.execute('SELECT * FROM accounts WHERE id=? AND stripe_customer=? AND demo=0',(uid,obj.get('customer'))).fetchone()
    if not u:return
    if kind=='subscription':
        items=obj.get('items',{}).get('data',[])
        if len(items)!=1 or items[0]['price']['id']!=os.getenv(TIERS[tier][0]):return
        validate_price(items[0]['price'],tier)
        active=obj['status'] in ['active','trialing']
    else:
        charge=obj.get('latest_charge') or {}
        if obj.get('currency')!='usd' or obj.get('amount')!=99900:return
        disputed=charge.get('disputed',False)
        if disputed:
            disputes=stripe('GET','disputes',{'charge':charge['id'],'limit':100})
            disputed=disputes.get('has_more',False) or not disputes.get('data') or any(d['status'] not in ['won','warning_closed'] for d in disputes['data'])
        active=obj['status']=='succeeded' and not charge.get('refunded') and not disputed
    c.execute('INSERT INTO billing_entitlements VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET active=excluded.active,tier=excluded.tier,updated_at=excluded.updated_at',(obj['id'],uid,tier,int(active),time.time()))
    has_access=c.execute('SELECT 1 FROM billing_entitlements WHERE user_id=? AND active=1',(uid,)).fetchone()
    c.execute("UPDATE accounts SET plan=? WHERE id=? AND role='member'",('premium' if has_access else 'free',uid))

@router.post('/api/billing/webhook')
async def webhook(request:Request):
    secret=os.getenv('STRIPE_WEBHOOK_SECRET','')
    if not secret:raise HTTPException(503,'Webhook not configured')
    body=await request.body();parts=request.headers.get('stripe-signature','').split(',')
    try: stamp=int(next(v[2:] for v in parts if v.startswith('t=')))
    except (ValueError,StopIteration):raise HTTPException(400,'Invalid signature')
    expected=hmac.new(secret.encode(),str(stamp).encode()+b'.'+body,hashlib.sha256).hexdigest()
    if abs(time.time()-stamp)>300 or not any(hmac.compare_digest(expected,v[3:]) for v in parts if v.startswith('v1=')):raise HTTPException(400,'Invalid signature')
    try:
        event=json.loads(body);event_id=event['id'];kind=event['type'];obj=event['data']['object']
    except (ValueError,KeyError,TypeError):raise HTTPException(400,'Invalid event')
    key=os.getenv('STRIPE_SECRET_KEY','')
    if event.get('livemode',False)!=(key.startswith('sk_live_') or key.startswith('rk_live_')):raise HTTPException(400,'Payment environment mismatch')
    return await run_in_threadpool(process_event,event_id,kind,obj)

def process_event(event_id,kind,obj):
    if not environment_valid():raise HTTPException(503,'Payment environment is not configured safely.')
    with core().db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM webhook_events WHERE id=?',(event_id,)).fetchone():return {'received':True}
        if kind.startswith('customer.subscription.'):
            sync_entitlement(c,'subscription',obj['id'])
        elif kind=='payment_intent.succeeded':
            sync_entitlement(c,'payment',obj['id'])
        elif kind in ['checkout.session.completed','checkout.session.async_payment_succeeded']:
            saved=c.execute('SELECT * FROM billing_checkouts WHERE id=?',(obj['id'],)).fetchone()
            if saved:
                session=stripe('GET','checkout/sessions/'+quote(obj['id'],safe=''))
                if session.get('client_reference_id')!=saved['user_id']:raise HTTPException(400,'Account mismatch')
                if session.get('payment_status')=='paid':
                    ref=session.get('subscription') or session.get('payment_intent')
                    if ref:sync_entitlement(c,'subscription' if session.get('subscription') else 'payment',ref)
        elif kind in ['charge.refunded','charge.dispute.created','charge.dispute.closed']:
            charge=obj if kind=='charge.refunded' else stripe('GET','charges/'+quote(obj['charge'],safe=''))
            if charge.get('payment_intent'):sync_entitlement(c,'payment',charge['payment_intent'])
        c.execute('INSERT INTO webhook_events VALUES(?)',(event_id,))
    return {'received':True}
