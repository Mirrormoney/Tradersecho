import json,time
from datetime import datetime,timezone
import httpx,pytest
from .test_service import isolate_tests,s,make_account
from . import social
from .social_art import card,banner
@pytest.fixture(autouse=True)
def reset_social():
    with s.db() as c:c.execute('DELETE FROM social_editions')

def report():return {'title':'Morning radar','label':'24 hours','rows':[{'ticker':t,'name':t,'mentions':100,'change':10,'as_of':1000} for t in ['NVDA','MU','AMD']],'text':'Morning radar','as_of':1000,'max_age':129600}

def test_art_and_owner_protection():
    assert card(report()).startswith(b'\x89PNG') and banner().startswith(b'\x89PNG')
    c,u=make_account('social-member@example.invalid')
    assert c.get('/api/admin/social').status_code==403
    assert c.get('/api/cron/social').status_code==401

def setup(monkeypatch):
    now=datetime(2026,9,18,12,0,tzinfo=timezone.utc).timestamp()
    monkeypatch.setenv('VERCEL_ENV','production');monkeypatch.setenv('X_PUBLISH_CONSUMER_KEY','test');monkeypatch.setenv('X_PUBLISH_CONSUMER_SECRET','test-secret')
    token={'oauth_token':'test','oauth_token_secret':'test'}
    with s.db() as c:
        social.save(c,'social_connection',{'secret':social.cipher().encrypt(json.dumps(token).encode()).decode(),'handle':'Tradersecho','id':'brand'})
        social.save(c,'social_paused',False);social.save(c,'social_label_confirmed',True)
    monkeypatch.setattr(social,'prepare',lambda *a:report())
    return now

def test_at_most_once_and_budget(monkeypatch):
    now=setup(monkeypatch);calls=[]
    def transport(req):
        calls.append(str(req.url))
        if req.url.path=='/2/users/me':return httpx.Response(200,json={'data':{'id':'brand','username':'Tradersecho'}})
        if req.url.path=='/2/media/upload':return httpx.Response(200,json={'data':{'id':'media'}})
        return httpx.Response(201,json={'data':{'id':'post'}})
    monkeypatch.setattr(social,'client',lambda *a:httpx.Client(transport=httpx.MockTransport(transport)))
    assert social.run(now)['sent']==1
    assert social.run(now+300)['sent']==0
    assert len(calls)==3
    with s.db() as c:
        assert c.execute('SELECT status FROM social_editions').fetchone()[0]=='published'
        assert c.execute("SELECT reserved FROM x_spend WHERE kind='social_publish'").fetchone()[0]==.5

def test_manual_research_publishes_only_once(monkeypatch):
    setup(monkeypatch)
    now=datetime(2026,9,23,15,0,tzinfo=timezone.utc).timestamp()
    writes=[]
    def transport(req):
        if req.url.path=='/2/users/me':return httpx.Response(200,json={'data':{'id':'brand','username':'Tradersecho'}})
        if req.url.path=='/2/media/upload':return httpx.Response(200,json={'data':{'id':'media'}})
        writes.append(json.loads(req.content));return httpx.Response(201,json={'data':{'id':'research-post'}})
    monkeypatch.setattr(social,'client',lambda *a:httpx.Client(transport=httpx.MockTransport(transport)))
    assert social.run(now,manual_research=True)['sent']==1
    assert social.run(now+300,manual_research=True)['sent']==0
    assert len(writes)==1 and '$LITE' in writes[0]['text']
    with s.db() as c:
        rows=c.execute('SELECT id,status FROM social_editions').fetchall()
        assert len(rows)==1 and rows[0][0]=='research:2026-09-23' and rows[0][1]=='published'

def test_ambiguous_publish_blocks_retries(monkeypatch):
    now=setup(monkeypatch);writes=[]
    def transport(req):
        if req.url.path=='/2/users/me':return httpx.Response(200,json={'data':{'id':'brand','username':'Tradersecho'}})
        if req.url.path=='/2/media/upload':return httpx.Response(200,json={'data':{'id':'media'}})
        writes.append(1);raise httpx.ReadTimeout('ambiguous',request=req)
    monkeypatch.setattr(social,'client',lambda *a:httpx.Client(transport=httpx.MockTransport(transport)))
    assert social.run(now)['state']=='review_required'
    social.run(now+300)
    assert len(writes)==1
    with s.db() as c:assert c.execute('SELECT status FROM social_editions').fetchone()[0]=='uncertain'

def test_wrong_account_never_posts(monkeypatch):
    now=setup(monkeypatch);calls=[]
    def transport(req):
        calls.append(req.method);return httpx.Response(200,json={'data':{'id':'personal','username':'knockouttrader'}})
    monkeypatch.setattr(social,'client',lambda *a:httpx.Client(transport=httpx.MockTransport(transport)))
    assert social.run(now)['state']=='review_required';assert calls==['GET']

def test_stale_or_partial_snapshot_withheld():
    with pytest.raises(ValueError):social.prepare('weekly',time.time())

def test_preview_cannot_publish(monkeypatch):
    monkeypatch.setenv('VERCEL_ENV','preview');assert social.run()['state']=='preview_disabled'

def test_preflight_uploads_once_without_posting(monkeypatch):
    setup(monkeypatch);calls=[]
    monkeypatch.setattr(social,'owner',lambda request:{'role':'owner'})
    def transport(req):
        calls.append(req.url.path)
        if req.url.path=='/2/users/me':return httpx.Response(200,json={'data':{'id':'brand','username':'Tradersecho'}})
        assert req.url.path=='/2/media/upload'
        return httpx.Response(200,json={'data':{'id':'media'}})
    monkeypatch.setattr(social,'client',lambda *a:httpx.Client(transport=httpx.MockTransport(transport)))
    assert social.preflight(None)['state']=='passed'
    assert social.preflight(None)['state']=='passed'
    assert calls==['/2/users/me','/2/media/upload']
    with s.db() as c:assert c.execute('SELECT COUNT(*) FROM social_editions').fetchone()[0]==0

def test_real_oauth_signing_preserves_upload_and_post_bodies(monkeypatch):
    monkeypatch.setenv('X_PUBLISH_CONSUMER_KEY','test');monkeypatch.setenv('X_PUBLISH_CONSUMER_SECRET','test-secret')
    bodies=[]
    def transport(req):
        if req.url.path=='/2/users/me':return httpx.Response(200,json={'data':{'id':'brand','username':'Tradersecho'}})
        bodies.append(json.loads(req.content))
        return httpx.Response(200,json={'data':{'id':'media'}})
    with social.client({'oauth_token':'test','oauth_token_secret':'test'}) as x:
        x._transport=httpx.MockTransport(transport)
        x._mounts={}
        social.upload_checked(x,{'id':'brand'},b'png-test')
        x.post('https://api.x.com/2/tweets',json={'text':'Test caption','media':{'media_ids':['media']}})
    assert bodies[0]['media']=='cG5nLXRlc3Q='
    assert bodies[1]['text']=='Test caption'

def test_promo_rotation_and_duplicate_ticks(monkeypatch):
    setup(monkeypatch);texts=[]
    monkeypatch.setattr(social,'due_slots',lambda now:[])
    def transport(req):
        if req.url.path=='/2/users/me':return httpx.Response(200,json={'data':{'id':'brand','username':'Tradersecho'}})
        if req.url.path=='/2/media/upload':return httpx.Response(200,json={'data':{'id':'media'}})
        texts.append(json.loads(req.content)['text'])
        return httpx.Response(201,json={'data':{'id':str(len(texts))}})
    monkeypatch.setattr(social,'client',lambda *a:httpx.Client(transport=httpx.MockTransport(transport)))
    for day in range(19,31,2):
        now=datetime(2026,9,day,17,tzinfo=timezone.utc).timestamp()
        assert social.run(now)['sent']==1
        assert social.run(now+300)['sent']==0
    assert texts==social.social_promos.COPY

def test_promo_schedule_boundaries():
    from .social_promos import slots,prepare,artwork
    for stamp in ['2026-09-18T17:00:00+00:00','2026-09-19T16:59:00+00:00','2026-09-19T19:00:00+00:00','2026-09-20T17:00:00+00:00']:
        assert not slots(datetime.fromisoformat(stamp).timestamp())
    # First Sunday after DST ends is on the two-day cadence; 13 NY is 18 UTC.
    assert slots(datetime(2026,11,2,18,tzinfo=timezone.utc).timestamp())
    for i in range(6):assert artwork(prepare(i)).startswith(b'\x89PNG')


def test_explicit_rejection_skips_without_blocking_with_reason(monkeypatch):
    now=setup(monkeypatch)
    def transport(req):
        if req.url.path=='/2/users/me':return httpx.Response(200,json={'data':{'id':'brand','username':'Tradersecho'}})
        if req.url.path=='/2/media/upload':return httpx.Response(200,json={'data':{'id':'media'}})
        return httpx.Response(403,json={'detail':'Only one cashtag is permitted.'})
    monkeypatch.setattr(social,'client',lambda *a:httpx.Client(transport=httpx.MockTransport(transport)))
    assert social.run(now)['state']=='edition_rejected'
    assert social.run(now+300)['sent']==0
    with s.db() as c:
        r=c.execute('SELECT status,error FROM social_editions').fetchone()
        assert r['status']=='rejected'
        assert social.value(c,'social_paused') is False
        assert '403' in r['error'] and 'Only one cashtag' in r['error']


def test_manual_promo_claims_scheduled_slot(monkeypatch):
    setup(monkeypatch);writes=[]
    def transport(req):
        if req.url.path=='/2/users/me':return httpx.Response(200,json={'data':{'id':'brand','username':'Tradersecho'}})
        if req.url.path=='/2/media/upload':return httpx.Response(200,json={'data':{'id':'media'}})
        writes.append(json.loads(req.content)['text'])
        return httpx.Response(201,json={'data':{'id':'promo'}})
    monkeypatch.setattr(social,'client',lambda *a:httpx.Client(transport=httpx.MockTransport(transport)))
    now=datetime(2026,9,19,10,tzinfo=timezone.utc).timestamp()
    assert social.run(now,manual_promo=True)['sent']==1
    assert social.run(now+60,manual_promo=True)['sent']==0
    assert social.run(now+7*3600)['sent']==0
    assert writes==[social.social_promos.COPY[0]]
    c,u=make_account('promo-member@example.invalid')
    assert c.post('/api/admin/social/publish-promotion').status_code==403


def test_weekday_editions_use_fresh_intraday_on_monday():
    now=datetime(2026,9,21,12,0,tzinfo=timezone.utc).timestamp()
    with s.db() as c:
        for ticker,n in [('NVDA',10),('MU',20),('AMD',30)]:
            for i in range(6):
                c.execute('INSERT INTO x_counts VALUES(?,?,?,?,?,?)',(ticker,now-21600+i*3600,now-18000+i*3600,n if i<3 else n*2,'test',now))
        # A stale high-volume name must not enter either edition.
        for i in range(6):
            c.execute('INSERT INTO x_counts VALUES(?,?,?,?,?,?)',('AAPL',now-108000+i*3600,now-104400+i*3600,9999,'test',now))
    morning=social.prepare('morning',now)
    closing=social.prepare('final',now)
    assert morning['rows']==closing['rows']
    assert [r['ticker'] for r in morning['rows']]==['AMD','MU','NVDA']
    assert morning['rows'][0]['mentions']==180
    assert morning['rows'][0]['change']==100
    assert '3 hours' in morning['text'] and '24h' not in morning['text']
    assert morning['max_age']==7200
    with pytest.raises(ValueError):social.prepare('morning',now+7201)


def test_promo_direct_destinations():
    copy=social.social_promos.COPY
    assert len(copy)==6
    assert copy[1].endswith('https://tradersecho.com/ai-supply-chain')
    assert copy[3].endswith('https://tradersecho.com/sec-filings')
    assert copy[4].endswith('https://tradersecho.com/ai-supply-chain')
    assert copy[3].startswith('Find the names gaining attention and immediately check their latest available SEC filings.')


@pytest.mark.parametrize('edition,days,hook',[('weekly',7,'this week'),('monthly',30,'this month')])
def test_period_spotlight_keeps_three_graphic_rows(monkeypatch,edition,days,hook):
    from . import count_metrics
    import re
    now=datetime(2026,10,1,16,tzinfo=timezone.utc).timestamp()
    monkeypatch.setattr(s,'reference',lambda source,c:now)
    seen=[]
    def rows(c,items,end,window):
        seen.append(window)
        return [{'ticker':t,'name':t,'heat':99.2-i,'mentions':20259-i,'change':None,'coverage_hours':days*24} for i,t in enumerate(['NVDA','MU','AMD'])]
    monkeypatch.setattr(count_metrics,'enrich',rows)
    p=social.prepare(edition,now)
    assert seen==[days] and len(p['rows'])==3
    assert p['text'].count('$')==1 and '$NVDA' in p['text']
    assert hook in p['text'] and '20,259' in p['text'] and '99.2' in p['text']
    assert '%' not in p['text'] and len(re.sub(r'https://\S+','x'*23,p['text']))<=280
    rows_incomplete=lambda *a:[{'ticker':t,'heat':10,'coverage_hours':days*24-1} for t in ['NVDA','MU','AMD']]
    monkeypatch.setattr(count_metrics,'enrich',rows_incomplete)
    with pytest.raises(ValueError):social.prepare(edition,now)


def test_rejected_post_does_not_block_following_promotion(monkeypatch):
    now=setup(monkeypatch);writes=[]
    def transport(req):
        if req.url.path=='/2/users/me':return httpx.Response(200,json={'data':{'id':'brand','username':'Tradersecho'}})
        if req.url.path=='/2/media/upload':return httpx.Response(200,json={'data':{'id':'media'}})
        writes.append(json.loads(req.content)['text'])
        if len(writes)==1:return httpx.Response(403,json={'errors':[{'code':99,'message':'Only one cashtag permitted'}]})
        return httpx.Response(201,json={'data':{'id':'success'}})
    monkeypatch.setattr(social,'client',lambda *a:httpx.Client(transport=httpx.MockTransport(transport)))
    assert social.run(now)['state']=='edition_rejected'
    assert social.run(now+300)['sent']==0
    assert social.run(datetime(2026,9,19,17,tzinfo=timezone.utc).timestamp())['sent']==1
    with s.db() as c:
        r=c.execute("SELECT error FROM social_editions WHERE status='rejected'").fetchone()
        assert 'Only one cashtag permitted' in r[0]
    assert len(writes)==2


def test_auth_rejection_still_pauses(monkeypatch):
    now=setup(monkeypatch)
    def transport(req):
        if req.url.path=='/2/users/me':return httpx.Response(200,json={'data':{'id':'brand','username':'Tradersecho'}})
        if req.url.path=='/2/media/upload':return httpx.Response(200,json={'data':{'id':'media'}})
        return httpx.Response(401,json={'detail':'Unauthorized'})
    monkeypatch.setattr(social,'client',lambda *a:httpx.Client(transport=httpx.MockTransport(transport)))
    assert social.run(now)['state']=='review_required'
    with s.db() as c:assert social.value(c,'social_paused') is True


def test_research_promotion_asset():
    from PIL import Image
    from io import BytesIO
    p=social.social_promos.prepare(5)
    assert p['text'].endswith('https://tradersecho.com/trending-research')
    im=Image.open(BytesIO(social.social_promos.artwork(p)))
    assert im.width>1000 and im.height>600
    assert len(im.getcolors(im.width*im.height))>100


def test_monthly_worker_publishes_once(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setattr(social.social_promos,'slots',lambda now:[])
    calls=[]
    def transport(req):
        if req.url.path=='/2/users/me':return httpx.Response(200,json={'data':{'id':'brand','username':'Tradersecho'}})
        if req.url.path=='/2/media/upload':return httpx.Response(200,json={'data':{'id':'media'}})
        calls.append(req.url.path);return httpx.Response(201,json={'data':{'id':'monthly'}})
    monkeypatch.setattr(social,'client',lambda *a:httpx.Client(transport=httpx.MockTransport(transport)))
    now=datetime(2026,10,1,16,tzinfo=timezone.utc).timestamp()
    assert social.run(now)['sent']==1
    assert social.run(now+300)['sent']==0
    with s.db() as c:assert c.execute("SELECT status FROM social_editions WHERE id='monthly:2026-10-01'").fetchone()[0]=='published'
    assert len(calls)==1
