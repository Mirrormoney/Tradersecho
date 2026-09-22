# Research inbox pilot

Primary address: researchimport@tradersecho.com (United Domains).
IMAP: imaps.udag.de:993 with verified TLS, username tradersecho-com-0003.
Save RESEARCH_IMAP_PASSWORD as a Production secret in Vercel; never in source control.

Five-minute /api/cron/research worker reads INBOX with BODY.PEEK and read-only selection. It imports up to three previously unseen messages per run within the last30days. No mark-read, move, deletion, remote URL fetching, or auto-publication.

PDF content hashes deduplicate attachments. Up to12MB/100pages/48KB extracted text per document; oversize, encrypted or scanned reports require manual review. Only selectable text is analyzed; figures/images are not interpreted. Extracted text is stored privately in the database; original PDFs remain in the mailbox. No automatic deletion/retention job is enabled.

Administration > research inbox lists imported PDFs. Analyze queues a report for the next worker. GPT-5 mini via the existing Vercel AI Gateway produces structured drafts. One AI call per queued document, no automatic paid retry after an ambiguous or invalid response. The existing AI ledger enforces the shared10USD monthly ceiling; research has an additional2USD pilot cap and reserves0.25USD per call. Exact source quote, page, ticker-universe and date checks gate draft creation. Draft stock links are visible only to staff in stock details. Report dates rather than email dates sort results. Human review remains necessary, including correctness of financial tables and dates.

The older Resend pilot address research@zpataa.resend.app remains a separate tested receiving destination, not part of this IMAP pipeline.

Prescreen: token-free sector-title plus selectable-text matching before AI budget reservation. Healthcare/biotech/consumer/retail reports with no detected active ticker or company name are screened_out at import. Broad or uncertain extractions remain eligible. Common prose abbreviations require explicit ticker notation or company-name evidence. This heuristic may miss aliases/image-only references; admins can Analyze anyway to override. Already analyzed historical reports retain their results and costs.
