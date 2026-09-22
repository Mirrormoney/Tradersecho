# SEC analysis validation plan

Status: proposal only; public badges and daily highlight tiles remain disabled. Current ingestion stores submission metadata and links, not document text. Existing X-post sentiment validation does not validate filing analysis.

## Initial scope
Fetch the primary document and relevant earnings exhibits for selected 8-K/6-K updates in the covered universe, respecting SEC access rules. Preserve accession, acceptance time, amendment relationship, document hash and exact supporting excerpts. Parse structured financial facts where available, with units, period and amendment provenance. Do not infer content from filing form or title alone.

## Output
Separate impact (bullish, bearish, neutral, mixed, unclear) from materiality (routine or potentially important). Hot means important news, not a prediction of a price increase. Explain the changed fact, evidence, caveats and missing comparison data. No earnings-beat claims without licensed consensus data; no fair-value claims from sentiment alone. Treat document content as untrusted data, never model instructions.

## Private validation before release
Use a balanced manually reviewed set covering positive guidance, negative guidance, dilution, debt/refinancing, routine disclosures, mixed earnings, amendments and missing exhibits. Include numeric/unit/period traps. Verify every excerpt exists in its source; independently validate extracted numbers and arithmetic. Report classification agreement by category, abstentions, unsupported claims, latency and actual cost. A model's confidence alone is not validation. Failed, incomplete or contradictory analyses stay unlabelled. Define release acceptance thresholds before evaluating an unseen holdout; human review the first live highlights.

## Daily tiles after validation
At most three qualified current-day filings, using America/New_York acceptance dates and DST-aware daily boundaries. Deduplicate amendments/events and avoid three tiles from the same company. Rank materiality separately from positive impact; make the section title match the selection rule. Empty or fewer than three is legitimate. At midnight start the new day's selection without deleting historical filings or analysis; never carry yesterday's tiles forward as today's. Source link and Why this label on every tile.

## Cost and operation
Use the existing shared AI budget ceiling of $10/month unless the owner explicitly raises it. Reserve budget before calls and cache once per document hash/model version across users. Pilot a bounded document sample before committing to throughput. Do not reprocess the entire filing archive or spend on page views. Use separate queue/leases, bounded retries, provider failure handling and monitoring. No public API resale or low-latency claims until measured and supported.
