from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, func
from db import SessionLocal, DailyRollup, Baseline, MentionMinute
def get_free_daily(tickers: Optional[List[str]] = None, limit: int = 50, sort: str = "interest_score"):
    with SessionLocal() as db:
        day = (datetime.utcnow().date() - timedelta(days=1))
        q = select(DailyRollup).where(DailyRollup.d == datetime.combine(day, datetime.min.time()))
        if tickers: q = q.where(DailyRollup.ticker.in_(tickers))
        rows = db.execute(q).scalars().all()
        data = []
        for r in rows:
            data.append(dict(
                date=day.isoformat(), ticker=r.ticker, mentions=r.mentions,
                interest_score=round(r.interest_score,3), zscore=round(r.zscore,3),
                pos=r.pos, neg=r.neg, neu=r.neu
            ))
        key = (lambda x: x.get(sort,0)) if sort in ("interest_score","mentions","zscore") else (lambda x: x["interest_score"])
        data.sort(key=key, reverse=True)
        return data[:limit]
def get_live_snapshot(limit: int = 50):
    with SessionLocal() as db:
        since = datetime.utcnow() - timedelta(minutes=5)
        q = select(MentionMinute.ticker, func.sum(MentionMinute.mentions), func.sum(MentionMinute.pos), func.sum(MentionMinute.neg), func.sum(MentionMinute.neu))\
            .where(MentionMinute.ts >= since).group_by(MentionMinute.ticker)
        rows = db.execute(q).all()
        bl = {b.ticker:(b.mean_mentions, max(1.0,b.std_mentions)) for b in db.execute(select(Baseline)).scalars().all()}
        data = []
        for t, m, p, n, nn in rows:
            mean,std = bl.get(t, (1000.0, 250.0))
            daily_equiv = m * 288  # scale 5-min to per-day
            interest = daily_equiv / mean
            change_vs_avg = interest - 1.0
            tot = max(1, p+n+nn)
            sentiment = (p - n) / tot
            data.append(dict(ticker=t, interest_score=round(interest,3), sentiment=round(sentiment,3), mentions=int(m), change_vs_avg=round(change_vs_avg,3)))
        data.sort(key=lambda x: x["interest_score"], reverse=True)
        return data[:limit]
