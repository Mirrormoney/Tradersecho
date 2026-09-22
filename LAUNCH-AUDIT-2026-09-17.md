# Tradersecho launch audit — 17 September 2026

## Decision
Keep the private preview. Do not start a paid public launch yet. Payment checkout has passed sandbox testing, but collection reliability, account recovery, and sentiment presentation still need work. This turn was an audit: no production data, subscriptions, collection settings or application code were changed.

## Verified
- Clicked through Home, Market pulse, Daily briefing, My watchlist, Tracked voices, Data sources, Trading room, My account and Administration. Checked admin overview, users, moderation, tracked voices, collection, data budget and publishing. These panels rendered; market search and Intel details loaded. Browser error log was empty at the check.
- Intel detail contains ScroogeCap's post linking MU and INTC. Opened its original X link and confirmed author/content match. Not every external post was opened individually.
- Database-wide cashtag integrity: 111 X posts, 278 post/ticker links, zero missing and zero unexpected links relative to stored text and active universe. This does not validate links missing from truncated original text or detect company references without cashtags.
- 357 active stocks. All have 24/24 daily count buckets and 168/168 weekly buckets. Thirty-day view currently has 168/720 hours per stock. No negative counts or invalid bucket durations.
- Recomputed heat and label arithmetic for all 357 stocks across 1-, 7- and 30-day views. Top-three public API growth/heat also independently matched. Daily comparisons complete for all stocks; previous-week/month comparisons incomplete and withheld.
- 30 backend tests passed, covering account isolation, limits, voices, screening, collection, billing and password changes.
- Hosted anonymous requests cannot read posts, weekly rankings, admin, community or account preferences. Public ranking API returns three rows. Synthetic free sandbox member is denied personal voices, Trading room and admin endpoints; can access watchlist/preferences.
- Main preview remains protected (unauthenticated request redirects to Vercel authentication). Main billing disabled. Payment sandbox separated from main membership data.
- Previous payment verification: user's $190 yearly sandbox checkout paid, subscription active, webhook processed, membership Premium. Billing portal and return link verified in the preceding turn.

## Launch blockers / high-priority findings

### 1. Automatic collection is not meeting its advertised cadence
Admin reports scheduler overdue. Last recorded heartbeat was 17 September 09:49:22 Europe/Berlin. GitHub's latest visible workflow run was successful at 07:49 UTC, but only six total runs were returned since activation, including older failures. Repository workflow is configured for minutes 7, 22, 37 and 52 every hour. Do not confuse a successful individual run with reliable scheduling. Investigate delivery delays and establish a monitored hosted cadence before promising hourly coverage. No current collection job was in error; one tracked-voice job was skipped under its allowance.

### 2. Sentiment presentation overstates the evidence
Zero stocks meet the current threshold of 20 independent sampled authors in any tested window. Individual rows correctly show insufficient evidence; the headline still computes 1% bullish from undersized samples. Hide that headline percentage until evidence is sufficient and label any aggregate as sampled language, not the sentiment of the whole market.
The keyword classifier is not validated financial sentiment. The ScroogeCap post describes a negative Micron thesis but is labeled neutral. Mixed-ticker clauses are forced neutral; lack of a recognized keyword is also neutral. Those cases should distinguish uncertain/unclassified from genuinely neutral. Methodology text still describes copying one post label to all tickers, whereas ranking screening uses ticker clauses: synchronize the explanation and post labels.

### 3. Long X posts are truncated in storage
The verified ScroogeCap original continues beyond the text shown in Tradersecho. Current collectors request text/created_at/author_id/public_metrics, without extended note-post content. Retrieve supported full text, preserve provenance, and re-link/reclassify when a stored post is updated. Current insert-ignore ingestion does not refresh text or like counts, so re-import alone does not repair an existing post. Avoid a paid bulk backfill until the repair path is tested.

### 4. Samples contain substantial irrelevant/promotional content
Intel's detail shows repeated promotional stock-group posts ahead of the curated analysis. Its daily sample has 14 posts but only 3 retained independent authors; screening removes repeats/templates for metrics but the reader still sees raw posts. Tracked voices also includes unrelated replies and emoji-only messages. Prefer curated ticker-linked posts in stock details, expose an explicit raw-post option, and separate account-wide chatter from research. Raw X count totals are not bot-filtered; do not market them as unique humans or organic attention.

### 5. Account recovery and verification are absent
Current deployed entrypoint has signup, login, logout and authenticated password change, but no forgot-password/reset endpoint or email-verification flow. A member who loses their password cannot recover through the app. Implement one-time expiring reset tokens, verified delivery and abuse controls before public registration. Earlier conversational assumptions about an existing recovery flow do not match this source.

### 6. Public launch and customer information remain incomplete
The audited site is a protected Vercel preview. A production domain cutover remains necessary. No public privacy, service terms, operator/contact or account-deletion pages/flow were found in the current frontend. Prepare these using actual business information and appropriate review; this audit is not legal approval. Backup restore and production incident recovery were not verified.

## Other gaps
- Coverage is 357 stocks, not 1,000. Current documented budget model is about $181.51/month at configured allowances; displayed reserved/estimated spend was $5.23, not a Stripe/X invoice. Do not advertise 1,000 tracked stocks or raise coverage without revisiting the budget.
- 30-day totals contain only seven days and equal the weekly totals. Rows show Partial history, but add a prominent 7/30-days coverage banner so users do not interpret this as a full month.
- Daily briefing is a saved snapshot while hourly count refreshes overwrite older buckets. Observed Intel briefing 1,636 vs current ranking 1,634 for the same reference day. Explain revisions or preserve immutable snapshot inputs.
- Main rankings use the completed daily snapshot; latest-hour attention is separate in stock details. Make the different timestamps explicit.
- My watchlist's summary total still describes the whole universe while other cards describe followed stocks; label the scope consistently.
- Newsletter preferences and draft generation exist, but delivery is hard-disabled in the current app. Prior owner test-email tooling is not an automated subscriber newsletter. X marketing publication is also disabled.
- Stripe portal currently supports cancellation at period end, card updates, billing address updates and invoice history. Monthly/yearly plan switching is disabled.
- Mobile viewport override did not take effect in the browser tooling; real phone layout validation remains outstanding. No claim of full mobile certification.

## Recommended order
1. Restore and observe reliable collection; reserve sufficient sampling allowance for curated voices and prevent low-value chatter from consuming it.
2. Repair long-post ingestion and sample presentation; suppress unsupported sentiment percentages; add clear coverage/freshness labels.
3. Implement account verification/recovery and customer-facing policy/support pages; verify backup restore.
4. Complete Stripe business activation, then configure separate live products/keys/webhook and verify one controlled live transaction and cancellation/refund process.
5. Run a small invited beta and validate sentiment against a manually labeled research sample before a public paid launch.

## Stripe activation
Official business-verification link: https://dashboard.stripe.com/account/onboarding
Choose the live business account rather than the sandbox and complete Stripe's business, representative and payout information privately. Official guide: https://docs.stripe.com/get-started/account/set-up
The available sandbox account currently reports charges_enabled=false, payouts_enabled=false and details_submitted=false. This test-key response is not a definitive assessment of any separate live account. Completing business setup does not itself install live credentials or activate real charges on Tradersecho.
