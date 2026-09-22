from .test_service import isolate_tests,s
from fastapi.testclient import TestClient
from . import engagement as e
import time

def member(name):
 c=TestClient(s.app)
 assert c.post('/api/auth/signup',json={'display_name':name,'email':name+'@example.com','password':'long-test-password'}).status_code==200
 return c

def test_radar_auth_unique_expiry_and_cross_account():
 anon=TestClient(s.app)
 assert anon.put('/api/radar/NVDA',json={'active':True}).status_code==401
 a=member('radarone');b=member('radartwo')
 one=a.put('/api/radar/NVDA',json={'active':True}).json()
 two=a.put('/api/radar/NVDA',json={'active':True}).json()
 assert one==two and two['counts']['NVDA']==1
 assert b.get('/api/radar').json()['mine']=={}
 assert b.put('/api/radar/NVDA',json={'active':True}).json()['counts']['NVDA']==2
 with s.db() as c:c.execute('UPDATE radar_votes SET expires=?',(time.time()-1,))
 assert a.get('/api/radar').json()=={'counts':{},'mine':{}}
 assert a.put('/api/radar/NVDA',json={'active':False}).status_code==200
 assert a.put('/api/radar/INVALID',json={'active':True}).status_code==404

def test_shares_are_allowlisted_immutable_public(monkeypatch):
 a=member('shareone')
 row={'ticker':'NVDA','name':'NVIDIA','mentions':1200,'heat':100,'change':20,'spark':[1,2,3],'research':'PRIVATE PDF CONTENT','email':'SECRET'}
 monkeypatch.setattr(s,'rankings',lambda *args,**kwargs:{'rows':[row],'as_of':time.time()//3600*3600})
 result=a.post('/api/shares',json={'ticker':'NVDA','window':'1'})
 assert result.status_code==200,result.text
 urls=result.json();path=urls['url'].split(s.ORIGIN)[1];ident=path.split('/')[-1]
 assert a.post('/api/shares',json={'ticker':'NVDA','window':'1'}).json()==urls
 snap=e.snapshot(ident);assert 'research' not in snap and 'email' not in snap
 row['mentions']=99999
 assert e.snapshot(ident)['mentions']==1200
 anon=TestClient(s.app)
 page=anon.get(path);assert page.status_code==200
 assert 'og:image' in page.text and 'PRIVATE' not in page.text
 pic=anon.get('/api/shares/'+ident+'/image.png');assert pic.status_code==200 and pic.content.startswith(b'\x89PNG')
 assert a.post('/api/shares',json={'ticker':'AMD','window':'1'}).status_code==403
 assert anon.post('/api/shares',json={'ticker':'NVDA'}).status_code==401
 assert anon.get('/share/missing').status_code==404
 assert a.post('/api/shares',json={'ticker':'NVDA','window':'666'}).status_code==422
