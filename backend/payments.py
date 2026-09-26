"""Account-bound Stripe hosted checkout. Prices and activation are server controlled."""
import hashlib, hmac, json, os, time
from urllib.parse import quote
import httpx
from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

router=APIRouter()
TIERS={'monthly':('STRIPE_PRICE_MONTHLY',900,'month'), 'yearly':('STRIPE_PRICE_YEARLY',9900,'year'), 'founder':('STRIPE_PRICE_FOUNDER',49900,None), 'pro_monthly':('STRIPE_PRICE_PRO_MONTHLY',1900,'month'), 'pro_yearly':('STRIPE_PRICE_PRO_YEARLY',19000,'year')}
LEGACY_AMOUNTS={'monthly':1900,'yearly':19000,'founder':99900}

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
    enabled=os.getenv('FREE_LAUNCH','false').lower()!='true' and environment_valid() and os.getenv('BILLING_ENABLED','false').lower()=='true' and bool(secret_key() and os.getenv('STRIPE_WEBHOOK_SECRET'))
    return {tier:bool(enabled and configured_price(tier)) for tier,config in TIERS.items()}

def sandbox():
    return os.getenv('BILLING_SANDBOX','false').lower()=='true'

def secret_key():
    # Marketplace-managed sandbox credentials remain isolated from live billing.
    if not sandbox() and os.getenv('STRIPE_LIVE_SECRET_KEY'):
        return os.environ['STRIPE_LIVE_SECRET_KEY']
    return os.getenv('STRIPE_SECRET_KEY','')

def environment_valid():
    key=secret_key()
    if key.startswith(('sk_test_','rk_test_')):
        return sandbox() and os.getenv('TRADERSECHO_SCHEMA','').startswith('billing_sandbox_')
    return key.startswith(('sk_live_','rk_live_')) and not sandbox()

def stripe(method,path,data=None,idempotency=None):
    key=secret_key()
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
        previous=c.execute('SELECT 1 FROM billing_entitlements WHERE user_id=?',(u['id'],)).fetchone()
        from .plan_limits import limits
        allowances=limits(c,u)
        from .pro_access import has_pro, launched
        pro=has_pro(c,u)
    return {'pro_access':pro,'features_launched':launched(),'limits':allowances,'billing_tier':'founder' if founder else 'trial' if u.get('trial_active') else 'pro' if pro else u['plan'],'billing_customer':bool(u.get('stripe_customer')),'trial_eligible':bool(not u['demo'] and u['role']=='member' and u['plan']=='free' and not u.get('trial_started_at') and not previous)}

def validate_price(price,tier,legacy=False):
    _,amount,interval=TIERS[tier]
    if legacy:amount=LEGACY_AMOUNTS.get(tier,amount)
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
    if tier not in TIERS: raise HTTPException(422,'Choose Premium, Pro or Founder.')
    if not options()[tier]: raise HTTPException(503,'Payments are not open yet. No payment has been taken.')
    return await run_in_threadpool(create_checkout,u,tier)

def create_checkout(u,tier):
    if not environment_valid():raise HTTPException(503,'Payment environment is not configured safely.')
    s=core()
    # Serialize checkout creation and entitlement changes across instances.
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        u=dict(c.execute('SELECT * FROM accounts WHERE id=?',(u['id'],)).fetchone())
        if u['plan'] in ('premium','pro') or c.execute("SELECT 1 FROM billing_entitlements WHERE user_id=? AND active=1 AND tier='founder'",(u['id'],)).fetchone() or u['role'] in ['owner','admin']:
            raise HTTPException(409,'You already have Premium access. Use Manage billing for an existing subscription.')
        existing=c.execute("SELECT * FROM billing_checkouts WHERE user_id=? AND tier!='api' ORDER BY created_at DESC LIMIT 1",(u['id'],)).fetchone()
        if existing:
            session=stripe('GET','checkout/sessions/'+quote(existing['id'],safe=''))
            if session['status']=='complete' and not c.execute('SELECT 1 FROM billing_entitlements WHERE user_id=?',(u['id'],)).fetchone():
                raise HTTPException(409,'Your payment is being confirmed. Please refresh your account shortly.')
            if session['status']=='open':
                if existing['tier']==tier:
                    lines=stripe('GET','checkout/sessions/'+quote(existing['id'],safe='')+'/line_items').get('data',[])
                    if len(lines)==1 and lines[0]['price']['id']==configured_price(tier) and (tier=='founder' or session.get('allow_promotion_codes')):return {'url':session['url']}
                stripe('POST','checkout/sessions/'+quote(existing['id'],safe='')+'/expire')
        price_id=configured_price(tier)
        validate_price(stripe('GET','prices/'+quote(price_id,safe='')),tier)
        nonce=f"{u['id']}-{tier}-{price_id}-{existing['id'] if existing else 'initial'}-{int(time.time()//1800)}"
        if not u['stripe_customer']:
            customer=stripe('POST','customers',{'email':u['email'],'metadata[account_id]':u['id']},'customer-'+u['id'])
            u['stripe_customer']=customer['id']
            c.execute('UPDATE accounts SET stripe_customer=? WHERE id=?',(customer['id'],u['id']))
        data={'mode':'payment' if tier=='founder' else 'subscription','customer':u['stripe_customer'],'client_reference_id':u['id'],
              'line_items[0][price]':price_id,'line_items[0][quantity]':'1','payment_method_types[0]':'card',
              'metadata[account_id]':u['id'],'metadata[tier]':tier,'success_url':s.ORIGIN+'/?billing=success',
              'cancel_url':s.ORIGIN+'/?billing=cancelled','billing_address_collection':'required'}
        if tier in ('monthly','yearly','pro_monthly','pro_yearly'):data['allow_promotion_codes']='true'
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
    data={'customer':u['stripe_customer'],'return_url':s.ORIGIN+'/?billing=portal'}
    if os.getenv('STRIPE_PORTAL_CONFIGURATION'):
        data['configuration']=os.environ['STRIPE_PORTAL_CONFIGURATION']
    result=stripe('POST','billing_portal/sessions',data)
    return {'url':result['url']}

def sync_entitlement(c,kind,object_id):
    if not environment_valid():raise HTTPException(503,'Payment environment is not configured safely.')
    obj=stripe('GET',('subscriptions/' if kind=='subscription' else 'payment_intents/')+quote(object_id,safe=''),None if kind=='subscription' else {'expand[0]':'latest_charge'})
    if kind=='subscription':
        from .customer_api import sync
        if sync(c,obj):return
    uid=obj.get('metadata',{}).get('account_id');tier=obj.get('metadata',{}).get('tier')
    # Portal changes retain subscription metadata; the actual configured price is authoritative.
    if kind=='subscription':
        items=obj.get('items',{}).get('data',[])
        if len(items)==1:
            actual=items[0]['price']['id']
            tier=next((t for t in TIERS if t!='founder' and configured_price(t)==actual),tier)

    if tier not in TIERS or (kind=='subscription')==(tier=='founder'): return
    u=c.execute('SELECT * FROM accounts WHERE id=? AND stripe_customer=? AND demo=0',(uid,obj.get('customer'))).fetchone()
    if not u:return
    if kind=='subscription':
        items=obj.get('items',{}).get('data',[])
        if len(items)!=1:return
        price=items[0]['price'];current=price['id']==configured_price(tier)
        legacy=price['id'] in os.getenv('STRIPE_LEGACY_PRICE_'+tier.upper(),'').split(',')
        if not current and not legacy:return
        validate_price(price,tier,legacy=not current)
        active=obj['status'] in ['active','trialing']
    else:
        charge=obj.get('latest_charge') or {}
        if obj.get('currency')!='usd' or obj.get('amount') not in (TIERS['founder'][1],LEGACY_AMOUNTS['founder']):return
        disputed=charge.get('disputed',False)
        if disputed:
            disputes=stripe('GET','disputes',{'charge':charge['id'],'limit':100})
            disputed=disputes.get('has_more',False) or not disputes.get('data') or any(d['status'] not in ['won','warning_closed'] for d in disputes['data'])
        active=obj['status']=='succeeded' and not charge.get('refunded') and not disputed
    c.execute('INSERT INTO billing_entitlements VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET active=excluded.active,tier=excluded.tier,updated_at=excluded.updated_at',(obj['id'],uid,tier,int(active),time.time()))
    has_access=c.execute("SELECT 1 FROM billing_entitlements WHERE user_id=? AND active=1 AND tier IN ('monthly','yearly','founder','pro_monthly','pro_yearly')",(uid,)).fetchone()
    pro=c.execute("SELECT 1 FROM billing_entitlements WHERE user_id=? AND active=1 AND tier IN ('founder','pro_monthly','pro_yearly')",(uid,)).fetchone()
    c.execute("UPDATE accounts SET plan=? WHERE id=? AND role='member'",('pro' if pro else 'premium' if has_access else 'free',uid))

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
    key=secret_key()
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
        if kind in ['charge.refunded','charge.dispute.created','charge.dispute.closed']:
            customer=charge.get('customer')
            if customer:c.execute('UPDATE referrals SET checked=0 WHERE friend IN (SELECT id FROM accounts WHERE stripe_customer=?)',(customer,))
        c.execute('INSERT INTO webhook_events VALUES(?)',(event_id,))
    return {'received':True}


def configured_price(tier):
 value=os.getenv(TIERS[tier][0])
 if value:return value
 if not tier.startswith('pro_'):return None
 with core().db() as c:
  row=c.execute("SELECT value FROM meta WHERE key=?",('billing_price_'+tier,)).fetchone()
 return row['value'] if row else None

@router.post('/api/admin/billing/prepare-pro')
def prepare_pro(request:Request):
 from .community import staff
 u=staff(request,owner=True)
 if not environment_valid():raise HTTPException(503,'Billing environment is not safe.')
 core().throttle(request)
 results=[]
 for tier in ('pro_monthly','pro_yearly'):
  price=configured_price(tier)
  if not price:
   product=stripe('POST','products',{'name':'Tradersecho Pro','description':'Full Signal Lab and AI Insights from October 1, plus all Premium features and higher allowances.','metadata[app]':'tradersecho'},'tradersecho-pro-product-v1')
   amount,interval=TIERS[tier][1:]
   obj=stripe('POST','prices',{'product':product['id'],'currency':'usd','unit_amount':str(amount),'recurring[interval]':interval,'tax_behavior':'inclusive','lookup_key':'tradersecho_'+tier+'_v1'},'tradersecho-price-'+tier+'-v1')
   validate_price(obj,tier);price=obj['id']
   with core().db() as c:c.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",('billing_price_'+tier,price))
  validate_price(stripe('GET','prices/'+quote(price,safe='')),tier)
  # Unpaid diagnostic session: no customer, entitlement or subscription is created.
  session=stripe('POST','checkout/sessions',{'mode':'subscription','line_items[0][price]':price,'line_items[0][quantity]':'1','allow_promotion_codes':'true','success_url':core().ORIGIN+'/plans','cancel_url':core().ORIGIN+'/plans','expires_at':str(int(time.time()//1800)*1800+3600),'metadata[purpose]':'owner_checkout_verification'},'verify-pro-'+tier+'-'+str(int(time.time()//1800)))
  results.append({'tier':tier,'amount':TIERS[tier][1],'url':session['url']})
 config=os.getenv('STRIPE_PORTAL_CONFIGURATION')
 if config:
  data={'features[subscription_update][enabled]':'true','features[subscription_update][default_allowed_updates][0]':'price','features[subscription_update][proration_behavior]':'create_prorations'}
  products={}
  for tier in ('monthly','yearly','pro_monthly','pro_yearly'):
   price=configured_price(tier)
   if not price:continue
   obj=stripe('GET','prices/'+quote(price,safe=''));validate_price(obj,tier)
   products.setdefault(obj['product'],[]).append(price)
  for i,(product,prices) in enumerate(products.items()):
   data[f'features[subscription_update][products][{i}][product]']=product
   for j,price in enumerate(prices):data[f'features[subscription_update][products][{i}][prices][{j}]']=price
  stripe('POST','billing_portal/configurations/'+quote(config,safe=''),data)
 return {'checkouts':results}

