"""Private, deterministic forward evaluation. Never fetches paid data or calls AI.

Versioned pilot rules, not calibrated forecasts. Snapshots preserve what was known
at observation time; missing research uses an explicitly labelled neutral baseline.
"""
import json, math, statistics, time, re
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
VERSION = 'lab-0.5'
OPTIONS_COMPATIBLE_VERSIONS = ('lab-0.2','lab-0.3','lab-0.4','lab-0.5')
TITLES = ['Price strength', 'Volume confirmation', 'Options pressure', 'X attention', 'Catalyst strength']


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS signal_lab_snapshots(
      ticker TEXT,slot INTEGER,version TEXT,observed REAL,price_at REAL,price REAL,
      payload TEXT,outcome TEXT,PRIMARY KEY(ticker,slot,version));
    CREATE INDEX IF NOT EXISTS signal_lab_observed ON signal_lab_snapshots(observed);
    ''')


def clamp(v): return round(max(0, min(100, v)), 1)


def axis(name, score=None, reason='', directional=False, **details):
    return dict(name=name, score=score, strength=(round(abs(score-50)*2,1) if directional else score) if score is not None else None,
                direction=('bullish' if score>55 else 'bearish' if score<45 else 'balanced') if directional and score is not None else None,
                state='ready' if score is not None else 'unavailable', reason=reason, details=details)


def price_axis(stock, peers, catalog, history):
    """v0.2 uses the fixed covered pilot basket and a labelled candle VWAP proxy."""
    end=stock['price_at']; ticker=stock['ticker']
    if not stock['price_fresh'] or stock['return_60m'] is None:
        return axis(TITLES[0],reason='A fresh, complete 60-minute price window is required.')
    available=[s for s in peers if s['ticker']!=ticker and s['price_at']==end and s['price_fresh'] and s['return_60m'] is not None]
    sector=[s for s in available if catalog[s['ticker']][1]==catalog[ticker][1]]
    if len(sector)<5 or len(available)<10:
        return axis(TITLES[0],reason='Need five aligned sector peers and ten aligned covered-basket peers.',sector_peers=len(sector),basket_peers=len(available))
    byday={}; dt=datetime.fromtimestamp(end,NY); minute=dt.hour*60+dt.minute
    for r in history:
        d=datetime.fromtimestamp(r['at'],NY)
        if d.date()<dt.date() and r.get('close',0)>0:byday.setdefault(d.date(),{})[d.hour*60+d.minute]=r['close']
    days=sorted(byday,reverse=True)[:20]
    returns=[abs((byday[d][minute]/byday[d][minute-60]-1)*100) for d in days if minute in byday[d] and minute-60 in byday[d]]
    candles=stock['candles']
    expected=list(range(580,minute+1,10))
    clock=[datetime.fromtimestamp(r['at'],NY).hour*60+datetime.fromtimestamp(r['at'],NY).minute for r in candles]
    if len(returns)<20 or clock!=expected or any(not all(k in r for k in ('high','low','close','volume')) for r in candles):
        return axis(TITLES[0],reason='Building 20 same-time price sessions and a complete session VWAP proxy.',sessions=len(returns))
    volume=sum(r['volume'] for r in candles)
    if volume<=0:return axis(TITLES[0],reason='No usable session volume.')
    proxy=sum((r['high']+r['low']+r['close'])/3*r['volume'] for r in candles)/volume
    scale=max(.1,statistics.median(returns))
    sector_return=statistics.mean(s['return_60m'] for s in sector)
    basket_return=statistics.mean(s['return_60m'] for s in available)
    components=[(stock['return_60m']-sector_return)/scale,(stock['return_60m']-basket_return)/scale,(candles[-1]['close']/proxy-1)*100/scale]
    score=clamp(50+25*sum(w*max(-2,min(2,v)) for w,v in zip((.4,.4,.2),components)))
    return axis(TITLES[0],score,'40% sector-relative, 40% covered-pilot-basket-relative, 20% candle VWAP proxy; volatility scaled.',True,
                sector_peers=[s['ticker'] for s in sector],basket_peers=[s['ticker'] for s in available],sector_return=round(sector_return,3),basket_return=round(basket_return,3),volatility_scale=round(scale,3),vwap_proxy=round(proxy,3))


def volume_axis(stock):
    v=stock.get('volume_baseline') or {}; ratio=v.get('relative_volume')
    if not stock['price_fresh'] or ratio is None:return axis(TITLES[1],reason='Needs fresh volume and 20 complete same-time sessions.',sessions=v.get('sessions',0))
    # 1x volume = 50, 2x = 100; persistence is independent of direction.
    score=clamp(.7*min(100,50*ratio)+.3*(v['persistence']/3*100))
    return axis(TITLES[1],score,'70% relative volume (2x reaches 100), 30% three-candle persistence.',relative_volume=ratio,persistence=v['persistence'],sessions=v['sessions'])


def options_axis(stock, past, now):
    f=stock.get('filtered_options') or {}; at=f.get('at',0)
    if not at or not 0<=now-at<=1200 or f.get('partial'):
        return axis(TITLES[2],reason='Requires a fresh, fully collected options window. Partial samples are excluded.')
    dt=datetime.fromtimestamp(at,NY)
    if dt.hour*60+dt.minute<630:return axis(TITLES[2],reason='The first full regular-session hour is not complete.')
    total=f.get('bull',0)+f.get('bear',0)
    if total<=0 or f.get('accepted',0)<20:return axis(TITLES[2],reason='Need at least 20 classified trades and positive premium.')
    days={}
    for r in past:
        d=datetime.fromtimestamp(r['observed'],NY)
        if r['version'] not in OPTIONS_COMPATIBLE_VERSIONS or d.date()>=dt.date() or abs((d.hour*60+d.minute)-(dt.hour*60+dt.minute))>5:continue
        prev=json.loads(r['payload']).get('options_observation') or {}
        if prev.get('partial') or prev.get('accepted',0)<20:continue
        p=prev.get('bull',0)+prev.get('bear',0)
        if p>0:days[d.date()]=p
    baseline=[days[d] for d in sorted(days,reverse=True)[:20]]
    balance=(f['bull']-f['bear'])/total
    if len(baseline)<20:return axis(TITLES[2],reason='Collecting 20 comparable sessions before scoring unusualness.',sessions=len(baseline),premium_balance=round(balance,3),classified=f['accepted'])
    ratio=total/statistics.median(baseline)
    unusual=max(0,min(1,ratio-1))
    score=clamp(50+50*(.6*balance+.4*unusual*(1 if balance>0 else -1 if balance<0 else 0)))
    return axis(TITLES[2],score,'60% directional premium balance; 40% excess activity versus 20 comparable sessions, signed by balance.',True,premium_balance=round(balance,3),relative_premium=round(ratio,3),sessions=20)


def attention_counts(rows,ticker,now):
    from .screening import stock_query
    query=stock_query(ticker)
    valid={r['start']:r for r in rows if r['query']==query and r['end']<=now and r['fetched_at']<=now and r['end']-r['start']==3600 and r['n']>=0}
    end=max((r['end'] for r in valid.values()),default=0)
    if not end or now-end>7200:return {'error':'No fresh completed hourly mention counts.'}
    def total(end):
        window=[valid.get(end-10800+i*3600) for i in range(3)]
        return sum(r['n'] for r in window) if all(window) else None
    current,previous=total(end),total(end-10800)
    if current is None or previous is None:return {'error':'Both three-hour count windows must be complete.'}
    local=datetime.fromtimestamp(end,NY);baseline=[]
    for i in range(1,29):
        prior=local-timedelta(days=i)
        if (prior.weekday()<5)!=(local.weekday()<5):continue
        n=total(prior.timestamp())
        if n is not None:baseline.append(n)
        if len(baseline)==20:break
    if len(baseline)<3:return {'error':'Need three prior same-time days with complete comparable counts.','baseline_days':len(baseline)}
    return dict(end=end,current=current,previous=previous,baseline=statistics.median(baseline),baseline_days=len(baseline))


def read_attention_counts(c,ticker,now):
    rows=[dict(r) for r in c.execute('SELECT start,end,n,query,fetched_at FROM x_counts WHERE ticker=? AND start>=? AND end<=? ORDER BY start',(ticker,now-29*86400,now))]
    return attention_counts(rows,ticker,now)


def x_axis(posts,ticker,now,counts=None):
    from .screening import fingerprint,stock_context
    from .post_quality import research_text
    counts=counts or {'error':'Mention count coverage is unavailable.'}
    if counts.get('error'):return axis(TITLES[3],reason=counts['error'],baseline_days=counts.get('baseline_days',0))
    end=counts['end'];authors={};seen=set();accepted=0;pending=0
    for p in sorted(posts,key=lambda p:p['ts'],reverse=True):
        if not end-10800<p['ts']<=end:continue
        author=str(p.get('author_id') or p.get('author') or '').strip().lower()
        if author in ('','x user','x author','author not loaded') or not stock_context(p['text'],ticker) or not research_text(p['text']):continue
        fp=fingerprint(p['text'])
        if not fp or fp in seen:continue
        seen.add(fp);accepted+=1
        label=next((v['label'] for v in p.get('ticker_sentiments',[]) if v['ticker']==ticker),None)
        if p.get('sentiment_status')!='done' or p.get('sentiment_analyzed_at',now)>now:label=None
        if label is None:pending+=1
        # Pending, neutral and unclear posts still contribute to activity breadth.
        authors.setdefault(author,label)
    labels={l:sum(v==l for v in authors.values()) for l in ('bullish','bearish','neutral','mixed','unclear')}
    directional=labels['bullish']+labels['bearish']
    sentiment='unavailable'
    if len(authors)>=10 and directional>=5:
        balance=(labels['bullish']-labels['bearish'])/directional
        sentiment='bullish' if balance>.2 else 'bearish' if balance<-.2 else 'mixed'
    current=counts['current']
    activity=clamp(50*current/max(5,counts['baseline']))
    acceleration=clamp(50*current/max(5,counts['previous']))
    breadth=clamp(100*(len(authors)/accepted)*min(1,len(authors)/10)) if accepted>=5 else None
    if current==0:breadth=0
    # Missing sample breadth isn't zero attention: label the count-only estimate.
    weight=.8 if breadth is None else 1
    score=clamp((.5*activity+.3*acceleration+(.2*breadth if breadth is not None else 0))/weight)
    return axis(TITLES[3],score,
        '50% unusual mention activity, 30% acceleration, 20% independent-author breadth. High attention has no bullish/bearish direction.'+(' Author coverage is limited: count-only estimate uses 62.5% / 37.5%; breadth is unavailable.' if breadth is None else ''),
        mentions_3h=current,previous_mentions_3h=counts['previous'],normal_mentions_3h=counts['baseline'],baseline_days=counts['baseline_days'],
        window_end=end,activity_score=activity,acceleration_score=acceleration,breadth_score=breadth,
        coverage='count-only estimate' if breadth is None else 'counts plus sampled breadth',component_coverage=80 if breadth is None else 100,
        sampled_posts=accepted,independent_authors=len(authors),pending_sentiment=pending,sentiment=sentiment,sentiment_labels=labels,
        sample_note='Mention counts cover the saved X query; author breadth is a filtered sample, not a census. Spam can remain in aggregate counts.')


def rating_bucket(rating):
    rating=re.sub(r'[^a-z]+',' ',str(rating or '').lower()).strip()
    if rating in ('buy','strong buy','outperform','overweight','positive','sector outperform'):return 'positive'
    if rating in ('sell','strong sell','underperform','underweight','negative','reduce','sector underperform'):return 'negative'
    if rating in ('hold','neutral','equal weight','market perform','sector perform','in line'):return 'neutral'
    return 'unknown'


def catalyst_axis(items,now):
    today=datetime.fromtimestamp(now,NY).date(); brokers={}
    for item in items:
        try:age=(today-datetime.fromisoformat(item['report_date']).date()).days
        except (KeyError,TypeError,ValueError):continue
        if not 0<=age<=7:continue
        event=item.get('_rating_event') or {}; target=item.get('_price_target') or {}
        direct=item.get('link_type','direct')=='direct'
        broker=str(event.get('broker') or target.get('broker') or item.get('firm') or '').strip().lower()
        # Unattributed notes cannot be treated as independent broker votes.
        key=broker or 'unattributed'
        order=(item['report_date'],item.get('received') or 0,str(item.get('id','')))
        if key in brokers and order<=brokers[key][0]:continue
        score={'bullish':65,'bearish':35}.get(item.get('stance'),50); basis='AI commentary'
        bucket=rating_bucket(event.get('rating')); action=event.get('action')
        scales={'upgrade':{'positive':95,'neutral':65,'negative':55,'unknown':85},
                'downgrade':{'positive':40,'neutral':25,'negative':5,'unknown':20},
                'initiation':{'positive':75,'neutral':50,'negative':25,'unknown':50},
                'reiteration':{'positive':60,'neutral':50,'negative':40,'unknown':50}}
        if direct and action in scales:
            score=scales[action][bucket];basis=f"{action} to {event.get('rating') or 'unspecified rating'}"
        elif direct and target.get('previous') and target.get('current'):
            delta=100*(target['current']/target['previous']-1)
            score=50+max(-30,min(30,delta));basis=f"Price target change {delta:+.1f}%"
        if not direct:score=50+(score-50)*.5;basis='Sector readthrough: '+basis
        score=clamp(50+(score-50)*(.8**age))
        brokers[key]=(order,score,item,basis,age)
    if not brokers:
        result=axis(TITLES[4],50,'No published research from the last seven days. 50 is the neutral starting point, not a broker assessment.',notes=0)
        result.update(state='no_research',direction='neutral');return result
    votes=list(brokers.values());score=clamp(statistics.mean(v[1] for v in votes))
    _,_,latest,_,_=max(votes,key=lambda v:v[0])
    result=axis(TITLES[4],score,'Latest view per broker, equally weighted. Rating actions take priority over explicit price-target changes, then AI commentary. Each day reduces the distance from neutral by 20%; notes older than seven days are excluded.',
        summary=latest['summary'],firm=latest.get('firm'),report_date=latest['report_date'],stance=latest.get('stance'),
        notes=len(votes),mixed_views=any(v[1]>50 for v in votes) and any(v[1]<50 for v in votes),
        assessments=[dict(broker=v[2].get('_rating_event',{}).get('broker') or v[2].get('firm') or 'Unattributed',date=v[2]['report_date'],score=v[1],basis=v[3]) for v in votes])
    result['direction']='bullish' if score>50 else 'bearish' if score<50 else 'neutral'
    return result


def candidate(axes):
    p,v,o,x,_=axes
    if p['score'] is None or v['score'] is None:return 'insufficient_data'
    if v['score']<60 or p['strength']<30:return 'watch'
    options_confirm=o['score'] is not None and o['strength']>=30 and o['direction']==p['direction']
    attention_confirm=x['score'] is not None and x['score']>=65
    return p['direction'] if options_confirm or attention_confirm else 'watch'


def read_posts(c,ticker,now):
    from .context_sentiment import annotate
    # Join all mentions for the existing sentiment cache key, after selecting this ticker.
    rows=[dict(r) for r in c.execute('''SELECT p.*,i.author_id,GROUP_CONCAT(DISTINCT m.ticker) tickers
      FROM posts p JOIN mentions m ON m.source=p.source AND m.post_id=p.id
      LEFT JOIN post_identity i ON i.source=p.source AND i.post_id=p.id
      WHERE p.source='x' AND p.ts>? AND p.ts<=? AND EXISTS
      (SELECT 1 FROM mentions wanted WHERE wanted.source=p.source AND wanted.post_id=p.id AND wanted.ticker=?)
      GROUP BY p.source,p.id,i.author_id ORDER BY p.ts DESC LIMIT 1200''',(now-21600,now,ticker))]
    annotate(c,rows,ticker)
    return rows


def aligned_price_inputs(stock, measurements, catalog, now):
    """Compare actual candles at one recent common endpoint, never mismatched returns."""
    from .uw_pilot import stock_measurements
    for end in sorted({bar['at'] for bar in stock['candles'] if 0<=now-bar['at']<=1200},reverse=True):
        aligned=[stock_measurements(m['ticker'],{'candles':[bar for bar in m['candles'] if bar['at']<=end]},now) for m in measurements]
        target=next(m for m in aligned if m['ticker']==stock['ticker'])
        peers=[m for m in aligned if m['ticker']!=stock['ticker'] and m['price_at']==end and m['price_fresh'] and m['return_60m'] is not None]
        sector=[m for m in peers if catalog[m['ticker']][1]==catalog[stock['ticker']][1]]
        if target['return_60m'] is not None and len(peers)>=10 and len(sector)>=5:return target,aligned
    return stock,measurements


def build(c,samples,catalog,focus,now):
    from .uw_pilot import stock_measurements
    from .research_feed import published
    measurements=[stock_measurements(t,d,now) for t,d in samples.items() if t in catalog]
    output=[]
    for stock in measurements:
        t=stock['ticker']
        if t not in focus:continue
        # Read comparable time slots, not every saved payload for the entire pilot.
        # Include +/- one hour for daylight-saving boundaries; options_axis checks NY time.
        slots=sorted({(int(now//600)+n)%144 for n in (-7,-6,-5,-1,0,1,5,6,7)})
        history=[dict(r) for r in c.execute('SELECT * FROM signal_lab_snapshots WHERE ticker=? AND observed>? AND observed<=? AND ((slot - CAST(slot / 144 AS INTEGER) * 144) IN ('+','.join('?' for _ in slots)+') OR observed>?) ORDER BY observed',(t,now-45*86400,now,*slots,now-1200))]
        price_stock,price_peers=aligned_price_inputs(stock,measurements,catalog,now)
        price=price_axis(price_stock,price_peers,catalog,samples[t].get('history',[]))
        price['details']['as_of']=price_stock['price_at']
        axes=[price,volume_axis(stock),options_axis(stock,history,now),x_axis(read_posts(c,t,now),t,now,read_attention_counts(c,t,now)),catalyst_axis(published(c,t),now)]
        state=candidate(axes)
        prev=next((r for r in reversed(history) if r['version']==VERSION and r['slot']<int(now//600)),None)
        persistent=bool(prev and 0<now-prev['observed']<=900 and json.loads(prev['payload']).get('candidate')==state and state in ('bullish','bearish'))
        baseline=axes[0]['direction'] if axes[0]['score'] is not None and axes[0]['strength']>=30 and axes[1]['score'] is not None and axes[1]['score']>=60 else 'watch'
        output.append(dict(ticker=t,axes=axes,version=VERSION,observed=now,candidate=state,price_volume_baseline=baseline,setup=state+' setup' if persistent else 'Awaiting a second check' if state in ('bullish','bearish') else 'Insufficient data' if state=='insufficient_data' else 'Watching',
                           options_observation=stock.get('filtered_options'),price_at=stock['price_at'],price=stock['candles'][-1]['close'] if stock['candles'] else None,
                           ready=sum(a['state']=='ready' for a in axes)))
    return output


def record(c,samples,catalog,focus,now):
    migrate(c)
    panels=build(c,samples,catalog,focus,now)
    for p in panels:
        c.execute('INSERT OR IGNORE INTO signal_lab_snapshots(ticker,slot,version,observed,price_at,price,payload) VALUES(?,?,?,?,?,?,?)',
                  (p['ticker'],int(now//600),VERSION,now,p['price_at'],p['price'],json.dumps(p)))
    # First known close at least an hour after observation, same session only.
    for row in c.execute('SELECT ticker,slot,version,observed,price_at,price FROM signal_lab_snapshots WHERE outcome IS NULL AND observed<=? AND observed>?',(now-3600,now-7*86400)).fetchall():
        invalid=not row['price'] or not row['price_at'] or row['observed']-row['price_at']>1200
        if invalid or datetime.fromtimestamp(row['observed'],NY).date()<datetime.fromtimestamp(now,NY).date():
            c.execute('UPDATE signal_lab_snapshots SET outcome=? WHERE ticker=? AND slot=? AND version=? AND outcome IS NULL',(json.dumps({'state':'unavailable','reason':'Stale entry' if invalid else 'No complete same-session outcome captured'}),row['ticker'],row['slot'],row['version']))
            continue
        bars=samples.get(row['ticker'],{}).get('candles',[])
        window=[r for r in bars if row['observed']<r['at']<=row['observed']+4200 and datetime.fromtimestamp(r['at'],NY).date()==datetime.fromtimestamp(row['observed'],NY).date()]
        target=next((r for r in sorted(window,key=lambda r:r['at']) if r['at']>=row['observed']+3600),None)
        if not target:continue
        window=[r for r in window if r['at']<=target['at']]
        if len(window)<6 or any(b['at']-a['at']!=600 for a,b in zip(sorted(window,key=lambda r:r['at']),sorted(window,key=lambda r:r['at'])[1:])):continue
        ret=(target['close']/row['price']-1)*100
        result=dict(return_1h=round(ret,3),cost_adjusted_long=round(ret-.1,3),cost_adjusted_short=round(-ret-.1,3),assumed_round_trip_bps=10,
                    low_excursion=round((min(r.get('low',r['close']) for r in window)/row['price']-1)*100,3),high_excursion=round((max(r.get('high',r['close']) for r in window)/row['price']-1)*100,3),end_at=target['at'],measured_at=now)
        c.execute('UPDATE signal_lab_snapshots SET outcome=? WHERE ticker=? AND slot=? AND version=? AND outcome IS NULL',(json.dumps(result),row['ticker'],row['slot'],row['version']))
    c.execute('DELETE FROM signal_lab_snapshots WHERE observed<?',(now-90*86400,))
    return panels


def saved(c):
    migrate(c)
    rows=[dict(r) for r in c.execute('SELECT ticker,observed,payload,outcome FROM signal_lab_snapshots WHERE version=? ORDER BY observed DESC LIMIT 30',(VERSION,))]
    newest=[dict(r) for r in c.execute('SELECT ticker,payload FROM (SELECT ticker,payload,ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY observed DESC) AS position FROM signal_lab_snapshots WHERE version=?) ranked WHERE position=1',(VERSION,))]
    latest={}
    for r in newest:latest[r['ticker']]=json.loads(r['payload'])
    return dict(version=VERSION,stocks=list(latest.values()),history=[dict(ticker=r['ticker'],observed=r['observed'],setup=json.loads(r['payload'])['setup'],baseline=json.loads(r['payload']).get('price_volume_baseline','watch'),outcome=json.loads(r['outcome']) if r['outcome'] else None) for r in rows[:30]])
