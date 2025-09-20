
# Adapter Notes (v1.5.0)

This release adds pluggable collectors that feed into the existing `mention_minutes` table.

## Enable adapters

1) Copy `.env.example` to `.env` and set values:
```
ADAPTERS=stocktwits,reddit
ADAPTER_TICKERS=AAPL,MSFT,TSLA,NVDA,AMZN
STOCKTWITS_RATE_PER_MIN=60
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=Tradersecho/1.0 by you
```

2) Run migration:
```
alembic upgrade head
```

3) Start live collector:
```
python collector.py live --adapters stocktwits,reddit --tickers AAPL,MSFT,TSLA
```

Without Reddit credentials the Reddit adapter is skipped. StockTwits uses public symbol streams.
