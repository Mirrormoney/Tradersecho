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


def test_third_attempt_recovers_without_alert(monkeypatch):
    monkeypatch.setenv('VERCEL_ENV','production');calls=[];delays=[]
    def transport(r):
        calls.append(r.url.path)
        if len(calls)<=6:raise httpx.ConnectTimeout('test')
        if r.url.path=='/login':return httpx.Response(200,text='<div id="root"></div>')
        if r.url.path=='/api/health':return httpx.Response(200,json={'ok':True})
        return httpx.Response(422,json={'detail':[]})
    with httpx.Client(transport=httpx.MockTransport(transport)) as c:
        assert a.run(client=c,sleep=delays.append)['state']=='recovered'
    assert len(calls)==9 and delays==[2,8]


def test_probe_records_safe_error_details_and_handles_invalid_json_shape(caplog):
    def transport(r):
        if r.url.path=='/login':raise httpx.ConnectError('secret must not be logged')
        return httpx.Response(200,json=[])
    with httpx.Client(transport=httpx.MockTransport(transport)) as c:
        assert a.probe(c)==['/login','/api/health','/api/auth/login']
    assert 'ConnectError' in caplog.text and 'elapsed_ms' in caplog.text
    assert 'secret must not be logged' not in caplog.text
