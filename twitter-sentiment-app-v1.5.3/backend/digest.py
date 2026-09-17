"""Verified daily briefings and opt-in preferences. External delivery is disabled."""
import json, time
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
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
    frequency:Literal['off','weekly','daily']='off'
    watchlist_only:bool=False

@router.get('/api/digest/preferences')
def get_preferences(request:Request):
    u=core().account(request)
    with core().db() as c:return {**preferences(c,u['id']),'delivery_enabled':False}

@router.put('/api/digest/preferences')
def save_preferences(payload:Preference,request:Request):
    u=core().account(request)
    if u['demo']:raise HTTPException(403,'Create a real account to save email preferences.')
    if payload.frequency=='daily' and u['plan']!='premium' and u['role'] not in ('owner','admin'):raise HTTPException(403,'Daily briefings require Premium.')
    with core().db() as c:
        c.execute('INSERT INTO digest_preferences VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET frequency=excluded.frequency,watchlist_only=excluded.watchlist_only,updated_at=excluded.updated_at',(u['id'],payload.frequency,int(payload.watchlist_only),time.time()))
        audit(c,u,'digest_preferences_updated',detail=json.dumps(payload.model_dump()))
    return {**payload.model_dump(),'delivery_enabled':False}

def personalized(report,u):
    if not report.get('ready'):return report
    s=core();premium=u['plan']=='premium' or u['role'] in ('owner','admin')
    with s.db() as c:
        watched={r[0] for r in c.execute('SELECT ticker FROM watchlist WHERE user_id=?',(u['id'],))}
        prefs=preferences(c,u['id'])
        posts=[dict(r) for r in c.execute("SELECT p.id,p.author,p.text,p.ts,p.sentiment FROM posts p WHERE p.source='x' AND p.ts>=? AND p.ts<? AND p.author IN (SELECT handle FROM handles WHERE user_id=? UNION SELECT handle FROM admin_voices) ORDER BY p.ts DESC LIMIT 100",(report['window_start'],report['window_end'],u['id']))] if premium else []
    from .post_quality import research_text
    from .screening import fingerprint
    seen=set();authors=set();filtered=[]
    for post in posts:
        fp=fingerprint(post['text'])
        if not post['text'].lstrip().startswith('@') and research_text(post['text']) and fp not in seen and post['author'] not in authors:
            filtered.append(post);seen.add(fp);authors.add(post['author'])
    posts=filtered[:5]
    selected=[r for r in report['rows'] if r['ticker'] in watched]
    for p in posts:p['url']='https://x.com/i/web/status/'+p['id']
    visible=selected if premium and prefs['watchlist_only'] else report['rows'][:10 if premium else 3]
    return {**report,'rows':visible,'watchlist':selected if premium else [],'posts':posts,'personalized':premium,'watchlist_only':bool(premium and prefs['watchlist_only']),'delivery_enabled':False}

@router.get('/api/digest')
def member_briefing(request:Request):
    u=core().account(request)
    return personalized(build(),u)

@router.get('/api/admin/digest')
def admin_briefing(request:Request):
    u=staff(request);report=build()
    preview=personalized(report,u)
    from .newsletter import render
    email=render(preview,u['display_name'],core().ORIGIN,preview=True) if preview.get('ready') else {}
    from .email_delivery import delivery_status
    return {'report':preview,'email_preview':email.get('text',''),'email_html':email.get('html',''),'email_subject':email.get('subject',''),'x_draft':report.get('x_draft',''),'email_enabled':False,'x_enabled':False,'delivery_status':delivery_status(request),'requirements':['Connect and test signed Resend delivery events on the final public address','Activate and verify subscriber dispatch with delivery reconciliation','Public business details and reviewed public website address','New X account authorization before publishing'],'note':'Design preview only. Sending stays off during the private testing week. This preview uses your own watchlist and followed voices; public X drafts never include personal lists.'}
