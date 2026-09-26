import time
from fastapi.testclient import TestClient
from .test_service import s,isolate_tests
from . import payments,pro_access,uw_pilot

def member(plan='free'):
 c=TestClient(s.app)
 u=c.post('/api/auth/signup',json={'display_name':'Pro '+str(time.time_ns()),'email':f'{time.time_ns()}@example.com','password':'test-secure-password'}).json()
 with s.db() as db:db.execute('UPDATE accounts SET plan=? WHERE id=?',(plan,u['id']))
 return c,u

def test_pro_access_matrix_and_release(monkeypatch):
 monkeypatch.setattr(pro_access,'launched',lambda:True)
 for plan,expected in [('free',403),('premium',403),('pro',200)]:
  c,u=member(plan)
  response=c.get('/api/signal-lab/overview');assert response.status_code==expected
  response=c.get('/api/insights/800-vdc');assert response.status_code==expected
  assert c.get('/api/admin/signal-lab-overview').status_code==403
  assert c.get('/api/admin/insights/800-vdc').status_code==403
  assert c.get('/api/admin/signal-lab-detail/MU').status_code==403
  assert c.get('/api/signal-lab/detail/MU').status_code==(404 if plan=='pro' else 403)
  assert c.post('/api/admin/billing/prepare-pro').status_code==403
 guest=TestClient(s.app)
 assert guest.get('/api/signal-lab/overview').status_code==401
 assert guest.get('/api/insights/800-vdc').status_code==401
 preview=guest.get('/api/insights').json()
 assert all(set(t)=={'slug','title','intro'} for t in preview)
 c,u=member('pro');monkeypatch.setattr(pro_access,'launched',lambda:False)
 assert c.get('/api/signal-lab/overview').status_code==403
 assert c.get('/api/insights/800-vdc').status_code==403

def test_founder_and_pro_limits():
 c,u=member('pro');me=c.get('/api/me').json()
 assert me['pro_access'] and me['billing_tier']=='pro'
 assert me['limits']=={'saved_stocks':50,'personal_voices':5,'ticker_refreshes':5}
 with s.db() as db:
  db.execute("UPDATE accounts SET plan='premium' WHERE id=?",(u['id'],))
  db.execute('INSERT INTO billing_entitlements VALUES(?,?,?,?,?)',('f',u['id'],'founder',1,time.time()))
 assert c.get('/api/me').json()['pro_access']

def test_launch_boundary():
 assert not pro_access.launched(pro_access.LAUNCH_AT-1)
 assert pro_access.launched(pro_access.LAUNCH_AT)

def test_pro_checkout_price_and_webhook(monkeypatch):
 monkeypatch.setenv('STRIPE_SECRET_KEY','sk_test_test');monkeypatch.setenv('STRIPE_PRICE_PRO_MONTHLY','price_pro')
 c,u=member()
 with s.db() as db:db.execute("UPDATE accounts SET stripe_customer='cus_pro' WHERE id=?",(u['id'],))
 obj={'id':'sub_pro','metadata':{'account_id':u['id'],'tier':'pro_monthly'},'customer':'cus_pro','status':'active','items':{'data':[{'price':{'id':'price_pro','currency':'usd','unit_amount':1900,'recurring':{'interval':'month','interval_count':1}}}]}}
 monkeypatch.setattr(payments,'stripe',lambda *args,**kwargs:obj)
 with s.db() as db:payments.sync_entitlement(db,'subscription','sub_pro')
 assert c.get('/api/me').json()['plan']=='pro'
 obj['status']='canceled'
 with s.db() as db:payments.sync_entitlement(db,'subscription','sub_pro')
 assert c.get('/api/me').json()['plan']=='free'
 assert not c.get('/api/me').json()['pro_access']
 for tier,amount,interval in [('pro_monthly',1900,'month'),('pro_yearly',19000,'year')]:
  payments.validate_price({'currency':'usd','unit_amount':amount,'recurring':{'interval':interval,'interval_count':1}},tier)

def test_pro_checkout_uses_server_prices(monkeypatch):
 monkeypatch.setenv('STRIPE_SECRET_KEY','sk_test_test');monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','test');monkeypatch.setenv('BILLING_ENABLED','true')
 calls=[]
 def stripe(method,path,data=None,idempotency=None):
  calls.append((path,data))
  if path=='customers':return {'id':'cus_verified'}
  if path.startswith('prices/'):
   annual='yearly' in path
   return {'id':path.split('/')[-1],'currency':'usd','unit_amount':19000 if annual else 1900,'recurring':{'interval':'year' if annual else 'month','interval_count':1}}
  if path=='checkout/sessions':return {'id':'cs_'+data['metadata[tier]'],'url':'https://checkout.stripe.com/test'}
  raise AssertionError(path)
 monkeypatch.setattr(payments,'stripe',stripe)
 for tier in ('pro_monthly','pro_yearly'):
  monkeypatch.setenv('STRIPE_PRICE_'+tier.upper(),'price_'+tier)
  c,u=member()
  r=c.post('/api/billing/checkout',json={'tier':tier,'price':'fake','amount':1})
  assert r.status_code==200
  data=next(d for p,d in reversed(calls) if p=='checkout/sessions')
  assert data['mode']=='subscription' and data['line_items[0][price]']=='price_'+tier
  assert data['metadata[account_id]']==u['id'] and data['subscription_data[metadata][tier]']==tier
  assert data['allow_promotion_codes']=='true'

def test_portal_price_change_overrides_old_tier_metadata(monkeypatch):
 monkeypatch.setenv('STRIPE_SECRET_KEY','sk_test_test');monkeypatch.setenv('STRIPE_PRICE_PRO_MONTHLY','price_pro');monkeypatch.setenv('STRIPE_PRICE_MONTHLY','price_premium')
 c,u=member('premium')
 with s.db() as db:db.execute("UPDATE accounts SET stripe_customer='cus_portal' WHERE id=?",(u['id'],))
 obj={'id':'sub_portal','metadata':{'account_id':u['id'],'tier':'monthly'},'customer':'cus_portal','status':'active','items':{'data':[{'price':{'id':'price_pro','currency':'usd','unit_amount':1900,'recurring':{'interval':'month','interval_count':1}}}]}}
 monkeypatch.setattr(payments,'stripe',lambda *args,**kwargs:obj)
 with s.db() as db:payments.sync_entitlement(db,'subscription','sub_portal')
 assert c.get('/api/me').json()['pro_access']
 obj['metadata']['tier']='pro_monthly';obj['items']['data'][0]['price'].update(id='price_premium',unit_amount=900)
 with s.db() as db:payments.sync_entitlement(db,'subscription','sub_portal')
 assert c.get('/api/me').json()['plan']=='premium'
 assert not c.get('/api/me').json()['pro_access']
