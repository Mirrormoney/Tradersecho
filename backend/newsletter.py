"""Branded daily newsletter renderer shared by admin previews and owner tests.
No delivery side effects. Inline PNG logo avoids protected/remote image requests.
"""
from .email_brand import LOGO, header as brand_header
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from html import escape
from urllib.parse import urlsplit, urlencode

# Small PNG version of the existing pulse mark, generated from its line geometry.

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
    preheader=f"Your {date} briefing: attention leaders, your watchlist and collected voices."
    def change(row,period=None):
        return f"{row['change']:+g}% vs prior {period or report.get('period_label','day')}" if row.get('change') is not None else 'Comparison unavailable · history building'
    def stock(row,index):
        return f'''<tr><td style="padding:17px 0;border-bottom:1px solid #dde5df;width:32px;vertical-align:top;color:#77877e;font-size:12px">{index:02}</td><td style="padding:14px 8px 14px 0;border-bottom:1px solid #dde5df"><a href="{e(link('market',row['ticker']))}" style="color:#123e33;text-decoration:none;font-size:18px;font-weight:bold">${e(row['ticker'])}</a><div style="font-size:12px;color:#64766c;margin-top:5px">{e(row['name'])}</div></td><td style="padding:14px 0;border-bottom:1px solid #dde5df;text-align:right;vertical-align:top"><strong style="font-size:18px;color:#123e33">{row['mentions']:,}</strong><div style="font-size:11px;color:#52695b;margin-top:5px">{e(change(row))}</div></td></tr>'''
    table=lambda items: '<table role="presentation" width="100%" cellspacing="0" cellpadding="0">'+''.join(stock(r,i) for i,r in enumerate(items,1))+'</table>'
    intro=f"Hi {name or 'there'}, here’s your AI supply-chain roundup. A little context to help you decide what deserves a closer look."
    lead_card=(f'''<p style="color:#adc5b8;font-size:13px;margin:20px 0 8px">{e(lead['name'])}</p><p style="font-size:48px;letter-spacing:-2px;line-height:1.1;margin:0;color:#c4f27a;font-weight:bold">{lead['mentions']:,}<span style="font-size:14px;letter-spacing:0;font-weight:normal;color:#dce8df"> mentions</span></p><p style="font-size:13px;color:#dce8df;margin:12px 0 0">{e(change(lead))} · completed UTC day</p>''' if lead else '<p style="color:#dce8df">No stocks from your watchlist appear in this report. Add a tracked stock or switch off watchlist-only in your preferences.</p>')

    def feature(r,i,window):
        light=window['label']=='24 hours' and len(report.get('focus_windows',[]))>1
        bg,fg,muted,accent=('#e3ecd9','#193f36','#45634f','#285944') if light else ('#183d30','#f4f8ec','#c1d2c6','#c4f27a')
        post=None;take=''
        if post and str(post.get('id','')).isdigit():
            def stamp(zone):
                return datetime.fromtimestamp(post['ts'],ZoneInfo(zone)).strftime('%d %b · %H:%M %Z')
            author=str(post.get('author') or '').strip().lstrip('@')
            author='@'+author if author and not author.isdigit() else 'X User'
            excerpt=post['text'][:180]+('…' if len(post['text'])>180 else '')
            take=f'''<div style="margin-top:18px;padding-top:15px;border-top:1px solid #789c87"><p style="color:{accent};font-size:11px;letter-spacing:1px;margin:0 0 10px">X TAKE</p><p style="color:{fg};font-size:13px;line-height:1.6;margin:0 0 12px">{e(excerpt)}</p><p style="color:{fg};font-size:12px;margin:0 0 6px">{e(author)}</p><p style="color:{muted};font-size:11px;line-height:1.5;margin:0 0 12px">{e(stamp('America/New_York'))}<br>{e(stamp('Europe/Berlin'))}</p><a href="https://x.com/i/web/status/{e(post['id'])}" style="color:{accent};font-size:12px">View on X →</a></div>'''
        return f'''<td class="top-stock" width="33.33%" valign="top" style="width:33.33%;padding:0 4px 12px"><div style="padding:22px 16px;background:{bg};border-radius:12px;overflow-wrap:anywhere"><p style="color:{muted};font-size:11px;margin:0 0 16px">{e(window['label'].upper())} / {i:02}</p><a href="{e(link('market',r['ticker']))}" style="font-size:25px;color:{accent};font-weight:bold;text-decoration:none">${e(r['ticker'])}</a><p style="font-size:12px;line-height:1.5;min-height:38px;color:{fg}">{e(r['name'])}</p><strong style="color:{fg};font-size:24px">{r['mentions']:,}</strong><p style="color:{muted};font-size:11px;margin:5px 0 12px">{'3-hour' if window['label']=='Intraday' else e(window['label'])} mentions</p><p style="color:{accent};font-size:12px;line-height:1.5">{e(change(r,window['period_label']))}</p>{take}</div></td>'''
    focus_windows=report.get('focus_windows') or [{'label':report.get('period_label','24 hours'),'period_label':report.get('period_label','day'),'rows':rows[:3]}]
    top_cards=''
    for window in focus_windows[:1]:
        cards=''.join(feature(r,i,window) for i,r in enumerate(window['rows'][:3],1))
        if not cards:cards='<td style="padding:18px;color:#64766c;font-size:13px">Fresh Intraday coverage is not available for this edition. The verified longer-window leaders are below.</td>'
        top_cards+=f'''<h2 style="font-size:21px;color:#123e33;margin:24px 0 12px">In focus · {e(window['label'])}</h2><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="table-layout:fixed"><tr>{cards}</tr></table>'''
        if window.get('coverage_label'):top_cards+=f'<p style="font-size:12px;line-height:1.6;color:#64766c">{e(window["coverage_label"])}</p>'
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
    if report.get('focus_windows'):
        collected=[];seen=set()
        for window in report['focus_windows'][:1]:
            for row in window['rows']:
                post=row.get('featured_post')
                if post and str(post.get('id','')).isdigit() and post['id'] not in seen:
                    collected.append({**post,'ticker':row['ticker']});seen.add(post['id'])
        voice_html=''
        for p in collected:
            author=str(p.get('author') or '').lstrip('@')
            author='@'+author if author and not author.isdigit() else 'X User'
            stamp=' / '.join(datetime.fromtimestamp(p['ts'],ZoneInfo(z)).strftime('%d %b · %H:%M %Z') for z in ['America/New_York','Europe/Berlin'])
            voice_html+=f'<div style="padding:22px 24px;background:#edf3eb;margin:12px 0;border-left:3px solid #84a35b;border-radius:8px"><strong style="font-size:13px;color:#123e33">{e(author)} · ${e(p["ticker"])}</strong><p style="font-size:11px;color:#64766c">{e(stamp)}</p><p style="font-size:14px;line-height:1.7;color:#344d40">{e(p["text"][:300])}{"…" if len(p["text"])>300 else ""}</p><a href="https://x.com/i/web/status/{e(p["id"])}" style="font-size:12px;color:#285e46">Read the original on X →</a></div>'
        heading='Today’s collected takes.' if report.get('edition') in ('morning','final') else 'Collected takes · '+report.get('period_label','')
        voice_html=f'<h2 style="font-size:23px;color:#123e33;margin:30px 0 8px">{e(heading)}</h2>'+ (voice_html or '<p style="font-size:13px;color:#64766c">No qualifying collected takes for these leaders in this edition.</p>')
    research_html=''
    for item in report.get('latest_research',[])[:3]:
        firm=e(item.get('firm') or '')
        research_html+=f'<div style="padding:22px 24px;margin:12px 0;background:#f0f3e5;border:1px solid #dce5d4;border-radius:10px"><strong style="font-size:20px;color:#123e33">${e(item["ticker"])}</strong><p style="font-size:11px;color:#365c43">{firm}{" · " if firm else ""}{e(item["report_date"])}</p><p style="font-size:14px;line-height:1.75;color:#344d40;margin:14px 0 16px">{e(item["summary"])}</p><a href="{e(link("research",item["ticker"]))}" style="font-size:12px;font-weight:bold;color:#285e46">Explore ${e(item["ticker"])} research →</a></div>'
    if research_html:research_html='<h2 style="font-size:23px;color:#123e33;margin:32px 0 8px">Latest trending research</h2><p style="font-size:12px;color:#64766c">Broker notes published today.</p>'+research_html
    windows_html=''
    for window in report.get('other_windows',[]):
        windows_html+=f'<h2 style="font-size:24px;color:#123e33;margin:32px 0 12px">{e(window["label"])} Market pulse</h2><p style="font-size:12px;line-height:1.7;color:#64766c">{e(window["coverage_label"])}</p>'
        for i,r in enumerate(window['rows'][:10],1):
            delta=f"{r['change']:+g}% vs previous {window['label']}" if r.get('change') is not None else 'Comparison unavailable · history building'
            windows_html+=f'<div style="padding:16px 20px;margin:8px 0;background:#edf3eb;border-radius:8px;color:#244b37"><strong>{i:02} / ${e(r["ticker"])} · {r["mentions"]:,} mentions</strong><p style="font-size:12px;margin:8px 0 0">{e(r["name"])} · {e(delta)}</p></div>'
    footer='Design preview / owner test. No subscription was started by this preview.' if preview else 'You opted in to Traders Echo research emails. Manage your editions or unsubscribe below.'
    logo='data:image/png;base64,'+LOGO if preview else 'cid:tradersecho-pulse'
    html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Traders Echo · Daily field notes</title><style>@media(max-width:480px){{.pad{{padding:24px 20px!important}}.headline{{font-size:32px!important}}.top-stock{{display:block!important;width:100%!important;min-width:0!important;box-sizing:border-box!important}}}}</style></head><body style="margin:0;padding:0;background:#e7ede5;font-family:Arial,Helvetica,sans-serif;color:#203b2e"><div style="display:none;max-height:0;overflow:hidden;opacity:0">{e(preheader)}</div><table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:24px 10px"><table role="presentation" width="720" cellspacing="0" cellpadding="0" style="width:100%;max-width:720px;background:#fbfcf8"><tr><td class="pad" style="padding:28px 36px;background:#102b24">{brand_header(preview)}<p style="color:#abc0ad;font-size:10px;letter-spacing:2px;margin:26px 0 8px">{e(report.get('edition_title','DAILY FIELD NOTES'))} / {e(date)}</p><h1 class="headline" style="font-size:40px;line-height:1.08;letter-spacing:-1px;color:#f5f8ee;margin:0 0 20px">Find the signal.<br>Keep your perspective.</h1><p style="color:#dce8df;font-size:14px;line-height:1.7;margin:0">{e(intro)}</p></td></tr><tr><td class="pad" style="padding:28px 36px 24px"><p style="font-size:10px;letter-spacing:2px;color:#637d60;margin:0 0 10px">01 / {scope}</p>{top_cards}<p style="font-size:12px;line-height:1.7;color:#64766c">Coverage: {report['tracked_stocks']:,} tracked AI-related stocks · {e(report.get('coverage_label','24-hour report · compared with the previous UTC day.'))} Ranked by heat: mention volume and acceleration. Attention is not a bullishness score.</p>{voice_html}{research_html}<h2 style="font-size:23px;margin:26px 0 4px;color:#123e33">In focus · {e(report.get("period_label","24 hours"))}</h2>{table(rows) if rows else "<p>No matching watchlist stocks in this report.</p>"}{watch_html}{windows_html}<div style="background:#f0f3e5;padding:20px;margin:28px 0"><p style="font-size:10px;letter-spacing:2px;color:#647352;margin:0 0 8px">KEEP THE CONTEXT</p><p style="font-size:13px;line-height:1.7;margin:0;color:#43553c">{e(report.get('disclosure',''))} Automated sentiment is withheld when evidence is insufficient. We don’t infer a news catalyst from a mention spike.</p></div><table role="presentation" cellspacing="0" cellpadding="0"><tr><td style="background:#c4f27a;border-radius:6px;padding:15px 22px"><a href="{e(link('briefing'))}" style="color:#143b28;font-size:14px;font-weight:bold;text-decoration:none">Open your research workspace →</a></td></tr></table><p style="font-size:12px;color:#64766c;line-height:1.7">Listen to the market. Form your own conviction.</p></td></tr><tr><td class="pad" style="padding:24px 36px;border-top:1px solid #dde5df;font-size:11px;line-height:1.8;color:#6e7f71"><strong style="color:#365644">TRADERS ECHO</strong><br>{e(footer)}<br><a href="{e(link('account'))}" style="color:#365644">Email preferences</a> · <a href="mailto:info@tradersecho.com" style="color:#365644">Contact us</a><br>Sentiment research. Not investment advice.</td></tr></table></td></tr></table></body></html>'''
    if preview:html=html.replace('<a href=', '<a aria-disabled="true" tabindex="-1" data-preview-href=')
    lines=['TRADERS ECHO | DAILY FIELD NOTES',date+' UTC',intro]
    for window in report.get('focus_windows',[])[:1]:
        lines+=['','IN FOCUS / '+window['label'],window.get('coverage_label','')]
        for r in window['rows']:
            lines.append(f"${r['ticker']} | {r['mentions']:,} mentions | {change(r,window['period_label'])} | {link('market',r['ticker'])}")
            p=r.get('featured_post')
            if p:lines.append(f"{p.get('author') or 'X User'}: {p['text'][:180]} | https://x.com/i/web/status/{p['id']}")
    for item in report.get('latest_research',[])[:3]:lines.append(f"Latest trending research | ${item['ticker']} | {item.get('firm','')} | {item['report_date']} | {item['summary']}")
    lines+=['','IN FOCUS / '+report.get('period_label','24 hours')+' / TOP 10']
    for r in rows:lines.append(f"${r['ticker']} | {r['name']} | {r['mentions']:,} mentions | {change(r)} | {link('market',r['ticker'])}")
    if watched and not report.get('watchlist_only'):
        lines+=['','YOUR WATCHLIST']+[f"${r['ticker']}: {r['mentions']:,} mentions ({change(r)})" for r in watched]
    if posts and not report.get('focus_windows'):lines+=['','FOLLOWED VOICES']+[f"@{p['author']}: {p['text'][:300]}\nhttps://x.com/i/web/status/{p['id']}" for p in posts if str(p.get('id','')).isdigit()]
    for window in report.get('other_windows',[]):
        lines+=[window['label']+' Market pulse',window['coverage_label']]+[f"${r['ticker']}: {r['mentions']:,} mentions" for r in window['rows'][:10]]
    lines+=['',report.get('disclosure',''),'Not investment advice.','Open your briefing: '+link('briefing'),'Email preferences: '+link('account'),footer,'Help: info@tradersecho.com']
    return {'subject':report.get('subject') or f"[Test] Traders Echo — {date} | "+(f"${lead['ticker']} in focus" if lead else 'Your research briefing'),'html':html,'text':'\n'.join(lines),'attachments':[] if preview else [{'filename':'tradersecho-pulse.png','content':LOGO,'content_id':'tradersecho-pulse','content_type':'image/png'}]}
