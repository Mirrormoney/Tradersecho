import time,json,secrets,io,html
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from typing import Literal
from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import HTMLResponse,Response
from pydantic import BaseModel
router=APIRouter()
def core():
 from . import service
 return service

def migrate(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS radar_votes(user_id TEXT REFERENCES accounts(id) ON DELETE CASCADE,ticker TEXT,expires REAL NOT NULL,PRIMARY KEY(user_id,ticker));
 CREATE INDEX IF NOT EXISTS radar_expiry ON radar_votes(expires);
 CREATE TABLE IF NOT EXISTS stock_shares(id TEXT PRIMARY KEY,user_id TEXT REFERENCES accounts(id) ON DELETE CASCADE,payload TEXT NOT NULL,created_at REAL NOT NULL);
 CREATE INDEX IF NOT EXISTS share_owner_time ON stock_shares(user_id,created_at);''')

class Vote(BaseModel):
 active:bool

@router.get('/api/radar')
def radar(request:Request):
 s=core();u=s.account(request,False);now=time.time()
 with s.db() as c:
  counts={r['ticker']:r['n'] for r in c.execute("SELECT v.ticker,COUNT(*) n FROM radar_votes v JOIN accounts a ON a.id=v.user_id WHERE v.expires>? AND a.status='active' AND a.demo=0 GROUP BY v.ticker",(now,)) if r['ticker'] in s.CATALOG}
  mine={r['ticker']:r['expires'] for r in c.execute('SELECT ticker,expires FROM radar_votes WHERE user_id=? AND expires>?',(u['id'],now))} if u else {}
 return {'counts':counts,'mine':mine}

@router.put('/api/radar/{ticker}')
def vote(ticker:str,body:Vote,request:Request):
 s=core();u=s.account(request);now=time.time()
 if u['demo']:raise HTTPException(403,'Sign in with your own account to add a reaction.')
 if ticker not in s.CATALOG:raise HTTPException(404,'Stock not covered.')
 with s.db() as c:
  c.execute('BEGIN IMMEDIATE')
  key='radar:'+u['id'];limit=c.execute('SELECT count,reset FROM attempts WHERE key=?',(key,)).fetchone()
  if limit and limit['reset']>now and limit['count']>=120:raise HTTPException(429,'Please wait before changing more reactions.')
  c.execute('INSERT INTO attempts(key,count,reset) VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=CASE WHEN attempts.reset<=? THEN 1 ELSE attempts.count+1 END,reset=CASE WHEN attempts.reset<=? THEN excluded.reset ELSE attempts.reset END',(key,now+3600,now,now))
  # Atomic upsert keeps the original expiry on repeated requests.
  if body.active:c.execute('INSERT INTO radar_votes(user_id,ticker,expires) VALUES(?,?,?) ON CONFLICT(user_id,ticker) DO UPDATE SET expires=CASE WHEN radar_votes.expires<=? THEN excluded.expires ELSE radar_votes.expires END',(u['id'],ticker,now+86400,now))
  else:c.execute('DELETE FROM radar_votes WHERE user_id=? AND ticker=?',(u['id'],ticker))
 return radar(request)

class Share(BaseModel):
 ticker:str
 window:Literal['intraday','1','7','30']='1'

@router.post('/api/shares')
def create_share(body:Share,request:Request):
 s=core();u=s.account(request)
 if u['demo']:raise HTTPException(403,'Only collected market activity can be shared.')
 if body.ticker not in s.CATALOG:raise HTTPException(404,'Stock not covered.')
 if body.window=='intraday':
  from .live_collection import intraday
  data=intraday(request)
 else:data=s.rankings(request,window=int(body.window),source='x',scope='market')
 row=next((r for r in data['rows'] if r['ticker']==body.ticker),None)
 if not row:raise HTTPException(403,'This stock is outside your current ranking access.')
 if row.get('mentions') is None or row.get('state','measured')!='measured':raise HTTPException(409,'Wait for a completed attention check before sharing.')
 payload={k:row.get(k) for k in ['ticker','name','mentions','change','heat','spark']}
 payload.update(window=body.window,as_of=row.get('as_of') or data['as_of'],comparison_complete=row.get('comparison_complete',body.window=='intraday'),coverage_hours=row.get('coverage_hours'))
 encoded=json.dumps(payload,sort_keys=True);now=time.time()
 with s.db() as c:
  c.execute('BEGIN IMMEDIATE')
  existing=c.execute('SELECT id FROM stock_shares WHERE user_id=? AND payload=? ORDER BY created_at DESC LIMIT 1',(u['id'],encoded)).fetchone()
  if existing:ident=existing['id']
  else:
   if c.execute('SELECT COUNT(*) FROM stock_shares WHERE user_id=? AND created_at>?',(u['id'],now-86400)).fetchone()[0]>=30:raise HTTPException(429,'You can create up to 30 snapshots per day.')
   ident=secrets.token_urlsafe(18)
   c.execute('INSERT INTO stock_shares VALUES(?,?,?,?)',(ident,u['id'],encoded,now))
 return {'url':s.ORIGIN+'/share/'+ident,'image_url':s.ORIGIN+'/api/shares/'+ident+'/image.png'}

def snapshot(ident):
 with core().db() as c:r=c.execute('SELECT payload FROM stock_shares WHERE id=?',(ident,)).fetchone()
 if not r:raise HTTPException(404,'Snapshot not found.')
 return json.loads(r['payload'])

def label(p):return {'intraday':'Intraday · 3 hours','1':'24 hours','7':'7 days','30':'30 days'}[p['window']]
def stamp(p):
 dt=datetime.fromtimestamp(p['as_of'],timezone.utc)
 return ' / '.join(dt.astimezone(ZoneInfo(z)).strftime('%d %b %H:%M %Z') for z in ['America/New_York','Europe/Berlin'])

@router.get('/api/shares/{ident}/image.png')
def share_image(ident:str):
 from PIL import Image,ImageDraw,ImageFont
 p=snapshot(ident);im=Image.new('RGB',(1200,630),'#102923');d=ImageDraw.Draw(im)
 def text(x,y,t,size=30,color='#f3f6ef'):d.text((x,y),str(t),font=ImageFont.load_default(size=size),fill=color)
 d.ellipse((55,45,125,115),outline='#a7e7b1',width=2);d.line([(65,82),(78,82),(86,62),(102,99),(110,78),(120,78)],fill='#a7e7b1',width=3)
 text(145,48,'tradersecho',38);text(145,94,'ATTENTION · PERSPECTIVE · COMMUNITY',15,'#a7e7b1')
 text(60,160,'$'+p['ticker'],68);text(60,240,p['name'][:55],30);text(60,305,label(p),25,'#a7e7b1')
 text(60,365,f"{p['mentions']:,} mentions",44)
 growth='Comparison unavailable' if p['change'] is None else f"{p['change']:+g}% vs previous period"
 text(60,432,growth,27);text(60,490,f"Attention heat: {p['heat']}",24)
 text(60,548,stamp(p),21,'#a7e7b1');text(60,585,'Saved snapshot · Attention is not a price signal · tradersecho.com',18)
 values=p.get('spark') or []
 if len(values)>1 and max(values)>0:
  points=[(720+i*410/(len(values)-1),460-v/max(values)*130) for i,v in enumerate(values)]
  d.line(points,fill='#a7e7b1',width=5);text(720,490,'Mention activity',20,'#a7e7b1')
 out=io.BytesIO();im.save(out,'PNG');return Response(out.getvalue(),media_type='image/png',headers={'Cache-Control':'public, max-age=86400'})

@router.get('/share/{ident}',response_class=HTMLResponse)
def share_page(ident:str):
 p=snapshot(ident);esc=lambda x:html.escape(str(x),quote=True);origin=core().ORIGIN;url=origin+'/share/'+ident;image=origin+'/api/shares/'+ident+'/image.png'
 title=f"${p['ticker']} · {label(p)} attention snapshot"
 description=f"{p['mentions']:,} mentions · Heat {p['heat']} · {stamp(p)}"
 return HTMLResponse(f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)} | Traders Echo</title><meta name="description" content="{esc(description)}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:image" content="{esc(image)}"><meta property="og:url" content="{esc(url)}"><meta name="twitter:card" content="summary_large_image"><meta name="robots" content="noindex"><style>body{{margin:0;background:#f4f5ee;color:#163c30;font-family:system-ui}}main{{max-width:850px;margin:40px auto;padding:24px}}img{{width:100%;border-radius:24px}}a{{color:inherit}}.cta{{display:inline-block;background:#bde5a9;padding:14px 22px;border-radius:12px;text-decoration:none;margin:8px 8px 0 0}}p{{line-height:1.6}}</style></head><body><main><a href="/">Traders Echo</a><h1>{esc(title)}</h1><p>{esc(description)}</p><img src="{esc(image)}" alt="{esc(title+' — '+description)}"><p>A saved snapshot of collected X attention, not a live quote or investment recommendation. Coverage and sampling can be incomplete. Reactions do not influence these rankings.</p><a class="cta" href="/marketpulse?view=market&amp;ticker={esc(p['ticker'])}">Explore ${esc(p['ticker'])}</a><a class="cta" href="/plans">Explore membership</a><p>Full research and other stock views follow normal membership access.</p></main></body></html>''')
