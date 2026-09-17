"""Hourly credit checks and deduplicated operational owner emails."""
import hashlib,json,os,time
from datetime import datetime,timezone
import httpx

def check(worker,token=None,client=None):
    from . import service as s
    recipient=os.getenv('AI_ALERT_EMAIL','')
    if not recipient:return {'state':'not_configured'}
    now=time.time();month=datetime.now(timezone.utc).strftime('%Y-%m')
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        previous=c.execute("SELECT value FROM meta WHERE key='ai_monitor_checked'").fetchone()
        if previous and now-float(previous[0])<3600:return {'state':'cached'}
        c.execute("INSERT INTO meta VALUES('ai_monitor_checked',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(now),))
        spent=c.execute('SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM ai_sentiment_spend WHERE month=?',(month,)).fetchone()[0]
    budget=min(10,max(0,float(os.getenv('SENTIMENT_AI_MONTHLY_USD','10'))))
    alerts=[];snapshot={'checked_at':now,'spent':spent,'budget':budget,'balance':None,'email_status':'no_alert_needed'}
    if spent+.03>=budget:alerts.append(('budget100:'+month,'AI monthly allowance reached. New analysis pauses until the next month or a reviewed budget change.'))
    elif spent>=budget*.8:alerts.append(('budget80:'+month,'AI analysis has used 80% of its monthly allowance.'))
    owned=client is None;client=client or httpx.Client(timeout=12)
    try:
        try:
            credential=token or os.getenv('AI_GATEWAY_API_KEY') or os.getenv('VERCEL_OIDC_TOKEN')
            response=client.get('https://ai-gateway.vercel.sh/v1/credits',headers={'Authorization':'Bearer '+(credential or '')})
            response.raise_for_status();snapshot['balance']=float(response.json()['balance'])
            if snapshot['balance']<=2:alerts.append(('credits:'+datetime.now(timezone.utc).date().isoformat(),'AI Gateway credit balance is low. Please refill credits in Vercel; automatic purchases remain off.'))
        except (httpx.HTTPError,ValueError,KeyError):
            snapshot['credit_check']='unavailable'
            alerts.append(('credits_check:'+datetime.now(timezone.utc).date().isoformat(),'AI Gateway balance could not be checked. Please review access and credits in Vercel.'))
        if worker.get('state') in ('provider_paused','configuration_required') or worker.get('state','').startswith('AI provider HTTP'):
            alerts.append(('provider:'+datetime.now(timezone.utc).date().isoformat(),'AI sentiment processing is paused by an access, credit or provider problem. Existing results remain available.'))
        for key,message in alerts:
            marker='ai_alert:'+key
            with s.db() as c:
                if c.execute('SELECT value FROM meta WHERE key=?',(marker,)).fetchone():continue
            if not os.getenv('RESEND_API_KEY'):snapshot['email_status']='not_configured';continue
            text=message+f'\n\nMonthly analysis usage: ${spent:.3f} / ${budget:.2f}.\nGateway balance: '+('unavailable' if snapshot['balance'] is None else f"${snapshot['balance']:.2f}")+'\n\nReview: https://vercel.com/sven-mais-projects/~/ai-gateway\nAdmin: https://tradersecho.com/admin\nNo automatic credit purchase was made.'
            from .email_brand import message as branded_message
            try:
                response=client.post('https://api.resend.com/emails',headers={'Authorization':'Bearer '+os.environ['RESEND_API_KEY'],'Idempotency-Key':'ai-alert-'+hashlib.sha256((recipient+key).encode()).hexdigest()},json={'from':os.getenv('ACCOUNT_EMAIL_FROM','Tradersecho <info@tradersecho.com>'),'to':[recipient],**branded_message('Tradersecho: AI budget or credit alert',text)})
                response.raise_for_status()
                with s.db() as c:c.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(marker,str(now)))
                snapshot['email_status']='sent'
            except httpx.HTTPError:snapshot['email_status']='delivery_failed'
    finally:
        if owned:client.close()
    with s.db() as c:c.execute("INSERT INTO meta VALUES('ai_monitor_status',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(snapshot),))
    return snapshot
