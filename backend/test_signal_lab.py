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

def test_x_minimums_author_cap_and_no_future():
    rows=[post('user'+chr(97+i),NOW-100,'bullish') for i in range(10)]
    rows += [post('old'+chr(97+i),NOW-11000,'bearish') for i in range(10)]
    assert lab.x_axis(rows,'NVDA',NOW)['score']==100
    rows += [post('usera',NOW-50,'bullish',f'$NVDA same author alternative {chr(97+i)}') for i in range(20)]
    rows += [post('future',NOW+1,'bearish')]
    a=lab.x_axis(rows,'NVDA',NOW)
    assert a['details']['current']['authors']==10
    assert lab.x_axis(rows[:5],'NVDA',NOW)['score'] is None

def test_pending_sentiment_not_neutral_or_directional():
    rows=[post('user'+chr(97+i),NOW-100,'bullish') for i in range(10)]
    for p in rows:p['sentiment_status']='pending'
    assert lab.x_axis(rows,'NVDA',NOW)['details']['current']['authors']==0

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
    axes=[lab.axis('Price',80,directional=True),lab.axis('Volume',80),lab.axis('Options'),lab.axis('X',80,directional=True),lab.axis('Catalyst')]
    assert lab.candidate(axes)=='bullish'
    axes[3]=lab.axis('X',20,directional=True)
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
