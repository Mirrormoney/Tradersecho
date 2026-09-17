# Free-launch operating notes

## Hosting decision: Vercel Pro approved; payment pending
Keep United Domains DNS and email. Its advertised PHP webspace is not confirmed to support this Python/FastAPI backend. Disk capacity is not a runtime guarantee. Ask support specifically about Python 3.12, ASGI hosting, custom packages, outbound HTTPS/PostgreSQL, HTTPS routing and scheduled jobs before any migration.

Vercel Hobby cannot schedule this collector every 15 minutes natively. Pro or an external scheduler is needed for that cadence. Pro is also the appropriate Vercel plan for commercial use, including a free acquisition launch for a planned paid business. The owner approved Pro; checkout must finish before activation.

The following is prepared in vercel.json. After verifying Pro is active, configure CRON_SECRET in Production, migrate the Production database, verify all runtime values, then deploy to protected Production:

    "crons": [{"path":"/api/cron/collect","schedule":"*/5 * * * *"}]

Native Vercel cron only runs on Production deployments. Do not assume a preview alias enables it. Disable the GitHub fallback after the new scheduler has demonstrated repeated successful runs. Existing shared database worker leases prevent simultaneous collectors.

External scheduler alternative: GET the protected preview /api/cron/collect every 15 minutes, timeout at least 200 seconds. Store Authorization: Bearer CRON_SECRET and x-vercel-protection-bypass in encrypted scheduler secrets. Never put secrets in the URL. No external account has been provisioned yet.

Monitor /api/cron/health with the same Authorization header (plus preview bypass where applicable). It returns 503 when scheduling is over 90 minutes late or the latest worker reported errors. An intentional admin pause returns healthy/paused. X cooldowns are reported without creating a retry loop.

## Free early access
FREE_LAUNCH=true opens rankings to real signed-in free members and disables all checkout options server-side. BILLING_ENABLED=false remains the main-site setting. It does not change membership records or cancel subscriptions. Keep the separate Stripe sandbox isolated. Free members retain five saved stocks and shared voices; personal tracking and chat still require premium. Newsletter delivery stays off.

## Account security
ACCOUNT_EMAIL_ENABLED=true plus RESEND_API_KEY enables reset and verification mail, from ACCOUNT_EMAIL_FROM (default Tradersecho <info@tradersecho.com>). APP_ORIGIN must be the actual site URL. Email verification is optional and user-triggered in My account. Reset links expire in one hour; verification links in 24 hours. Tokens are hashed, single use and bound to the account's current email. Reset signs out all sessions. Apply the additive account_security migration before deploying.

## Launch gates
- Scheduling provider/plan selected and repeated automatic runs verified.
- Public business identity/address completed and policies reviewed before public release. The UI currently shows Traders Echo and info@tradersecho.com; no address is invented. This is not a declaration of legal readiness.
- Backup/restore procedure verified with the database provider.
- Public domain, protection removal and live configuration reviewed separately.
- No live Stripe setup needed for the free version, and no automatic upgrade or charges.

## Data quality
Long X posts now request note_tweet text. Older short stored excerpts only expand when collected again; historical text is not magically restored by a deploy. Default posts filter promotional templates, prioritize curated voices and remove identical text. All collected posts remain available through the feed selector. Automated language labels include unclear; percentages require 20 independent authors with classifiable language. This is a heuristic, not validated financial sentiment.

## Approved staged launch — 17 September 2026
- Owner approved upgrading the existing Vercel team to Pro ($20 base monthly). Payment entry remains with owner; do not report Pro active until verified.
- Launch with free accounts for roughly 1–2 weeks. Keep FREE_LAUNCH=true, BILLING_ENABLED=false, BILLING_SANDBOX=false. No automatic paid conversion or time-based billing activation.
- Prepared native Vercel cron: /api/cron/collect every five minutes, production only. Ticks drain bounded batches; existing hourly/daily database markers, shared-account collection, leases and spend limits control actual X purchases. This is not five-minute stock resampling.
- Before activation: verify Pro and production environment (real public schema, X token, database, CRON_SECRET, account email and correct origin). Preserve deployment protection during scheduler commissioning. Never copy sandbox credentials or schema into production.
- Verify at least two consecutive native scheduled invocations and freshness before removing the GitHub schedule; leave workflow_dispatch for operator recovery. Never claim a manual request proves the scheduler works.
- Preserve the $185 X ceiling. Hosting usage is a separate budget; inspect spend-management controls after upgrade.
- Public release still requires completed operator details and a verified restore drill. Do not expose the site as a side effect of enabling the scheduler.
- Premium is a later explicit release with verified live Stripe configuration, tested cancellation/refund and announced plan terms. Keep existing owner/admin access and isolated payment test accounts intact.
