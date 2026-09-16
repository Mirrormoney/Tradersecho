import math

def enrich(c,rows,now,window):
    """Keep post samples distinct from full-query volume; report missing hour coverage."""
    start=now-window*86400;previous=start-window*86400
    totals=c.execute('SELECT ticker,SUM(n) n,COUNT(*) hours FROM x_counts WHERE start>=? AND end<=? GROUP BY ticker',(start,now)).fetchall()
    if not totals: return rows
    old={r['ticker']:r for r in c.execute('SELECT ticker,SUM(n) n,COUNT(*) hours FROM x_counts WHERE start>=? AND end<=? GROUP BY ticker',(previous,start))}
    existing={r['ticker']:r for r in rows}
    from .service import CATALOG
    output=[]
    all_buckets={}
    for b in c.execute('SELECT ticker,MIN(13,CAST((start-?)/? AS INTEGER)) bucket,SUM(n) n FROM x_counts WHERE start>=? AND end<=? GROUP BY ticker,bucket',(start,window*86400/14,start,now)):
        all_buckets.setdefault(b['ticker'],[0]*14)[min(13,b['bucket'])]=b['n']
    for r in totals:
        ticker=r['ticker'];sample=existing.get(ticker,{})
        counts=all_buckets.get(ticker,[0]*14)
        earlier=old.get(ticker);complete=r['hours']==window*24 and earlier and earlier['hours']==window*24
        prev=earlier['n'] if earlier else 0;growth=round((r['n']/prev-1)*100,1) if complete and prev else None
        heat=round(10*math.log1p(r['n'])*(1+max(0,math.log2((r['n']+5)/(prev+5))) if complete else 1),1)
        output.append({**sample,'ticker':ticker,'name':CATALOG.get(ticker,(ticker,'Other'))[0],'sector':CATALOG.get(ticker,(ticker,'Other'))[1],'mentions':r['n'],'sample_mentions':sample.get('mentions',0),'authors':sample.get('authors',0),'bullish':sample.get('bullish',0),'bearish':sample.get('bearish',0),'neutral':sample.get('neutral',0),'sentiment':sample.get('sentiment',0),'previous':prev,'change':growth,'heat':heat,'spark':counts,'volume_source':'X counts','coverage_hours':r['hours'],'comparison_complete':bool(complete)})
    return output
