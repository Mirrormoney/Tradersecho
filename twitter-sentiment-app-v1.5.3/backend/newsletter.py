"""Branded daily newsletter renderer shared by admin previews and owner tests.
No delivery side effects. Inline PNG logo avoids protected/remote image requests.
"""
import base64
from datetime import datetime,timezone
from html import escape
from urllib.parse import urlsplit, urlencode

# Small PNG version of the existing pulse mark, generated from its line geometry.
LOGO = 'iVBORw0KGgoAAAANSUhEUgAAAGAAAABgCAIAAABt+uBvAAACb0lEQVR4nO3cwU0DMRAF0JTgIrjRARI1UAE3TpRAEVxphwMVpQJWWikgsjMe79p/vsOX5oKEgvdlvr1rJ5zK/Z3KqVP6CMhLQAISkIAERFwCEpCABCQg4hKQgAQkIAERl4AEJKDbBHp9f7pUugId0Mfny9f57VLLj+kQREBLy/zWWYu2jxKA/rQPeRMlAF3rrJVuQQG0mS/mlKGBNvMloJ+ydGhTBgVy8rXW4/NDukgmkJMv2pRBgXwdzsUeB1TNF+c0hAOq5oszZTigiA5hykBAwXwRpgwEFMwX4WIPArLSxD8NIYCsfDm5S3eBAlmd4tilu0CBnNXKaa50GhBQlYB8sR8O5OQr+As3DlRtEPKUjQUKXvz/BQrGh3mxHwsUnICtRmO4pR4IFJ9cFgjalEWB1jNiKwtNtfn6uxf7HQNrOu8OATU9avplXfO+xf7IwIK3WnWgXo3jp2bHYn98YJE+QgM5f6j1fT7e13RAflc3pcya1+cG8gfUtNh3GVUfoC7NXG0fpyk2LwMwngagcmyZjy+r1iv0zVf/ZR5Wwf0zq6NH3HnPARR5uL12vEEg6+ITt0fogHZvsA16sqUD8hvEmp7HbdHSARV3/wy//TgN0Joy5PTMC9R60Dj0CIQRqPU+cOjGIyNQaXySGDoSUqD409/obVlSoPhz3+iNfVKgEksZ4ISaFyiSMsCxBy9QJGWAYfACVRd7zCdAeIFKbRrCnLtSA/kpw4xhViDYqTQ1ULFTBvtcAztQ+hdc2YHSvyLNDlSyv2Q/AVBJ/TcNcwAlloAEJCABCYi4BCQgAQlIQMQlIAEJSEACIi4BVeobFFvVJvdJcUMAAAAASUVORK5CYII='

def e(value):
    return escape(str(value), quote=True)

def render(report, name='there', origin='https://tradersecho.com', preview=False):
    if not report.get('ready'):
        raise ValueError('A complete, current report is required; never substitute invented data.')
    url=urlsplit(origin)
    if url.scheme not in ('https','http') or not url.netloc or url.username or url.password:
        raise ValueError('A valid website origin is required')
    origin=url.scheme+'://'+url.netloc
    def link(page,ticker=None):
        return origin+'/?'+urlencode({'view':page,**({'ticker':ticker} if ticker else {})})
    rows=report.get('rows',[])[:10]
    watched=report.get('watchlist',[])[:5]
    posts=report.get('posts',[])[:6]
    scope='YOUR WATCHLIST' if report.get('watchlist_only') else 'THE MARKET CONVERSATION'
    date=report['date']
    lead=rows[0] if rows else None
    headline=f"${lead['ticker']} leads your watchlist." if lead and report.get('watchlist_only') else f"${lead['ticker']} leads the conversation." if lead else 'A quieter page in your research.'
    preheader=f"Your {date} briefing: attention leaders, your watchlist and collected voices."
    def change(row):
        return f"{row['change']:+g}% vs prior day" if row.get('change') is not None else 'No prior-day mentions'
    def stock(row,index):
        return f'''<tr><td style="padding:17px 0;border-bottom:1px solid #dde5df;width:32px;vertical-align:top;color:#77877e;font-size:12px">{index:02}</td><td style="padding:14px 8px 14px 0;border-bottom:1px solid #dde5df"><a href="{e(link('market',row['ticker']))}" style="color:#123e33;text-decoration:none;font-size:18px;font-weight:bold">${e(row['ticker'])}</a><div style="font-size:12px;color:#64766c;margin-top:5px">{e(row['name'])}</div></td><td style="padding:14px 0;border-bottom:1px solid #dde5df;text-align:right;vertical-align:top"><strong style="font-size:18px;color:#123e33">{row['mentions']:,}</strong><div style="font-size:11px;color:#52695b;margin-top:5px">{e(change(row))}</div></td></tr>'''
    table=lambda items: '<table role="presentation" width="100%" cellspacing="0" cellpadding="0">'+''.join(stock(r,i) for i,r in enumerate(items,1))+'</table>'
    intro=f"Hi {name or 'there'}, here’s your daily field note. A little context to help you decide what deserves a closer look."
    lead_card=(f'''<p style="color:#adc5b8;font-size:13px;margin:20px 0 8px">{e(lead['name'])}</p><p style="font-size:48px;letter-spacing:-2px;line-height:1.1;margin:0;color:#c4f27a;font-weight:bold">{lead['mentions']:,}<span style="font-size:14px;letter-spacing:0;font-weight:normal;color:#dce8df"> mentions</span></p><p style="font-size:13px;color:#dce8df;margin:12px 0 0">{e(change(lead))} · completed UTC day</p>''' if lead else '<p style="color:#dce8df">No stocks from your watchlist appear in this report. Add a tracked stock or switch off watchlist-only in your preferences.</p>')

    def feature(r,i):
        return f"""<div class="top-stock" style="display:inline-block;vertical-align:top;width:31%;min-width:145px;margin:0 1% 12px 0;background:#183d30;border-radius:12px"><div style="padding:18px 12px"><p style="color:#adc5b8;font-size:11px;margin:0 0 16px">IN FOCUS / {i:02}</p><a href="{e(link('market',r['ticker']))}" style="font-size:27px;color:#c4f27a;font-weight:bold;text-decoration:none">${e(r['ticker'])}</a><p style="font-size:12px;line-height:1.5;min-height:38px;color:#eef4e8">{e(r['name'])}</p><strong style="color:white;font-size:24px">{r['mentions']:,}</strong><p style="color:#adc5b8;font-size:11px;margin:5px 0 12px">ticker mentions</p><p style="color:#c4f27a;font-size:12px;line-height:1.5">{e(change(r))}</p><a href="{e(link('market',r['ticker']))}" style="color:#eef4e8;font-size:12px">Explore the signal →</a></div></div>"""
    top_cards=''.join(feature(r,i) for i,r in enumerate(rows[:3],1))
    rest_cards=''.join(f"""<div style="background:#edf3eb;border:1px solid #dce6da;border-radius:10px;padding:18px;margin:10px 0"><span style="font-size:12px;color:#71866e">{i:02} / </span><a href="{e(link('market',r['ticker']))}" style="font-size:20px;font-weight:bold;color:#163d30;text-decoration:none">${e(r['ticker'])}</a><p style="font-size:12px;color:#617562;margin:7px 0">{e(r['name'])}</p><p style="font-size:14px;color:#244b37;margin:0"><strong>{r['mentions']:,}</strong> mentions · {e(change(r))}</p></div>""" for i,r in enumerate(rows[3:],4))

    watch_html=('<h2 style="font-size:23px;color:#123e33;margin:30px 0 8px">Closer to your conviction.</h2><p style="color:#64766c;font-size:13px">From your saved watchlist.</p>'+table(watched)) if watched and not report.get('watchlist_only') else ''
    voice_html=''
    for p in posts:
        if not str(p.get('id','')).isdigit():continue
        published=datetime.fromtimestamp(p['ts'],timezone.utc).strftime('%d %b %Y · %H:%M UTC') if p.get('ts') else 'Publication time unavailable'
        excerpt=p['text'][:300]+('…' if len(p['text'])>300 else '')
        voice_html+=f'''<div style="padding:18px;background:#edf3eb;margin:12px 0;border-left:3px solid #84a35b"><strong style="font-size:13px;color:#123e33">@{e(p['author'])}</strong><span style="font-size:12px;color:#64766c"> · {e(' / '.join('$'+t for t in (p.get('tickers') or '').split(',') if t))}</span><p style="font-size:11px;color:#64766c">{e(published)}</p><p style="font-size:14px;line-height:1.7;color:#344d40;white-space:pre-line">{e(excerpt)}</p><a href="https://x.com/i/web/status/{e(p['id'])}" style="font-size:12px;color:#285e46">Read the original on X →</a></div>'''
    if voice_html:voice_html=f'<h2 style="font-size:23px;color:#123e33;margin:30px 0 8px">Today’s collected takes.</h2><p style="color:#64766c;font-size:13px">{e(report.get('post_date',report['date']))} UTC · Posted since midnight UTC and linked to the top three. Ranked by likes, newest first on ties; one per author. Not endorsements.</p>'+voice_html
    if not voice_html:voice_html=f'<h2 style="font-size:23px;color:#123e33">Today’s collected takes.</h2><p style="font-size:13px;color:#64766c">{e(report.get("post_date",report["date"]))} UTC · No qualifying posts collected for these leaders since midnight UTC. Yesterday’s posts are not reused. Check Tracked voices for updates.</p>'
    footer='Design preview / owner test. Automatic newsletter delivery is off. No subscription was started by this preview.'
    logo='data:image/png;base64,'+LOGO if preview else 'cid:tradersecho-pulse'
    html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Traders Echo · Daily field notes</title><style>@media(max-width:480px){{.pad{{padding:24px 20px!important}}.headline{{font-size:32px!important}}.top-stock{{width:100%!important;min-width:0!important}}}}</style></head><body style="margin:0;padding:0;background:#e7ede5;font-family:Arial,Helvetica,sans-serif;color:#203b2e"><div style="display:none;max-height:0;overflow:hidden;opacity:0">{e(preheader)}</div><table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:24px 10px"><table role="presentation" width="600" cellspacing="0" cellpadding="0" style="width:100%;max-width:600px;background:#fbfcf8"><tr><td class="pad" style="padding:28px 36px;background:#102b24"><table role="presentation" cellspacing="0" cellpadding="0"><tr><td><img src="{logo}" alt="Traders Echo pulse logo" width="36" height="36" style="display:block;border:0"></td><td style="padding-left:10px;font-size:23px;font-weight:bold;color:#f5f8ee">traders<span style="color:#c4f27a">echo</span></td></tr></table><p style="color:#abc0ad;font-size:10px;letter-spacing:2px;margin:26px 0 8px">DAILY FIELD NOTES / {e(date)} UTC</p><h1 class="headline" style="font-size:40px;line-height:1.08;letter-spacing:-1px;color:#f5f8ee;margin:0 0 20px">Find the signal.<br>Keep your perspective.</h1><p style="color:#dce8df;font-size:14px;line-height:1.7;margin:0">{e(intro)}</p></td></tr><tr><td class="pad" style="padding:28px 36px 24px"><p style="font-size:10px;letter-spacing:2px;color:#637d60;margin:0 0 10px">01 / {scope}</p><h2 style="font-size:26px;color:#123e33;margin:0 0 18px">{e(headline)}</h2>{top_cards}<p style="font-size:12px;line-height:1.7;color:#64766c">Coverage: {report['tracked_stocks']:,} tracked stocks · 24-hour report · compared with the previous UTC day. Ranked by heat: mention volume and acceleration. Attention is not a bullishness score.</p>{voice_html}<h2 style="font-size:23px;margin:26px 0 4px;color:#123e33">More on the radar · 4–10</h2>{rest_cards if rows else "<p>No matching watchlist stocks in this report.</p>"}{watch_html}<div style="background:#f0f3e5;padding:20px;margin:28px 0"><p style="font-size:10px;letter-spacing:2px;color:#647352;margin:0 0 8px">KEEP THE CONTEXT</p><p style="font-size:13px;line-height:1.7;margin:0;color:#43553c">{e(report.get('disclosure',''))} Automated sentiment is withheld when evidence is insufficient. We don’t infer a news catalyst from a mention spike.</p></div><table role="presentation" cellspacing="0" cellpadding="0"><tr><td style="background:#c4f27a;border-radius:6px;padding:15px 22px"><a href="{e(link('briefing'))}" style="color:#143b28;font-size:14px;font-weight:bold;text-decoration:none">Open your research workspace →</a></td></tr></table><p style="font-size:12px;color:#64766c;line-height:1.7">Listen to the market. Form your own conviction.</p></td></tr><tr><td class="pad" style="padding:24px 36px;border-top:1px solid #dde5df;font-size:11px;line-height:1.8;color:#6e7f71"><strong style="color:#365644">TRADERS ECHO</strong><br>{e(footer)}<br><a href="{e(link('account'))}" style="color:#365644">Email preferences</a> · <a href="mailto:info@tradersecho.com" style="color:#365644">Contact us</a><br>Sentiment research. Not investment advice.</td></tr></table></td></tr></table></body></html>'''
    if preview:html=html.replace('<a href=', '<a aria-disabled="true" tabindex="-1" data-preview-href=')
    lines=['TRADERS ECHO | DAILY FIELD NOTES',date+' UTC',intro,'',headline]
    for r in rows:lines.append(f"${r['ticker']} | {r['name']} | {r['mentions']:,} mentions | {change(r)} | {link('market',r['ticker'])}")
    if watched and not report.get('watchlist_only'):
        lines+=['','YOUR WATCHLIST']+[f"${r['ticker']}: {r['mentions']:,} mentions ({change(r)})" for r in watched]
    if posts:lines+=['','FOLLOWED VOICES']+[f"@{p['author']}: {p['text'][:300]}\nhttps://x.com/i/web/status/{p['id']}" for p in posts if str(p.get('id','')).isdigit()]
    lines+=['',report.get('disclosure',''),'Not investment advice.','Open your briefing: '+link('briefing'),'Email preferences: '+link('account'),footer,'Help: info@tradersecho.com']
    return {'subject':f"[Test] Traders Echo — {date} | "+(f"${lead['ticker']} in focus" if lead else 'Your research briefing'),'html':html,'text':'\n'.join(lines),'attachments':[] if preview else [{'filename':'tradersecho-pulse.png','content':LOGO,'content_id':'tradersecho-pulse','content_type':'image/png'}]}
