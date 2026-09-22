"""Read-only search of saved data. Never triggers collection or AI calls."""
import json,time
from fastapi import APIRouter,Query,Request
from .community import core
router=APIRouter()

def pattern(q):
    return '%'+q.lower().replace('!','!!').replace('%','!%').replace('_','!_')+'%'

def snippet(text,q):
    start=max(0,text.lower().find(q.lower())-60)
    return ('…' if start else '')+text[start:start+220]+('…' if len(text)>start+220 else '')

@router.get('/api/search')
def search(request:Request,q:str=Query('',max_length=100)):
    s=core();u=s.account(request,required=False);q=q.strip().lstrip('$')
    if not q:return {'results':[],'sign_in':not bool(u)}
    results=[];p=pattern(q)
    with s.db() as c:
        stocks=[dict(r) for r in c.execute('SELECT ticker,name FROM stocks WHERE active=1')]
        matched=[r for r in stocks if (r['ticker'].lower()==q.lower() if len(q)==1 else q.lower() in (r['ticker']+' '+r['name']).lower())]
        matched.sort(key=lambda r:(r['ticker'].lower()!=q.lower(),not r['ticker'].lower().startswith(q.lower()),r['ticker']))
        results.extend({'kind':'stock','ticker':r['ticker'],'title':r['name'],'text':'Open stock details'} for r in matched[:8])
        if u and len(q)>1:
            rows=c.execute("SELECT f.form,f.title,f.filed,f.url,m.ticker,s.name FROM sec_filings f JOIN sec_companies m ON m.cik=f.cik JOIN stocks s ON s.ticker=m.ticker WHERE s.active=1 AND LOWER(m.ticker||' '||s.name||' '||f.form||' '||f.title||' '||f.accession) LIKE ? ESCAPE '!' ORDER BY f.accepted DESC LIMIT 6",(p,)).fetchall()
            results.extend({'kind':'filing','ticker':r['ticker'],'title':r['form']+' · '+r['title'],'text':r['filed']+' · '+r['name'],'url':r['url']} for r in rows)
            if not u.get('demo'):
                rows=c.execute("SELECT DISTINCT p.id,p.author,p.text,p.ts,m.ticker FROM posts p JOIN mentions m ON m.source=p.source AND m.post_id=p.id JOIN stocks s ON s.ticker=m.ticker WHERE s.active=1 AND p.source='x' AND p.ts>? AND LOWER(p.text||' '||p.author||' '||m.ticker||' '||s.name) LIKE ? ESCAPE '!' ORDER BY p.ts DESC LIMIT 6",(time.time()-30*86400,p)).fetchall()
                results.extend({'kind':'take','ticker':r['ticker'],'title':'@'+r['author'],'text':snippet(r['text'],q),'url':'https://x.com/i/web/status/'+r['id']} for r in rows)
            if u.get('role') in ('owner','admin'):
                rows=c.execute("SELECT d.result,l.ticker FROM research_documents d JOIN research_links l ON l.document_id=d.id JOIN stocks s ON s.ticker=l.ticker WHERE d.status='draft' AND s.active=1 AND LOWER(d.result||' '||l.ticker||' '||s.name) LIKE ? ESCAPE '!' ORDER BY d.received DESC LIMIT 20",(p,)).fetchall()
                for r in rows:
                    report=json.loads(r['result'])
                    for f in report['findings']:
                        if f['ticker']==r['ticker']:
                            results.append({'kind':'research','ticker':r['ticker'],'title':report['title'],'text':snippet(f['summary'],q)})
    return {'results':results[:26],'sign_in':not bool(u)}
