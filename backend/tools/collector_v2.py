#!/usr/bin/env python
"""
Tradersecho — v2.0 Step 1b: Hardened collector_v2

- Prints detected columns of `mention_minutes`.
- Timezone-aware UTC.
- Fills `mentions=1` if column exists; one-hot pos/neg/neu when present.
- `--force-aggregated` to always include mentions/pos/neg/neu when columns exist.

Usage:
  python backend/tools/collector_v2.py --tickers-file backend/symbols.txt --simulate --batch-size 200 --sleep-sec 2 --loops 1 --force-aggregated
"""
import argparse
import datetime as dt
import os
import sys
import time
import uuid
import random
from typing import List, Iterable, Dict, Any

from sqlalchemy import create_engine, MetaData, Table, insert
from sqlalchemy.engine import Engine
from sqlalchemy import inspect as sa_inspect

def parse_args():
    p = argparse.ArgumentParser(description="Collector v2 (hardened) with tickers-file and batch rotation.")
    p.add_argument("--tickers-file", type=str, required=True, help="Path to newline-separated tickers file.")
    p.add_argument("--simulate", action="store_true", help="Generate synthetic mentions (stocktwits-like).")
    p.add_argument("--batch-size", type=int, default=int(os.environ.get("STOCKTWITS_BATCH_SIZE", "200")), help="Batch size per rotation.")
    p.add_argument("--sleep-sec", type=int, default=int(os.environ.get("STOCKTWITS_SLEEP_SEC", "5")), help="Sleep seconds between batches.")
    p.add_argument("--loops", type=int, default=1, help="How many full rotations to run (simulation mode).")
    p.add_argument("--source", type=str, default="stocktwits", help="Source label to write into DB.")
    p.add_argument("--debug-schema", action="store_true", help="Print detected mention_minutes columns then continue.")
    p.add_argument("--force-aggregated", action="store_true", help="Always include mentions/pos/neg/neu in inserts when columns exist.")
    return p.parse_args()

def get_engine() -> Engine:
    db_url = os.environ.get("DB_URL")
    if not db_url:
        print("ERROR: DB_URL not set in environment.", file=sys.stderr)
        sys.exit(1)
    return create_engine(db_url, future=True)

def read_tickers(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8") as f:
        tickers = [line.strip().upper() for line in f if line.strip()]
    if not tickers:
        raise ValueError("No tickers found in file.")
    return tickers

def batches(items: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield items[i:i+size]

def reflect_mention_minutes(engine: Engine) -> Table:
    meta = MetaData()
    return Table("mention_minutes", meta, autoload_with=engine)

def detect_columns(engine: Engine, table: Table) -> Dict[str, bool]:
    cols = {c.name for c in table.columns}
    insp = sa_inspect(engine)
    try:
        info = insp.get_columns(table.name, schema=getattr(table, "schema", None))
        not_null = {c["name"] for c in info if not c.get("nullable", True)}
    except Exception:
        not_null = set()
    return {"cols": cols, "not_null_mentions": ("mentions" in not_null), "has_mentions": ("mentions" in cols),
            "has_pos": ("pos" in cols), "has_neg": ("neg" in cols), "has_neu": ("neu" in cols),
            "has_sentiment": ("sentiment" in cols), "ts_col": ("ts" if "ts" in cols else ("timestamp" if "timestamp" in cols else None))}

def _row_for_schema(d: Dict[str, bool], ticker: str, now_utc: dt.datetime, source: str, sentiment: int, force_agg: bool) -> Dict[str, Any]:
    row: Dict[str, Any] = {}
    if "ticker" in d["cols"]:
        row["ticker"] = ticker
    ts_col = d["ts_col"]
    if ts_col:
        row[ts_col] = now_utc.replace(tzinfo=None)  # DB col likely naive
    if "source" in d["cols"]:
        row["source"] = source
    if "external_id" in d["cols"]:
        row["external_id"] = f"sim-{source}-{ticker}-{now_utc.isoformat(timespec='minutes')}-{uuid.uuid4().hex[:8]}"
    include_agg = force_agg or d["has_mentions"] or d["has_pos"] or d["has_neg"] or d["has_neu"]
    if include_agg:
        if d["has_mentions"]:
            row["mentions"] = 1
        if d["has_pos"]:
            row["pos"] = 1 if sentiment == 1 else 0
        if d["has_neg"]:
            row["neg"] = 1 if sentiment == -1 else 0
        if d["has_neu"]:
            row["neu"] = 1 if sentiment == 0 else 0
    if d["has_sentiment"]:
        row["sentiment"] = sentiment
    for k in list(row.keys()):
        if k not in d["cols"] or row[k] is None:
            row.pop(k, None)
    return row

def simulate_insert(engine: Engine, mention_minutes: Table, tickers: List[str], source: str, debug_dict: Dict[str, bool], force_agg: bool):
    now_utc = dt.datetime.now(dt.UTC).replace(second=0, microsecond=0)
    sentiments = [-1, 0, 1, 0, 0, 1]
    values = []
    for t in tickers:
        for _ in range(random.randint(1, 3)):
            sent = random.choice(sentiments)
            row = _row_for_schema(debug_dict, t, now_utc, source, sent, force_agg)
            values.append(row)
    if not values:
        return 0
    with engine.begin() as conn:
        conn.execute(insert(mention_minutes), values)
    return len(values)

def main():
    args = parse_args()
    engine = get_engine()
    mention_minutes = reflect_mention_minutes(engine)
    debug_dict = detect_columns(engine, mention_minutes)
    print("[collector_v2] detected columns:", sorted(list(debug_dict["cols"])))
    print("[collector_v2] has_mentions:", debug_dict["has_mentions"], "not_null_mentions:", debug_dict["not_null_mentions"])
    print("[collector_v2] ts_col:", debug_dict["ts_col"], "has_pos/neg/neu:", debug_dict["has_pos"], debug_dict["has_neg"], debug_dict["has_neu"], "has_sentiment:", debug_dict["has_sentiment"])
    tickers = read_tickers(args.tickers_file)
    for loop_idx in range(args.loops):
        total_inserted = 0
        for batch in batches(tickers, args.batch_size):
            if args.simulate:
                inserted = simulate_insert(engine, mention_minutes, batch, args.source, debug_dict, args.force_aggregated)
                total_inserted += inserted
                print(f"[collector_v2] inserted {inserted} mentions [source={args.source}] for {len(batch)} tickers.")
            else:
                print(f"[collector_v2] (noop) would ingest for {len(batch)} tickers from {args.source}.")
            time.sleep(args.sleep_sec)
        print(f"[collector_v2] loop {loop_idx+1}/{args.loops} complete. Inserted total {total_inserted} mentions.")

if __name__ == "__main__":
    main()
