"""Account-bound referrals. Rewards follow verified Stripe payment history, never clicks."""
import hashlib,hmac,json,os,secrets,time
from datetime import datetime,timezone
from urllib.parse import quote
from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import RedirectResponse
from . import payments as p
router=APIRouter()
DAY=86400

def migrate(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS referral_codes(user_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,code TEXT UNIQUE NOT NULL);
    CREATE TABLE IF NOT EXISTS referrals(id TEXT PRIMARY KEY,inviter TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,friend TEXT UNIQUE NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,created REAL NOT NULL,state TEXT NOT NULL DEFAULT 'joined',checked REAL NOT NULL DEFAULT 0,first_paid REAL,subscription TEXT,reward TEXT,granted REAL,reason TEXT);
    CREATE TABLE IF NOT EXISTS referral_cards(fingerprint TEXT PRIMARY KEY,friend TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE);
    CREATE INDEX IF NOT EXISTS referrals_inviter ON referrals(inviter);
    CREATE INDEX IF NOT EXISTS referrals_checked ON referrals(checked);
    CREATE TABLE IF NOT EXISTS referral_access(referral_id TEXT PRIMARY KEY REFERENCES referrals(id) ON DELETE CASCADE,user_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,starts REAL NOT NULL,ends REAL NOT NULL,revoked INTEGER NOT NULL DEFAULT 0);
    CREATE INDEX IF NOT EXISTS referral_access_user ON referral_access(user_id,ends);''')

def attach(c,friend,code):
    if not code:return
    owner=c.execute("SELECT a.* FROM accounts a JOIN referral_codes r ON a.id=r.user_id WHERE r.code=? AND a.demo=0 AND a.status='active' AND a.email_verified=1",(code,)).fetchone()
    new=c.execute('SELECT * FROM accounts WHERE id=?',(friend,)).fetchone()
    if not owner or not new or owner['id']==friend or owner['email'].lower()==new['email'].lower():return
    c.execute('INSERT OR IGNORE INTO referrals(id,inviter,friend,created) VALUES(?,?,?,?)',(secrets.token_hex(16),owner['id'],friend,time.time()))

@router.get('/api/referrals/visit/{code}')
def visit(code:str):
    if len(code)>64:raise HTTPException(404)
    with p.core().db() as c:
        if not c.execute('SELECT 1 FROM referral_codes WHERE code=?',(code,)).fetchone():raise HTTPException(404,'Referral link not found')
    response=RedirectResponse(p.core().ORIGIN+'/plans',status_code=303)
    response.set_cookie('te_referral',code,max_age=30*DAY,httponly=True,secure=p.core().SECURE,samesite='lax',path='/')
    return response

@router.get('/api/referrals')
def overview(request:Request):
    u=p.core().account(request)
    if u['demo']:raise HTTPException(403,'Referral rewards require a real account.')
    with p.core().db() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('INSERT OR IGNORE INTO referral_codes VALUES(?,?)',(u['id'],secrets.token_urlsafe(18)))
        code=c.execute('SELECT code FROM referral_codes WHERE user_id=?',(u['id'],)).fetchone()[0]
        rows=c.execute('SELECT state,created,first_paid,granted,reward FROM referrals WHERE inviter=? ORDER BY created DESC LIMIT 100',(u['id'],)).fetchall()
    # Never reveal a friend's identity or billing details to the inviter.
    return {'url':p.core().ORIGIN+'/api/referrals/visit/'+code,'verified':bool(u['email_verified']),'cap':6,'items':[{'state':r['state'],'joined':r['created'],'eligible_after':r['first_paid']+45*DAY if r['first_paid'] else None,'granted':r['granted']} for r in rows]}

def access_until(c,uid,now):
    row=c.execute('SELECT MAX(ends) FROM referral_access WHERE user_id=? AND revoked=0 AND starts<=? AND ends>?',(uid,now,now)).fetchone()
    return row[0] if row and row[0] else None

def get(path,params=None):return p.stripe('GET',path,params)
def discount_coupon(d):
    coupon=d.get('coupon') or {}
    return coupon if isinstance(coupon,dict) else {'id':coupon}

def discounts(sub):
    values=sub.get('discounts') or ([sub['discount']] if sub.get('discount') else [])
    if any(not isinstance(d,dict) for d in values):raise ValueError('Unexpanded discounts')
    return values

def subscription(sid):return get('subscriptions/'+quote(sid,safe=''),{'expand[0]':'discounts'})

def eligibility(c,r,now):
    friend=c.execute('SELECT * FROM accounts WHERE id=?',(r['friend'],)).fetchone()
    owner=c.execute('SELECT * FROM accounts WHERE id=?',(r['inviter'],)).fetchone()
    if not friend or not owner or friend['demo'] or owner['demo'] or friend['status']!='active' or owner['status']!='active':return 'ineligible',None,None
    if not friend['email_verified'] or not owner['email_verified']:return 'joined',None,None
    if not friend['stripe_customer']:return 'joined',None,None
    sid=r['subscription']
    if not sid:
        ent=c.execute("SELECT id FROM billing_entitlements WHERE user_id=? AND tier IN ('monthly','yearly') ORDER BY updated_at LIMIT 1",(friend['id'],)).fetchone()
        if not ent:return 'joined',None,None
        sid=ent['id']
    sub=subscription(sid)
    if sub.get('customer')!=friend['stripe_customer'] or sub.get('metadata',{}).get('account_id')!=friend['id']:return 'ineligible',None,None
    tier=sub.get('metadata',{}).get('tier')
    if tier not in ('monthly','yearly'):return 'ineligible',None,None
    result=get('invoices',{'subscription':sid,'status':'paid','limit':100,'expand[0]':'data.charge'})
    if result.get('has_more'):return 'review',None,None
    invoices=[i for i in result.get('data',[]) if i.get('amount_paid',0)>0 and i.get('currency')=='usd' and i.get('billing_reason') in ('subscription_create','subscription_cycle')]
    if not invoices:return 'waiting',None,sid
    fingerprints=set()
    for inv in invoices:
        charge=inv.get('charge')
        if isinstance(charge,str):charge=get('charges/'+quote(charge,safe=''))
        if not charge or charge.get('status')!='succeeded':return 'review',None,sid
        if charge.get('amount_refunded',0)>0 or charge.get('refunded') or charge.get('disputed'):return 'ineligible',None,sid
        fp=charge.get('payment_method_details',{}).get('card',{}).get('fingerprint')
        if fp:fingerprints.add(fp)
    if not fingerprints:return 'review',None,sid
    if owner['stripe_customer']:
        cards=get('payment_methods',{'customer':owner['stripe_customer'],'type':'card','limit':100})
        if cards.get('has_more'):return 'review',None,sid
        if fingerprints & {v.get('card',{}).get('fingerprint') for v in cards.get('data',[])}:return 'ineligible',None,sid
    for fp in fingerprints:
        hashed=hashlib.sha256(fp.encode()).hexdigest()
        prior=c.execute('SELECT friend FROM referral_cards WHERE fingerprint=?',(hashed,)).fetchone()
        if prior and prior['friend']!=friend['id']:return 'ineligible',None,sid
        c.execute('INSERT OR IGNORE INTO referral_cards VALUES(?,?)',(hashed,friend['id']))
    first=min(i.get('status_transitions',{}).get('paid_at') or now for i in invoices)
    if first<r['created']-60:return 'ineligible',first,sid
    if sub.get('status')!='active' or sub.get('cancel_at_period_end') or sub.get('cancel_at'):return 'ineligible',first,sid
    cycles={i.get('period_start') for i in invoices if i.get('period_start') is not None}
    if now<first+45*DAY or (tier=='monthly' and len(cycles)<2):return 'waiting',first,sid
    return 'qualified',first,sid

def reward_plan(c,r,now):
    u=c.execute('SELECT * FROM accounts WHERE id=?',(r['inviter'],)).fetchone()
    year=datetime.fromtimestamp(now,timezone.utc).year
    begin=datetime(year,1,1,tzinfo=timezone.utc).timestamp()
    if c.execute("SELECT COUNT(*) FROM referrals WHERE inviter=? AND (granted>=? OR (state='applying' AND checked>=?))",(r['inviter'],begin,begin)).fetchone()[0]>=6:return None,'annual_limit'
    ent=c.execute("SELECT * FROM billing_entitlements WHERE user_id=? AND active=1 AND tier IN ('monthly','yearly','founder') ORDER BY updated_at DESC",(u['id'],)).fetchall()
    if any(e['tier']=='founder' for e in ent) or u['role']!='member':return None,'already_premium'
    if not ent:
        if u['plan']=='premium':return None,'already_premium'
        latest=c.execute('SELECT MAX(ends) FROM referral_access WHERE user_id=? AND revoked=0',(u['id'],)).fetchone()[0] or 0
        start=max(now,latest,u['trial_ends_at'] or 0)
        return {'mode':'access','start':start,'end':start+30*DAY},None
    if len(ent)!=1:return None,'review'
    sub=subscription(ent[0]['id']);tier=ent[0]['tier']
    if sub.get('status')!='active' or sub.get('customer')!=u['stripe_customer']:return None,'waiting_reward'
    ds=discounts(sub)
    # No stacking with an event promotion; monthly rewards cover separate invoices.
    if ds and (tier=='monthly' or any(not str(discount_coupon(d).get('id','')).startswith('te_ref_') for d in ds)):return None,'waiting_reward'
    items=sub.get('items',{}).get('data',[])
    if len(items)!=1:return None,'review'
    price=items[0]['price']
    if price.get('currency')!='usd' or price.get('recurring',{}).get('interval')!=('month' if tier=='monthly' else 'year'):return None,'review'
    if tier=='yearly' and sum(discount_coupon(d).get('amount_off',0) for d in ds)+900>price['unit_amount']:return None,'waiting_reward'
    amount=price['unit_amount'] if tier=='monthly' else 900
    if amount not in (900,1900):return None,'review'
    return {'mode':'coupon','subscription':sub['id'],'coupon':'te_ref_'+r['id'],'amount':amount,'product':price['product'],'tier':tier,'attempted':now},None

def apply_reward(c,r,plan,now):
    if plan['mode']=='access':
        c.execute('INSERT OR IGNORE INTO referral_access VALUES(?,?,?,?,0)',(r['id'],r['inviter'],plan['start'],plan['end']))
    else:
        # Stable coupon ID and request keys recover an interrupted request without a second reward.
        sub=subscription(plan['subscription']);ds=discounts(sub)
        exists=any(discount_coupon(d).get('id')==plan['coupon'] for d in ds)
        if not exists:
            if now-plan['attempted']>20*3600:raise ValueError('Reward outcome requires reconciliation')
            if ds and (plan['tier']=='monthly' or any(not str(discount_coupon(d).get('id','')).startswith('te_ref_') for d in ds)):raise ValueError('Discount changed during reward')
            p.stripe('POST','coupons',{'id':plan['coupon'],'duration':'once','amount_off':str(plan['amount']),'currency':'usd','name':'Tradersecho referral reward','applies_to[products][0]':plan['product'],'max_redemptions':'1'},'ref-coupon-'+r['id'])
            data={f'discounts[{i}][discount]':d['id'] for i,d in enumerate(ds)}
            data[f'discounts[{len(ds)}][coupon]']=plan['coupon']
            p.stripe('POST','subscriptions/'+quote(plan['subscription'],safe=''),data,'ref-apply-'+r['id'])
    c.execute("UPDATE referrals SET state='rewarded',granted=? WHERE id=?",(now,r['id']))

def revoke(c,r):
    if not r['reward']:return
    plan=json.loads(r['reward'])
    if plan['mode']=='access':
        # Revoke remaining access only. Do not charge back already-used days.
        c.execute('UPDATE referral_access SET revoked=1 WHERE referral_id=?',(r['id'],))
    else:
        sub=subscription(plan['subscription']);ds=discounts(sub)
        kept=[d for d in ds if discount_coupon(d).get('id')!=plan['coupon']]
        if len(kept)!=len(ds):
            data={f'discounts[{i}][discount]':d['id'] for i,d in enumerate(kept)} if kept else {'discounts':''}
            p.stripe('POST','subscriptions/'+quote(plan['subscription'],safe=''),data,'ref-revoke-'+r['id'])

def check_one(rid,now):
    with p.core().db() as c:
        r=dict(c.execute('SELECT * FROM referrals WHERE id=?',(rid,)).fetchone())
        state,first,sid=eligibility(c,r,now)
        c.execute('UPDATE referrals SET checked=?,first_paid=COALESCE(first_paid,?),subscription=COALESCE(subscription,?) WHERE id=?',(now,first,sid,rid))
        if r['state']=='rewarded':
            # Cancellation after qualification does not undo an earned reward. Only refund/dispute does.
            if state=='ineligible' and refund_or_dispute(r):
                revoke(c,r);c.execute("UPDATE referrals SET state='reversed' WHERE id=?",(rid,))
            return
        if state!='qualified':
            c.execute('UPDATE referrals SET state=? WHERE id=?',(state,rid));return
        if r['reward']:plan=json.loads(r['reward'])
        else:
            plan,hold=reward_plan(c,r,now)
            if not plan:
                c.execute('UPDATE referrals SET state=? WHERE id=?',(hold,rid));return
            c.execute("UPDATE referrals SET state='applying',reward=? WHERE id=?",(json.dumps(plan),rid))
    # Persist the exact action before the external request. The worker lease serializes grants.
    with p.core().db() as c:
        apply_reward(c,r,plan,now)

def refund_or_dispute(r):
    result=get('invoices',{'subscription':r['subscription'],'status':'paid','limit':100,'expand[0]':'data.charge'})
    for i in result.get('data',[]):
        ch=i.get('charge')
        if isinstance(ch,str):ch=get('charges/'+quote(ch,safe=''))
        if isinstance(ch,dict) and (ch.get('amount_refunded',0)>0 or ch.get('refunded') or ch.get('disputed')):return True
    return False

def run():
    if not p.environment_valid():return {'state':'billing_unavailable'}
    now=time.time();token=secrets.token_hex(16)
    with p.core().db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute("SELECT value FROM meta WHERE key='referral_worker_lease'").fetchone()
        if row and json.loads(row[0])['until']>now:return {'state':'busy'}
        c.execute("INSERT INTO meta VALUES('referral_worker_lease',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps({'until':now+300,'token':token}),))
        rows=c.execute("SELECT id FROM referrals WHERE state NOT IN ('ineligible','reversed','review','already_premium') AND checked<? ORDER BY checked LIMIT 2",(now-3600,)).fetchall()
    errors=0
    try:
        for row in rows:
            try:check_one(row['id'],now)
            except ValueError:
                errors+=1
                with p.core().db() as c:c.execute("UPDATE referrals SET state='review',checked=?,reason='Reward needs reconciliation; no duplicate action taken' WHERE id=?",(now,row['id']))
            except Exception:
                errors+=1
                with p.core().db() as c:c.execute("UPDATE referrals SET checked=?,reason='Automatic check will retry' WHERE id=?",(now,row['id']))
        return {'state':'retry_pending' if errors else 'ok','checked':len(rows),'errors':errors}
    finally:
        with p.core().db() as c:
            row=c.execute("SELECT value FROM meta WHERE key='referral_worker_lease'").fetchone()
            if row and json.loads(row[0])['token']==token:c.execute("DELETE FROM meta WHERE key='referral_worker_lease'")
            c.execute("INSERT INTO meta VALUES('referral_worker_result',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps({'at':now,'checked':len(rows),'errors':errors}),))

@router.get('/api/cron/referrals')
def cron(request:Request):
    secret=os.getenv('CRON_SECRET','')
    if not secret or not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+secret):raise HTTPException(401,'Unauthorized')
    return run()
