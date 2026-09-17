"""New York editorial schedule, saved-data reports and bounded durable delivery."""
import hashlib,hmac,json,os,time
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from html import escape
import httpx
from fastapi import APIRouter,Request,HTTPException
from .community import core

router=APIRouter()
EDITION_NAMES={'morning':'Morning Roundup','final':'Final view','weekly':'Weekly Update','monthly':'Monthly All in One'}
NY=ZoneInfo('America/New_York')

def enabled():
    return os.getenv('NEWSLETTER_ENABLED','false').lower()=='true' and bool(os.getenv('RESEND_API_KEY'))

def choices(c,uid):
    row=c.execute('SELECT editions,trial_reminder FROM newsletter_preferences WHERE user_id=?',(uid,)).fetchone()
    if row:return {'editions':json.loads(row['editions']),'trial_reminder':bool(row['trial_reminder'])}
    old=c.execute('SELECT frequency FROM digest_preferences WHERE user_id=?',(uid,)).fetchone()
    return {'editions':{'daily':['morning','final'],'weekly':['weekly'],'monthly':['monthly'],'all':list(EDITION_NAMES)}.get(old[0] if old else 'off',[]),'trial_reminder':True}

def due_slots(now):
    local=datetime.fromtimestamp(now,NY);day=local.date();result=[]
    candidates=[]
    if local.weekday()<5:candidates+=[('morning',8,0),('final',16,30)]
    if local.weekday()==6:candidates.append(('weekly',12,0))
    if local.day==1:candidates.append(('monthly',12,0))
    for edition,hour,minute in candidates:
        at=datetime(day.year,day.month,day.day,hour,minute,tzinfo=NY).timestamp()
        if 0<=now-at<2*3600:result.append({'edition':edition,'at':at,'key':edition+':'+day.isoformat()})
    return result

def report_for(slot,user):
    """Use the same saved count windows and heat formula as Market pulse. Never fetch X."""
    from .count_metrics import enrich
    from .digest import personalized
    s=core();now=slot['at'];windows=[]
    with s.db() as c:
        end=s.reference('x',c)
        if end>now or now-end>36*3600:raise ValueError('Waiting for a fresh complete market snapshot')
        for days,label in [(1,'24 hours'),(7,'7 days'),(30,'30 days')]:
            rows=enrich(c,[],end,days)
            rows.sort(key=lambda r:(-r['heat'],r['ticker']))
            if not rows:raise ValueError('Waiting for stored market counts')
            hours=min(r.get('coverage_hours',0) for r in rows)
            complete=all(r.get('coverage_hours')==days*24 for r in rows) and len(rows)==len(s.CATALOG)
            coverage=(label+' of collected counts' if complete else f'Partial history: at least {hours/24:.1f} of {days} days per listed stock; not a complete {label} window')
            windows.append({'days':days,'label':label,'rows':rows,'coverage_label':coverage})
    primary=next(w for w in windows if w['days']=={'weekly':7,'monthly':30}.get(slot['edition'],1))
    local=datetime.fromtimestamp(now,NY)
    label=local.strftime('%Y-%m-%d')
    if slot['edition']=='weekly':label=f"week {local.isocalendar().week} · {local.isocalendar().year}"
    if slot['edition']=='monthly':label=(local.replace(day=1)-timedelta(days=1)).strftime('%B %Y')
    title=EDITION_NAMES[slot['edition']]
    report={'ready':True,'date':label,'subject':f'Traders Echo {title} [{label}]','edition_title':title,'period_label':primary['label'],'window_start':end-primary['days']*86400,'window_end':end,'created_at':now,'tracked_stocks':len(primary['rows']),'rows':primary['rows'],'coverage_label':primary['coverage_label']+' · snapshot '+datetime.fromtimestamp(end,timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),'disclosure':'Selected AI supply-chain universe. Mentions measure attention, not bullishness. Post samples are capped. Comparisons are withheld without complete current and prior periods.'}
    report=personalized(report,user,now=now,preserve_ranking=True)
    with s.db() as c:watched={r[0] for r in c.execute('SELECT ticker FROM watchlist WHERE user_id=?',(user['id'],))}
    report['other_windows']=[{**w,'rows':[r for r in w['rows'] if not report.get('watchlist_only') or r['ticker'] in watched][:10]} for w in windows if w is not primary]
    return report

def enqueue(user,kind,slot=None):
    from .email_delivery import valid_recipient,optout_token
    from .account_security import trial_account
    from .newsletter import render
    from .email_brand import trial_reminder
    s=core();now=time.time()
    marker=slot['key'] if slot else 'trial:'+str(user['trial_ends_at'])
    key=hashlib.sha256((marker+':'+user['id']+':'+user['email']).encode()).hexdigest()
    with s.db() as c:
        if c.execute('SELECT 1 FROM email_deliveries WHERE id=?',(key,)).fetchone():return
    content=trial_reminder(user,s.ORIGIN) if kind=='trial' else render(report_for(slot,trial_account(user)),user['display_name'],s.ORIGIN)
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        current=c.execute('SELECT * FROM accounts WHERE id=?',(user['id'],)).fetchone()
        if not current or current['email']!=user['email'] or not valid_recipient(c,current,kind):return
        if c.execute('SELECT 1 FROM email_deliveries WHERE id=?',(key,)).fetchone():return
        token=optout_token(c,current);url=s.ORIGIN+'/api/newsletter/unsubscribe?token='+token
        content['html']=content['html'].replace('</body>','<p style="text-align:center;font:12px Arial;padding:20px"><a href="'+escape(url,quote=True)+'">Unsubscribe from research and trial-reminder emails</a></p></body>')
        content['text']+='\nUnsubscribe: '+url
        payload={'from':'Traders Echo <newsletter@tradersecho.com>','to':[current['email']],'reply_to':'info@tradersecho.com',**content,'headers':{'X-Tradersecho-Edition':kind,'List-Unsubscribe':'<'+url+'>','List-Unsubscribe-Post':'List-Unsubscribe=One-Click'}}
        c.execute('INSERT INTO email_deliveries(id,user_id,email,window_end,payload,status,created_at) VALUES(?,?,?,?,?,?,?)',(key,current['id'],current['email'],slot['at'] if slot else now,json.dumps(payload),'pending',now))
    return True

def run(now=None,client=None):
    from .email_delivery import claim_delivery,valid_recipient,email_hash
    s=core();now=time.time() if now is None else now
    if not enabled():return {'state':'disabled'}
    owner=client is None;client=client or httpx.Client(timeout=12)
    lease=hashlib.sha256(os.urandom(24)).hexdigest();result={'state':'ok','sent':0,'errors':0}
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        lock=c.execute("SELECT value FROM meta WHERE key='email_worker_lease'").fetchone()
        if lock and json.loads(lock[0])['until']>now:
            if owner:client.close()
            return {'state':'busy'}
        c.execute("INSERT INTO meta VALUES('email_worker_lease',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps({'token':lease,'until':now+240}),))
    try:
        with s.db() as c:users=[dict(r) for r in c.execute("SELECT * FROM accounts WHERE demo=0 AND status='active' AND email_verified=1")]
        prepared=0
        for u in users:
            for kind,slot in [('trial',None)]+[(x['edition'],x) for x in due_slots(now)]:
                with s.db() as c:valid=valid_recipient(c,u,kind,now)
                if valid:
                    try:prepared+=bool(enqueue(u,kind,slot))
                    except ValueError:result['waiting_for_data']=True
                if prepared>=50:break
            if prepared>=50:break
        day=int(now//86400)*86400;month=datetime.fromtimestamp(now,timezone.utc).replace(day=1,hour=0,minute=0,second=0,microsecond=0).timestamp()
        with s.db() as c:
            today=c.execute('SELECT COUNT(*) FROM email_deliveries WHERE first_attempt>=?',(day,)).fetchone()[0]
            monthly=c.execute('SELECT COUNT(*) FROM email_deliveries WHERE first_attempt>=?',(month,)).fetchone()[0]
            keys=[r[0] for r in c.execute("SELECT id FROM email_deliveries WHERE status IN ('pending','uncertain','sending') AND lease_until<=? ORDER BY created_at LIMIT 5",(now,))]
        allowance=min(max(0,80-today),max(0,2400-monthly))
        for key in keys:
            with s.db() as c:attempted=c.execute('SELECT first_attempt FROM email_deliveries WHERE id=?',(key,)).fetchone()[0]
            if not attempted and allowance<=0:result['state']='email_allowance_reached';break
            claim=claim_delivery(key,now=now)
            if not claim:continue
            if not attempted:allowance-=1
            try:
                r=client.post('https://api.resend.com/emails',headers={'Authorization':'Bearer '+os.environ['RESEND_API_KEY'],'Idempotency-Key':claim['idempotency_key']},json=claim['payload'])
                if r.is_success and r.json().get('id'):
                    with s.db() as c:c.execute("UPDATE email_deliveries SET status='sent',provider_id=?,lease_until=0 WHERE id=? AND status='sending'",(r.json()['id'],key))
                    result['sent']+=1
                else:
                    status='uncertain' if r.is_success or r.status_code>=500 or r.status_code in (409,429) else 'failed'
                    with s.db() as c:c.execute('UPDATE email_deliveries SET status=?,lease_until=? WHERE id=? AND status=\'sending\'',(status,now+300,key))
                    result['errors']+=1
            except (httpx.HTTPError,ValueError):
                with s.db() as c:c.execute("UPDATE email_deliveries SET status='uncertain',lease_until=? WHERE id=? AND status='sending'",(now+300,key))
                result['errors']+=1
            if owner:time.sleep(.6)
        # Reconcile accepted messages even if a delivery webhook was delayed.
        with s.db() as c:pending=[dict(r) for r in c.execute("SELECT id,provider_id,email FROM email_deliveries WHERE status='sent' ORDER BY created_at LIMIT 5")]
        for row in pending:
            try:
                r=client.get('https://api.resend.com/emails/'+row['provider_id'],headers={'Authorization':'Bearer '+os.environ['RESEND_API_KEY']})
                if r.is_success:
                    event=r.json().get('last_event')
                    if event in ('delivered','bounced','complained','suppressed'):
                        with s.db() as c:
                            c.execute('UPDATE email_deliveries SET status=? WHERE id=? AND status=\'sent\'',('delivered' if event=='delivered' else 'suppressed',row['id']))
                            if event!='delivered':c.execute('INSERT INTO email_suppressions VALUES(?,?,?) ON CONFLICT(email_hash) DO NOTHING',(email_hash(row['email']),event,now))
            except (httpx.HTTPError,ValueError):result['reconciliation_pending']=True
            if owner:time.sleep(.6)
        return result
    finally:
        if owner:client.close()
        with s.db() as c:
            lock=c.execute("SELECT value FROM meta WHERE key='email_worker_lease'").fetchone()
            if lock and json.loads(lock[0])['token']==lease:c.execute("DELETE FROM meta WHERE key='email_worker_lease'")
            c.execute("INSERT INTO meta VALUES('email_worker_result',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps({**result,'at':now}),))

@router.get('/api/cron/email')
def cron(request:Request):
    secret=os.getenv('CRON_SECRET','')
    if not secret or not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+secret):raise HTTPException(401,'Unauthorized')
    return run()
