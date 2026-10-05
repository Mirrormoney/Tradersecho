import os,tempfile,hashlib,time
for key in ('DATABASE_URL','APP_DATABASE_URL','POSTGRES_URL','POSTGRES_PRISMA_URL','POSTGRES_URL_NON_POOLING'):os.environ.pop(key,None)
os.environ.update(TRADERSECHO_DB=tempfile.mktemp(suffix='.sqlite'),DEMO_ENABLED='false',BILLING_SANDBOX='true')
from backend import service as s,account_security as security
from backend.campaign_attribution import summary
from fastapi.testclient import TestClient
security.configured=lambda:False
client=TestClient(s.app)
a={'source':'x','medium':'paid_social','campaign':'signal_audience_test_oct2026','content':'signal_video_v1'}
r=client.post('/api/auth/signup',json={'email':'campaign-test@example.com','password':'long-password-test','display_name':'Campaign Test','campaign_attribution':a})
assert r.status_code==200,r.text
uid=r.json()['id']
with s.db() as c:
 assert summary(c)['campaigns'][0]['signups']==1
 assert summary(c)['campaigns'][0]['trials']==0
 c.execute('INSERT INTO account_tokens(hash,user_id,email,purpose,expires,used) VALUES(?,?,?,?,?,0)',(hashlib.sha256(b'campaign-test-token-longer-than-thirty-characters').hexdigest(),uid,'campaign-test@example.com','verify',time.time()+600))
r=client.post('/api/auth/verify-email',json={'token':'campaign-test-token-longer-than-thirty-characters'})
assert r.status_code==200,r.text
with s.db() as c:
 assert summary(c)['campaigns'][0]['verified']==1
 assert summary(c)['campaigns'][0]['trials']==1
assert client.get('/api/signal-lab/overview').status_code==200
assert client.get('/api/insights/800-vdc').status_code==200
assert client.get('/api/admin/campaign-results').status_code==403
for i,headers,attribution in [(1,{'dnt':'1'},a),(2,{'sec-gpc':'1'},a),(3,{},dict(a,campaign='unknown')),(4,{},dict(a,campaign=[]))]:
 r=client.post('/api/auth/signup',json={'email':f'other{i}@example.com','password':'long-password-test','display_name':f'Other User {i}','campaign_attribution':attribution},headers=headers)
 assert r.status_code==200,r.text
with s.db() as c:
 assert c.execute('SELECT COUNT(*) FROM campaign_signups').fetchone()[0]==1
 c.execute("UPDATE accounts SET role='owner' WHERE id=?",(uid,))
client.post('/api/auth/login',json={'email':'campaign-test@example.com','password':'long-password-test'})
r=client.get('/api/admin/campaign-results');assert r.status_code==200,r.text
assert r.json()['campaigns'][0]['signups']==0
print('PASS: signup to email verification to trial, opt outs, unknown campaign, owner authorization/exclusion')




