
"""Jobs helpers (package-safe)"""
import argparse, os, sys
from datetime import datetime, timedelta
from sqlalchemy import select, func, delete

# Ensure package import
ROOT = os.path.dirname(__file__)
PARENT = os.path.dirname(ROOT)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

try:
    from .db import SessionLocal, MentionMinute, DailyRollup, Baseline  # type: ignore
except Exception:
    from backend.db import SessionLocal, MentionMinute, DailyRollup, Baseline  # type: ignore

def recompute_baselines(window: int):
    with SessionLocal() as db:
        tickers = [t[0] for t in db.execute(select(MentionMinute.ticker).distinct()).all()]
        for t in tickers:
            # placeholder: a simple mean/std over last `window` days
            total = db.execute(select(func.sum(MentionMinute.mentions)).where(MentionMinute.ticker==t)).scalar() or 0
            mean = float(total) / max(1, window)
            std = max(1.0, mean * 0.2)
            base = db.execute(select(Baseline).where(Baseline.ticker==t)).scalar_one_or_none()
            if base:
                base.mean, base.std = mean, std
            else:
                db.add(Baseline(ticker=t, mean=mean, std=std))
        db.commit()

def recompute_rollup(day_str: str):
    day = datetime.fromisoformat(day_str)
    start = datetime(day.year, day.month, day.day)
    end = start + timedelta(days=1)
    with SessionLocal() as db:
        db.execute(delete(DailyRollup).where(DailyRollup.day==start))
        rows = db.execute(select(MentionMinute.ticker, func.sum(MentionMinute.mentions), func.sum(MentionMinute.pos), func.sum(MentionMinute.neg), func.sum(MentionMinute.neu)).where(MentionMinute.ts>=start, MentionMinute.ts<end).group_by(MentionMinute.ticker)).all()
        for t, m, p, n, u in rows:
            db.add(DailyRollup(ticker=t, day=start, mentions=int(m or 0), pos=int(p or 0), neg=int(n or 0), neu=int(u or 0), interest=float(m or 0), zscore=0.0))
        db.commit()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd")
    b = sp.add_parser("baselines"); b.add_argument("--window", type=int, default=30)
    r = sp.add_parser("rollup"); r.add_argument("--date", type=str, required=True)
    args = ap.parse_args()
    if args.cmd == "baselines": recompute_baselines(args.window)
    elif args.cmd == "rollup": recompute_rollup(args.date)
    else: ap.print_help()
