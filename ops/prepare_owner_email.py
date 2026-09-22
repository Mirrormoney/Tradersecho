"""Prepare a personalized owner-only email test. Never sends email."""
import json,os,sys
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env.local')
os.environ['VERCEL']='1'
os.environ['DEMO_ENABLED']='false'
os.environ['TRADERSECHO_SCHEMA']='public'
sys.path.insert(0,str(ROOT))
from backend import service,digest,newsletter

def render(report):
    return newsletter.render(report,origin=service.ORIGIN)

if __name__=='__main__':
    if len(sys.argv)!=2:raise ValueError('Provide a private output JSON path')
    out=Path(sys.argv[1])
    with service.db() as c:
        owners=[dict(r) for r in c.execute("SELECT * FROM accounts WHERE role='owner' AND status='active'")]
    if len(owners)!=1:raise ValueError('Exactly one active owner required')
    owner=owners[0];report=digest.personalized(digest.build(),owner)
    origin=os.getenv('APP_ORIGIN','https://tradersecho-preview-sven-mais-projects.vercel.app')
    email=newsletter.render(report,owner['display_name'],origin)
    payload={'from':'Tradersecho <newsletter@tradersecho.com>','to':[owner['email']],'reply_to':'info@tradersecho.com',**email}
    out.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    out.with_suffix('.html').write_text(newsletter.render(report,owner['display_name'],origin,preview=True)['html'],encoding='utf-8')
    print(json.dumps({'subject':email['subject'],'stocks':report['tracked_stocks'],'preview':str(out.with_suffix('.html'))}))
