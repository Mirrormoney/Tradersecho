"""Shared research sources; private follows never create private collection jobs."""
import re, time
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from .community import core, staff, audit

router=APIRouter()
PERSONAL_LIMIT=5

def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS admin_voices(handle TEXT PRIMARY KEY,note TEXT NOT NULL DEFAULT '',created_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS voice_checkpoints(handle TEXT PRIMARY KEY,window_end REAL NOT NULL,checked_at REAL NOT NULL,truncated INTEGER NOT NULL DEFAULT 0);
    ''')
    # Retain existing shared collection progress when introducing the registry.
    if not c.execute("SELECT 1 FROM meta WHERE key='voice_checkpoints_v1'").fetchone():
        for r in c.execute("SELECT ticker,MAX(window_end) latest,MAX(updated_at) checked FROM collection_jobs WHERE kind='hour_voice' AND status='done' GROUP BY ticker"):
            for handle in r['ticker'].split(','):
                c.execute('INSERT INTO voice_checkpoints VALUES(?,?,?,0) ON CONFLICT(handle) DO UPDATE SET window_end=excluded.window_end WHERE excluded.window_end>voice_checkpoints.window_end',(handle,r['latest'],r['checked']))
        c.execute("INSERT INTO meta VALUES('voice_checkpoints_v1','1') ON CONFLICT(key) DO NOTHING")

def normalize(value):
    handle=value.strip().lstrip('@').lower()
    if not re.fullmatch(r'[a-z0-9_]{1,15}',handle):raise HTTPException(422,'Enter a valid X handle (letters, numbers, underscores).')
    return handle

def shared_handles(c):
    return [r[0] for r in c.execute("SELECT handle FROM admin_voices UNION SELECT h.handle FROM handles h JOIN accounts a ON a.id=h.user_id WHERE a.demo=0 AND a.status='active' AND (a.plan='premium' OR a.role IN ('owner','admin')) ORDER BY handle")]

class Voice(BaseModel):
    handle:str=Field(min_length=1,max_length=16)
    note:str=Field(default='',max_length=250)

@router.get('/api/voices/curated')
def curated(request:Request):
    s=core();s.account(request)
    with s.db() as c:
        return [dict(r) for r in c.execute('SELECT v.handle,v.note,p.window_end,p.checked_at,p.truncated FROM admin_voices v LEFT JOIN voice_checkpoints p ON p.handle=v.handle ORDER BY v.handle')]

@router.get('/api/admin/voices')
def registry(request:Request):
    staff(request)
    with core().db() as c:
        common={r['handle']:dict(r) for r in c.execute('SELECT * FROM admin_voices')}
        followers={r['handle']:r['n'] for r in c.execute("SELECT h.handle,COUNT(*) n FROM handles h JOIN accounts a ON a.id=h.user_id WHERE a.demo=0 AND a.status='active' AND (a.plan='premium' OR a.role IN ('owner','admin')) GROUP BY h.handle")}
        checkpoints={r['handle']:dict(r) for r in c.execute('SELECT * FROM voice_checkpoints')}
        rows=[{'handle':h,'curated':h in common,'note':common.get(h,{}).get('note',''),'followers':followers.get(h,0),**{k:v for k,v in checkpoints.get(h,{}).items() if k!='handle'}} for h in shared_handles(c)]
    return {'rows':rows,'unique_accounts':len(rows),'personal_limit':PERSONAL_LIMIT}

@router.post('/api/admin/voices')
def add_curated(payload:Voice,request:Request):
    u=staff(request);handle=normalize(payload.handle)
    with core().db() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('INSERT INTO admin_voices VALUES(?,?,?) ON CONFLICT(handle) DO UPDATE SET note=excluded.note',(handle,payload.note,time.time()))
        audit(c,u,'curated_voice_saved',target=handle)
    return {'ok':True}

@router.delete('/api/admin/voices/{handle}')
def remove_curated(handle:str,request:Request):
    u=staff(request);handle=normalize(handle)
    with core().db() as c:
        c.execute('DELETE FROM admin_voices WHERE handle=?',(handle,))
        audit(c,u,'curated_voice_removed',target=handle)
    return {'ok':True}
