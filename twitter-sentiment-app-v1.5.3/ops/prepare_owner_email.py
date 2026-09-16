"""Prepare an owner-only test from a stored report. Never sends email."""
import json
import os
import sys
import time
from html import escape
from pathlib import Path

from dotenv import load_dotenv
import psycopg

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env.local')
sys.path.insert(0, str(ROOT))


def render(report):
    if not report.get('ready') or not report.get('rows'):
        raise ValueError('A complete report is required')
    heading = f"Your daily market pulse | {report['date']} UTC"
    lines = ['TRADERSECHO — TEST REPORT', heading,
             f"Most-mentioned stocks across {report['tracked_stocks']} tracked names.",
             'A completed UTC calendar day; changes compare with the previous day.', '']
    rows = []
    for i, row in enumerate(report['rows'][:10], 1):
        change = f"{row['change']:+g}%" if row['change'] is not None else 'No prior mentions'
        lines.append(f"{i}. ${row['ticker']} — {row['mentions']:,} mentions ({change})")
        rows.append('<tr>' + ''.join(f'<td style="padding:12px 8px;border-bottom:1px solid #e5e7eb">{escape(str(x))}</td>'
                    for x in [i, '$'+row['ticker'], f"{row['mentions']:,}", change]) + '</tr>')
    note = report['disclosure'] + ' Not investment advice.'
    footer = 'This one-time test was requested by the account owner. Automatic newsletter delivery is not enabled. Questions or feedback: info@tradersecho.com.'
    url = 'https://tradersecho-preview-sven-mais-projects.vercel.app/'
    lines.extend(['', note, '', 'Open your private preview: '+url, '', footer])
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#f3f5f4;font-family:Arial,sans-serif;color:#172723">
<table role="presentation" width="100%"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" style="max-width:620px;width:100%;background:white;border-radius:16px"><tr><td style="padding:32px">
<p style="color:#168565;font-weight:bold;letter-spacing:2px">TRADERS ECHO</p><p style="font-size:12px;color:#66746e">OWNER PREVIEW · TEST EMAIL</p>
<h1 style="font-size:28px">Your daily market pulse</h1><p>{escape(report['date'])} · Completed UTC day</p>
<p>The ten most-mentioned stocks across <strong>{report['tracked_stocks']} tracked names</strong>. Changes compare with the previous UTC day.</p>
<table style="width:100%;border-collapse:collapse;text-align:left;font-size:14px"><thead><tr><th>#</th><th>Stock</th><th>Mentions</th><th>Change</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<p style="padding:16px;background:#eef7f2;line-height:1.6">{escape(note)}</p>
<p><a href="{url}" style="display:inline-block;background:#167d60;color:white;padding:14px 20px;border-radius:8px;text-decoration:none">Open Tradersecho</a></p>
<p style="font-size:12px;color:#67746e;line-height:1.6">{escape(footer)}</p>
</td></tr></table></td></tr></table></body></html>'''
    return {'subject': f"[Test] Tradersecho daily briefing — {report['date']}", 'html': html, 'text': '\n'.join(lines)}


if __name__ == '__main__':
    out = Path(sys.argv[1])
    with psycopg.connect(os.getenv('APP_DATABASE_URL') or os.environ['DATABASE_URL']) as c:
        c.execute('SET LOCAL search_path TO public')
        owner = c.execute("SELECT email FROM accounts WHERE role='owner' AND status='active'").fetchall()
        if len(owner) != 1:
            raise ValueError('Exactly one active owner required')
        row = c.execute('SELECT payload FROM daily_briefings ORDER BY window_end DESC LIMIT 1').fetchone()
        if not row:
            raise ValueError('No completed report available')
        report = json.loads(row[0])
    if not 0 <= time.time()-report['window_end'] <= 36*3600:
        raise ValueError('Report is stale or future-dated')
    payload = {'from': 'Tradersecho <newsletter@tradersecho.com>', 'to': [owner[0][0]],
               'reply_to': 'info@tradersecho.com', **render(report)}
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    out.with_suffix('.html').write_text(payload['html'], encoding='utf-8')
    print(json.dumps({'recipient': payload['to'], 'subject': payload['subject'], 'stocks': report['tracked_stocks'], 'preview': str(out.with_suffix('.html'))}))
