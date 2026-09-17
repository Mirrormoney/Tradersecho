import httpx,time
from .test_service import isolate_tests,s
from .ai_monitor import check

def test_low_credit_email_deduplicated_and_budget_warning(monkeypatch):
    monkeypatch.setenv('AI_ALERT_EMAIL','owner@example.invalid')
    monkeypatch.setenv('RESEND_API_KEY','mock')
    monkeypatch.setenv('SENTIMENT_AI_MONTHLY_USD','10')
    calls=[]
    def handler(r):
        calls.append(r)
        return httpx.Response(200,json={'balance':'1.50'} if r.method=='GET' else {'id':'mail'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert check({'state':'ready'},token='mock',client=client)['email_status']=='sent'
        assert check({'state':'ready'},token='mock',client=client)['state']=='cached'
        with s.db() as c:c.execute("UPDATE meta SET value='0' WHERE key='ai_monitor_checked'")
        check({'state':'ready'},token='mock',client=client)
    assert len([r for r in calls if r.method=='POST'])==1

def test_failed_email_is_retried(monkeypatch):
    monkeypatch.setenv('AI_ALERT_EMAIL','owner@example.invalid');monkeypatch.setenv('RESEND_API_KEY','mock')
    def handler(r):return httpx.Response(200,json={'balance':'0'}) if r.method=='GET' else httpx.Response(503)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert check({'state':'ready'},token='mock',client=client)['email_status']=='delivery_failed'
    with s.db() as c:assert not c.execute("SELECT value FROM meta WHERE key LIKE 'ai_alert:%'").fetchone()
