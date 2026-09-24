# UW Basic private pilot

September 24, 2026. Owner obtained API access, saved UW_API_KEY privately in Vercel Production, and explicitly confirmed UW permission for private Tradersecho evaluation. Production pilot enabled. Preview remains disabled. First live requests return current candles and net premium; provider quota header confirms 40,000/day. No public redistribution or finished scores enabled.

Owner-only status: Administration -> signal lab. Members cannot access /api/admin/uw-pilot; the endpoint requires the non-demo owner role. Existing member features and customer API do not read the new tables.

## Activation configuration and remaining validation
1. Owner obtains UW confirmation that Basic permits private Tradersecho product evaluation. API conventions allow personal/internal use, while pricing says personal only; do not assume public display or redistribution rights.
2. Owner creates account/accepts subscription terms privately. Basic advertised $150/month after seven-day trial; billing begins automatically. Verify checkout price/conditions; no paid action authorized here.
3. Save UW_API_KEY as sensitive, Production only, in existing Tradersecho Vercel project. Never send the key in chat or add it to frontend variables.
4. Only after permission confirmation set UW_PRIVATE_EVALUATION_APPROVED=true. Set UW_PILOT_ENABLED=true only when ready to consume the account's API quota; redeploy. Defaults are false. Preview must stay disabled, without the key.
5. Verify first provider request, account quota headers, twenty pilot names, provider field semantics, timestamps, market/holiday coverage, price-feed venue scope and empty/non-optionable handling. Do not claim signal readiness until these checks pass.

## Collector
Authenticated ten-minute Vercel cron; inactive gates return before requests. Weekday 09:30–16:00 America/New_York window with DST, no overnight polling. Holiday/early-close calendar not yet integrated: this is a pilot session filter, not a complete exchange calendar. Cap twenty in-universe tickers and forty HTTP calls per invocation; ~1,560 calls per full session for two endpoints. Distributed three-minute lease, sixty-second work budget, approximately one call/second, reserve before request. Compare local reservations and provider usage against min(32,000, provider cap). Quota reset at 20:00 ET. 401/403 pause one hour; 429 pauses fifteen minutes. Other ticker errors recorded and next item proceeds. No automatic same-call retries. Provider error bodies/credentials are not stored or shown.

Endpoints from official OpenAPI https://api.unusualwhales.com/api/openapi:
- GET /api/stock/{ticker}/ohlc/10m?date=YYYY-MM-DD&limit=100
- GET /api/stock/{ticker}/net-prem-ticks?date=YYYY-MM-DD

Completed candles only; normalize numeric fields; order by actual source timestamps; ignore future data and observations older than 24h; stale after 20m. Empty is distinct from failure. Latest payload bounded to 400 observations per ticker/dataset; owner response includes only latest observation. Historical intervals are inserted once by ticker/dataset/source time, with first-seen time preserved; 45-day retention. No repeated whole-day archival on each poll. Tables: uw_pilot_latest, uw_pilot_history, uw_pilot_usage. All additive.

## Deliberate pilot limits
Fixed representative twenty-stock cohort, not yet dynamic top-20/remainder routing. No SPY or out-of-universe fetching. No 0–100 scores yet; net premium aggregates do not support the agreed DTE/single-leg filters. No fabricated baseline or sector-relative output. Next work after real credentials: validate schemas and entitlement, add necessary filtered options observations and benchmark prices under agreed scope, accumulate same-time baselines, then connect experimental five-axis calculations to approved private design.

The approved visual preview remains separate until real measurements support its axes. No changes to public navigation, prices, X/AI ceilings or existing collection pipelines.
