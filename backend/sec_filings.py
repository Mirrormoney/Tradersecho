"""Shared SEC submissions cache. No paid feeds or model calls."""
import os, re, time, json, hmac, ssl
from datetime import datetime, timezone
from urllib.parse import quote
import httpx
from fastapi import APIRouter, Request, Query, HTTPException
from .community import core

router = APIRouter()
LABELS = {'8-K':'Company update', '6-K':'Foreign issuer update', '10-Q':'Quarterly report', '10-K':'Annual report', '20-F':'Annual report', '40-F':'Annual report', '4':'Insider transaction disclosure', '3':'Initial insider ownership', '5':'Annual insider disclosure', 'S-1':'Securities registration', 'S-3':'Shelf registration', '424B5':'Prospectus supplement', 'DEF 14A':'Proxy statement', 'SC 13D':'Beneficial ownership disclosure', 'SC 13G':'Beneficial ownership disclosure'}

def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS sec_companies(ticker TEXT PRIMARY KEY,cik TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sec_checks(cik TEXT PRIMARY KEY,checked_at REAL DEFAULT 0,attempted_at REAL DEFAULT 0,error TEXT);
    CREATE TABLE IF NOT EXISTS sec_filings(accession TEXT PRIMARY KEY,cik TEXT,form TEXT,filed TEXT,accepted REAL,title TEXT,url TEXT,report_date TEXT,collected_at REAL);
    CREATE INDEX IF NOT EXISTS sec_filings_company ON sec_filings(cik,accepted);
    CREATE INDEX IF NOT EXISTS sec_filings_time ON sec_filings(accepted);
    ''')

def getmeta(c, key, default=None):
    r=c.execute('SELECT value FROM meta WHERE key=?',('sec_'+key,)).fetchone()
    return json.loads(r[0]) if r else default

def setmeta(c,key,value):
    c.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('sec_'+key,json.dumps(value)))

def norm(t): return t.upper().replace('-','.')

def map_companies(c, payload):
    lookup={norm(r['ticker']):str(int(r['cik_str'])) for r in payload.values() if r.get('ticker') and r.get('cik_str')}
    stocks=c.execute('SELECT ticker FROM stocks WHERE active=1').fetchall()
    matches=[];missing=[]
    for row in stocks:
        ticker=row[0];cik=lookup.get(norm(ticker))
        if cik:
            matches.append((ticker,cik))
        else: missing.append((ticker,))
    c.executemany('INSERT INTO sec_companies VALUES(?,?) ON CONFLICT(ticker) DO UPDATE SET cik=excluded.cik',matches)
    c.executemany('INSERT OR IGNORE INTO sec_checks(cik) VALUES(?)',[(cik,) for cik in sorted({r[1] for r in matches})])
    c.executemany('DELETE FROM sec_companies WHERE ticker=?',missing)

def parse_filings(payload,cik,now):
    recent=payload.get('filings',{}).get('recent',{})
    rows=[]
    for i,accession in enumerate(recent.get('accessionNumber',[])):
        def val(key):
            values=recent.get(key,[])
            return values[i] if i<len(values) else ''
        if not re.fullmatch(r'\d{10}-\d{2}-\d{6}',accession):continue
        filed=val('filingDate')
        try:
            accepted=datetime.fromisoformat(val('acceptanceDateTime').replace('Z','+00:00'))
            if accepted.tzinfo is None:
                from zoneinfo import ZoneInfo
                accepted=accepted.replace(tzinfo=ZoneInfo('America/New_York'))
            ts=accepted.timestamp()
        except (ValueError,TypeError):
            try:ts=datetime.fromisoformat(filed).replace(tzinfo=timezone.utc).timestamp()
            except (ValueError,TypeError):continue
        if ts<now-90*86400 or ts>now+300:continue
        form=val('form');base=form.removesuffix('/A')
        title=LABELS.get(base,'SEC filing')+(' · amendment' if form.endswith('/A') else '')
        doc=val('primaryDocument')
        # Construct only SEC links; never follow document URLs during collection.
        path=f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/'
        url=path+quote(doc,safe='') if doc and '/' not in doc and '\\' not in doc else path+accession+'-index.html'
        rows.append((accession,cik,form,filed,ts,title,url,val('reportDate'),now))
    return rows

def run(client=None):
    if os.getenv('VERCEL_ENV')!='production':return {'state':'preview_disabled'}
    s=core();now=time.time();token=os.urandom(12).hex()
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        if getmeta(c,'lease',{}).get('until',0)>now:return {'state':'already_running'}
        if getmeta(c,'cooldown',0)>now:return {'state':'cooldown'}
        setmeta(c,'lease',{'token':token,'until':now+180});setmeta(c,'heartbeat',now)
    own=client is None
    if own:
        ctx=ssl.create_default_context();ctx.load_default_certs()
        client=httpx.Client(timeout=12,verify=ctx,headers={'User-Agent':'TradersEcho info@tradersecho.com','Accept-Encoding':'gzip, deflate'})
    checked=0;stored=0;failed=0;started=time.monotonic()
    try:
        with s.db() as c: mapped=getmeta(c,'mapped_at',0)
        if now-mapped>86400:
            response=client.get('https://www.sec.gov/files/company_tickers.json');response.raise_for_status()
            with s.db() as c:map_companies(c,response.json());setmeta(c,'mapped_at',now)
            time.sleep(.2)
        with s.db() as c:
            companies=c.execute('SELECT DISTINCT q.cik,q.attempted_at FROM sec_checks q JOIN sec_companies m ON m.cik=q.cik JOIN stocks s ON s.ticker=m.ticker WHERE s.active=1 AND q.attempted_at<? ORDER BY q.attempted_at,q.cik LIMIT 40',(now-1800,)).fetchall()
        for company in companies:
            if time.monotonic()-started>65:break
            cik=company['cik']
            with s.db() as c:c.execute('UPDATE sec_checks SET attempted_at=? WHERE cik=?',(now,cik))
            try:
                r=client.get(f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json');r.raise_for_status()
                rows=parse_filings(r.json(),cik,now)
                with s.db() as c:
                    before=c.execute('SELECT COUNT(*) FROM sec_filings WHERE cik=?',(cik,)).fetchone()[0]
                    c.executemany('INSERT OR IGNORE INTO sec_filings VALUES(?,?,?,?,?,?,?,?,?)',rows)
                    stored+=c.execute('SELECT COUNT(*) FROM sec_filings WHERE cik=?',(cik,)).fetchone()[0]-before
                    c.execute('UPDATE sec_checks SET checked_at=?,error=NULL WHERE cik=?',(now,cik))
                checked+=1
            except (httpx.HTTPError,ValueError) as exc:
                failed+=1
                with s.db() as c:c.execute('UPDATE sec_checks SET error=? WHERE cik=?',(type(exc).__name__,cik))
                if isinstance(exc,httpx.HTTPStatusError) and exc.response.status_code in (403,429):raise
            time.sleep(.2)
        with s.db() as c:
            setmeta(c,'last_run',{'at':now,'checked':checked,'new_filings':stored,'failed':failed})
            setmeta(c,'error',None)
        return {'state':'complete','checked':checked,'new_filings':stored,'failed':failed}
    except (httpx.HTTPError,ValueError) as exc:
        with s.db() as c:
            setmeta(c,'error',{'at':now,'type':type(exc).__name__});setmeta(c,'cooldown',now+3600)
        return {'state':'upstream_unavailable','checked':checked}
    finally:
        if own:client.close()
        with s.db() as c:
            if getmeta(c,'lease',{}).get('token')==token:setmeta(c,'lease',{})

@router.get('/api/cron/sec')
def cron(request:Request):
    secret=os.getenv('CRON_SECRET','')
    if not secret or not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+secret):raise HTTPException(401,'Unauthorized')
    return run()

@router.get('/api/filings')
def filings(request:Request,ticker:str='',kind:str='',days:int=Query(30,ge=1,le=90),offset:int=Query(0,ge=0,le=10000),limit:int=Query(30,ge=1,le=100)):
    s=core();s.account(request);ticker=ticker.strip().upper()
    if ticker and ticker not in s.CATALOG:raise HTTPException(404,'Unknown ticker')
    filters=['s.active=1','f.accepted>=?'];args=[time.time()-days*86400]
    if ticker:filters.append('m.ticker=?');args.append(ticker)
    groups={'updates':['8-K','6-K'],'reports':['10-K','10-Q','20-F','40-F'],'insiders':['3','4','5']}
    if kind:
        if kind not in groups:raise HTTPException(422,'Unknown filing category')
        forms=groups[kind]+[f+'/A' for f in groups[kind]]
        filters.append('f.form IN ('+','.join('?' for _ in forms)+')');args+=forms
    with s.db() as c:
        rows=[dict(r) for r in c.execute('SELECT f.*,m.ticker,s.name FROM sec_filings f JOIN sec_companies m ON m.cik=f.cik JOIN stocks s ON s.ticker=m.ticker WHERE '+' AND '.join(filters)+' ORDER BY f.accepted DESC,f.accession DESC,m.ticker LIMIT ? OFFSET ?',args+[limit+1,offset])]
        coverage=dict(c.execute('SELECT COUNT(DISTINCT m.cik) AS mapped,COUNT(DISTINCT CASE WHEN q.checked_at>0 THEN m.cik END) AS checked,MIN(q.checked_at) AS oldest_check FROM sec_companies m JOIN stocks s ON s.ticker=m.ticker LEFT JOIN sec_checks q ON q.cik=m.cik WHERE s.active=1').fetchone())
        company=c.execute('SELECT m.cik,q.checked_at,q.error FROM sec_companies m LEFT JOIN sec_checks q ON q.cik=m.cik WHERE m.ticker=?',(ticker,)).fetchone() if ticker else None
        state={'last_run':getmeta(c,'last_run'),'upstream_error':bool(getmeta(c,'error')),'coverage':coverage,'company':dict(company) if company else None}
    return {'rows':rows[:limit],'has_more':len(rows)>limit,**state}
