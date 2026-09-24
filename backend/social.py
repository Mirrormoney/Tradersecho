"""Owner-authorized X publishing with durable, at-most-once edition claims."""
import base64,hashlib,hmac,json,os,time,secrets
from datetime import datetime,timezone
from urllib.parse import urlencode
from cryptography.fernet import Fernet
from authlib.integrations.httpx_client import OAuth1Client
from fastapi import APIRouter,Request,HTTPException,Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from .community import core
from .newsletter_schedule import due_slots,NY
from .social_art import card
from . import social_promos,social_research
router=APIRouter()
HANDLE='tradersecho'
CALLBACK='https://tradersecho.com/api/social/callback'
def migrate(c):
    c.execute("CREATE TABLE IF NOT EXISTS social_editions(id TEXT PRIMARY KEY,scheduled REAL,payload TEXT,status TEXT,post_id TEXT,error TEXT,updated REAL)")
def config():return bool(os.getenv('X_PUBLISH_CONSUMER_KEY') and os.getenv('X_PUBLISH_CONSUMER_SECRET'))
def cipher():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(('tradersecho-social:'+os.environ['X_PUBLISH_CONSUMER_SECRET']).encode()).digest()))
def client(token=None):
    return OAuth1Client(os.environ['X_PUBLISH_CONSUMER_KEY'],client_secret=os.environ['X_PUBLISH_CONSUMER_SECRET'],token=(token or {}).get('oauth_token'),token_secret=(token or {}).get('oauth_token_secret'),force_include_body=True,timeout=15)
def owner(request):
    s=core();u=s.account(request)
    if u['demo'] or u['role']!='owner':raise HTTPException(403,'Only the owner can manage the X account.')
    return u

def value(c,key,default=None):
    r=c.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
    return json.loads(r[0]) if r else default

def save(c,key,val):c.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(val)))

def upload_checked(x,connection,image):
    me=x.get('https://api.x.com/2/users/me');me.raise_for_status();who=me.json()['data']
    if who['id']!=connection['id'] or who['username'].lower()!=HANDLE:raise ValueError('Publishing account mismatch')
    media=x.post('https://api.x.com/2/media/upload',json={'media':base64.b64encode(image).decode(),'media_category':'tweet_image'})
    media.raise_for_status()
    return media.json()['data']['id']

@router.post('/api/admin/social/preflight')
def preflight(request:Request):
    """Bounded identity and real media-upload check; never creates a public post."""
    owner(request)
    if os.getenv('VERCEL_ENV')!='production':raise HTTPException(409,'Run this check on production.')
    if not config():raise HTTPException(409,'Publishing credentials are missing.')
    now=time.time();s=core()
    try:p=prepare('morning',now);image=card(p)
    except ValueError as e:raise HTTPException(409,str(e))
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        connection=value(c,'social_connection')
        if not connection:raise HTTPException(409,'Connect the publishing account first.')
        previous=value(c,'social_preflight',{})
        if now-previous.get('at',0)<(60 if previous.get('state')=='failed' else 3600):return previous
        from .community import data_settings
        month=datetime.fromtimestamp(now,timezone.utc).strftime('%Y-%m')
        spent=c.execute('SELECT COALESCE(SUM(COALESCE(actual_estimate,reserved)),0) FROM x_spend WHERE month=?',(month,)).fetchone()[0]
        if spent+.5>min(250,data_settings(c)['monthly_budget']):raise HTTPException(409,'Monthly X budget reached.')
        c.execute('INSERT INTO x_spend(month,kind,reserved,ts,status) VALUES(?,?,?,?,?)',(month,'social_preflight',.5,now,'reserved'))
        save(c,'social_preflight',{'at':now,'state':'checking'})
    try:
        token=json.loads(cipher().decrypt(connection['secret'].encode()))
        with client(token) as x:upload_checked(x,connection,image)
        result={'at':now,'state':'passed','message':'X account and image upload verified. No public post was created.'}
    except Exception as e:
        response=getattr(e,'response',None)
        status=getattr(response,'status_code',None)
        detail=''
        if response is not None:
            try:
                problem=response.json()
                detail=str(problem.get('detail') or problem.get('title') or '')[:400]
                detail+=' '.join(str(v.get('message',''))[:200] for v in problem.get('errors',[]) if isinstance(v,dict))[:400]
            except Exception:pass
        result={'at':now,'state':'failed','message':'X upload check failed'+(f' (HTTP {status})' if status else '')+'. '+detail+' No public post was created.'}
    with s.db() as c:save(c,'social_preflight',result)
    return result

def prepare(edition,now):
    s=core()
    from .count_metrics import enrich
    with s.db() as c:
        if edition in ('morning','final'):
            # Same completed-hour heat formula as Intraday, without personal data.
            import math
            rows=[]
            ends=c.execute('SELECT ticker,MAX(end) AS end FROM x_counts WHERE end>? AND end<=? GROUP BY ticker',(now-7200,now)).fetchall()
            for r in ends:
                if r['ticker'] not in s.CATALOG:continue
                end=r['end'];b=c.execute('SELECT start,end,n FROM x_counts WHERE ticker=? AND start>=? AND end<=? ORDER BY start',(r['ticker'],end-21600,end)).fetchall()
                if len(b)!=6 or [x['start'] for x in b]!=[end-21600+i*3600 for i in range(6)] or any(x['end']-x['start']!=3600 for x in b):continue
                old=sum(x['n'] for x in b[:3]);n=sum(x['n'] for x in b[3:])
                rows.append({'ticker':r['ticker'],'name':s.CATALOG[r['ticker']][0],'mentions':n,'change':round((n/old-1)*100,1) if old else None,'heat':round(10*math.log1p(n)*(1+max(0,math.log2((n+5)/(old+5)))),1),'as_of':end})
            label='Last 3 completed hours vs preceding 3';title='Your morning radar' if edition=='morning' else 'The closing conversation';max_age=7200
        else:
            end=s.reference('x',c);days={'weekly':7,'monthly':30}.get(edition,1)
            if end>now or now-end>36*3600:raise ValueError('Waiting for a fresh complete snapshot')
            rows=enrich(c,[],end,days)
            rows.sort(key=lambda r:(-r['heat'],r['ticker']))
            if len(rows)<3 or any(r.get('coverage_hours')!=days*24 for r in rows[:3]):raise ValueError('Top three do not yet have complete period coverage')
            for r in rows:r['as_of']=end
            label=f'{days} days'+' ending '+datetime.fromtimestamp(end,NY).strftime('%b %d %H:%M ET')
            title='The month in AI attention' if days==30 else 'The week in AI attention';max_age=36*3600
    rows.sort(key=lambda r:(-r['heat'],r['ticker']))
    if len(rows)<3:raise ValueError('Waiting for three measured leaders')
    rows=rows[:3];as_of=min(r['as_of'] for r in rows)
    date=datetime.fromtimestamp(now,NY).strftime('%b %d, %Y')
    hook={'morning':"What's hot on X this morning?",'final':"What's hot on X after closing?",'weekly':"What was hot on X this week?",'monthly':"What was hot on X this month?"}[edition]
    leader=rows[0]
    period={'morning':'3 hours','final':'3 hours','weekly':'7 days','monthly':'30 days'}[edition]
    lines=[hook,'',f"${leader['ticker']} leads our AI-stock attention ranking.",
           f"{leader['mentions']:,} mentions in {period}.",f"Heat score: {leader['heat']:g}."]
    if leader.get('change') is not None:
        lines.append(f"{leader['change']:+g}% vs prior {period}.")
    lines+=['','Explore the top 3 below.','https://tradersecho.com/marketpulse','Attention, not investment advice.']
    text='\n'.join(lines)
    import re
    if len(re.sub(r'https://\S+','x'*23,text))>280:raise ValueError('Post exceeds standard length')

    return {'title':title,'label':label,'rows':rows,'text':text,'as_of':as_of,'max_age':max_age,'edition':edition,'date':date}

@router.post('/api/admin/social/connect')
def connect(request:Request):
    u=owner(request)
    if not config():raise HTTPException(409,'Save X_PUBLISH_CONSUMER_KEY and X_PUBLISH_CONSUMER_SECRET in Vercel Production first. Use an X app with Read and Write permissions.')
    try:
        with client() as x:
            x.redirect_uri=CALLBACK
            token=x.fetch_request_token('https://api.x.com/oauth/request_token')
    except Exception:raise HTTPException(502,'X authorization could not start. Check app permissions and callback URL.')
    with core().db() as c:save(c,'social_oauth:'+hashlib.sha256(token['oauth_token'].encode()).hexdigest(),{'user':u['id'],'until':time.time()+600,'secret':cipher().encrypt(json.dumps(token).encode()).decode()})
    return {'url':'https://api.x.com/oauth/authorize?'+urlencode({'oauth_token':token['oauth_token']})}

@router.get('/api/social/callback')
def callback(request:Request,oauth_token:str='',oauth_verifier:str=''):
    u=owner(request);s=core();key='social_oauth:'+hashlib.sha256(oauth_token.encode()).hexdigest()
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE');pending=value(c,key)
        if not pending or pending['until']<time.time() or pending['user']!=u['id']:raise HTTPException(400,'Connection expired. Start again in Administration.')
        c.execute('DELETE FROM meta WHERE key=?',(key,))
    try:
        temporary=json.loads(cipher().decrypt(pending['secret'].encode()))
        with client(temporary) as x:token=x.fetch_access_token('https://api.x.com/oauth/access_token',verifier=oauth_verifier)
        with client(token) as x:
            r=x.get('https://api.x.com/2/users/me');r.raise_for_status();identity=r.json()['data']
        if identity['username'].lower()!=HANDLE:raise ValueError('wrong account')
    except Exception:raise HTTPException(400,'Could not connect @Tradersecho. Make sure you authorize as that account, not your personal account.')
    with s.db() as c:
        save(c,'social_connection',{'secret':cipher().encrypt(json.dumps(token).encode()).decode(),'handle':identity['username'],'id':identity['id']})
        save(c,'social_paused',True)
    return RedirectResponse('https://tradersecho.com/admin?social=connected',status_code=303)

@router.get('/api/admin/social')
def status(request:Request):
    owner(request)
    with core().db() as c:
        connection=value(c,'social_connection',{})
        rows=[dict(r) for r in c.execute('SELECT id,scheduled,payload,status,post_id,error,updated FROM social_editions ORDER BY scheduled DESC LIMIT 20')]
        for r in rows:r['payload']=json.loads(r['payload'])
        return {'configured':config(),'connected':connection.get('handle'),'paused':value(c,'social_paused',True),'label_confirmed':value(c,'social_label_confirmed',False),'rows':rows,'last_run':value(c,'social_last_run'),'preflight':value(c,'social_preflight')}
class Settings(BaseModel):
    paused:bool=True
    label_confirmed:bool=False
@router.post('/api/admin/social/settings')
def settings(request:Request,body:Settings):
    owner(request)
    with core().db() as c:
        if not body.paused and (not value(c,'social_connection') or not body.label_confirmed):raise HTTPException(409,'Connect @Tradersecho and confirm its automated-account label first.')
        save(c,'social_paused',body.paused);save(c,'social_label_confirmed',body.label_confirmed)
    return {'ok':True}
@router.post('/api/admin/social/preview/{edition}')
def preview(request:Request,edition:str):
    owner(request)
    if edition in tuple('promo'+str(i+1) for i in range(len(social_promos.COPY))):
        p=social_promos.prepare(int(edition[-1])-1)
        return {**p,'image':'data:image/png;base64,'+base64.b64encode(social_promos.artwork(p)).decode()}
    if edition=='research':
        try:p=social_research.prepare(time.time())
        except ValueError as e:raise HTTPException(409,str(e))
        return {**p,'image':'data:image/png;base64,'+base64.b64encode(social_research.artwork(p)).decode()}
    if edition not in ('morning','final','weekly','monthly'):raise HTTPException(400,'Unknown edition')
    try:p=prepare(edition,time.time())
    except ValueError as e:raise HTTPException(409,str(e))
    return {**p,'image':'data:image/png;base64,'+base64.b64encode(card(p)).decode()}

def run(now=None,manual_promo=False,manual_research=False):
    now=time.time() if now is None else now;s=core()
    if os.getenv('VERCEL_ENV')!='production':return {'state':'preview_disabled'}
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        # An ambiguous publish is never retried, and blocks later editions until reviewed.
        c.execute("UPDATE social_editions SET status='uncertain',error='Interrupted publish; check X before resuming.' WHERE status='sending' AND updated<?",(now-600,))
        connection=value(c,'social_connection')
        if not config() or not connection:return {'state':'connection_required'}
        if value(c,'social_paused',True) or not value(c,'social_label_confirmed',False):return {'state':'paused'}
        if c.execute("SELECT 1 FROM social_editions WHERE status IN ('uncertain','failed') LIMIT 1").fetchone():return {'state':'review_required'}
    result={'state':'ok','sent':0}
    slots=due_slots(now)+social_promos.slots(now)+social_research.slots(now)+social_promos.signal_slots(now)
    if manual_research:
        slots=[{'edition':'research','at':now,'key':'research:'+datetime.fromtimestamp(now,NY).date().isoformat()}]
    if manual_promo:
        # Same durable key as today's scheduled promotion: an early publish never duplicates it.
        slots=[{'edition':'promo','at':now,'key':'promo:'+datetime.fromtimestamp(now,NY).date().isoformat()}]
    for slot in slots:
        key=slot['key']
        with s.db() as c:
            if c.execute('SELECT 1 FROM social_editions WHERE id=?',(key,)).fetchone():continue
        try:
            if slot['edition']=='promo':
                with s.db() as c:
                    n=c.execute("SELECT COUNT(*) FROM social_editions WHERE id LIKE 'promo:%' AND status='published'").fetchone()[0]
                p=social_promos.prepare(n%len(social_promos.COPY));image=social_promos.artwork(p)
            elif slot['edition']=='signal_launch':
                p=social_promos.prepare_signal(slot,now);image=social_promos.signal_artwork()
            elif slot['edition']=='research':
                p=social_research.prepare(now,approved=manual_research);image=social_research.artwork(p)
            else:p=prepare(slot['edition'],now);image=card(p)
        except ValueError as e:result={'state':'waiting_for_data','reason':str(e)};continue
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            if value(c,'social_paused',True) or c.execute('SELECT 1 FROM social_editions WHERE id=?',(key,)).fetchone():continue
            if c.execute("SELECT 1 FROM social_editions WHERE status IN ('sending','uncertain','failed') LIMIT 1").fetchone():continue
            # Suppress an identical data payload, even when the edition label changes.
            fingerprint=hashlib.sha256((p['text'] if slot['edition'] in ('promo','research','signal_launch') else json.dumps([(r['ticker'],r['mentions'],r['as_of']) for r in p['rows']])).encode()).hexdigest()
            if value(c,'social_last_fingerprint')==fingerprint:continue
            month=datetime.fromtimestamp(now,timezone.utc).strftime('%Y-%m')
            from .community import data_settings
            spent=c.execute('SELECT COALESCE(SUM(COALESCE(actual_estimate,reserved)),0) FROM x_spend WHERE month=?',(month,)).fetchone()[0]
            # Conservative $0.50 per edition reservation, including identity and media operations.
            if spent+.5>min(250,data_settings(c)['monthly_budget']):result={'state':'budget_paused'};continue
            c.execute('INSERT INTO x_spend(month,kind,reserved,ts,status) VALUES(?,?,?,?,?)',(month,'social_publish',.5,now,'reserved'))
            c.execute('INSERT INTO social_editions VALUES(?,?,?,?,?,?,?)',(key,slot['at'],json.dumps(p),'sending',None,None,now))
        post_attempted=False
        try:
            token=json.loads(cipher().decrypt(connection['secret'].encode()))
            with client(token) as x:
                mid=upload_checked(x,connection,image)
                with s.db() as c:
                    if value(c,'social_paused',True):raise ValueError('Paused before publishing')
                post_attempted=True
                response=x.post('https://api.x.com/2/tweets',json={'text':p['text'],'media':{'media_ids':[mid]}})
                response.raise_for_status();pid=response.json()['data']['id']
            with s.db() as c:
                c.execute("UPDATE social_editions SET status='published',post_id=?,updated=? WHERE id=?",(pid,now,key));save(c,'social_last_fingerprint',fingerprint)
            result['sent']=result.get('sent',0)+1
        except Exception as e:
            response=getattr(e,'response',None)
            code=getattr(response,'status_code',None)
            rejected=code is not None and 400<=code<500
            message='Delivery uncertain; check X before resuming.' if post_attempted and not rejected else 'Publishing failed before a post was accepted.'
            if code:
                message+=f' X returned HTTP {code}.'
                # Keep only documented error fields, never request headers or credentials.
                try:
                    problem=response.json()
                    details=[str(problem.get(k) or '')[:500] for k in ('title','detail','type')]
                    details += [str(err.get(k) or '')[:300] for err in problem.get('errors',[]) if isinstance(err,dict) for k in ('code','message','detail')]
                    message+=' '+' | '.join(v for v in details if v)[:1800]
                except (ValueError,AttributeError):pass
            # A definitive caption rejection never retries this edition or blocks later ones.
            # Authentication, credit/rate limits, wrong account and ambiguous delivery still stop.
            skip_edition=post_attempted and code in (400,403,404,422)
            state='rejected' if skip_edition else ('uncertain' if post_attempted and not rejected else 'failed')
            message=('Post creation: ' if post_attempted else 'Identity/media setup: ')+message
            if skip_edition:message+=' Edition skipped; later scheduled posts remain enabled.'
            with s.db() as c:
                c.execute('UPDATE social_editions SET status=?,error=?,updated=? WHERE id=?',(state,message,now,key))
                if not skip_edition:save(c,'social_paused',True)
            result={**result,'state':'edition_rejected' if skip_edition else 'review_required'}
    with s.db() as c:save(c,'social_last_run',{**result,'at':now})
    return result

@router.post('/api/admin/social/publish-research')
def publish_research(request:Request):
    owner(request)
    return run(manual_research=True)

@router.post('/api/admin/social/publish-promotion')
def publish_promotion(request:Request):
    owner(request)
    return run(manual_promo=True)

@router.post('/api/admin/social/review/{edition_id}')
def reviewed(request:Request,edition_id:str):
    owner(request)
    with core().db() as c:
        c.execute("UPDATE social_editions SET status='reviewed',updated=? WHERE id=? AND status IN ('failed','uncertain')",(time.time(),edition_id))
    return {'ok':True}

@router.get('/api/cron/social')
def cron(request:Request):
    secret=os.getenv('CRON_SECRET','')
    if not secret or not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+secret):raise HTTPException(401,'Unauthorized')
    return run()
