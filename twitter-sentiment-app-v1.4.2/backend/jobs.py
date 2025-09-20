"""Maintenance jobs: baselines recompute & day rollup.
Usage:
  .venv\Scripts\activate
  python jobs.py baselines --window 30
  python jobs.py rollup --date 2025-09-18
"""
import argparse
from datetime import datetime, timedelta
from sqlalchemy import select, func, delete
from db import SessionLocal, MentionMinute, DailyRollup, Baseline

def recompute_baselines(window: int):
    with SessionLocal() as db:
        tickers = [t[0] for t in db.execute(select(MentionMinute.ticker).distinct()).all()]
        for t in tickers:
            since = datetime.utcnow() - timedelta(days=window)
            total = db.execute(select(func.sum(MentionMinute.mentions)).where(MentionMinute.ticker==t, MentionMinute.ts>=since)).scalar() or 0
            mean = total / max(1, window)
            std = max(1.0, mean ** 0.5)
            b = db.execute(select(Baseline).where(Baseline.ticker==t)).scalar_one_or_none()
            if b: b.mean_mentions=mean; b.std_mentions=std
            else: db.add(Baseline(ticker=t, window_days=window, mean_mentions=mean, std_mentions=std))
        db.commit()
    print(f"Updated baselines for {len(tickers)} tickers over {window} days.")

def rollup_day(iso: str):
    day = datetime.fromisoformat(iso).date()
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(days=1)
    with SessionLocal() as db:
        db.execute(delete(DailyRollup).where(DailyRollup.d==start))
        rows = db.execute(
            select(MentionMinute.ticker, func.sum(MentionMinute.mentions), func.sum(MentionMinute.pos), func.sum(MentionMinute.neg), func.sum(MentionMinute.neu))
            .where(MentionMinute.ts>=start, MentionMinute.ts<end)
            .group_by(MentionMinute.ticker)
        ).all()
        bl = {b.ticker:(b.mean_mentions, max(1.0,b.std_mentions)) for b in db.execute(select(Baseline)).scalars().all()}
        for t, m, p, n, nn in rows:
            mean,std = bl.get(t, (max(1.0,m or 1.0), max(1.0, (m or 1.0)**0.5)))
            interest = (m or 0) / mean
            z = ((m or 0) - mean) / std
            db.add(DailyRollup(d=start, ticker=t, mentions=int(m or 0), pos=int(p or 0), neg=int(n or 0), neu=int(nn or 0), interest_score=interest, zscore=z))
        db.commit()
    print(f"Rolled up {iso}.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd")
    b = sp.add_parser("baselines"); b.add_argument("--window", type=int, default=30)
    r = sp.add_parser("rollup"); r.add_argument("--date", type=str, required=True)
    args = ap.parse_args()
    if args.cmd == "baselines": recompute_baselines(args.window)
    elif args.cmd == "rollup": rollup_day(args.date)
    else: ap.print_help()
