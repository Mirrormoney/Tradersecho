"""Verified daily briefings and opt-in preferences. External delivery is disabled."""
import json, time, math
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel,Field
from .community import core, staff, audit

router=APIRouter()

def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS daily_briefings(window_end REAL PRIMARY KEY,created_at REAL,payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS digest_preferences(user_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,frequency TEXT NOT NULL DEFAULT 'off',watchlist_only INTEGER NOT NULL DEFAULT 0,updated_at REAL NOT NULL);
    ''')

def build(now=None):
    s=core();now=time.time() if now is None else now
    with s.db() as c:
        snapshot=c.execute("SELECT value FROM meta WHERE key='completed_snapshot'").fetchone()
        if not snapshot:return {'ready':False,'reason':'Waiting for the first complete market snapshot.'}
        end=int(float(snapshot[0]))
        if end>now or now-end>36*3600:return {'ready':False,'reason':'The market snapshot is stale. Collection must finish before a new briefing is prepared.'}
        existing=c.execute('SELECT payload FROM daily_briefings WHERE window_end=?',(end,)).fetchone()
        if existing:return json.loads(existing[0])
        buckets=[dict(r) for r in c.execute('SELECT ticker,start,end,n FROM x_counts WHERE start>=? AND end<=? ORDER BY ticker,start',(end-172800,end))]
    by={}
    for r in buckets:by.setdefault(r['ticker'],[]).append(r)
    catalog=dict(s.CATALOG);expected=list(range(end-172800,end,3600));rows=[]
    for ticker,info in catalog.items():
        history=by.get(ticker,[])
        if [int(r['start']) for r in history]!=expected or any(r['end']-r['start']!=3600 or r['n']<0 for r in history):
            return {'ready':False,'reason':'Waiting for complete 48-hour coverage across the tracked universe. Daily comparisons are withheld.'}
        previous=sum(r['n'] for r in history[:24]);current=sum(r['n'] for r in history[24:])
        rows.append({'ticker':ticker,'name':info[0],'mentions':current,'previous':previous,'change':round((current/previous-1)*100,1) if previous else None})
    if not rows:return {'ready':False,'reason':'The stock universe is empty.'}
    rows.sort(key=lambda r:(-r['mentions'],r['ticker']))
    label=datetime.fromtimestamp(end-1,timezone.utc).strftime('%Y-%m-%d')
    # This is a UTC calendar-day report, not an exchange-close report.
    lines=[f'Tradersecho | {label} UTC','Most-mentioned stocks in our tracked universe:']
    for i,r in enumerate(rows[:3],1):
        change=f"{r['change']:+g}%" if r['change'] is not None else 'no prior mentions'
        lines.append(f"{i}. ${r['ticker']}: {r['mentions']:,} ({change})")
    lines.append('Mention counts; not a buy/sell signal.')
    result={'ready':True,'window_start':end-86400,'window_end':end,'date':label,'created_at':now,'tracked_stocks':len(rows),'rows':rows,'x_draft':'\n'.join(lines),'disclosure':'Mentions measure attention, not sentiment. English cashtag queries exclude reposts. Tracked posts are a capped sample.'}
    with s.db() as c:
        c.execute('INSERT INTO daily_briefings VALUES(?,?,?) ON CONFLICT(window_end) DO NOTHING',(end,now,json.dumps(result)))
        return json.loads(c.execute('SELECT payload FROM daily_briefings WHERE window_end=?',(end,)).fetchone()[0])

def preferences(c,uid):
    row=c.execute('SELECT frequency,watchlist_only,updated_at FROM digest_preferences WHERE user_id=?',(uid,)).fetchone()
    return dict(row) if row else {'frequency':'off','watchlist_only':False,'updated_at':None}

class Preference(BaseModel):
    frequency:Literal['off','weekly','daily','monthly','all']='off'
    watchlist_only:bool=False
    editions:list[Literal['morning','final','weekly','monthly']]|None=Field(default=None,max_length=4)
    trial_reminder:bool=True

@router.get('/api/digest/preferences')
def get_preferences(request:Request):
    u=core().account(request)
    from .newsletter_schedule import choices,enabled
    with core().db() as c:return {**preferences(c,u['id']),**choices(c,u['id']),'delivery_enabled':enabled()}

@router.put('/api/digest/preferences')
def save_preferences(payload:Preference,request:Request):
    u=core().account(request)
    if u['demo']:raise HTTPException(403,'Create a real account to save email preferences.')
    if payload.frequency=='daily' and u['plan']!='premium' and u['role'] not in ('owner','admin'):raise HTTPException(403,'Daily briefings require Premium.')
    with core().db() as c:
        from .newsletter_schedule import choices,enabled,EDITION_NAMES
        editions=list(dict.fromkeys(payload.editions)) if payload.editions is not None else {'daily':['morning','final'],'weekly':['weekly'],'monthly':['monthly'],'all':list(EDITION_NAMES)}.get(payload.frequency,[])
        if editions and u['plan']!='premium' and u['role'] not in ('owner','admin'):raise HTTPException(403,'Research emails require Premium or an active trial.')
        c.execute('INSERT INTO newsletter_preferences VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET editions=excluded.editions,trial_reminder=excluded.trial_reminder',(u['id'],json.dumps(editions),int(payload.trial_reminder)))
        c.execute('INSERT INTO digest_preferences VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET frequency=excluded.frequency,watchlist_only=excluded.watchlist_only,updated_at=excluded.updated_at',(u['id'],payload.frequency,int(payload.watchlist_only),time.time()))
        audit(c,u,'digest_preferences_updated',detail=json.dumps(payload.model_dump()))
    return {**payload.model_dump(),'editions':editions,'delivery_enabled':enabled()}

def personalized(report,u,now=None,preserve_ranking=False):
    if not report.get('ready'):return report
    s=core();premium=u['plan']=='premium' or u['role'] in ('owner','admin')
    ranked=report['rows'] if preserve_ranking else [{**r,'heat':round(math.log1p(r['mentions'])*(1+max(0,math.log2((r['mentions']+5)/(r.get('previous',0)+5))))*10,1)} for r in report['rows']]
    ranked.sort(key=lambda r:(-r['heat'],r['ticker']))
    report={**report,'rows':ranked}
    now=time.time() if now is None else now
    post_start=int(now//86400)*86400
    leaders={r['ticker'] for r in ranked[:3]}
    with s.db() as c:
        watched={r[0] for r in c.execute('SELECT ticker FROM watchlist WHERE user_id=?',(u['id'],))}
        prefs=preferences(c,u['id'])
        if premium and prefs['watchlist_only']:leaders=set(list(r['ticker'] for r in ranked if r['ticker'] in watched)[:3])
        posts=[dict(r) for r in c.execute("SELECT p.id,p.author,p.text,p.ts,p.sentiment,(SELECT GROUP_CONCAT(DISTINCT m.ticker) FROM mentions m WHERE m.post_id=p.id AND m.source=p.source) tickers FROM posts p WHERE p.source='x' AND p.ts>=? AND p.ts<? AND p.author IN (SELECT handle FROM handles WHERE user_id=? UNION SELECT handle FROM admin_voices) ORDER BY p.likes DESC,p.ts DESC LIMIT 100",(post_start,now,u['id']))] if premium else []
    from .post_quality import research_text
    from .screening import fingerprint
    seen=set();authors=set();filtered=[]
    for post in posts:
        fp=fingerprint(post['text'])
        if leaders.intersection((post.get('tickers') or '').split(',')) and not post['text'].lstrip().startswith('@') and research_text(post['text']) and fp not in seen and post['author'] not in authors:
            filtered.append(post);seen.add(fp);authors.add(post['author'])
    posts=filtered[:6]
    selected=[r for r in report['rows'] if r['ticker'] in watched]
    for p in posts:p['url']='https://x.com/i/web/status/'+p['id']
    visible=selected if premium and prefs['watchlist_only'] else report['rows'][:10 if premium else 3]
    from .newsletter_schedule import enabled
    return {**report,'post_window_start':post_start,'post_window_end':now,'post_date':datetime.fromtimestamp(now,timezone.utc).strftime('%Y-%m-%d'),'rows':visible,'watchlist':selected if premium else [],'posts':posts,'personalized':premium,'watchlist_only':bool(premium and prefs['watchlist_only']),'delivery_enabled':enabled()}

@router.get('/api/digest')
def member_briefing(request:Request):
    u=core().account(request)
    return personalized(build(),u)

@router.get('/api/admin/digest')
def admin_briefing(request:Request,edition:Literal['daily','morning','final','weekly','monthly','trial']='morning'):
    u=staff(request);report=build()
    preview=personalized(report,u)
    from .newsletter import render
    from .newsletter_schedule import report_for,enabled
    if edition in ('morning','final','weekly','monthly'):
        try:preview=report_for({'edition':edition,'at':time.time()},u)
        except ValueError as exc:preview={'ready':False,'reason':str(exc)}
    email=render(preview,u['display_name'],core().ORIGIN,preview=True) if preview.get('ready') else {}
    if edition=='trial':
        from .email_brand import trial_reminder
        email=trial_reminder({**dict(u),'trial_ends_at':time.time()+86400},core().ORIGIN,preview=True)
    from .email_delivery import delivery_status
    return {'report':preview,'email_preview':email.get('text',''),'email_html':email.get('html',''),'email_subject':email.get('subject',''),'x_draft':report.get('x_draft',''),'email_enabled':enabled(),'x_enabled':False,'delivery_status':delivery_status(request),'requirements':[],'note':'Preview uses your own watchlist and followed voices. Newsletter delivery is opt-in and follows New York time. X drafts are never published automatically.'}
