import json,sqlite3
from datetime import datetime,timedelta
from . import signal_lab as lab

NOW=datetime(2026,9,24,12,0,tzinfo=lab.NY).timestamp()

def test_scoring_module_is_in_deployment_allowlist():
    from pathlib import Path
    ignore=(Path(__file__).resolve().parents[1]/'.vercelignore').read_text(encoding='utf8')
    assert '!backend/signal_lab.py' in ignore.splitlines()

def post(author,ts,label,text=None):
    return dict(author=author,ts=ts,text=text or f'$NVDA {author} expects earnings growth to continue',sentiment_status='done',ticker_sentiments=[dict(ticker='NVDA',label=label)])

def counts(current=100,previous=50,baseline=50):
    return dict(end=NOW,current=current,previous=previous,baseline=baseline,baseline_days=5)


def test_attention_does_not_require_sentiment():
    rows=[post('user'+chr(97+i),NOW-100,'neutral') for i in range(10)]
    for p in rows:p['sentiment_status']='pending'
    a=lab.x_axis(rows,'NVDA',NOW,counts())
    assert a['score']==100 and a['direction'] is None
    assert a['details']['independent_authors']==10 and a['details']['sentiment']=='unavailable'
    assert a['details']['component_coverage']==100


def test_count_only_zero_missing_and_future():
    a=lab.x_axis([],'NVDA',NOW,counts())
    assert a['score']==100 and a['details']['breadth_score'] is None
    assert a['details']['component_coverage']==80
    assert lab.x_axis([],'NVDA',NOW,counts(0,0,0))['score']==0
    assert lab.x_axis([],'NVDA',NOW)['score'] is None
    future=[post('future',NOW+1,'bullish')]
    assert lab.x_axis(future,'NVDA',NOW,counts())['details']['sampled_posts']==0


def test_author_concentration_duplicates_and_separate_direction():
    rows=[post('same',NOW-100,'bearish',f'$NVDA earnings concern {chr(97+i)} remains uncertain') for i in range(10)]
    a=lab.x_axis(rows+rows,'NVDA',NOW,counts())
    assert a['details']['sampled_posts']==10 and a['details']['independent_authors']==1
    assert a['details']['breadth_score']==1
    rows=[post('user'+chr(97+i),NOW-100,'bearish') for i in range(10)]
    a=lab.x_axis(rows,'NVDA',NOW,counts())
    assert a['score']==100 and a['direction'] is None and a['details']['sentiment']=='bearish'


def test_hourly_windows_query_coverage_and_baseline():
    from .screening import stock_query
    rows=[]
    # Thursday and three prior weekdays, matching NY-clock endpoints.
    for days in (0,1,2,3):
        end=NOW-days*86400
        for i in range(6):rows.append(dict(start=end-(i+1)*3600,end=end-i*3600,n=10,query=stock_query('NVDA'),fetched_at=end))
    a=lab.attention_counts(rows,'NVDA',NOW)
    assert a['current']==30 and a['previous']==30 and a['baseline_days']==3
    assert 'error' in lab.attention_counts(rows[1:],'NVDA',NOW)
    assert 'error' in lab.attention_counts(rows,'NVDA',NOW+7201)
    assert 'error' in lab.attention_counts(rows,'AI',NOW)
    rows[-1]['fetched_at']=NOW+1
    assert lab.attention_counts(rows,'NVDA',NOW)['baseline_days']==3 # outside baseline 3h
    rows[-6]['fetched_at']=NOW+1
    assert 'error' in lab.attention_counts(rows,'NVDA',NOW)

def test_volume_thresholds_and_staleness():
    s=dict(price_fresh=True,volume_baseline=dict(relative_volume=2,persistence=3,sessions=20))
    assert lab.volume_axis(s)['score']==100
    s['price_fresh']=False
    assert lab.volume_axis(s)['score'] is None

def test_options_partial_and_history_gates():
    sample=dict(at=NOW,partial=False,bull=200,bear=0,accepted=30)
    s=dict(filtered_options=sample)
    assert lab.options_axis(s,[],NOW)['score'] is None
    past=[]
    for i in range(1,21):
        prev={**sample,'bull':100,'at':NOW-i*86400}
        past.append(dict(observed=NOW-i*86400,version=lab.VERSION,payload=json.dumps({'options_observation':prev})))
    assert lab.options_axis(s,past,NOW)['score']==100
    sample['partial']=True
    assert lab.options_axis(s,past,NOW)['score'] is None
    sample['partial']=False
    assert lab.options_axis(s,past,NOW+1201)['score'] is None
    for row in past:row['version']='lab-0.2'
    assert lab.options_axis(s,past,NOW)['score']==100
    past[-1]['version']='older-rules'
    assert lab.options_axis(s,past,NOW)['score'] is None

def test_catalyst_publication_date_readthrough_and_missing():
    item=dict(report_date='2026-09-24',summary='Broker raises estimates.',original=True,id='a',stance='bullish')
    a=lab.catalyst_axis([item],NOW)
    assert a['score']==73 and a['direction'] is None
    assert lab.catalyst_axis([{**item,'report_date':'2026-09-25'}],NOW)['score'] is None
    assert lab.catalyst_axis([{**item,'report_date':'2026-09-01'}],NOW)['score'] is None
    assert lab.catalyst_axis([{**item,'link_type':'readthrough'}],NOW)['score']<a['score']

def test_setup_requires_direction_volume_and_confirmation():
    axes=[lab.axis('Price',80,directional=True),lab.axis('Volume',80),lab.axis('Options'),lab.axis('X',80),lab.axis('Catalyst')]
    assert lab.candidate(axes)=='bullish'
    axes[0]=lab.axis('Price',20,directional=True)
    assert lab.candidate(axes)=='bearish'
    axes[3]=lab.axis('X',20)
    assert lab.candidate(axes)=='watch'
    axes[0]=lab.axis('Price')
    assert lab.candidate(axes)=='insufficient_data'

def test_price_aligned_benchmarks_and_history():
    candles=[dict(at=NOW-(14-i)*600,close=100+i*.1,high=101+i*.1,low=99+i*.1,volume=100) for i in range(15)]
    stock=dict(ticker='NVDA',price_at=NOW,price_fresh=True,return_60m=1,candles=candles)
    peers=[dict(ticker=f'P{i}',price_at=NOW,price_fresh=True,return_60m=0) for i in range(10)]
    catalog={t:('name','sector') for t in ['NVDA',*[p['ticker'] for p in peers]]}
    history=[]
    for i in range(1,21):history.extend([dict(at=NOW-i*86400-3600,close=100),dict(at=NOW-i*86400,close=101)])
    assert lab.price_axis(stock,peers,catalog,history)['score'] is not None
    peers[0]['price_at']-=600
    assert lab.price_axis(stock,peers,catalog,history)['score'] is None

def test_record_idempotency_and_forward_outcome(monkeypatch):
    c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
    first=NOW-3600
    panel=dict(ticker='NVDA',price_at=first,price=100,observed=first,candidate='watch',setup='Watching',axes=[],options_observation=None)
    monkeypatch.setattr(lab,'build',lambda *args:[panel])
    lab.record(c,{}, {}, ['NVDA'],first)
    panel['price']=999
    lab.record(c,{}, {}, ['NVDA'],first)
    assert c.execute('SELECT price FROM signal_lab_snapshots').fetchone()[0]==100
    bars=[dict(at=first+i*600,close=100+i,low=99+i,high=101+i) for i in range(1,7)]
    monkeypatch.setattr(lab,'build',lambda *args:[])
    lab.record(c,{'NVDA':{'candles':bars}}, {}, ['NVDA'],NOW)
    result=json.loads(c.execute('SELECT outcome FROM signal_lab_snapshots').fetchone()[0])
    assert result['return_1h']==6 and result['cost_adjusted_long']==5.9
    assert result['cost_adjusted_short']==-6.1
