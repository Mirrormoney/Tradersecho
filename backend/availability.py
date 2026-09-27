"""Small hosted availability probe; alerts still work during database outages."""
import hashlib
import hmac
import logging
import os
import time
import httpx
from fastapi import APIRouter, HTTPException, Request
from .email_brand import message

router=APIRouter()
BASE='https://tradersecho.com'

def probe(client):
    problems=[]
    for path,method in [('/login','GET'),('/api/health','GET'),('/api/auth/login','POST')]:
        try:
            response=client.request(method,BASE+path,**({'json':{}} if method=='POST' else {}))
            if path=='/login':
                valid=response.status_code==200 and 'id="root"' in response.text
            elif path=='/api/health':
                valid=response.status_code==200 and response.json().get('ok') is True
            else:
                # Invalid schema must reach FastAPI validation, never create a session.
                valid=response.status_code==422 and isinstance(response.json().get('detail'),list)
            if not valid:problems.append(path)
        except (httpx.HTTPError,ValueError):problems.append(path)
    return problems

def run(now=None,client=None,sleep=time.sleep):
    if os.getenv('VERCEL_ENV')!='production':return {'state':'preview_disabled'}
    now=time.time() if now is None else now
    if client is None:
        with httpx.Client(timeout=8,follow_redirects=False) as client:return run(now,client,sleep)
    problems=probe(client)
    if not problems:return {'state':'ok'}
    sleep(2)
    problems=probe(client)
    if not problems:return {'state':'recovered'}
    logging.error('Availability probe failed twice: %s',','.join(problems))
    recipient=os.getenv('OWNER_ALERT_EMAIL') or os.getenv('AI_ALERT_EMAIL')
    if not recipient or not os.getenv('RESEND_API_KEY'):return {'state':'failed','alert':'not_configured','paths':problems}
    # Stable hourly message and provider idempotency key: no DB dependency or email storm.
    bucket=int(now//3600)
    payload={'from':os.getenv('ACCOUNT_EMAIL_FROM','Traders Echo <info@tradersecho.com>'),'to':[recipient],**message(
        'Traders Echo - Website availability needs attention',
        'The hosted website check failed twice. Login, API routing or database access may be affected. The check will continue every five minutes. No account settings or data were changed. Review Vercel runtime logs and https://tradersecho.com/api/health . Check window: '+str(bucket))}
    try:
        response=client.post('https://api.resend.com/emails',headers={'Authorization':'Bearer '+os.environ['RESEND_API_KEY'],'Idempotency-Key':hashlib.sha256(('availability:'+str(bucket)).encode()).hexdigest()},json=payload)
        delivered=response.is_success and bool(response.json().get('id'))
    except (httpx.HTTPError,ValueError):delivered=False
    return {'state':'failed','alert':'sent' if delivered else 'delivery_failed','paths':problems}

@router.get('/api/cron/availability')
def cron(request:Request):
    secret=os.getenv('CRON_SECRET','')
    if not secret or not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+secret):raise HTTPException(401,'Unauthorized')
    return run()
