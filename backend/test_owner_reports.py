import json
from datetime import datetime
import httpx
from fastapi.testclient import TestClient
from .test_service import s, isolate_tests
from . import owner_reports as o

def configured(monkeypatch):
    monkeypatch.setenv('BILLING_SANDBOX','false')
    monkeypatch.setenv('VERCEL_ENV','production')
    monkeypatch.setenv('AI_ALERT_EMAIL','owner@example.com')
    monkeypatch.setenv('RESEND_API_KEY','test')

def test_signup_durable_once_and_duplicates(monkeypatch):
    configured(monkeypatch)
    monkeypatch.setattr('backend.account_security.configured',lambda:False)
    client=TestClient(s.app)
    body={'email':'new@example.com','display_name':'New Member','password':'secure-test-password'}
    assert client.post('/api/auth/signup',json=body).status_code==200
    assert client.post('/api/auth/signup',json=body).status_code==409
    captured=[]
    def send(req):
        captured.append(json.loads(req.content));return httpx.Response(200,json={'id':'test-id'})
    with httpx.Client(transport=httpx.MockTransport(send)) as mail:
        assert o.run(client=mail)['sent']==1
        assert o.run(client=mail)['sent']==0
    assert len(captured)==1 and captured[0]['to']==['owner@example.com']
    assert 'New Member' in captured[0]['text']
    assert 'secure-test-password' not in str(captured)

def test_weekly_window_and_ledger(monkeypatch):
    configured(monkeypatch)
    end=datetime(2026,9,20,18,tzinfo=o.BERLIN).timestamp()
    start,slot=o.weekly_slot(end)
    assert slot==end and o.weekly_slot(end-1)[1]<end
    with s.db() as c:
        o.save(c,'owner_mail_enabled_at',end-86400)
        c.execute("INSERT INTO x_spend(month,kind,reserved,actual_estimate,ts,status) VALUES('2026-09','posts',2,1,?,'done')",(end-100,))
        c.execute("INSERT INTO ai_sentiment_spend(id,cache_key,month,reserved,actual,ts,status,usage) VALUES('owner-test','c','2026-09',.02,.01,?,'received',?)",(end-100,json.dumps({'total_tokens':123})))
    data=o.report(start,end)
    assert data['ai_tokens']==123 and data['estimated_total']==1.01
    captured=[]
    with httpx.Client(transport=httpx.MockTransport(lambda req:(captured.append(json.loads(req.content)) or httpx.Response(200,json={'id':'weekly'})))) as mail:
        assert o.run(now=end+60,client=mail)['sent']==1
        assert o.run(now=end+360,client=mail)['sent']==0
    assert 'Weekly performance' in captured[0]['subject']
    assert 'not invoices' in captured[0]['text']
    assert captured[0]['attachments']

def test_uncertain_retry_same_key_and_expiry(monkeypatch):
    configured(monkeypatch)
    now=1800000000
    with s.db() as c:
        o.save(c,o.PREFIX+'test',{'kind':'signup','created':now,'status':'pending','next':0,'payload':{'to':['owner@example.com'],'subject':'test'}})
    keys=[]
    def fail(req):
        keys.append(req.headers['Idempotency-Key']);return httpx.Response(503)
    with httpx.Client(transport=httpx.MockTransport(fail)) as mail:
        o.run(now=now,client=mail)
        o.run(now=now+300,client=mail)
        o.run(now=now+86400,client=mail)
    assert len(keys)==2 and keys[0]==keys[1]
    with s.db() as c: assert o.get(c,o.PREFIX+'test')['status']=='needs_review'

def test_preview_disabled_and_admin_protected(monkeypatch):
    configured(monkeypatch)
    monkeypatch.setenv('VERCEL_ENV','preview')
    assert o.run()['state']=='disabled_nonproduction'
    assert TestClient(s.app).get('/api/admin/owner-emails').status_code in (401,403)

def test_research_alert_deduplicates_and_uses_owner_queue(monkeypatch):
    configured(monkeypatch)
    monkeypatch.setenv('RESEARCH_DRIVE_ENABLED','true')
    captured=[]
    with httpx.Client(transport=httpx.MockTransport(lambda req:(captured.append(json.loads(req.content)) or httpx.Response(200,json={'id':'health'})))) as mail:
        assert o.run(client=mail)['sent']==1
        assert o.run(client=mail)['sent']==0
    assert 'Research import' in captured[0]['subject']
    assert 'heartbeat is overdue' in captured[0]['text']
    assert captured[0]['to']==['owner@example.com']
