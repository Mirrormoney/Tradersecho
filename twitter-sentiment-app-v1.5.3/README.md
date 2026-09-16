# Tradersecho — v2 working preview

An extension of the original `twitter-sentiment-app-v1.5.3` React/Python project. The new entrypoint is **backend.service:app**. The earlier Python modules and migrations are retained as legacy reference and are not used by v2. The v2 database is separate; no existing users or records are modified or silently migrated.

## Try it

The local preview runs at http://127.0.0.1:8000. Choose **Create account → Try free / Try premium** to explore an isolated sample account. These are real server sessions over a fictional dataset. No shared passwords are shipped. Real signup creates a Free account.

### Included

- Rolling 24-hour, 7-day and 30-day rankings, heat score, growth, sentiment, sparklines, sector filters and search.
- Ticker details and underlying posts; latest or most-liked sorting surfaces higher-engagement takes.
- Free and Premium accounts, scrypt password hashes, opaque HttpOnly sessions, logout, basic sign-in throttling and same-origin checks.
- Account-owned watchlists (5 Free / 50 Premium) and manually tracked X handles (25 Premium), with notes and a filtered post feed.
- Separate fictional sample and collected-X datasets. Empty live data stays empty.
- Administrator JSON import with full-batch validation and unique `(source, post, ticker)` deduplication.
- Official X recent-search collector with pagination checkpoints, retry-safe writes and daily request caps.
- Optional Stripe subscription Checkout and signed, idempotent webhook handling. No payments are enabled without configuration.
- Docker configuration with persistent storage, optional collector service, and backend integration tests.

## Run locally

Requires Node 24 and Python 3.12+. From this directory:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements-v2.txt
cd frontend
npm ci
npm run build
cd ..
uvicorn backend.service:app --host 127.0.0.1 --port 8000
```

For frontend development use `npm run dev` in `frontend` while the API runs on port 8000. Its `/api` requests proxy to the API. Use the same hostname throughout to keep cookies consistent.

Configuration is read from **process environment variables**, not the old committed `.env`. `.env.v2.example` lists the keys. Docker Compose explicitly loads `.env.v2`. Do not place keys in browser code.

## Live X data

Set `X_BEARER_TOKEN` to a newly issued credential and `X_DAILY_REQUEST_LIMIT` to an approved request budget. The default is 24 requests/day, at most 100 returned posts per request; this is a request ceiling, not a currency cap. X charges depend on provider usage and current terms. Configure a provider-side spending limit too.

```sh
python -m backend.collect_x --max-pages 2
# Continuous collection, only after approving your X data budget:
python -m backend.collect_x --loop --interval 3600 --max-pages 2
```

Do not run multiple collector processes against the same database. Each run resumes unfinished pagination before advancing the time window, and a 60-second overlap plus deduplication avoids boundary losses. Rate-limit failures retain the checkpoint. If a backlog ages beyond the recent-search window, the collector stops rather than silently claiming full coverage. Use an archive export/import to fill gaps, then reset the relevant `cursor:` metadata only after reviewing the backfill.

The initial collection looks back one day. Recent search supports seven days; monthly views accumulate over time or require archive data. Supported cashtags are deliberately limited to `CATALOG` in `backend/service.py` (16 stocks). Add supported symbols there to expand the query; keep within X query-length limits. Tracked handles filter the collected universe, not arbitrary posts or complete account history. English posts only; reposts excluded. A selected handle may have no collected cashtag posts.

Current official references: [search capabilities](https://docs.x.com/x-api/posts/search/introduction), [usage pricing](https://docs.x.com/x-api/getting-started/pricing). Verify commercial display/retention requirements for your approved access before public launch. Removal/compliance synchronization is not implemented yet.

### JSON import

Set a random `ADMIN_TOKEN` server-side, open **Data sources → Import X posts**, and select an array of up to 1,000 posts or `{ "posts": [...] }`:

```json
[{"id":"1234567890123456789","author":"example_handle","text":"Bullish $NVDA and $AMD","created_at":"2026-09-16T08:00:00Z","likes":12}]
```

This schema example is not a real X post. Do not import it as real data. `sentiment` can optionally be `bullish`, `bearish`, or `neutral`; otherwise the classifier assigns it. Full exports can be adapted to this format. Posts without supported cashtags are ignored. Existing IDs are retained rather than counted twice. Refreshes do not yet update stored like counts or edited posts.

## Free / Premium

Free: all three ranking windows, ticker details and 5 saved stocks. Premium: 50 saved stocks and 25 tracked handles with filtered posts. Both use the same collection; Premium does not promise better coverage. Demo Premium cannot access the premium live-post feed.

To grant early-access Premium without billing, an administrator can POST `/api/admin/plan` with header `x-admin-token` and JSON `{ "email": "the-account-email", "plan": "premium" }`. Users cannot grant themselves a plan. Do not distribute the admin token.

For subscriptions, configure `STRIPE_SECRET_KEY`, recurring `STRIPE_PRICE_ID`, `STRIPE_WEBHOOK_SECRET`, and your HTTPS `APP_ORIGIN`. Register `/api/billing/webhook` for `customer.subscription.created`, `.updated`, and `.deleted`. The server retrieves canonical subscription status and grants Premium only for active/trialing subscriptions. Configure and test Stripe Customer Portal/cancellation support before accepting public payments; the in-app portal flow is not yet implemented. Checkout and actual webhook delivery were not tested against a live Stripe account.

## Hosting

This is a **local working preview**, not a public deployment. Deploy the included Docker image on a host with a persistent disk; SQLite must not be placed on ephemeral/serverless storage. Start with one web instance and one collector. Put HTTPS in front, set `APP_ORIGIN` exactly and `COOKIE_SECURE=true`, persist `/app/data`, set a random admin token, and disable sample accounts using `DEMO_ENABLED=false` if not desired. Back up the database.

Docker usage: copy `.env.v2.example` to `.env.v2`, fill only the necessary values, then `docker compose up --build -d`. The collector is off by default. Enable it with `docker compose --profile live up -d` only after configuring the X budget.

Before inviting public paying users: add email verification/password reset and account deletion, billing portal, X deletion/compliance handling, operational monitoring, and stronger distributed abuse controls if scaling. The current app is suitable for local evaluation and controlled early access after deployment configuration. No old credential or historical database has been reused.

## Metrics & limits

One post counts once per supported ticker, including posts with several tickers. Bullish share uses all mentions including neutral. Growth compares the preceding equal-length window. Heat is `10 * ln(1+n) * (1 + max(0, log2((n+5)/(previous+5))))`. Historical gaps or capped collection distort counts and growth; these are observed samples, not exhaustive X volumes. The displayed history span is not proof of continuous collection.

Sentiment is a small English keyword model with basic negation. It is not a financial NLP model, and sarcasm, mixed opinions and per-ticker nuance are not reliably handled. Each ticker in a post gets that post's sentiment. Like-based sorting uses the imported like count, not necessarily the latest total. All sample authors and posts are fictional.

## Verification

```sh
pip install pytest
python -m pytest backend/test_service.py -q
cd frontend
npm run build
npm audit
```

Six integration scenarios cover time windows, source separation, sign-in/logout, account isolation, limits, premium gates, multi-ticker deduplication, atomic validation, CSRF origin rejection, unsigned webhooks, and mocked X pagination/request caps. Browser checks cover period switching, search, details, saved watchlists, tracked handles, and desktop/mobile layout. Real X ingestion, live Stripe payments and Docker hosting need external configuration and were not executed.

## Repository hygiene

The source repository exposed a root `.env` and `user login data.docx`. The proposed branch removes these from its tip and adds ignore rules. **Removal does not erase Git history**: rotate any real credentials they contained and review repository history separately. No secrets were read, copied into the new app or included in its deliverables.
