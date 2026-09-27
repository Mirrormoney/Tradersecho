# AI Insights roadmaps

Seven source-dated guides combine curated historical milestones, future expectations,
supplier exposure, glossary terms and questions that test the commercial thesis.
The existing October 1 launch and server-side Pro gates still apply.

## Automatic updates

- Incoming research can contribute up to eight evidence-checked topic developments,
  including sector notes without a covered stock finding.
- `/api/cron/insights` runs at minute 23 each hour. Each run checks at most one public
  newsroom (each newsroom at most daily) and analyses at most three saved items.
- It gradually revisits saved `draft`, `published` and `no_match` research excerpts.
  It does not claim to reread pages absent from the stored extraction or recover
  unreadable PDFs. Skipped/uncertain items are not automatically charged twice.
- Public news and archive research share the existing $15 research allowance within
  the $20 total AI ceiling. Page visits never generate AI requests.
- Admins can run a bounded check from AI Insights. A ten-minute shared cooldown
  and atomic item claims prevent overlapping manual/cron runs from duplicating work.

## Source coverage

NVIDIA and TrendForce HTML article discovery and date extraction were verified.
Coherent, Lumentum, AXT and Vertiv newsrooms are attempted daily but some returned
timeouts or no static article links during commissioning. Their curated source
entries remain available; no complete automatic coverage is claimed. Public source
fetches use a fixed hostname/path allowlist, reject redirects and cap response size.
No paywalls are bypassed. There is no independent DigiTimes or rumours subscription.
Rumours contained in supported research must retain explicit unconfirmed labels.

## Evidence and history

Publication dates and target windows are distinct. A passed forecast is labelled
as needing confirmation, never silently changed into a completed milestone.
Exact source passages and numeric checks validate extracted developments; those
private passages and PDF filenames are never returned in the article response.
This validates source support, not the truth of a broker's prediction.
Older backfill cannot overwrite a newer beneficiary relationship. Original forecasts
remain visible alongside revisions. Duplicate passages are collapsed.

Article responses are cached in memory for five minutes, then assembled from bounded
queries. Completed public-source raw text is discarded; analysis and provenance are
retained. Existing research imports, stock summaries and original documents are unchanged.

## Validation

September 27: 52 focused tests passed, frontend build passed, PostgreSQL article assembly
checked for all seven topics. Unauthenticated topic detail returns 401; production is
public and preview/generated deployment URLs retain Vercel protection.
