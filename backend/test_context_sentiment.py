"""Shared fixtures use the isolated SQLite service from test_service."""
import json,time
from datetime import datetime,timezone
import httpx,pytest
from .test_service import isolate_tests,s
from . import context_sentiment as ai

def seed():
    s.ingest([{'id':'991122','author':'research','text':'$NVDA demand is accelerating. $MU margins are deteriorating.','created_at':datetime.now(timezone.utc).isoformat()}])
    return {'source':'x','id':'991122','text':'$NVDA demand is accelerating. $MU margins are deteriorating.','tickers':'MU,NVDA'}

def stance(label,evidence):return {'label':label,'confidence':.9,'reason':'The text supports this directional interpretation.','evidence':evidence}

def answer():return {'overall':stance('mixed','demand is accelerating'),'tickers':[{'ticker':'NVDA',**stance('bullish','demand is accelerating')},{'ticker':'MU',**stance('bearish','margins are deteriorating')}]}

def test_shared_cache_ticker_labels_and_changed_content(monkeypatch):
    monkeypatch.setenv('SENTIMENT_AI_ENABLED','true');p=seed();calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(answer())}}],'usage':{'prompt_tokens':500,'completion_tokens':150}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert ai.run_batch(client=client,token='mock')['completed']==1
        assert ai.run_batch(client=client,token='mock')['completed']==0
    assert len(calls)==1
    with s.db() as c:
        assert ai.annotate(c,[dict(p)],'MU')[0]['sentiment']=='bearish'
        assert ai.annotate(c,[dict(p)],'NVDA')[0]['sentiment']=='bullish'
        assert ai.annotate(c,[dict(p)])[0]['sentiment']=='mixed'
        changed={**p,'text':p['text']+' A correction follows.'}
        assert ai.annotate(c,[changed])[0]['sentiment']=='pending'
        assert c.execute('SELECT COUNT(*) FROM ai_sentiment_spend').fetchone()[0]==1

def test_invalid_evidence_and_tickers_rejected():
    p=seed();raw=answer();raw['tickers'][0]['evidence']='not in the source'
    with pytest.raises(ValueError):ai.validate(raw,p)
    raw=answer();raw['tickers'][0]['ticker']='MSFT'
    with pytest.raises(ValueError):ai.validate(raw,p)
    raw=answer();raw['tickers'][0]['confidence']=.4
    assert ai.validate(raw,p)['tickers'][0]['label']=='unclear'

def test_evidence_preserves_source_entities_and_rejects_joined_snippets():
    assert ai.source_quote('S&P is hard to ignore','The S&amp;P is hard to ignore.')=='S&amp;P is hard to ignore'
    assert ai.source_quote('“Demand” is rising','"Demand" is rising.')=='"Demand" is rising'
    with pytest.raises(ValueError):ai.source_quote('Demand is rising. Margins improved.','Demand is rising. But costs grew. Margins improved.')

def test_budget_and_lease_prevent_duplicate_purchases(monkeypatch):
    monkeypatch.setenv('SENTIMENT_AI_ENABLED','true');p=seed()
    def unexpected(request):raise AssertionError('No request should be sent')
    with s.db() as c:c.execute('INSERT INTO ai_sentiment(cache_key,source,post_id,model,version,status,lease_until,updated_at) VALUES(?,?,?,?,?,?,?,?)',(ai.cache_key(p),'x',p['id'],ai.MODEL,ai.VERSION,'running',time.time()+120,time.time()))
    with httpx.Client(transport=httpx.MockTransport(unexpected)) as client:
        assert ai.run_batch(client=client,token='mock')['completed']==0
        with s.db() as c:c.execute('UPDATE ai_sentiment SET lease_until=0')
        monkeypatch.setenv('SENTIMENT_AI_MONTHLY_USD','0')
        assert ai.run_batch(client=client,token='mock')['state']=='budget_paused'

def test_provider_failure_is_visible_and_not_retried_immediately(monkeypatch):
    monkeypatch.setenv('SENTIMENT_AI_ENABLED','true');p=seed();calls=[]
    def fail(request):calls.append(request);return httpx.Response(403,json={'error':'verification'})
    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        assert ai.run_batch(client=client,token='mock')['state']=='AI provider HTTP 403'
        assert ai.run_batch(client=client,token='mock')['state']=='provider_paused'
    assert len(calls)==1
    with s.db() as c:
        result=ai.annotate(c,[p])[0]
        assert result['sentiment']=='pending' and result['sentiment_status']=='error'
        assert c.execute('SELECT actual FROM ai_sentiment_spend').fetchone()[0] is None
