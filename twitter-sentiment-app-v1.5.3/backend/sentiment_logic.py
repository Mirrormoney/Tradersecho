
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import select, desc, asc, and_
from db import SessionLocal, DailyRollup

def _default_date_range(date_from: Optional[str], date_to: Optional[str]):
    if date_from and date_to:
        start = datetime.fromisoformat(date_from)
        end = datetime.fromisoformat(date_to)
    else:
        # default to yesterday UTC (00:00 to 23:59:59)
        today = datetime.utcnow().date()
        start = datetime.combine(today - timedelta(days=1), datetime.min.time())
        end = datetime.combine(today - timedelta(days=1), datetime.max.time())
    return start, end

def get_free_daily(tickers: Optional[List[str]]=None,
                   date_from: Optional[str]=None,
                   date_to: Optional[str]=None,
                   limit: int=50,
                   page: int=1,
                   sort: str="interest"):
    start, end = _default_date_range(date_from, date_to)
    # map sort fields; keep backward compat: 'interest_score' -> 'interest'
    sort_map = {
        "interest": DailyRollup.interest,
        "interest_score": DailyRollup.interest,
        "mentions": DailyRollup.mentions,
        "pos": DailyRollup.pos,
        "neg": DailyRollup.neg,
        "neu": DailyRollup.neu,
        "zscore": DailyRollup.zscore,
        "ticker": DailyRollup.ticker,
        "day": DailyRollup.day,
    }
    sort_col = sort_map.get((sort or "").lower(), DailyRollup.interest)

    stmt = select(DailyRollup).where(and_(DailyRollup.day >= start, DailyRollup.day <= end))
    if tickers:
        up = [t.upper() for t in tickers]
        stmt = stmt.where(DailyRollup.ticker.in_(up))

    # default sort desc for numeric metrics, asc for ticker/day
    if sort_col in (DailyRollup.ticker, DailyRollup.day):
        stmt = stmt.order_by(asc(sort_col))
    else:
        stmt = stmt.order_by(desc(sort_col))

    # pagination
    offset = max(0, (page-1) * max(1, limit))
    stmt = stmt.offset(offset).limit(max(1, min(200, limit)))

    out = []
    with SessionLocal() as db:
        rows = db.execute(stmt).scalars().all()
        for r in rows:
            interest_val = float(r.interest or 0.0)
            out.append({
                "ticker": r.ticker,
                "date": r.day.date().isoformat(),
                "mentions": r.mentions,
                "pos": r.pos,
                "neg": r.neg,
                "neu": r.neu,
                # Back-compat: include BOTH fields
                "interest": interest_val,
                "interest_score": interest_val,
                "zscore": float(r.zscore or 0.0),
            })
    return out

def get_live_snapshot(limit: int=50):
    start, end = _default_date_range(None, None)
    stmt = select(DailyRollup).where(and_(DailyRollup.day >= start, DailyRollup.day <= end)).order_by(desc(DailyRollup.interest)).limit(limit)
    out = []
    with SessionLocal() as db:
        rows = db.execute(stmt).scalars().all()
        for r in rows:
            interest_val = float(r.interest or 0.0)
            out.append({
                "ticker": r.ticker,
                "date": r.day.date().isoformat(),
                "mentions": r.mentions,
                "pos": r.pos,
                "neg": r.neg,
                "neu": r.neu,
                "interest": interest_val,
                "interest_score": interest_val,
                "zscore": float(r.zscore or 0.0),
            })
    return out
