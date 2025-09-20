from typing import List,Dict,Any,Optional
from datetime import datetime,timedelta
from sqlalchemy import select,func
from db import SessionLocal,DailyRollup,Baseline,MentionMinute

def get_free_daily(tickers:Optional[List[str]]=None,date_from:Optional[str]=None,date_to:Optional[str]=None,limit:int=50,page:int=1,sort:str='interest_score'):
    with SessionLocal() as db:
        q=select(DailyRollup)
        if date_from: q=q.where(DailyRollup.d>=datetime.fromisoformat(date_from))
        if date_to: q=q.where(DailyRollup.d<=datetime.fromisoformat(date_to))
        if tickers: q=q.where(DailyRollup.ticker.in_(tickers))
        rows=db.execute(q).scalars().all()
        data=[]
        for r in rows:
            data.append({'date':r.d.date().isoformat(),'ticker':r.ticker,'mentions':r.mentions,'interest_score':round(r.interest_score,3),'zscore':round(r.zscore,3),'pos':r.pos,'neg':r.neg,'neu':r.neu})
        key=(lambda x:x.get(sort,0)) if sort in ('interest_score','mentions','zscore') else (lambda x:x['interest_score'])
        data.sort(key=key, reverse=True)
        start=max(0,(page-1)*limit); end=start+limit
        return data[start:end]

def get_live_snapshot(limit:int=50):
    with SessionLocal() as db:
        since=datetime.utcnow()-timedelta(minutes=5)
        q=select(MentionMinute.ticker, func.sum(MentionMinute.mentions), func.sum(MentionMinute.pos), func.sum(MentionMinute.neg), func.sum(MentionMinute.neu)).where(MentionMinute.ts>=since).group_by(MentionMinute.ticker)
        rows=db.execute(q).all()
        bl={b.ticker:(b.mean_mentions,max(1.0,b.std_mentions)) for b in db.execute(select(Baseline)).scalars().all()}
        data=[]
        for t,m,p,n,nn in rows:
            mean,std=bl.get(t,(1000.0,250.0))
            daily_equiv=(m or 0)*288
            interest=daily_equiv/max(1.0,mean)
            change_vs_avg=interest-1.0
            tot=max(1,(p or 0)+(n or 0)+(nn or 0))
            sentiment=((p or 0)-(n or 0))/tot
            data.append({'ticker':t,'interest_score':round(interest,3),'sentiment':round(sentiment,3),'mentions':int(m or 0),'change_vs_avg':round(change_vs_avg,3)})
        data.sort(key=lambda x:x['interest_score'], reverse=True)
        return data[:limit]
