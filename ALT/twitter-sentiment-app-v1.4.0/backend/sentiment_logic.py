from datetime import datetime,timedelta
from typing import List,Optional
from sqlalchemy import select,func
from db import SessionLocal,DailyRollup,Baseline,MentionMinute

def get_free_daily(tickers:Optional[List[str]]=None,date_from:Optional[str]=None,date_to:Optional[str]=None,limit:int=50,page:int=1,sort:str='interest_score'):
    with SessionLocal() as db:
        q=select(DailyRollup)
        if date_from: from datetime import datetime as _dt; q=q.where(DailyRollup.d>=_dt.fromisoformat(date_from))
        if date_to: from datetime import datetime as _dt; q=q.where(DailyRollup.d<=_dt.fromisoformat(date_to))
        if tickers: q=q.where(DailyRollup.ticker.in_(tickers))
        rows=db.execute(q).scalars().all()
        data=[dict(date=r.d.date().isoformat(),ticker=r.ticker,mentions=r.mentions,interest_score=round(r.interest_score,3),zscore=round(r.zscore,3),pos=r.pos,neg=r.neg,neu=r.neu) for r in rows]
        key=(lambda x:x.get(sort,0)) if sort in ('interest_score','mentions','zscore') else (lambda x:x['interest_score'])
        data.sort(key=key,reverse=True); s=max(0,(page-1)*limit); e=s+limit; return data[s:e]

def get_live_snapshot(limit:int=50):
    with SessionLocal() as db:
        since=datetime.utcnow()-timedelta(minutes=5)
        rows=db.execute(select(MentionMinute.ticker,func.sum(MentionMinute.mentions),func.sum(MentionMinute.pos),func.sum(MentionMinute.neg),func.sum(MentionMinute.neu)).where(MentionMinute.ts>=since).group_by(MentionMinute.ticker)).all()
        bl={b.ticker:(b.mean_mentions,max(1.0,b.std_mentions)) for b in db.execute(select(Baseline)).scalars().all()}
        data=[]
        for t,m,p,n,nn in rows:
            mean,std=bl.get(t,(1000.0,250.0)); daily=(m or 0)*288; interest=daily/max(1.0,mean); change=interest-1.0; tot=max(1,(p or 0)+(n or 0)+(nn or 0)); sent=((p or 0)-(n or 0))/tot
            data.append(dict(ticker=t,interest_score=round(interest,3),sentiment=round(sent,3),mentions=int(m or 0),change_vs_avg=round(change,3)))
        data.sort(key=lambda x:x['interest_score'],reverse=True); return data[:limit]
