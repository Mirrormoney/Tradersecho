import httpx
from fastapi.testclient import TestClient
from . import availability as a
from .test_service import s,isolate_tests

def test_protected_and_preview(monkeypatch):
    monkeypatch.setenv('CRON_SECRET','test')
    assert TestClient(s.app).get('/api/cron/availability').status_code==401
    monkeypatch.setenv('VERCEL_ENV','preview')
    assert a.run()['state']=='preview_disabled'

def test_retry_recovers_without_email(monkeypatch):
    monkeypatch.setenv('VERCEL_ENV','production')
    calls=[]
    def transport(r):
        calls.append(r.url.path)
        if len(calls)==1:return httpx.Response(503)
        if r.url.path=='/login':return httpx.Response(200,text='<div id="root"></div>')
        if r.url.path=='/api/health':return httpx.Response(200,json={'ok':True})
        return httpx.Response(422,json={'detail':[]})
    with httpx.Client(transport=httpx.MockTransport(transport)) as c:
        assert a.run(client=c,sleep=lambda _:None)['state']=='recovered'
    assert len(calls)==6

def test_failure_alert_does_not_require_database(monkeypatch):
    monkeypatch.setenv('VERCEL_ENV','production')
    monkeypatch.setenv('OWNER_ALERT_EMAIL','owner@example.invalid')
    monkeypatch.setenv('RESEND_API_KEY','test-key')
    alerts=[]
    def transport(r):
        if r.url.host=='api.resend.com':
            alerts.append((r.headers['Idempotency-Key'],r.content))
            return httpx.Response(200,json={'id':'email'})
        return httpx.Response(503)
    with httpx.Client(transport=httpx.MockTransport(transport)) as c:
        assert a.run(36001,c,sleep=lambda _:None)['alert']=='sent'
        assert a.run(36301,c,sleep=lambda _:None)['alert']=='sent'
    assert alerts[0]==alerts[1]
