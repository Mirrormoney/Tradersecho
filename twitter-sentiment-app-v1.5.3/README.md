> Current plans, Stripe sandbox and live activation checklist: see [PAYMENTS.md](PAYMENTS.md).

> Current hourly collection and scheduler configuration: see [AUTOMATION.md](AUTOMATION.md).

# Tradersecho — protected online preview

**Current deployment and X setup:** [ONLINE-SETUP.md](ONLINE-SETUP.md). The Vercel preview uses PostgreSQL, a reviewed AI universe (capacity 1,000), resumable daily collection and sample screening. The local/Docker instructions below remain available for offline work. [Stock selection](UNIVERSE.md).

An extension of the original `twitter-sentiment-app-v1.5.3` React/Python project. The new entrypoint is **backend.service:app**. The earlier Python modules and migrations are retained as legacy reference and are not used by v2. The v2 database is separate; no existing users or records are modified or silently migrated.

## Try it

**Membership update:** see [MEMBERSHIPS.md](MEMBERSHIPS.md) for the private owner invitation, administration, visitor statistics, Premium trading room and the recommended count-first X collector. Logged-out visitors see three stocks; Free members see five ranked stocks; Premium unlocks full rankings. Existing v2 accounts are migrated additively without deleting their data.

The local preview runs at http://127.0.0.1:8000. Choose **Create account → Try free / Try premium** to explore an isolated sample account. These are real server sessions over a fictional dataset. No shared passwords are shipped. Real signup creates a Free account.

### Included

- Rolling 24-hour, 7-day and 30-day rankings, heat score, growth, sentiment, sparklines, sector filters and search.
- Ticker details and underlying posts; latest or most-liked sorting surfaces higher-engagement takes.
- Free and Premium accounts, scrypt password hashes, opaque HttpOnly sessions, logout, basic sign-in throttling and same-origin checks.
- Account-owned watchlists (5 Free / 50 Premium) and manually tracked X handles (5 personal voices for Premium), with notes and a filtered post feed.
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

The recommended collector is the checkpointed daily queue in `backend.collection`, described in [ONLINE-SETUP.md](ONLINE-SETUP.md). It is paused by default, has a $185 monthly API ceiling, and supports up to 1,000 active stocks. The initial universe contains 357 exchange-validated AI supply-chain and adjacent names. Manage it in Administration; see [UNIVERSE.md](UNIVERSE.md).

For local or Docker collection, configure `X_BEARER_TOKEN`, enable the owner budget setting, and run `python -m backend.run_local` once daily, or use `--loop`. For the protected online preview, use the admin batch button or `backend.run_remote` from a trusted scheduler. A daily schedule is not yet provisioned for the private preview.

Raw mention counts and screened sentiment samples are separate. History accumulates for weekly/monthly comparisons; insufficient evidence is shown explicitly. Set a provider-side spending cap as well. Actual paid X requests have not been tested because the owner's credentials are not connected.

Official references: [search capabilities](https://docs.x.com/x-api/posts/search/introduction), [usage pricing](https://docs.x.com/x-api/getting-started/pricing). Removal/compliance synchronization is not implemented yet and is required before public launch.

### JSON import

Sign in as owner or administrator, open **Data sources → Import X posts**, and select an array of up to 1,000 posts or `{ "posts": [...] }`. Legacy operator scripts can alternatively use a server-configured `ADMIN_TOKEN`:

```json
[{"id":"1234567890123456789","author":"example_handle","text":"Bullish $NVDA and $AMD","created_at":"2026-09-16T08:00:00Z","likes":12}]
```

This schema example is not a real X post. Do not import it as real data. `sentiment` can optionally be `bullish`, `bearish`, or `neutral`; otherwise the classifier assigns it. Full exports can be adapted to this format. Posts without supported cashtags are ignored. Existing IDs are retained rather than counted twice. Refreshes do not yet update stored like counts or edited posts.

## Free / Premium

Free: all three ranking windows, ticker details and 5 saved stocks. Premium: 50 saved stocks, 25 tracked handles with filtered posts, and the private trading room. Both use the same collection; Premium does not promise better coverage. Demo Premium cannot enter the community or access the premium live-post feed.

Grant early-access Premium from **Administration → Users**. Legacy scripts can POST `/api/admin/plan` with header `x-admin-token` and JSON `{ "email": "the-account-email", "plan": "premium" }`. Users cannot grant themselves a plan. Do not distribute the admin token.

For subscriptions, configure `STRIPE_SECRET_KEY`, recurring `STRIPE_PRICE_ID`, `STRIPE_WEBHOOK_SECRET`, and your HTTPS `APP_ORIGIN`. Register `/api/billing/webhook` for `customer.subscription.created`, `.updated`, and `.deleted`. The server retrieves canonical subscription status and grants Premium only for active/trialing subscriptions. Configure and test Stripe Customer Portal/cancellation support before accepting public payments; the in-app portal flow is not yet implemented. Checkout and actual webhook delivery were not tested against a live Stripe account.

## Hosting

A **protected Vercel preview** is now available; see ONLINE-SETUP.md. The following is an alternative Docker hosting path. Deploy the included Docker image on a host with a persistent disk; SQLite must not be placed on ephemeral/serverless storage. Start with one web instance and one collector. Put HTTPS in front, set `APP_ORIGIN` exactly and `COOKIE_SECURE=true`, persist `/app/data`, set a random admin token, and disable sample accounts using `DEMO_ENABLED=false` if not desired. Back up the database.

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

Ten integration scenarios cover time windows, source separation, sign-in/logout, account isolation, limits, premium gates, multi-ticker deduplication, atomic validation, origin rejection, unsigned webhooks, mocked X pagination/counts/budgets, owner claims, administration, room moderation and analytics. Browser checks cover period switching, search, details, watchlists, tracked handles, landing, owner form, administration, chat posting and responsive layout. Real X ingestion, live Stripe payments and Docker hosting need external configuration and were not executed.

## Repository hygiene

The source repository exposed a root `.env` and `user login data.docx`. The proposed branch removes these from its tip and adds ignore rules. **Removal does not erase Git history**: rotate any real credentials they contained and review repository history separately. No secrets were read, copied into the new app or included in its deliverables.
