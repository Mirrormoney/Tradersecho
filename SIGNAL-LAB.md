# Tradersecho Signal Lab — agreed definitions, v0.1

Saved September 24, 2026. Private prototype only. Not a production scoring engine.

## Purpose and evaluation
Identify bullish and bearish stock setups over the next trading session. Options are evidence about the underlying stock, not option-trade recommendations. Compare against price/volume-only rules, then test incremental options and X value. Record every eligible signal, forward return, adverse excursion, sector-relative return and estimated transaction costs. Use original availability times, separate training and held-out evaluation, and live forward observation. Do not label a score as a win probability.

## Five agreed indicators
1. Price strength: 40% sector-relative return, 40% market-relative return, 20% VWAP position. Latest 60 trading minutes, adjusted for normal volatility. Overnight gaps separate. Match timestamps and corporate-action adjustments.
2. Volume confirmation: 70% relative volume in the latest 30 minutes versus the median same interval of the previous 20 sessions; 30% persistence across the latest three ten-minute intervals. Use consistent venue coverage. Volume measures participation, not bullishness.
3. Options pressure: 60% estimated bullish/bearish premium balance over 60 minutes; 40% historical unusualness of directional activity. Initial candidate scope: liquid, classifiable single-leg trades with 7–60 days to expiry. Exclude ambiguous direction/structure; no assumption that a call purchase represents unhedged conviction. Unknown/non-optionable is unavailable, not neutral or zero.
4. X conviction: 60% current author-balanced directional sentiment over three hours; 40% shift versus preceding three hours. Confirm company relevance, deduplicate, cap author contribution. Proposed minimum: ten relevant independent authors, at least five directional. Retain neutral/mixed/unclear coverage statistics. Show sample age and budget-limited coverage.
5. Catalyst strength: 40% materiality, 35% evidence quality, 25% freshness. Direction separate. Supported primary disclosures or attributed broker research; deduplicate reports of the same event; use original publication time. Label sector readthrough separately. No catalyst is not proof that there is none.

Weights above are draft starting rules, not validated parameters. Exact feature normalization, thresholds, eligibility, freshness cutoffs and catalyst rubric remain to be implemented and validated. Do not silently treat these descriptions as complete executable specifications.

## Benchmarks agreed with owner
Start with an equal-weight basket of the other eligible covered stocks in the same Tradersecho sector. Label it "versus covered sector peers", never the entire sector. Exclude evaluated stock. Fix membership each trading day, require at least five fresh eligible peers, align time windows. Define missing-price handling before calculations go live; never silently change the basket and create artificial returns. Sector unavailable if insufficient coverage. Broad-market reference candidate: SPY, subject to feed coverage/licensing. Additional external benchmark symbols need explicit scope recording.

Example: stock +1.8%, peers +0.7% -> +1.1 percentage points, not 1.1% relative outperformance.

## Display
Pentagon with five axes; directional support must be labelled (bullish/bearish) and separate from participation/catalyst magnitude. Mixed setup has no qualifying directional conclusion. Raw measurements, source timestamps, evidence and unavailable states accessible per axis. Do not turn missing axes into zeroes or fill a complete polygon when any axis is missing. No overall probability or averaged buy/sell score.

Private preview fixtures are invented and explicitly labelled; no current claims about real tickers. UI preview values are not outputs of a finished scoring engine. Future eligible candidate rules require price direction, elevated volume, options or X confirmation and persistence over two checks. Fresh catalyst strengthens context but is not mandatory. Test all thresholds before release.

## Collection and cost plan
Pilot: 20–30 covered stocks; active top 20 every ten minutes, other eligible covered stocks every thirty minutes during regular US trading; daily slow-moving data; pause routine options polling outside relevant sessions. Schedule in America/New_York with DST. One shared calculation per stock, not per visitor. Store bounded snapshots, not all raw trades.

UW Basic currently advertised $150/month after seven-day trial, 40,000 requests/day. Confirm private commercial evaluation permission and needed price/volume/history coverage before subscribing. No subscription, credentials, budget increase or public release authorized by this document. Initial new-service estimate $150–170/month, with $0–20 incremental hosting allowance (estimate, not cap). Preserve existing X $250/month and AI $20/month ($15 research within total). No automatic purchases. Public display/API distribution requires appropriate provider rights and separate release decision.

## Next gates
1. Try private interactive preview (bullish, bearish, mixed, missing-data examples).
2. Complete exact normalization/eligibility spec and automated boundary tests.
3. Confirm UW evaluation terms; prepare ingestion before activating trial.
4. Connect authorized credentials privately; measure request use and feed coverage.
5. Backtest where point-in-time data is available, then forward-test frozen rules.
6. Choose retained indicators, commercial licence and pricing based on measured evidence.


## Private implementation v0.2 — September 24

Owner-only hosted engine and five-axis inspector are implemented. This is an experimental evaluation product, not a validated customer trading signal. No additional AI calls are made by scoring. Existing collected per-ticker AI labels and published research are reused. An unavailable axis remains null; incomplete polygons are never filled with fabricated neutral scores.

Pilot basket is frozen in `uw_pilot.PILOT`, 20 covered names. Rebalanced to give NVDA/AMD five semiconductor peers and MU five memory/storage peers, without raising the 20-name allowance. It is a selected covered basket, NOT a whole-market benchmark. Constituents used in each computation are saved in the snapshot. At least five sector and ten basket peers with identical candle endpoints are required.

Price: retains 40/40/20 weights, but v0.2 explicitly substitutes the covered basket for a market index and a typical-price-times-volume candle proxy for exact trade VWAP. Each component is scaled by the median absolute same-time 60-minute move over 20 prior observed sessions (floor 0.1 percentage points), clipped to +/-2. Score = clip(50 + 25 * weighted components, 0, 100). Full regular-session candle coverage is required for the proxy. Corporate-action/venue consistency is not independently certified; no public release claim.

Volume: 70% min(100, 50 * relative volume) + 30% (above-median candles / 3 * 100). Twenty complete same-clock historical sessions required. It measures participation, not direction.

Options: complete single-leg 7–60 DTE sample, at least 20 classified trades, fresh within 20 minutes, after the first full regular-session hour. Collect 20 prior comparable NY-clock sessions under this rule version before enabling the axis. Score = 50 + 50 * (0.6 * (bull-bear)/(bull+bear) + 0.4 * min(1,max(0,total/median-1)) * sign(balance)). Partial / rate-limited / ambiguous data is not scored. Forward baselines cannot be manufactured on launch day.

X: one latest classified opinion per author in each nonoverlapping 3h window; exact template duplicates and promotional/irrelevant text removed, unknown authors excluded. Both windows need 10 distinct authors and 5 directional authors. Score = 50 + 50 * (0.6 * current balance + 0.4 * (current-prior balance)/2). Coverage counts retain neutral/mixed/unclear and pending labels. This is the collected sample, not all of X.

Catalysts: published, deduplicated research only, original report date within 7 calendar days. Materiality rubric: direct attributed rating event 70; direct commentary 50; readthrough 25. Source quality: direct original 80, direct relay 60, readthrough 35. Freshness: today 100, yesterday 70, age 2–3 days 40, age 4–7 days 10. Weighted 40/35/25. Direction displayed separately from source's saved stance. These are explicit heuristic evidence scores, not measured earnings impact. SEC metadata alone is NOT an AI-validated catalyst and does not produce a direction score.

Setup: price strength at least 30 (distance from midpoint scaled to 0–100), volume score at least 60, and either options or X strength at least 30 in the same direction. Must persist across two consecutive checks at most 15 minutes apart. Price/volume-only baseline saved separately. Every check is immutable and versioned, including incomplete observations, with original collection times. Same-session one-hour outcomes plus high/low excursion and illustrative 10bp round-trip costs are recorded. These overlapping observations are not independent trades or a backtest. Longer-horizon validation, corporate-action checks, calibration and out-of-sample performance remain release gates.

Operational boundaries: owner-only endpoint, production-only authorized collector, unchanged quota controls. Saved observations retained 90 days; comparable baseline queries bounded to same-time slots from 45 days. UI reads only the latest 30 entries; visitors do not trigger provider or AI requests. Worker evaluation errors are isolated from collection and exposed in diagnostics. The weekday clock guard is not yet an exchange holiday/early-close calendar; source freshness gates block stale scores, but that calendar remains required before customer release. Public distribution still requires appropriate UW rights.
