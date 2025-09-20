
"""
Collector with adapters (v1.5.0)
Usage:
  python collector.py backfill --days 14
  python collector.py live --adapters stocktwits,reddit --tickers AAPL,MSFT,TSLA
"""
import argparse, random, time
from datetime import datetime, timedelta
from sqlalchemy import select
from db import SessionLocal, MentionMinute
from config import ADAPTERS, ADAPTER_TICKERS, STOCKTWITS_RATE_PER_MIN, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
from adapters.stocktwits import StockTwitsAdapter
from adapters.reddit import RedditAdapter

def _insert_minute(db, t: str, ts: datetime, pos: int, neg: int, neu: int, source: str, external_id: str|None):
    # dedup at DB level via unique constraint; here we best-effort guard
    exists = False
    if external_id:
        exists = db.execute(select(MentionMinute.id).where(MentionMinute.source==source, MentionMinute.external_id==external_id)).scalar_one_or_none()
    if exists: 
        return
    mentions = max(0, pos+neg+neu)
    db.add(MentionMinute(ticker=t, ts=ts.replace(second=0, microsecond=0), mentions=mentions, pos=pos, neg=neg, neu=neu, source=source, external_id=external_id))

def backfill(days: int=14):
    """Synthetic backfill identical to previous behavior (twitter source)."""
    TICKERS = {"AAPL": 20000, "MSFT": 18000, "TSLA": 45000, "NVDA": 35000, "AMZN": 22000}
    with SessionLocal() as db:
        end = datetime.utcnow().replace(second=0, microsecond=0)
        start = end - timedelta(days=days)
        cur = start
        while cur <= end:
            for t, daily in TICKERS.items():
                # simple Poisson-ish per-minute
                base = max(1, int(daily/1440))
                val = max(0, int(random.gauss(base, max(1, base*0.2))))
                p = max(0, int(val*0.35))
                n = max(0, int(val*0.25))
                nn = max(0, val - p - n)
                _insert_minute(db, t, cur, p, n, nn, "twitter", None)
            db.commit()
            cur += timedelta(minutes=1)

def live(adapters_arg: str|None=None, tickers_arg: str|None=None):
    adapters_list = [a.strip() for a in (adapters_arg or ",".join(ADAPTERS)).split(",") if a.strip()]
    tickers = [t.strip().upper() for t in (tickers_arg or ",".join(ADAPTER_TICKERS)).split(",") if t.strip()]
    adapters = []
    if "stocktwits" in adapters_list:
        adapters.append(StockTwitsAdapter(rate_per_min=STOCKTWITS_RATE_PER_MIN))
    if "reddit" in adapters_list:
        adapters.append(RedditAdapter(client_id=REDDIT_CLIENT_ID, client_secret=REDDIT_CLIENT_SECRET, user_agent=REDDIT_USER_AGENT))

    last = datetime.utcnow() - timedelta(minutes=10)
    with SessionLocal() as db:
        while True:
            for a in adapters:
                items = a.fetch_since(last, tickers)
                for it in items:
                    # simple sentiment conversion
                    pos = 1 if it.sentiment=="pos" else 0
                    neg = 1 if it.sentiment=="neg" else 0
                    neu = 1 if it.sentiment=="neu" else 0
                    _insert_minute(db, it.ticker, it.ts, pos, neg, neu, a.source_name, it.external_id)
            db.commit()
            last = datetime.utcnow()
            time.sleep(30)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd")
    bf = sp.add_parser("backfill"); bf.add_argument("--days", type=int, default=14)
    lv = sp.add_parser("live"); lv.add_argument("--adapters", type=str, default=None); lv.add_argument("--tickers", type=str, default=None)
    args = ap.parse_args()
    if args.cmd == "backfill": backfill(args.days)
    elif args.cmd == "live": live(args.adapters, args.tickers)
    else: ap.print_help()
