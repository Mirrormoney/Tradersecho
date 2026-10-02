# Private AI Industry Radar pilot

Owner authorization: October 2, 2026, additional USD20 per calendar month. This budget is isolated from existing sentiment and research allowances; no credit purchases are automated.

Admin tab: industry radar. Both data and manual-run endpoints require staff. Native production cron: /api/cron/industry-radar, every five minutes at minute 4 modulo 5. Preview collection is disabled. Two sources rotate each tick (roughly twenty-minute source cadence); at most two unseen links per source and one two-pass analysis per tick. Manual checks share a four-minute cooldown.

Initial topics: memory/HBM, optical networking, advanced packaging. Active stock universe is supplied to the analysis. Source-backed direct company mentions and conditional inferred business effects are distinct. Each company link must cite a supplied passage establishing the exposure. No comprehensive supplier graph is claimed in this pilot. Comparisons use at most five related saved evidence records from the latest eighty completed analyses; novelty means new to this limited archive, not new to the market.

Completed imported research from both Drive and email enters via research_documents, at most twelve records per tick from the last fourteen days. Imports remain read-only and use extracted text already available. Raw public article text is discarded after analysis. PDFs, research evidence and all pilot results stay private. No writes to public research, Insights timelines or Catalyst scores.

Sources: TrendForce research/news, The Elec, ETNews, NVIDIA, SK hynix, Coherent, Lumentum. Every source respects robots.txt; requests are restricted to fixed HTTPS hosts/paths, reject redirects and have time/size bounds. Source failures stay visible. Commissioning found usable listing links at TrendForce, The Elec and NVIDIA; other sources require further access/extraction work. Partial coverage is intentional and displayed.

Budget uses radar_spend, separate from ai_sentiment_spend. Atomic admission accounts USD0.25 for an in-flight pair of bounded GPT-5-mini requests. Actual gateway-reported costs replace this immediately, even if evidence validation fails. If a response's cost is unavailable, USD0.25 is retained as an explicitly labelled attempted-cost estimate, not as actual spending or a reservation for future retries. Definitely rejected HTTP requests cost zero. Items are not retried automatically after paid attempts. Authentication/credit/rate-limit errors back off for an hour. Interrupted attempts become skipped and estimated. At USD20 no new analysis starts. Pending items do not reserve funds. Source checks continue.

Verification: focused backend tests cover authorization, allowed URLs, grounded company links, duplicate text, budget admission, two-pass settlement, failure continuation and read-only preview. Browser and production commissioning recorded separately in work/.
