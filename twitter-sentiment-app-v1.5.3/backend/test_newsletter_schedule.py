from datetime import datetime,timezone
import json,time
import httpx
from .test_service import isolate_tests,s,make_account
from . import newsletter_schedule as n,email_delivery as delivery

def test_schedule_new_york_dst_weekends_months():
    stamp=lambda text:datetime.fromisoformat(text).timestamp()
    assert [x['edition'] for x in n.due_slots(stamp('2026-09-18T12:00:00+00:00'))]==['morning']
    assert [x['edition'] for x in n.due_slots(stamp('2026-12-18T13:00:00+00:00'))]==['morning']
    assert [x['edition'] for x in n.due_slots(stamp('2026-09-18T20:30:00+00:00'))]==['final']
    assert not n.due_slots(stamp('2026-09-19T12:00:00+00:00'))
    assert [x['edition'] for x in n.due_slots(stamp('2026-11-01T17:00:00+00:00'))]==['weekly','monthly']
    assert not n.due_slots(stamp('2026-09-18T11:59:00+00:00'))
    assert not n.due_slots(stamp('2026-09-18T14:01:00+00:00'))

def test_trial_reminder_once_and_cancel_after_purchase(monkeypatch):
    c,u=make_account('reminder@example.invalid');now=time.time()
    with s.db() as db:
        db.execute('UPDATE accounts SET email_verified=1,trial_started_at=?,trial_ends_at=? WHERE id=?',(now-6*86400,now+86390,u['id']))
        user=dict(db.execute('SELECT * FROM accounts WHERE id=?',(u['id'],)).fetchone())
        assert delivery.valid_recipient(db,user,'trial',now)
    assert n.enqueue(user,'trial')
    assert not n.enqueue(user,'trial')
    with s.db() as db:
        rows=db.execute('SELECT id,payload FROM email_deliveries').fetchall();assert len(rows)==1
        payload=json.loads(rows[0]['payload'])
        assert '$19/month or $190/year' in payload['html'] and '$999 once' in payload['html']
        assert 'ATTENTION · PERSPECTIVE · COMMUNITY' in payload['html']
        db.execute("UPDATE accounts SET plan='premium' WHERE id=?",(u['id'],))
    assert delivery.claim_delivery(rows[0]['id']) is None

def test_retry_dispatch_idempotency_and_reconciliation(monkeypatch):
    now=datetime(2026,9,18,12,0,tzinfo=timezone.utc).timestamp()
    monkeypatch.setattr(time,'time',lambda:now)
    monkeypatch.setenv('NEWSLETTER_ENABLED','true');monkeypatch.setenv('RESEND_API_KEY','test')
    c,u=make_account('scheduled@example.invalid')
    with s.db() as db:
        db.execute("UPDATE accounts SET plan='premium',email_verified=1 WHERE id=?",(u['id'],))
        db.execute('INSERT INTO newsletter_preferences VALUES(?,?,?)',(u['id'],'["morning"]',0))
    report={'ready':True,'date':'2026-09-18','subject':'Traders Echo Morning Roundup [2026-09-18]','tracked_stocks':1,'rows':[{'ticker':'MU','name':'Micron','mentions':50,'change':None}],'posts':[]}
    monkeypatch.setattr(n,'report_for',lambda slot,user:report)
    attempts=[]
    def transport(req):
        if req.method=='POST':
            attempts.append((req.headers['idempotency-key'],req.content))
            if len(attempts)==1:raise httpx.ReadTimeout('ambiguous send',request=req)
            return httpx.Response(200,json={'id':'email-test'})
        return httpx.Response(200,json={'last_event':'delivered'})
    client=httpx.Client(transport=httpx.MockTransport(transport))
    assert n.run(now,client)['errors']==1
    now+=301
    assert n.run(now,client)['sent']==1
    assert attempts[0]==attempts[1]
    assert n.run(now+300,client)['sent']==0
    with s.db() as db:assert db.execute('SELECT status FROM email_deliveries').fetchone()[0]=='delivered'

def test_period_reports_withhold_incomplete_comparisons(monkeypatch):
    now=datetime(2026,9,18,12,0,tzinfo=timezone.utc).timestamp();end=int(now//86400)*86400
    monkeypatch.setattr(s,'CATALOG',{'MU':('Micron','Memory')})
    _,u=make_account('periods@example.invalid');u={**u,'plan':'premium'}
    with s.db() as db:
        db.execute("INSERT INTO meta VALUES('completed_snapshot',?)",(str(end),))
        db.executemany('INSERT INTO x_counts VALUES(?,?,?,?,?,?)',[('MU',end-48*3600+i*3600,end-47*3600+i*3600,5,'test',now) for i in range(48)])
    result=n.report_for({'edition':'morning','at':now},u)
    assert result['rows'][0]['change']==0
    assert result['subject']=='Traders Echo Morning Roundup [2026-09-18]'
    assert len(result['other_windows'])==2
    for window in result['other_windows']:
        assert 'Partial history' in window['coverage_label']
        assert window['rows'][0]['change'] is None

def test_unauthenticated_cron_rejected(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv('CRON_SECRET','private-test-only')
    assert TestClient(s.app).get('/api/cron/email').status_code==401
