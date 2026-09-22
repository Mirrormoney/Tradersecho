"""Run bounded batches against a protected preview. Secrets come only from env."""
import os,time
import httpx

def main():
    url=os.environ['TRADERSECHO_URL'].rstrip('/')
    if not url.startswith('https://'):raise SystemExit('HTTPS preview URL required.')
    headers={'Authorization':'Bearer '+os.environ['CRON_SECRET']}
    if os.getenv('VERCEL_AUTOMATION_BYPASS_SECRET'):
        headers['x-vercel-protection-bypass']=os.environ['VERCEL_AUTOMATION_BYPASS_SECRET']
    with httpx.Client(timeout=150,follow_redirects=False) as client:
        for _ in range(150):
            response=client.get(url+'/api/cron/collect',headers=headers)
            if response.status_code!=200:raise SystemExit(f'Batch HTTP {response.status_code}; stopping without retries.')
            result=response.json()
            if result.get('paused') or result.get('errors'):raise SystemExit(result.get('reason') or 'Collection reported an error; review Admin → Collection.')
            print('Completed jobs:',result.get('completed',0),flush=True)
            if not result.get('completed'):return
            time.sleep(2)
    raise SystemExit('Batch limit reached; inspect remaining jobs.')

if __name__=='__main__':main()
