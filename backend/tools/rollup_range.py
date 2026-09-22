#!/usr/bin/env python
"""
Tradersecho — v2.0 Step 1: rollup-range job (robust upsert)

- Detects unique index/constraint for (day,ticker[,source]).
- Uses Postgres ON CONFLICT only if matching unique index/constraint exists.
- Otherwise falls back to delete+insert.
- Matches 'day' column type (DATE vs TIMESTAMP).

Usage:
  python backend/tools/rollup_range.py --days 7 --verbose
  python backend/tools/rollup_range.py --from 2025-09-01 --to 2025-09-21 --verbose
  python backend/tools/rollup_range.py --date 2025-09-20 --source stocktwits --verbose
"""
import argparse
import datetime as dt
import os
import sys
from typing import Iterable, Optional, List
from sqlalchemy import create_engine, MetaData, Table, select, func, and_, insert as sa_insert
from sqlalchemy.engine import Engine
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.sql.sqltypes import DateTime
try:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
except Exception:
    pg_insert = None

def parse_args():
    p = argparse.ArgumentParser(description="Aggregate daily rollups across a date range.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--days", type=int, help="Recompute last N days (including today).")
    g.add_argument("--date", type=str, help="Recompute a single YYYY-MM-DD date.")
    g.add_argument("--from", dest="date_from", type=str, help="Start date YYYY-MM-DD (inclusive).")
    p.add_argument("--to", dest="date_to", type=str, help="End date YYYY-MM-DD (inclusive). Required with --from.")
    p.add_argument("--source", type=str, default=None, help="Optional source filter (e.g., stocktwits/reddit).")
    p.add_argument("--verbose", action="store_true", help="Verbose logging.")
    return p.parse_args()

def daterange(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    cur = start
    while cur <= end:
        yield cur
        cur += dt.timedelta(days=1)

def get_engine() -> Engine:
    db_url = os.environ.get("DB_URL")
    if not db_url:
        print("ERROR: DB_URL not set in environment.", file=sys.stderr)
        sys.exit(1)
    return create_engine(db_url, future=True)

def reflect_tables(engine: Engine):
    meta = MetaData()
    mention_minutes = Table("mention_minutes", meta, autoload_with=engine)
    daily_rollups = Table("daily_rollups", meta, autoload_with=engine)
    baselines = Table("baselines", meta, autoload_with=engine)
    return mention_minutes, daily_rollups, baselines

def _find_ts_col(mention_minutes: Table):
    if "ts" in mention_minutes.c:
        return mention_minutes.c.ts
    if "timestamp" in mention_minutes.c:
        return mention_minutes.c.timestamp
    raise RuntimeError("mention_minutes needs 'ts' or 'timestamp'.")

def _has_unique(engine: Engine, table: Table, cols: List[str]) -> bool:
    insp = sa_inspect(engine)
    try:
        for uc in insp.get_unique_constraints(table.name, schema=getattr(table, "schema", None)):
            if uc.get("column_names") == cols:
                return True
    except Exception:
        pass
    try:
        for idx in insp.get_indexes(table.name, schema=getattr(table, "schema", None)):
            if idx.get("unique") and idx.get("column_names") == cols:
                return True
    except Exception:
        pass
    return False

def compute_day(engine: Engine, mention_minutes: Table, daily_rollups: Table, baselines: Table, day: dt.date, source_filter: Optional[str], verbose: bool = False):
    with engine.begin() as conn:
        day_start = dt.datetime.combine(day, dt.time.min)
        day_end = dt.datetime.combine(day, dt.time.max)
        ts_col = _find_ts_col(mention_minutes)
        conditions = [ts_col >= day_start, ts_col <= day_end]
        if source_filter and "source" in mention_minutes.c:
            conditions.append(mention_minutes.c.source == source_filter)
        if "ticker" not in mention_minutes.c:
            raise RuntimeError("mention_minutes missing 'ticker'.")
        ticker_col = mention_minutes.c.ticker
        sent_col = mention_minutes.c.sentiment if "sentiment" in mention_minutes.c else None
        if "mentions" in mention_minutes.c:
            agg_mentions = func.coalesce(func.sum(mention_minutes.c.mentions), 0)
            pos_sum = func.coalesce(func.sum(mention_minutes.c.pos), 0) if "pos" in mention_minutes.c else func.sum(0)
            neg_sum = func.coalesce(func.sum(mention_minutes.c.neg), 0) if "neg" in mention_minutes.c else func.sum(0)
            neu_sum = func.coalesce(func.sum(mention_minutes.c.neu), 0) if "neu" in mention_minutes.c else func.sum(0)
        else:
            if sent_col is None:
                agg_mentions = func.count()
                pos_sum = func.sum(0)
                neg_sum = func.sum(0)
                neu_sum = func.count()
            else:
                agg_mentions = func.count()
                pos_sum = func.sum(func.case((sent_col == 1, 1), else_=0))
                neg_sum = func.sum(func.case((sent_col == -1, 1), else_=0))
                neu_sum = func.sum(func.case((sent_col == 0, 1), else_=0))
        q = (
            select(
                ticker_col.label("ticker"),
                agg_mentions.label("mentions"),
                pos_sum.label("pos"),
                neg_sum.label("neg"),
                neu_sum.label("neu"),
            )
            .where(and_(*conditions))
            .group_by(ticker_col)
        )
        rows = conn.execute(q).all()
        z_by_ticker = {}
        if rows:
            tickers = [r.ticker for r in rows]
            base_q = select(baselines.c.ticker, baselines.c.mean, baselines.c.std)
            if "source" in baselines.c and source_filter:
                base_q = base_q.where(baselines.c.ticker.in_(tickers), baselines.c.source == source_filter)
            else:
                base_q = base_q.where(baselines.c.ticker.in_(tickers))
            for b in conn.execute(base_q):
                z_by_ticker[b.ticker] = (b.mean, b.std)
        day_value = day
        if isinstance(daily_rollups.c.day.type, DateTime):
            day_value = dt.datetime(day.year, day.month, day.day)
        conflict_cols = ["day", "ticker"]
        if "source" in daily_rollups.c and source_filter:
            conflict_cols.append("source")
        can_on_conflict = (
            engine.dialect.name == "postgresql"
            and pg_insert is not None
            and _has_unique(engine, daily_rollups, conflict_cols)
        )
        for r in rows:
            mentions = int(r.mentions or 0)
            pos = int(r.pos or 0)
            neg = int(r.neg or 0)
            neu = int(r.neu or 0)
            interest = mentions
            mean_std = z_by_ticker.get(r.ticker)
            if mean_std and mean_std[1] and float(mean_std[1]) > 0:
                zscore = (mentions - float(mean_std[0])) / float(mean_std[1])
            else:
                zscore = None
            ins_values = {
                "day": day_value,
                "ticker": r.ticker,
                "mentions": mentions,
                "pos": pos,
                "neg": neg,
                "neu": neu,
                "interest": interest,
                "zscore": zscore,
            }
            if "source" in daily_rollups.c and source_filter:
                ins_values["source"] = source_filter
            if can_on_conflict:
                stmt = pg_insert(daily_rollups).values(**ins_values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=conflict_cols,
                    set_={
                        "mentions": mentions,
                        "pos": pos,
                        "neg": neg,
                        "neu": neu,
                        "interest": interest,
                        "zscore": zscore,
                    },
                )
                conn.execute(stmt)
            else:
                del_cond = (daily_rollups.c.day == day_value) & (daily_rollups.c.ticker == r.ticker)
                if "source" in daily_rollups.c and source_filter:
                    del_cond = del_cond & (daily_rollups.c.source == source_filter)
                conn.execute(daily_rollups.delete().where(del_cond))
                conn.execute(sa_insert(daily_rollups).values(**ins_values))
        if verbose:
            print(f"[rollup-range] Rolled up {len(rows)} tickers for {day.isoformat()} (source={source_filter or 'ALL'}) | upsert={'ON CONFLICT' if can_on_conflict else 'delete+insert'}.")
def main():
    args = parse_args()
    today = dt.date.today()
    if args.days is not None:
        start = today - dt.timedelta(days=args.days - 1)
        end = today
    elif args.date:
        d = dt.date.fromisoformat(args.date)
        start = d
        end = d
    else:
        if not args.date_from or not args.date_to:
            print("--from requires --to as well.", file=sys.stderr)
            sys.exit(2)
        start = dt.date.fromisoformat(args.date_from)
        end = dt.date.fromisoformat(args.date_to)
        if end < start:
            print("Invalid range: --to is before --from.", file=sys.stderr)
            sys.exit(2)
    engine = get_engine()
    mention_minutes, daily_rollups, baselines = reflect_tables(engine)
    for day in daterange(start, end):
        compute_day(engine, mention_minutes, daily_rollups, baselines, day, args.source, args.verbose)
if __name__ == "__main__":
    main()
