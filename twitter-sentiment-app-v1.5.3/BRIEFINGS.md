# Daily briefing and marketing rollout

## Available in the private preview
- Daily briefing: a completed UTC calendar day, with a comparison to the previous UTC day. Not a US market-close report. Exact 48-hour hourly-bucket coverage is required for every current tracked stock; stale snapshots older than 36 hours are withheld.
- Daily reports are stored once per snapshot and immutable. The hosted collection tick prepares them without another X purchase; opening the page can prepare a missing report from stored counts.
- Free accounts see three leading stocks; Premium sees ten or its selected watchlist. Followed-account posts are a capped sample within the report day, not today's newer posts.
- My account includes explicit off/weekly/daily email preferences. Defaults are off. Daily frequency requires Premium. Delivery is disabled for everyone.
- Administration > publishing shows the X draft, a text email preview, and connection requirements. Public X drafts contain only aggregated market data, never personal watchlists or email addresses.

## Before external delivery
1. Owner creates and connects the Tradersecho X account using user authorization with publishing permission. Do not paste credentials into chat. Set the appropriate automated account disclosure.
2. Choose a public domain and verified newsletter sender. Connect Resend or an equivalent email provider. No provider was provisioned or purchased in this release.
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
- Domain ownership was provided by the owner; DNS verification is still pending. Keep existing mail records intact.
