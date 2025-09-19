"""Collector scaffold: backfill and live simulate per-minute mentions.
Usage:
  .venv\Scripts\activate
  python collector.py backfill --days 14
  python collector.py live
"""
import argparse, random, time
from datetime import datetime, timedelta
from sqlalchemy import select, delete
from db import SessionLocal, MentionMinute, DailyRollup, Baseline
TICKERS = {
    "AAPL": 20000, "MSFT": 18000, "TSLA": 45000, "NVDA": 35000, "AMZN": 22000,
    "META": 20000, "GOOGL": 19000, "NFLX": 12000, "AMD": 11000, "INTC": 10000
}
def minute_weight(minute):
    # simple day profile (UTC): more in market hours (13:30-20:00 UTC roughly US equities)
    hour = (minute // 60) % 24
    return 1.6 if 13 <= hour <= 20 else 0.7
def backfill(days: int):
    with SessionLocal() as db:
        cutoff = (datetime.utcnow().date() - timedelta(days=days))
        db.execute(delete(MentionMinute).where(MentionMinute.ts >= datetime.combine(cutoff, datetime.min.time())))
        db.execute(delete(DailyRollup).where(DailyRollup.d >= datetime.combine(cutoff, datetime.min.time())))
        db.commit()
        for t, base in TICKERS.items():
            for d in range(days, 0, -1):
                day = datetime.utcnow().date() - timedelta(days=d)
                total=pos=neg=neu=0
                for m in range(24*60):
                    w = minute_weight(m) * (0.8 + random.random()*0.5)
                    val = int(base * w / (24*60))
                    ts = datetime.combine(day, datetime.min.time()) + timedelta(minutes=m)
                    p = int(val * (0.45 + random.random()*0.2))
                    n = int(val * (0.2 + random.random()*0.2))
                    nn = max(0, val - p - n)
                    db.add(MentionMinute(ticker=t, ts=ts, mentions=val, pos=p, neg=n, neu=nn))
                    total += val; pos += p; neg += n; neu += nn
                mean = base; std = max(1.0, base*0.25)
                interest = total / mean
                z = (total - mean) / std
                db.add(DailyRollup(d=datetime.combine(day, datetime.min.time()), ticker=t, mentions=total, pos=pos, neg=neg, neu=neu, interest_score=interest, zscore=z))
            # baselines
            mean = base; std = max(1.0, base*0.25)
            b = db.execute(select(Baseline).where(Baseline.ticker==t)).scalar_one_or_none()
            if b: b.mean_mentions=mean; b.std_mentions=std
            else: db.add(Baseline(ticker=t, window_days=30, mean_mentions=mean, std_mentions=std))
        db.commit()
    print(f"Backfilled {days} days for {len(TICKERS)} tickers.")
def live():
    with SessionLocal() as db:
        while True:
            now = datetime.utcnow().replace(second=0, microsecond=0)
            for t, base in TICKERS.items():
                exp = base / (24*60)
                val = max(0, int(random.gauss(exp, max(1.0, exp*0.4))))
                p = int(val * (0.45 + random.random()*0.2))
                n = int(val * (0.2 + random.random()*0.2))
                nn = max(0, val - p - n)
                db.add(MentionMinute(ticker=t, ts=now, mentions=val, pos=p, neg=n, neu=nn))
            db.commit()
            time.sleep(60)
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd")
    bf = sp.add_parser("backfill"); bf.add_argument("--days", type=int, default=14)
    lv = sp.add_parser("live")
    args = ap.parse_args()
    if args.cmd == "backfill": backfill(args.days)
    elif args.cmd == "live": live()
    else: ap.print_help()
