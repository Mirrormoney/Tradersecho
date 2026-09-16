"""Reviewed stock universe; up to 1,000 active names, never fabricated padding."""
import json, re, time
from pathlib import Path
from collections.abc import Mapping
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from .community import core, staff, audit

router=APIRouter()

def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS stocks(ticker TEXT PRIMARY KEY,name TEXT,sector TEXT,theme TEXT,reason TEXT,exchange TEXT,active INTEGER DEFAULT 1,updated_at REAL);
    CREATE TABLE IF NOT EXISTS collection_jobs(id INTEGER PRIMARY KEY AUTOINCREMENT,day TEXT,kind TEXT,ticker TEXT,status TEXT DEFAULT 'pending',attempts INTEGER DEFAULT 0,lease_until REAL DEFAULT 0,error TEXT,updated_at REAL,UNIQUE(day,kind,ticker));
    CREATE INDEX IF NOT EXISTS collection_pending ON collection_jobs(day,status,kind);
    CREATE TABLE IF NOT EXISTS post_authors(id TEXT PRIMARY KEY,handle TEXT,created_at REAL,followers INTEGER,following INTEGER,posts INTEGER,fetched_at REAL);
    ''')
    if not c.execute('SELECT 1 FROM stocks LIMIT 1').fetchone():
        seed=json.loads((Path(__file__).parent/'stock_universe.json').read_text(encoding='utf-8'))
        for r in seed:
            c.execute('INSERT OR IGNORE INTO stocks VALUES(?,?,?,?,?,?,1,?)',(r['ticker'],r['name'],r['sector'],r['theme'],r['reason'],r['exchange'],time.time()))

class Catalog(Mapping):
    def __init__(self): self.snapshot={}; self.loaded=0
    def refresh(self,force=False):
        if force or time.time()-self.loaded>60:
            with core().db() as c: rows=c.execute('SELECT ticker,name,sector FROM stocks WHERE active=1 ORDER BY ticker').fetchall()
            self.snapshot={r['ticker']:(r['name'],r['sector']) for r in rows};self.loaded=time.time()
        return self.snapshot
    def __getitem__(self,k): return self.refresh()[k]
    def __len__(self): return len(self.refresh())
    def __iter__(self): return iter(self.refresh())

@router.get('/api/admin/stocks')
def stocks(request:Request):
    staff(request)
    with core().db() as c: rows=[dict(r) for r in c.execute('SELECT * FROM stocks ORDER BY active DESC,sector,ticker')]
    return {'rows':rows,'active':sum(r['active'] for r in rows),'capacity':1000}

class Stock(BaseModel):
    ticker:str=Field(pattern=r'^[A-Z]{1,5}(?:\.[A-Z])?$')
    name:str=Field(min_length=2,max_length=180)
    sector:str=Field(min_length=2,max_length=80)
    theme:str=Field(min_length=2,max_length=80)
    reason:str=Field(min_length=10,max_length=500)
    exchange:str=Field(default='',max_length=30)
    active:bool=True

class StockImport(BaseModel):
    stocks:list[Stock]=Field(min_length=1,max_length=1000)

@router.post('/api/admin/stocks')
def save_stocks(payload:StockImport,request:Request):
    u=staff(request,owner=True);s=core()
    if len({r.ticker for r in payload.stocks})!=len(payload.stocks): raise HTTPException(422,'Duplicate tickers in this import.')
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        active={r[0] for r in c.execute('SELECT ticker FROM stocks WHERE active=1')}
        for r in payload.stocks:
            if r.active: active.add(r.ticker)
            else: active.discard(r.ticker)
        if len(active)>1000: raise HTTPException(422,'Maximum 1,000 active tickers. Disable other names first.')
        for r in payload.stocks:
            c.execute('INSERT INTO stocks VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(ticker) DO UPDATE SET name=excluded.name,sector=excluded.sector,theme=excluded.theme,reason=excluded.reason,exchange=excluded.exchange,active=excluded.active,updated_at=excluded.updated_at',(r.ticker,r.name,r.sector,r.theme,r.reason,r.exchange,int(r.active),time.time()))
        audit(c,u,'universe_updated',detail=str(len(payload.stocks))+' stocks')
    s.CATALOG.refresh(True)
    return {'ok':True,'active':len(active)}
