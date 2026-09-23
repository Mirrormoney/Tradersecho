"""Durable owner-only operational emails, driven by the hosted email cron."""
import hashlib
import json
import os
import time
from datetime import datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Request
from .email_brand import message

router = APIRouter()
PREFIX = 'owner_mail:'
BERLIN = ZoneInfo('Europe/Berlin')

def core():
    from . import service
    return service

def get(c, key, default=None):
    row = c.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default

def save(c, key, value):
    c.execute('INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value)))

def enqueue_signup(c, uid, now):
    # Same transaction as account creation: no lost alerts and no alerts for rolled-back signups.
    key = PREFIX + 'signup:' + uid
    save(c, key, {'kind':'signup', 'uid':uid, 'created':now, 'status':'pending', 'next':0})

def weekly_slot(now):
    local = datetime.fromtimestamp(now, BERLIN)
    end = (local - timedelta(days=(local.weekday()-6)%7)).replace(hour=18, minute=0, second=0, microsecond=0)
    if end > local:
        end -= timedelta(days=7)
    return (end-timedelta(days=7)).timestamp(), end.timestamp()

def report(start, end):
    with core().db() as c:
        def scalar(sql, args=()):
            return c.execute(sql, args).fetchone()[0] or 0
        users = scalar('SELECT COUNT(*) FROM accounts WHERE demo=0')
        new = scalar('SELECT COUNT(*) FROM accounts WHERE demo=0 AND created_at>=? AND created_at<?', (start,end))
        verified = scalar('SELECT COUNT(*) FROM accounts WHERE demo=0 AND email_verified=1')
        views = scalar('SELECT COUNT(*) FROM traffic_events WHERE ts>=? AND ts<?', (start,end))
        visitors = scalar('SELECT COUNT(DISTINCT visitor) FROM traffic_events WHERE ts>=? AND ts<?', (start,end))
        posts = scalar("SELECT COUNT(*) FROM posts WHERE source='x' AND ts>=? AND ts<?", (start,end))
        published = scalar("SELECT COUNT(*) FROM social_editions WHERE status='published' AND updated>=? AND updated<?", (start,end))
        jobs = [dict(r) for r in c.execute('SELECT status,COUNT(*) n FROM collection_jobs WHERE updated_at>=? AND updated_at<? GROUP BY status',(start,end))]
        emails = [dict(r) for r in c.execute('SELECT status,COUNT(*) n FROM email_deliveries WHERE first_attempt>=? AND first_attempt<? GROUP BY status',(start,end))]
        x = [dict(r) for r in c.execute('SELECT kind,COUNT(*) n,SUM(COALESCE(actual_estimate,reserved)) cost FROM x_spend WHERE ts>=? AND ts<? GROUP BY kind',(start,end))]
        ai = [dict(r) for r in c.execute('SELECT reserved,actual,usage FROM ai_sentiment_spend WHERE ts>=? AND ts<?',(start,end))]
        heartbeat = get(c,'scheduler_seen')
    tokens = 0
    known = 0
    for row in ai:
        usage = json.loads(row['usage'] or '{}')
        if usage.get('total_tokens') is not None:
            tokens += int(usage['total_tokens']); known += 1
        elif usage.get('prompt_tokens') is not None and usage.get('completion_tokens') is not None:
            tokens += int(usage['prompt_tokens']) + int(usage['completion_tokens']); known += 1
    ai_cost = sum(r['actual'] if r['actual'] is not None else r['reserved'] for r in ai)
    x_cost = sum(r['cost'] or 0 for r in x)
    return {'users':users,'new':new,'verified':verified,'views':views,'visitor_days':visitors,'posts':posts,'published':published,'jobs':jobs,'emails':emails,'x':x,'ai_requests':len(ai),'ai_tokens':tokens,'ai_usage_known':known,'ai_cost':ai_cost,'x_cost':x_cost,'estimated_total':ai_cost+x_cost,'scheduler':heartbeat}

def weekly_content(start, end):
    data = report(start,end)
    period = datetime.fromtimestamp(start,BERLIN).strftime('%d %b') + ' – ' + datetime.fromtimestamp(end,BERLIN).strftime('%d %b %Y')
    rows = [('New accounts',data['new']),('Total accounts / verified',f"{data['users']} / {data['verified']}"),('Tracked page views',data['views']),('Visitor-days (not unique weekly people)',data['visitor_days']),('Stored X posts dated in this period',data['posts']),('Published X editions',data['published']),('AI requests',data['ai_requests']),('Reported AI tokens',f"{data['ai_tokens']:,} ({data['ai_usage_known']}/{data['ai_requests']} requests have usage)")]
    rows += [('X · '+r['kind'],f"${(r['cost'] or 0):.3f} · {r['n']} ledger entries") for r in data['x']]
    hosting = 20 * 12 / 365 * ((end-start)/86400)
    rows += [('X estimated usage',f"${data['x_cost']:.2f}"),('AI usage / outstanding reservations',f"${data['ai_cost']:.2f}"),('Total metered estimate',f"${data['estimated_total']:.2f}"),('Vercel base plan · allocated estimate',f'${hosting:.2f} ($20/month assumption)'),('Known-cost subtotal · estimate',f"${data['estimated_total']+hosting:.2f}")]
    notes = ('Costs are application-ledger estimates, not invoices. Missing final charges retain conservative reservations. X ledger entries are not a count of tweets. '
             'The Vercel base allocation assumes the owner’s $20/month plan, before tax; additional seats or usage are excluded. Database, email, domain and Stripe charges are not included: their invoices are not connected. '
             'Budget ceilings remain $250/month for X and $20/month for AI; these are limits, not subscription charges. '
             'Page views exclude administrators and visitors who opt out. Visitor identifiers rotate daily. '
             'Account totals are current; activity covers the seven-day reporting window. Retained job states and X editions do not represent every retry or follow-up reply.')
    health = 'Collection job states: ' + (', '.join(f"{r['status']}: {r['n']}" for r in data['jobs']) or 'none recorded')
    delivery = 'Subscriber / trial email states: ' + (', '.join(f"{r['status']}: {r['n']}" for r in data['emails']) or 'none attempted')
    text = 'Your weekly operations overview · '+period+' (Berlin time, 18:00 to 18:00)\n\n'+'\n'.join(f'{k}: {v}' for k,v in rows)+'\n\n'+health+'\n'+delivery+'\n\n'+notes+'\nhttps://tradersecho.com/admin'
    body = '<p style="line-height:1.7">'+escape(period)+' · Your weekly operations overview</p><table role="presentation" width="100%" cellspacing="0">'
    body += ''.join('<tr><td style="padding:12px;border-bottom:1px solid #dce7df">'+escape(str(k))+'</td><td style="padding:12px;border-bottom:1px solid #dce7df;text-align:right;font-weight:bold">'+escape(str(v))+'</td></tr>' for k,v in rows)
    body += '</table><p style="line-height:1.8">'+escape(health)+'<br>'+escape(delivery)+'</p><p style="font-size:12px;line-height:1.7;color:#52665b">'+escape(notes)+'</p><p><a href="https://tradersecho.com/admin">Open Administration →</a></p>'
    return message('Traders Echo · Weekly performance · '+period,text,body)

def run(now=None, client=None):
    now = time.time() if now is None else now
    if os.getenv('VERCEL_ENV','production') != 'production' or os.getenv('BILLING_SANDBOX','false').lower() == 'true':
        return {'state':'disabled_nonproduction'}
    recipient = os.getenv('OWNER_ALERT_EMAIL') or os.getenv('AI_ALERT_EMAIL')
    if not recipient or not os.getenv('RESEND_API_KEY'):
        return {'state':'not_configured'}
    s = core(); result = {'state':'ok','sent':0,'errors':0}
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        activated = get(c,'owner_mail_enabled_at')
        if activated is None:
            activated = now; save(c,'owner_mail_enabled_at',now)
        start,end = weekly_slot(now)
        key = PREFIX+'weekly:'+str(int(end))
        if end >= activated and not get(c,key):
            save(c,key,{'kind':'weekly','start':start,'end':end,'created':now,'status':'pending','next':0})
        from .research_health import snapshot as research_health
        health=research_health(c,now) if os.getenv('RESEARCH_DRIVE_ENABLED')=='true' or os.getenv('RESEARCH_IMAP_PASSWORD') else {'issues':[],'checked_at':now}
        save(c,'research_health',health)
        alert_key=PREFIX+'research:'+datetime.fromtimestamp(now,BERLIN).date().isoformat()+(':failure' if health.get('operational_issues') else ':review')
        if health.get('operational_issues') and not get(c,alert_key):
            save(c,alert_key,{'kind':'research','issues':health['operational_issues'],'health':health,'created':now,'status':'pending','next':0})
        queue = [(r['key'],json.loads(r['value'])) for r in c.execute('SELECT key,value FROM meta WHERE key LIKE ?',(PREFIX+'%',))]
    owner = client is None; client = client or httpx.Client(timeout=10)
    try:
        # Ten owner emails/day reserves capacity for security messages and prevents signup spam.
        today = datetime.fromtimestamp(now,BERLIN).date().isoformat()
        for key,event in sorted(queue,key=lambda r:(r[1]['kind']!='weekly',r[1]['created'])):
            if result['sent']+result['errors'] >= 2: break
            with s.db() as c:
                c.execute('BEGIN IMMEDIATE')
                event = get(c,key)
                if event['status'] not in ('pending','sending') or event.get('next',0)>now: continue
                if event['kind']=='research' and not health.get('operational_issues'):
                    event['status']='cancelled';save(c,key,event);continue
                if event.get('first') and now-event['first']>=23*3600:
                    event['status']='needs_review';save(c,key,event);continue
                count = get(c,'owner_mail_allowance:'+today,0)
                if not event.get('first') and count>=10: continue
                if not event.get('payload'):
                    if event['kind']=='weekly':
                        # Render outside this transaction below; lease protects concurrent workers.
                        content = None
                    elif event['kind']=='research':
                        health=event.get('health',{})
                        review_only='operational_issues' in health and not health['operational_issues']
                        title='Research import - Notes held for review' if review_only else 'Research import needs attention'
                        intro='Import workers are healthy. Individual notes were held for review; other documents continue processing.' if review_only else 'An import worker or queue needs attention. See the recorded checks below.'
                        progress=health.get('recent',{})
                        detail='\n'.join(str(r['count'])+' - '+r['reason'] for r in health.get('review_reasons',[]))
                        content=message('Traders Echo - '+title,intro+'\n\n'+'\n'.join(event['issues'])+'\n\nPast 24 hours: '+str(progress.get('draft',0))+' validated summaries; '+str(progress.get('no_match',0))+' notes with no covered findings.\n\n'+detail+'\n\nIndividual held notes are skipped automatically; you do not need to approve them to keep imports running. Check the worker status above; reconnect credentials or replenish credits only if the status requests it.\nStatus: https://tradersecho.com/admin')
                    else:
                        user = c.execute('SELECT email,display_name FROM accounts WHERE id=? AND demo=0',(event['uid'],)).fetchone()
                        if not user:
                            event['status']='cancelled';save(c,key,event);continue
                        content = message('Traders Echo · New account',f"A new account was created.\n\nUsername: {user['display_name']}\nEmail: {user['email']}\n\nRegistration does not mean the email is verified or a payment has been made.\n\nManage accounts: https://tradersecho.com/admin")
                    if content: event['payload']={'from':os.getenv('ACCOUNT_EMAIL_FROM','Traders Echo <info@tradersecho.com>'),'to':[recipient],**content}
                if not event.get('first'):
                    event['first']=now;save(c,'owner_mail_allowance:'+today,count+1)
                event.update(status='sending',next=now+180,attempts=event.get('attempts',0)+1)
                save(c,key,event)
            try:
                if not event.get('payload'):
                    event['payload']={'from':os.getenv('ACCOUNT_EMAIL_FROM','Traders Echo <info@tradersecho.com>'),'to':[recipient],**weekly_content(event['start'],event['end'])}
                    with s.db() as c: save(c,key,event)
                response = client.post('https://api.resend.com/emails',headers={'Authorization':'Bearer '+os.environ['RESEND_API_KEY'],'Idempotency-Key':hashlib.sha256(key.encode()).hexdigest()},json=event['payload'])
                if response.is_success and response.json().get('id'):
                    event.update(status='sent',provider_id=response.json()['id'],sent_at=now)
                    event.pop('payload',None)
                    result['sent']+=1
                else:
                    event['status']='pending' if response.status_code>=500 or response.status_code in (409,429) or response.is_success else 'needs_review'
                    result['errors']+=1
            except Exception:
                event['status']='pending';result['errors']+=1
            with s.db() as c: save(c,key,event)
        with s.db() as c:
            states = [json.loads(r[0])['status'] for r in c.execute('SELECT value FROM meta WHERE key LIKE ?',(PREFIX+'%',))]
            result.update(pending=states.count('pending')+states.count('sending'),needs_review=states.count('needs_review'),at=now)
            save(c,'owner_mail_worker',result)
        return result
    finally:
        if owner: client.close()

@router.get('/api/admin/owner-emails')
def status(request:Request):
    from .community import staff
    staff(request)
    with core().db() as c:
        return {'configured':bool((os.getenv('OWNER_ALERT_EMAIL') or os.getenv('AI_ALERT_EMAIL')) and os.getenv('RESEND_API_KEY')),'schedule':'Sunday 18:00 Europe/Berlin','worker':get(c,'owner_mail_worker')}
