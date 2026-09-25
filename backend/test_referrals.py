import time,json
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from . import service as s,referrals as r,payments as p

@pytest.fixture
def setup(tmp_path,monkeypatch):
 monkeypatch.setattr(s,'DB_PATH',str(tmp_path/'referrals.sqlite'));monkeypatch.setattr(s,'DEMO',False)
 monkeypatch.setenv('ACCOUNT_EMAIL_ENABLED','false');s.init()
 now=time.time()
 with s.db() as c:
  for uid in ('owner','friend','other'):
   c.execute("INSERT INTO accounts(id,email,password,display_name,email_verified,created_at,stripe_customer) VALUES(?,?,?,?,1,?,?)",(uid,uid+'@example.com','hash',uid,now-100*r.DAY,'cus_'+uid))
  c.execute("INSERT INTO referrals(id,inviter,friend,created) VALUES('ref','owner','friend',?)",(now-70*r.DAY,))
  c.execute("INSERT INTO billing_entitlements VALUES('sub_friend','friend','monthly',1,?)",(now,))
 price={'id':'price_monthly','unit_amount':900,'currency':'usd','product':'prod_premium','recurring':{'interval':'month'}}
 subs={'sub_friend':{'id':'sub_friend','customer':'cus_friend','metadata':{'account_id':'friend','tier':'monthly'},'status':'active','items':{'data':[{'price':price}]},'discounts':[]}}
 invs=[{'amount_paid':900,'currency':'usd','billing_reason':'subscription_cycle','period_start':now-days*r.DAY,'status_transitions':{'paid_at':now-days*r.DAY},'charge':{'id':'ch_'+str(days),'status':'succeeded','payment_method_details':{'card':{'fingerprint':'friendcard'}}}} for days in (50,20)]
 calls=[];coupons={};applied={}
 def stripe(method,path,data=None,idempotency=None):
  calls.append((method,path,data,idempotency))
  if method=='GET' and path.startswith('subscriptions/'):return deepcopy(subs[path.split('/')[-1]])
  if path=='invoices':return {'data':deepcopy(invs)}
  if path=='payment_methods':return {'data':[]}
  if path=='coupons':
   coupons.setdefault(data['id'],{'id':data['id'],'amount_off':int(data['amount_off'])});return coupons[data['id']]
  if method=='POST' and path.startswith('subscriptions/'):
   if idempotency in applied:return applied[idempotency]
   sub=subs[path.split('/')[-1]]
   if data.get('discounts')=='':sub['discounts']=[]
   elif 'revoke' in idempotency:sub['discounts']=[d for d in sub['discounts'] if d['id'] in data.values()]
   else:
    cid=next(v for k,v in data.items() if k.endswith('[coupon]'))
    sub['discounts'].append({'id':'di_'+cid,'coupon':coupons[cid]})
   applied[idempotency]=deepcopy(sub);return sub
  raise AssertionError((method,path,data))
 monkeypatch.setattr(p,'stripe',stripe);monkeypatch.setattr(p,'environment_valid',lambda:True)
 return now,subs,invs,calls

def row():
 with s.db() as c:return dict(c.execute("SELECT * FROM referrals WHERE id='ref'").fetchone())

def test_free_reward_once_and_expires(setup):
 now,*_=setup
 r.check_one('ref',now);r.check_one('ref',now+1)
 assert row()['state']=='rewarded'
 with s.db() as c:
  assert c.execute('SELECT COUNT(*) FROM referral_access').fetchone()[0]==1
  assert r.access_until(c,'owner',now+1)==now+30*r.DAY
  assert r.access_until(c,'owner',now+31*r.DAY) is None
  u=dict(c.execute("SELECT * FROM accounts WHERE id='owner'").fetchone())
 assert s.public_account(u)['referral_active'] is True
 assert s.public_account(u)['plan']=='premium'

@pytest.mark.parametrize('case',['early','one_invoice','refund','dispute','cancelled','unverified','same_card'])
def test_no_reward_until_all_conditions(setup,monkeypatch,case):
 now,subs,invs,calls=setup
 if case=='early':invs[0]['status_transitions']['paid_at']=now-44*r.DAY
 if case=='one_invoice':invs.pop()
 if case=='refund':invs[0]['charge']['amount_refunded']=1
 if case=='dispute':invs[0]['charge']['disputed']=True
 if case=='cancelled':subs['sub_friend']['cancel_at_period_end']=True
 if case=='unverified':
  with s.db() as c:c.execute("UPDATE accounts SET email_verified=0 WHERE id='friend'")
 if case=='same_card':
  original=p.stripe
  monkeypatch.setattr(p,'stripe',lambda method,path,data=None,idempotency=None:{'data':[{'card':{'fingerprint':'friendcard'}}]} if path=='payment_methods' else original(method,path,data,idempotency))
 r.check_one('ref',now)
 assert row()['state']!='rewarded'
 assert not any(call[0]=='POST' for call in calls)
 with s.db() as c:assert not c.execute('SELECT 1 FROM referral_access').fetchone()

@pytest.mark.parametrize('tier,amount',[('monthly',900),('yearly',9900)])
def test_subscriber_reward_scoped_and_idempotent(setup,tier,amount):
 now,subs,invs,calls=setup
 subs['sub_owner']={'id':'sub_owner','customer':'cus_owner','status':'active','items':{'data':[{'price':{'currency':'usd','unit_amount':amount,'product':'premium','recurring':{'interval':'month' if tier=='monthly' else 'year'}}}]},'discounts':[]}
 with s.db() as c:c.execute('INSERT INTO billing_entitlements VALUES(?,?,?,?,?)',('sub_owner','owner',tier,1,now))
 r.check_one('ref',now);r.check_one('ref',now+1)
 assert row()['state']=='rewarded'
 coupon=[call for call in calls if call[1]=='coupons'][0][2]
 assert coupon['amount_off']=='900' and coupon['duration']=='once' and coupon['applies_to[products][0]']=='premium'
 assert len([call for call in calls if call[0]=='POST' and call[1]=='subscriptions/sub_owner'])==1
 invs[0]['charge']['refunded']=True
 r.check_one('ref',now+2)
 assert row()['state']=='reversed' and not subs['sub_owner']['discounts']

def test_free_refund_revokes_unused_access(setup):
 now,subs,invs,calls=setup
 r.check_one('ref',now);invs[0]['charge']['disputed']=True;r.check_one('ref',now+100)
 assert row()['state']=='reversed'
 with s.db() as c:assert r.access_until(c,'owner',now+100) is None

def test_cancel_after_earning_keeps_reward(setup):
 now,subs,invs,calls=setup
 r.check_one('ref',now);subs['sub_friend']['cancel_at_period_end']=True;r.check_one('ref',now+100)
 assert row()['state']=='rewarded'

def test_existing_promotion_waits(setup):
 now,subs,invs,calls=setup
 subs['sub_owner']={'id':'sub_owner','customer':'cus_owner','status':'active','discounts':[{'id':'di_event','coupon':{'id':'cyberweek'}}]}
 with s.db() as c:c.execute("INSERT INTO billing_entitlements VALUES('sub_owner','owner','monthly',1,?)",(now,))
 r.check_one('ref',now)
 assert row()['state']=='waiting_reward' and not any(call[0]=='POST' for call in calls)

def test_annual_cap(setup):
 now,*_=setup
 with s.db() as c:
  for i in range(6):
   uid='past'+str(i)
   c.execute('INSERT INTO accounts(id,email,display_name) VALUES(?,?,?)',(uid,uid+'@example.com',uid))
   c.execute("INSERT INTO referrals(id,inviter,friend,created,state,granted) VALUES(?,'owner',?,?,'rewarded',?)",(uid,uid,now,now))
 r.check_one('ref',now)
 assert row()['state']=='annual_limit'

def test_signup_cookie_account_isolation_and_private_progress(setup):
 now,*_=setup
 with s.db() as c:c.execute("INSERT INTO referral_codes VALUES('owner','test-link')")
 client=TestClient(s.app)
 assert client.get('/api/referrals').status_code==401
 assert client.get('/api/cron/referrals').status_code==401
 response=client.get('/api/referrals/visit/test-link',follow_redirects=False)
 assert response.status_code==303 and 'HttpOnly' in response.headers['set-cookie']
 data=client.post('/api/auth/signup',json={'display_name':'New Friend','email':'new@example.com','password':'long-password-123'}).json()
 with s.db() as c:assert c.execute('SELECT inviter FROM referrals WHERE friend=?',(data['id'],)).fetchone()[0]=='owner'
 assert 'te_referral' not in client.cookies
 out=client.get('/api/referrals').json()
 assert out['items']==[] and 'new@example.com' not in json.dumps(out)
 with s.db() as c:r.attach(c,'owner','test-link');assert not c.execute("SELECT 1 FROM referrals WHERE friend='owner'").fetchone()

def test_reward_retry_after_lost_response_does_not_duplicate(setup,monkeypatch):
 now,subs,invs,calls=setup
 subs['sub_owner']={'id':'sub_owner','customer':'cus_owner','status':'active','items':{'data':[{'price':{'currency':'usd','unit_amount':900,'product':'premium','recurring':{'interval':'month'}}}]},'discounts':[]}
 with s.db() as c:c.execute("INSERT INTO billing_entitlements VALUES('sub_owner','owner','monthly',1,?)",(now,))
 original=p.stripe;failed=[False]
 def unreliable(method,path,data=None,idempotency=None):
  result=original(method,path,data,idempotency)
  if method=='POST' and path=='subscriptions/sub_owner' and not failed[0]:
   failed[0]=True;raise RuntimeError('Response lost')
  return result
 monkeypatch.setattr(p,'stripe',unreliable)
 with pytest.raises(RuntimeError):r.check_one('ref',now)
 assert row()['state']=='applying'
 r.check_one('ref',now+3600)
 assert row()['state']=='rewarded'
 assert len(subs['sub_owner']['discounts'])==1
 assert len([call for call in calls if call[0]=='POST' and call[1]=='subscriptions/sub_owner'])==1

def test_access_reward_starts_after_trial(setup):
 now,*_=setup
 with s.db() as c:c.execute("UPDATE accounts SET trial_ends_at=? WHERE id='owner'",(now+3*r.DAY,))
 r.check_one('ref',now)
 with s.db() as c:
  assert r.access_until(c,'owner',now) is None
  assert r.access_until(c,'owner',now+4*r.DAY)==now+33*r.DAY

def test_shared_card_cannot_qualify_second_friend(setup):
 now,subs,invs,calls=setup
 with s.db() as c:c.execute("INSERT INTO referral_cards VALUES(?,'other')",(r.hashlib.sha256(b'friendcard').hexdigest(),))
 r.check_one('ref',now)
 assert row()['state']=='ineligible'
