"""Small hosted availability probe; alerts still work during database outages."""
import hashlib
import hmac
import logging
import json
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
        started=time.monotonic();status=None;failure=None
        try:
            response=client.request(method,BASE+path,**({'json':{}} if method=='POST' else {}))
            status=response.status_code
            if path=='/login':
                valid=response.status_code==200 and 'id="root"' in response.text
            elif path=='/api/health':
                valid=response.status_code==200 and isinstance(response.json(),dict) and response.json().get('ok') is True
            else:
                # Invalid schema must reach FastAPI validation, never create a session.
                valid=response.status_code==422 and isinstance(response.json(),dict) and isinstance(response.json().get('detail'),list)
            if not valid:failure='unexpected_response'
        except (httpx.HTTPError,ValueError) as exc:failure=type(exc).__name__
        if failure:
            problems.append(path)
            logging.warning('Availability probe detail: %s',json.dumps({'path':path,'status':status,'failure':failure,'elapsed_ms':round((time.monotonic()-started)*1000)}))
    return problems

def run(now=None,client=None,sleep=time.sleep):
    if os.getenv('VERCEL_ENV')!='production':return {'state':'preview_disabled'}
    now=time.time() if now is None else now
    if client is None:
        with httpx.Client(timeout=httpx.Timeout(10,connect=5),transport=httpx.HTTPTransport(retries=1),follow_redirects=False) as client:return run(now,client,sleep)
    problems=probe(client)
    if not problems:return {'state':'ok'}
    for delay in (2,8):
        sleep(delay)
        problems=probe(client)
        if not problems:
            logging.info('Availability recovered after retry')
            return {'state':'recovered'}
    logging.error('Availability probe failed after three checks: %s',','.join(problems))
    recipient=os.getenv('OWNER_ALERT_EMAIL') or os.getenv('AI_ALERT_EMAIL')
    if not recipient or not os.getenv('RESEND_API_KEY'):return {'state':'failed','alert':'not_configured','paths':problems}
    # Stable hourly message and provider idempotency key: no DB dependency or email storm.
    bucket=int(now//3600)
    payload={'from':os.getenv('ACCOUNT_EMAIL_FROM','Traders Echo <info@tradersecho.com>'),'to':[recipient],**message(
        'Traders Echo - Website availability needs attention',
        'The hosted website check failed after three checks with automatic connection retries. Login, API routing or database access may be affected. The check will continue every five minutes. No account settings or data were changed. The runtime logs include the endpoint, response status or connection error, and elapsed time. Review Vercel runtime logs and https://tradersecho.com/api/health . Check window: '+str(bucket))}
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
