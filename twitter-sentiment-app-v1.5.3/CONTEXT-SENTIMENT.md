# Contextual post sentiment

Collected X posts use Claude Haiku 4.5 through Vercel AI Gateway. Analysis interprets the whole available text and each linked ticker, including conflicting directions. Labels are bullish, bearish, neutral, mixed or unclear; they are interpretations, not verified investment signals. Images, linked articles and missing thread context are not retrieved.

The existing collection cron analyzes up to four posts per invocation, with a 75-second worker deadline. Page requests only read saved results. A versioned cache includes post text and all linked tickers, shared across users. Per-job leases prevent concurrent duplicate purchases. Administrative voices receive priority.

Enable with SENTIMENT_AI_ENABLED=true. Authentication uses AI_GATEWAY_API_KEY or Vercel OIDC. SENTIMENT_AI_MONTHLY_USD defaults to 10 and cannot exceed $10 in this implementation. Each attempt reserves $0.03 before requesting the model; reported cost replaces the reservation. Unknown costs retain the reservation. The cap covers this worker, not other uses of the team's AI Gateway balance. Keep automatic credit purchases off in Vercel.

Before deploying to an existing database, run backend.context_sentiment.migrate with the service database connection. It creates ai_sentiment and ai_sentiment_spend. Store model responses, usage and validated interpretations for inspection. Never commit credentials or production environment files.

Validation checks ticker coverage, allowed labels and source excerpts. Invalid responses stay pending/delayed, with no keyword fallback. Retries wait an hour and stop after three attempts; provider failures pause the worker globally for an hour. Low-confidence or missing context remains unclear. Admin > AI sentiment exposes queue and spending status.

The ranking sample still requires 20 independent authors with classifiable language before showing percentages. Mixed/unclear/pending posts do not satisfy that threshold. Counts measure attention, separately from AI interpretation of the collected sample.

Validation: 44 backend regression tests; six synthetic contextual examples passed an initial smoke evaluation, which is not an accuracy benchmark. Real-post outputs require continued review, especially quoted opinions, sarcasm and mixed time horizons.

The logged-out carousel contains six explicitly labeled illustrative scenarios, not customer endorsements. It pauses on hover/focus or its button and respects reduced-motion preferences.

Operational alerts: AI_ALERT_EMAIL enables hourly Gateway credit checks and owner email warnings at 80% monthly use, monthly exhaustion, balance <= $2, or provider/access problems. Resend delivery uses stable idempotency keys; successful budget alerts deduplicate monthly and credit/provider alerts daily. Failed sends retry on the next hourly check. Admin status displays the last balance check and email outcome. No automatic top-up is enabled.

Workspace sections and informational dialogs now have browser paths. Vercel rewrites the explicit application paths to the frontend index; APIs and static assets retain their existing routing.
