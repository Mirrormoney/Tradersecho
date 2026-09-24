"""Published, redacted research. No paid requests on page views."""
import json,re,time,hashlib,threading
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter,Request,HTTPException
from .community import core,staff
router=APIRouter()

def migrate(c):
    c.execute('CREATE TABLE IF NOT EXISTS research_publications(document_id TEXT PRIMARY KEY REFERENCES research_documents(id), published REAL NOT NULL)')

def premium(user):
    return bool(user and not user.get('demo') and (user.get('plan')=='premium' or user.get('role') in ('owner','admin')))

def clean_finding(doc,f):
    # Conservative migration for earlier summaries: reported external ratings must
    # never carry the compiling firm's badge. Unclassified material has no badge.
    kind=f.get('attribution','unclear')
    text=f.get('summary','')
    if re.search(r'third.party|external downgrade|author is (reporting|relaying)|rather than (issuing|making)',text,re.I):kind='relayed'
    firm=doc.get('firm','') if kind in ('original','readthrough') else ''
    if firm and firm.lower() not in ('unknown','unknown broker','not identified'):
        text=re.sub(r'\b(?:the report|the note|the author)\b',lambda _:firm,text,flags=re.I)
    event=f.get('event') or {}
    key=None
    if all(event.get(k) for k in ('broker','action','rating','date')) and event.get('action') in ('upgrade','downgrade','initiation','reiteration'):
        key='|'.join([f['ticker'],event['date'],*[re.sub(r'[^a-z0-9]','',event[k].lower()) for k in ('broker','action','rating')]])
    return {'_rating_event':{k:v for k,v in event.items() if k in ('broker','action','rating','date')},'_price_target':{k:v for k,v in (f.get('price_target') or {}).items() if k in ('broker','currency','current','previous')},'link_type':f.get('link_type','direct'),'link_reason':f.get('link_reason',''),'ticker':f['ticker'],'summary':text,'stance':f.get('stance','unclear'),'firm':firm,'report_date':doc.get('report_date'),'catalysts':f.get('catalysts',[]),'risks':f.get('risks',[]),'event_key':key,'original':kind=='original','id':doc['id']+':'+f['ticker']}

def deduplicate(items):
    chosen={}
    for item in items:
        # Distinct desk comments stay separate; merge only confidently identified events.
        key=item['event_key'] or item['id']
        old=chosen.get(key)
        if not old or (item['original'],item.get('report_date') or '')>(old['original'],old.get('report_date') or ''):chosen[key]=item
    return sorted(chosen.values(),key=lambda i:(i.get('report_date') or '',i['id']),reverse=True)

def published(c,ticker=None):
    migrate(c)
    sql="SELECT d.id,d.result,d.received FROM research_documents d JOIN research_publications p ON p.document_id=d.id WHERE d.status='draft'"
    args=()
    if ticker:
        sql+=" AND EXISTS (SELECT 1 FROM research_links l WHERE l.document_id=d.id AND l.ticker=?)"
        args=(ticker,)
    rows=c.execute(sql,args).fetchall()
    items=[]
    for row in rows:
        doc=json.loads(row['result']);doc['id']=row['id']
        for f in doc.get('findings',[]):
            if f['ticker'] in core().CATALOG and (ticker is None or f['ticker']==ticker):items.append({**clean_finding(doc,f),'received':row['received']})
    return deduplicate(items)

def public_item(item):
    return {k:v for k,v in item.items() if k not in ('event_key','original','received') and not k.startswith('_')}

def order_research(items,rankings,catalog,today):
    # Report date defines freshness; import time breaks ties, never makes an old note today's research.
    latest=lambda i:(i.get('report_date') or '',i.get('received') or 0,i['id'])
    groups={}
    for item in sorted(items,key=latest,reverse=True):
        groups.setdefault(item['ticker'],[]).append(item)
    ranks={row['ticker']:rank for rank,row in enumerate(rankings,1)}
    recent=sorted(groups,key=lambda t:latest(groups[t][0]),reverse=True)
    current=[t for t in recent if groups[t][0].get('report_date')==today and t in ranks]
    current.sort(key=lambda t:ranks[t])
    selected=current[:3]
    # Fill any vacant tiles with the newest available research, never with old heat leaders.
    selected += [t for t in recent if t not in selected][:3-len(selected)]
    def row(t,featured=False):
        result={'ticker':t,'name':catalog[t][0],'research':[public_item(i) for i in groups[t]]}
        if featured and t in current:result['daily_rank']=ranks[t]
        return result
    return [row(t,True) for t in selected],[row(t) for t in recent if t not in selected]

def restrict_feed(ranked,other,full):
    # Enforce two preview stocks across both sections; hidden research never leaves the API.
    preview_rows=ranked[:2]
    preview_other=other[:max(0,2-len(preview_rows))]
    return {'rows':ranked if full else preview_rows,'other':other if full else preview_other,'locked':not full,'total':len(ranked)+len(other),'featured_total':len(ranked)}

_feed_cache=None
_feed_lock=threading.Lock()

def shared_overview():
    # Shared research only. Membership is checked separately on every request.
    global _feed_cache
    today=datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    with _feed_lock:
        if _feed_cache and _feed_cache['today']==today and time.monotonic()-_feed_cache['at']<60:
            return _feed_cache['value']
        from .count_metrics import enrich
        with core().db() as c:
            items=published(c)
            rankings=sorted(enrich(c,[],core().reference('x',c),1),key=lambda r:-r['heat'])
        ranked,other=order_research(items,rankings,core().CATALOG,today)
        value=(ranked,other,time.time(),today)
        _feed_cache={'today':today,'at':time.monotonic(),'value':value}
        return value

@router.get('/api/trending-research')
def feed(request:Request):
    user=core().account(request)
    ranked,other,as_of,today=shared_overview()
    return {**restrict_feed(ranked,other,premium(user)),'as_of':as_of,'research_today':today}

@router.get('/api/member-research/{ticker}')
def detail(ticker:str,request:Request):
    user=core().account(request)
    if not premium(user):return {'documents':[],'locked':True}
    with core().db() as c:items=published(c,ticker.upper())
    return {'documents':[{'id':i['id'],'firm':i['firm'],'report_date':i['report_date'],'findings':[public_item(i)]} for i in items],'locked':False}

@router.post('/api/admin/research/{document_id}/publish')
def publish(document_id:str,request:Request):
    staff(request)
    with core().db() as c:
        migrate(c)
        row=c.execute("SELECT result FROM research_documents WHERE id=? AND status='draft'",(document_id,)).fetchone()
        if not row or not json.loads(row['result']).get('report_date'):raise HTTPException(409,'A dated, validated draft is required')
        c.execute('INSERT OR IGNORE INTO research_publications VALUES(?,?)',(document_id,time.time()))
    return {'ok':True}
