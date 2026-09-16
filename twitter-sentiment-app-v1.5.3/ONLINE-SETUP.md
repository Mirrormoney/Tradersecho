# Protected online preview

The Vercel project is `sven-mais-projects/tradersecho`. Deploy preview branches only. Do not promote or deploy `--prod` until public launch is explicitly approved. Vercel Authentication must remain enabled. No public alias is needed for testing.

## Storage

Neon PostgreSQL was provisioned separately for Tradersecho in Frankfurt on the free plan. `APP_DATABASE_URL` pins the protected preview to a stable pooled database; this takes precedence over integration-generated per-deployment branches. Use a different database for future production. Connections set a transaction-local search path to avoid pooled connection state leaking between test schemas.

The schema contains accounts, hashed sessions, owner invitations, profile/status/plan/roles, watchlists, tracked voices, posts, ticker mentions, author identity/profile metadata, hourly X counts, collection jobs/checkpoints, spending reservations, settings, analytics, chat/messages/reports and audit logs. Offline development may use SQLite; Vercel refuses to fall back to temporary files.

Run `python -m backend.migrate` with the target database URL before code requiring new tables is deployed. Migrations are additive; back up persistent data before changing schemas. Never expose database credentials in frontend variables or Git.

## First owner

The owner's private single-use invitation is delivered separately, never in GitHub. Open the protected preview while signed into the authorized Vercel account, select **Owner setup** in the landing-page footer, enter the reserved email, private invitation, and a password of your choice. This grants Owner and Premium. The code expires after 72 hours. The ordinary signup form always creates a Free member.

To renew an unused invitation, run `python -m backend.owner_setup --email YOUR_EMAIL --output ../PRIVATE-owner-setup.txt` with the online database environment. Update the instructions' URL to the protected preview. Never run this against a different database accidentally.

## X access: what the owner supplies

1. Create or use your X developer account at https://developer.x.com/ and create a project/app with recent search, recent counts and user lookup access.
2. Add credits and set a provider spending ceiling. Recommended app API ceiling is **$185/month**, leaving some room within the $200 overall target for hosting/taxes. Exact hosting/tax costs are not guaranteed.
3. In Vercel → Tradersecho → Settings → Environment Variables, add **X_BEARER_TOKEN** as a **Secret**, for **Preview only**, then redeploy the preview. Do not send an X password, API secret, or bearer token in chat or commit it to GitHub.
4. Sign in as owner, review the stock universe and **Data budget**, then enable collection. Enabling is separate from running a batch. No X call is made while paused or without a token.
5. Run **Administration → Collection → Run next batch**. Each request handles up to ten jobs. Repeat until complete, or use the protected runner below.

Current defaults: 357 reviewed starting symbols, maximum 1,000 active; 120 sampled posts/day, up to 32 selected profile reads/day, $185 monthly local ceiling. At 1,000 active names and 31 days, the conservative X API estimate is $183.52. At 357 names it is $83.855. These are estimates at $0.005/count request, $0.005/post and $0.010/profile, excluding retries, taxes and hosting. The local reservation gate is shared and fails closed; X's billing console is authoritative.

Counts update daily for the previous completed UTC day. Initial backfill is six days; later requests overlap one hour. Full history accumulates for week/month comparisons. Daily membership of the universe is frozen once its run starts; changes apply to the next day. Missing count buckets withhold snapshot completion. Error jobs need owner review/retry, with at most three attempts. Failed/uncertain calls retain budget reservations.

Post samples target high-volume stocks and rotate through up to two manually tracked voices per day. The sampling budget is shared across members, not per member. Voice collection only retrieves cashtag posts and may miss a person's takes. Profiles are selectively refreshed, not fetched for every post.

## Scheduled batches

Vercel Cron runs on production deployments, not preview deployments. This private preview therefore has no silently implied automatic schedule. The implemented endpoint `/api/cron/collect` requires `Authorization: Bearer <CRON_SECRET>` and remains behind Vercel protection.

To run all daily batches from a trusted scheduler, set `TRADERSECHO_URL`, `CRON_SECRET`, and `VERCEL_AUTOMATION_BYPASS_SECRET` privately in that scheduler, then run `python -m backend.run_remote` daily after 00:00 UTC. Use the project-scoped Vercel automation bypass secret; do not disable deployment protection. The runner stops on errors or paused collection and caps each invocation at 150 batch requests. Scheduler provisioning is intentionally separate from the private preview; X access is still off.

## Screening limits

Raw X count totals cannot be deduplicated by author without retrieving the underlying posts. They are clearly labeled as raw attention and may contain spam. Sample analysis limits each author to one retained post/ticker/day, suppresses matching and near-identical templates, stores author concentration and duplicate indicators, and withholds sentiment until at least 20 distinct retained authors are present. This is an evidence threshold, not a statistical confidence guarantee or proof of human authorship. Keyword sentiment is per clause/ticker, with mixed-ticker clauses treated as uncertain. Sarcasm and sophisticated coordinated campaigns remain limitations.

## Verification

13 local integration tests cover access control, ownership, imports, counts, budgets, sample screening, queue resumption and cron authentication. Separate disposable PostgreSQL schemas verify production SQL behavior without leaving QA accounts in the preview database. Actual X calls and payments require external credentials and have not been executed.
