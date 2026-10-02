"""Approved October 2 ranked-post artwork, rendered locally without AI calls."""
from pathlib import Path
from functools import lru_cache
from io import BytesIO
import re
from PIL import Image, ImageDraw, ImageFont
ASSETS=Path(__file__).with_name('social_assets')

def fit(d,xy,s,width,size,c='#f2f6ee',b=False):
 while size>10 and d.textlength(s,font=ft(size,b))>width:size-=1
 txt(d,xy,s,size,c,b)

def finish(im):
 out=BytesIO();im.save(out,format='PNG');data=out.getvalue()
 if len(data)>5_000_000:raise ValueError('Full image exceeds upload allowance; no text was clipped')
 return data

def research_label(row):
 # Only classify explicit source language. No inferred ratings or promotional claims.
 if row.get('link_type')=='sector_readthrough':return 'SECTOR READ-THROUGH'
 s=row.get('summary','')
 if re.search(r'\binitiat(?:e[sd]?|ing|ion)\b',s,re.I):return 'COVERAGE INITIATION'
 if re.search(r'\banalyst day\b',s,re.I):return 'ANALYST DAY'
 if re.search(r'\b(earnings|guidance)\b',s,re.I):return 'EARNINGS & OUTLOOK'
 return 'RESEARCH UPDATE'

G='#c4f27a'; W='#f2f6ee'; M='#9cb5aa'; BG='#081514'
@lru_cache(maxsize=64)
def ft(n,b=False):
 try:
  f=ImageFont.truetype(str(ASSETS/'Manrope.ttf'),n)
 except OSError:
  from .social_font import FONT
  import base64
  try:f=ImageFont.truetype(BytesIO(base64.b64decode(FONT)),n)
  except OSError:return ImageFont.load_default(size=n)
 try:f.set_variation_by_axes([700 if b else 400])
 except (OSError,AttributeError):pass
 return f
def txt(d,xy,s,n=24,c=W,b=False):d.text(xy,s,font=ft(n,b),fill=c)
def wrap(d,s,w,n):
 # Normalize legacy Windows punctuation before measuring and drawing text.
 s=s.translate({i:bytes([i]).decode('cp1252',errors='replace') for i in range(128,160)})
 lines=[];line=''
 for word in s.split():
  t=(line+' '+word).strip()
  if d.textlength(t,font=ft(n))>w and line:lines.append(line);line=word
  else:line=t
 if line:lines.append(line)
 return lines
def para(d,x,y,s,w,n=25):
 for line in wrap(d,s,w,n):txt(d,(x,y),line,n);y+=n+10
 return y
def base(h,kicker,title,sub,date):
 im=Image.new('RGB',(1200,h),BG);d=ImageDraw.Draw(im)
 for y in range(h):
  v=max(0,1-y/700);d.line((0,y,1200,y),fill=(8+int(v*6),21+int(v*14),20+int(v*9)))
 # subtle diagonal circuit lines, deliberately decorative, not market data
 for i in range(7):
  x=770+i*75;d.line([(x,0),(x,90+i*12),(x-85,175+i*12),(x-85,275)],fill='#243c31',width=2)
  d.ellipse((x-90,272,x-80,282),fill='#3a5739')
 d.ellipse((48,44,98,94),outline='#557246',width=2)
 d.line([(53,70),(63,70),(68,56),(79,83),(85,68),(94,68)],fill=G,width=2)
 txt(d,(112,40),'tradersecho',30,b=True)
 txt(d,(112,79),'ATTENTION / PERSPECTIVE / COMMUNITY',11,c=M)
 txt(d,(895,55),date,18,c=M)
 d.line((48,125,1152,125),fill='#30463a',width=1)
 txt(d,(48,152),kicker,17,c=G,b=True)
 fit(d,(45,185),title,1105,53,b=True)
 fit(d,(48,259),sub,1104,21,c=M)
 return im,d
def logo(im,d,t,x,y,size=74):
 d.rounded_rectangle((x-4,y-4,x+size+4,y+size+4),radius=15,fill='#020807',outline='#425348',width=2)
 path=ASSETS/'logos'/(t+'.png')
 if not path.is_file():
  fit(d,(x+8,y+size//3),t,size-16,24,c=G,b=True)
  return
 a=Image.open(path).convert('RGB').resize((size,size),Image.Resampling.LANCZOS)
 mask=Image.new('L',(size,size));ImageDraw.Draw(mask).rounded_rectangle((0,0,size-1,size-1),radius=11,fill=255)
 im.paste(a,(x,y),mask)
def badge(d,x,y,s,col=G):
 width=int(d.textlength(s,font=ft(17,True)))+28
 d.rounded_rectangle((x,y,x+width,y+32),radius=8,fill='#263e2c')
 txt(d,(x+14,y+4),s,17,c=col,b=True)
def footer(d,y,label):
 d.line((48,y,1152,y),fill='#30463a')
 fit(d,(48,y+20),label,780,18,c=M)
 txt(d,(858,y+17),'tradersecho.com',25,c=G,b=True)
 txt(d,(48,y+57),'Context for your research. Not investment advice.',13,c=M)

def research_card(report):
 from .social_research import full_tile_text
 rows=report['rows'][:3]
 probe=ImageDraw.Draw(Image.new('RGB',(1,1)))
 layouts=[]
 for r in rows:
  names=wrap(probe,r['name'],780,19)
  paragraphs=[wrap(probe,s,1000,25) for s in full_tile_text(r)]
  # Extra room for long company names; summaries are always fully wrapped.
  offset=max(0,len(names)-1)*29
  height=188+offset+sum(len(lines)*35+12 for lines in paragraphs)+32
  layouts.append((r,names,paragraphs,offset,height))
 h=335+sum(v[4]+20 for v in layouts)+125
 if h>8000:raise ValueError('Full research artwork exceeds readable image size; no text was clipped')
 im,d=base(h,'RESEARCH / BEFORE THE BELL','Three names. The bigger picture.',
           'Fresh perspectives across the AI investment chain.',report.get('date',''))
 y=322
 for i,(r,names,paragraphs,offset,ch) in enumerate(layouts):
  d.rounded_rectangle((48,y,1152,y+ch),radius=24,fill=('#182c23' if i==0 else '#10231e'),outline=('#718d4e' if i==0 else '#304b3c'),width=2)
  d.rounded_rectangle((48,y+22,53,y+ch-22),radius=2,fill=G if i==0 else '#587642')
  logo(im,d,r['ticker'],76,y+26)
  txt(d,(170,y+17),'$'+r['ticker'],39,b=True)
  for j,line in enumerate(names):txt(d,(172,y+70+j*29),line,19,c=M)
  txt(d,(1050,y+23),f'0{i+1}',41,c=G,b=True)
  badge(d,76,y+119+offset,research_label(r))
  fit(d,(430,y+122+offset),r.get('firm') or 'Published research',645,22,c=M)
  yy=y+170+offset
  for lines in paragraphs:
   for line in lines:txt(d,(76,yy),line,25);yy+=35
   yy+=12
  txt(d,(76,y+ch-29),'Note date: '+str(r.get('report_date') or 'Not specified'),15,c=M)
  y+=ch+20
 footer(d,y+2,'Read the research. Form your own view.')
 return finish(im)

def attention_card(p):
 rs=p['rows'][:3]
 if len(rs)!=3:raise ValueError('Attention artwork requires three ranked names')
 title=p.get('title','Your attention radar')
 kicker='X ATTENTION / '+title.upper()
 im,d=base(1250,kicker,'Where the conversation is moving.',p.get('label',''),p.get('date',''))
 y=328;r=rs[0]
 d.rounded_rectangle((48,y,1152,722),radius=28,fill='#182e24',outline='#708d4d',width=2)
 badge(d,76,y+25,'01 / ATTENTION LEADER')
 logo(im,d,r['ticker'],79,y+93,98)
 fit(d,(203,y+82),'$'+r['ticker'],420,66,b=True)
 fit(d,(207,y+173),r['name'],420,20,c=M)
 fit(d,(76,y+238),f"{r['mentions']:,}",330,70,b=True)
 txt(d,(min(420,96+int(d.textlength(f"{r['mentions']:,}",font=ft(70,True)))),y+285),'mentions',22,c=M)
 change=r.get('change')
 txt(d,(79,y+343),f'{change:+g}% vs previous period' if change is not None else 'Comparison unavailable',23,c=G if change is not None and change>=0 else M,b=True)
 txt(d,(675,y+36),'MENTION VOLUME',17,c=M,b=True)
 maxm=max(1,max(z['mentions'] for z in rs))
 for j,z in enumerate(rs):
  by=y+98+j*84
  fit(d,(675,by),z['ticker'],230,23,b=True)
  fit(d,(995,by),f"{z['mentions']:,}",110,23,b=True)
  d.rounded_rectangle((675,by+40,1085,by+49),radius=4,fill='#314b3a')
  width=int(410*z['mentions']/maxm)
  if width:d.rounded_rectangle((675,by+40,675+width,by+49),radius=min(4,width//2),fill=G if j==0 else '#759870')
 for j,r in enumerate(rs[1:]):
  x=48+j*564
  d.rounded_rectangle((x,746,x+540,1080),radius=25,fill='#10231e',outline='#304b3c',width=2)
  txt(d,(x+25,766),f'0{j+2} / ON THE RADAR',17,c=G,b=True)
  logo(im,d,r['ticker'],x+28,817,66)
  fit(d,(x+115,805),'$'+r['ticker'],390,45,b=True)
  # Fit the complete company name in its own measured line.
  fit(d,(x+118,868),r['name'],390,20,c=M)
  fit(d,(x+28,919),f"{r['mentions']:,}",280,54,b=True)
  txt(d,(x+min(325,48+int(d.textlength(f"{r['mentions']:,}",font=ft(54,True)))),952),'mentions',21,c=M)
  change=r.get('change')
  txt(d,(x+28,1021),f'{change:+g}% attention' if change is not None else 'Comparison unavailable',24,c=G if change is not None and change>=0 else M,b=True)
 footer(d,1115,'Ranked by heat. Attention is not price performance.')
 return finish(im)
