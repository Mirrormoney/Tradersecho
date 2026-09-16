# Memberships, ownership and affordable X collection

## Owner setup

Run this locally on the server, using the same database as the web app:

```sh
python -m backend.owner_setup --email YOUR_EMAIL --output ../PRIVATE-owner-setup.txt
```

Open **Owner setup** in the landing-page footer. Enter the reserved email, your own password and the private code. The invitation expires in 72 hours, is single-use, and grants Owner + Premium. It is stored hashed, outside the repository. Ordinary signup always grants Free/member; the first signup is never automatically an administrator. While the invitation is active its email cannot be registered without the code. If already registered, sign in and claim from **My account**.

## Administration and community

Administration lists/searches members, status, joined/last-seen timestamps, plans and roles. Owners can appoint administrators. Administrators manage ordinary members; only the owner can manage administrators or collection settings. Self-modification and owner demotion/suspension are blocked. Suspension revokes sessions immediately. Changes are audited.

Grant early-access Premium from **Administration → Users**. Plan grants change access; they do not cancel Stripe subscriptions. Use Stripe to cancel billing. Owner/admin privileges are checked independently of a paid plan.

Traffic records use random browser-session IDs, daily hashed identifiers and navigation counts retained for 30 days. They exclude known bots, preview and staff activity and respect DNT/GPC. No raw IP is stored in traffic records; authentication throttling separately stores IPs temporarily. These are approximate, client-reported sessions, not unique people or fraud-resistant analytics. Pre-upgrade traffic cannot be reconstructed.

The persistent Premium trading room supports general/ticker discussions, public display names, ten-second polling, reports and moderator hiding. Messages render as text. The feed never returns emails. Free and preview accounts cannot read or post. Posting is limited to five messages/minute and a three-second minimum interval.

## Daily X collection

See [ONLINE-SETUP.md](ONLINE-SETUP.md) for the current checkpointed collector, protected Vercel deployment, database setup and X credentials. The universe starts with 357 reviewed names and supports up to 1,000 active stocks managed in Administration. The default monthly API ceiling is $185; collection remains paused until the owner enables it.

The online queue is `backend.collection`. For Docker/local scheduling use `python -m backend.run_local --loop`; Compose's optional live profile runs this queue. Do not run legacy `collect_economy` or `collect_x` alongside it. They remain reference alternatives and share the spending gate, but do not use the new daily snapshot queue.

Counts measure raw attention. Sentiment uses a separate capped sample with repeated-author/template screening and minimum evidence requirements. Manually tracked voices share the daily sampling budget. Neither counts nor samples promise complete or bot-free coverage.

## Verification and launch status

Thirteen integration scenarios cover accounts, ownership, membership gates, moderation, analytics, counts, budgets and queue behavior using mocked X responses. Disposable PostgreSQL schema tests cover online SQL behavior. The protected Vercel preview additionally passed real HTTP signup, secure cookies, watchlist persistence, membership gates and logout; its disposable test account was removed.

Hosting and persistent PostgreSQL are provisioned. X credentials/credits and automatic private-preview scheduling are not connected. Stripe payments remain disabled. Before public paying access, complete email verification/recovery, billing cancellation, account deletion, X compliance/deletion handling and production operations as described in README.
