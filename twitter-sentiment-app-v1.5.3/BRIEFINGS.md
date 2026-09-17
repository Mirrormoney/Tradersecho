# Daily briefing and marketing rollout

## Available in the private preview
- Daily briefing: a completed UTC calendar day, with a comparison to the previous UTC day. Not a US market-close report. Exact 48-hour hourly-bucket coverage is required for every current tracked stock; stale snapshots older than 36 hours are withheld.
- Daily reports are stored once per snapshot and immutable. The hosted collection tick prepares them without another X purchase; opening the page can prepare a missing report from stored counts.
- Free accounts see three leading stocks; Premium sees ten or its selected watchlist. Followed-account posts are a capped sample within the report day, not today's newer posts.
- My account includes explicit off/weekly/daily email preferences. Defaults are off. Daily frequency requires Premium. Delivery is disabled for everyone.
- Administration > publishing shows the X draft, a text email preview, and connection requirements. Public X drafts contain only aggregated market data, never personal watchlists or email addresses.

## Before external delivery
1. Owner creates and connects the Tradersecho X account using user authorization with publishing permission. Do not paste credentials into chat. Set the appropriate automated account disclosure.
2. Choose a public domain and verified newsletter sender. Connect Resend or an equivalent email provider. Resend free plan is connected to Preview; tradersecho.com and all three DNS records are verified.
3. Implement and verify email confirmation, tokenized unsubscribe, authenticated delivery webhooks with bounce/complaint suppression, and membership checks at send time. Saved preferences alone do not verify ownership of the email address.
4. Add a durable delivery ledger with one dispatch per report/channel/recipient, provider idempotency keys and reconciliation for ambiguous responses. No send route exists yet, so environment variables alone cannot enable broadcasts.
5. Run owner-only test emails and review several X drafts. Add the public link only once the website is intentionally launched. Integrate publishing spend into the existing monthly ceiling before enabling writes.
6. Add weekly aggregation with seven full days of coverage before enabling the free weekly email. Current preview is daily only; weekly is a stored preference, not an implemented dispatch.

## Initial marketing plan
- Validate collection, calculations and daily reports during the monitoring week.
- Launch one useful daily recap on the dedicated X account: three leaders, day-over-day changes, a concise attention-versus-sentiment explanation and one clear invitation to explore.
- Use a free weekly recap for discovery and a personalized Premium digest for retention.
- Show a transparent data timestamp and sample coverage. Skip stale/incomplete reports. Do not fabricate catalysts from mention counts or imply investment returns.
- Measure visits from recap links, registrations, returning users and Premium conversion. Begin with organic distribution; no advertising spend is authorized.
- Add watchlist spike alerts after collecting enough baseline history, then richer account-to-ticker research views. Evaluate whether users return before adding more channels.

## Owner-confirmed sending identity
- Domain: tradersecho.com; DNS provider: United Domains (owner described as Uniter Domains).
- From: Tradersecho <newsletter@tradersecho.com>.
- Reply-To and support: info@tradersecho.com.
- Resend verified domain and all three DNS records on 2026-09-16. Existing mail records were preserved.

## Owner-only delivery test
- `ops/prepare_owner_email.py` prepares HTML and plain text from the latest stored complete report, checks freshness, and reads the active owner recipient from the database. Pass a private output JSON path.
- `ops/send_owner_test.cjs payload.json receipt.json --send` sends only an explicitly prepared test using server-side RESEND_API_KEY. The persisted receipt freezes the payload hash and idempotency key before transmission; successful retries do not resend, and ambiguous attempts older than 23 hours require reconciliation. Keep payloads, environment files and receipts outside the repository.
- The first authorized owner test on 2026-09-16 was confirmed delivered by Resend. It used the September 15 UTC report, top ten stocks across the 357-stock universe, and the stable private preview link.
- These are operator tools, not public endpoints or an automated newsletter launch. Subscriber delivery remains off pending the confirmation, unsubscribe, suppression and durable database delivery work above.

## Branded daily field notes
- The shared newsletter renderer provides HTML, plain text and the inline pulse-logo attachment for admin previews and owner tests.
- Personal greetings, a lead-stock card, up to five watchlist highlights and three filtered voice excerpts use stored report data. No additional X requests.
- Administration > Publishing includes desktop and mobile design previews. Links are disabled inside the sandboxed preview; email links open the appropriate app view and ticker after sign-in.
- Incomplete or stale reports produce no send payload. Empty personal lists remain empty rather than being replaced with unrelated stocks.
- Sending remains disabled during private testing. Subscriber dispatch still needs unsubscribe tokens, delivery reconciliation, verified recipients, suppression handling and completed business details.
- Inbox appearance still needs testing in Gmail, Outlook and Apple Mail; a browser preview is not a guarantee of identical rendering.

## Delivery safeguards implemented during prelaunch
- Scanner-safe unsubscribe: GET shows confirmation; POST performs opt-out without requiring login. Tokens are stored hashed, recipient-bound, and responses suppress referrers.
- Signed Resend event endpoint validates raw-body signatures and timestamps, deduplicates event IDs, and retains suppression after out-of-order delivery events. Provider connection remains pending the public endpoint.
- Database ledger freezes a single test payload per recipient/report, checks verified membership and opt-in, leases attempts and keeps the same idempotency key. Retries older than 23 hours require review.
- These are preparation primitives, not an active sender: subscriber dispatch and ambiguous provider-response reconciliation remain launch work. No environment switch enables broadcasts. Existing owner-test tooling is separate.
- Regression coverage includes signature tampering/expiry, duplicate events, bounce suppression, scanner-safe opt-out and duplicate payload/attempt protection.

## Top-ten field notes redesign
The owner preview now shows three responsive feature cards, relevant shared/followed X excerpts linked to those leaders, and ranks 4-10 as separate cards. Report ordering uses the Market Pulse heat formula for the completed UTC day (not the live rolling window). Posts are selected by likes and limited to one per author; missing qualifying posts are disclosed. Broader licensed market-news summaries and individual click tracking remain unimplemented. No tracking pixels or additional analytics cookies were added. Owner sample delivered September 17 via Resend; subscriber dispatch stays disabled.
