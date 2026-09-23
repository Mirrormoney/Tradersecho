"""Weekday research edition using published summaries only; no AI or X reads."""
from datetime import datetime
from pathlib import Path
import re
from PIL import Image,ImageDraw
from .newsletter_schedule import NY
from .social_art import BG,PANEL,GREEN,WHITE,MUTED,font,pulse,png

APPROVED_TEXT="Research before the bell 🔎\n\n$LITE leads our latest research selection: Citi highlights tight laser supply and AI optics demand.\n\nPlus: PANW’s new AI security service and a memory-sector read-through for MU.\n\nExplore the three perspectives:\nhttps://tradersecho.com/trending-research"

def slots(now):
    local=datetime.fromtimestamp(now,NY)
    at=local.replace(hour=8,minute=45,second=0,microsecond=0).timestamp()
    if local.weekday()<5 and 0<=now-at<45*60:
        return [{'edition':'research','at':at,'key':'research:'+local.date().isoformat()}]
    return []

def prepare(now,approved=False):
    day=datetime.fromtimestamp(now,NY).date().isoformat()
    if approved:
        if day!='2026-09-23':raise ValueError('Approved September 23 preview has expired')
        return {'edition':'research','title':'Research before the bell','text':APPROVED_TEXT,'date':day,'approved_preview':True,'rows':[]}
    from .research_feed import shared_overview
    ranked,other,_,_=shared_overview()
    rows=[]
    for row in ranked+other:
        notes=[n for n in row['research'] if n.get('report_date')==day]
        if notes:rows.append({'ticker':row['ticker'],'name':row['name'],**notes[0]})
        if len(rows)==3:break
    if not rows:raise ValueError('No validated research dated today; waiting until 9:30am New York')
    leader=rows[0]
    prefix=f"Research before the bell 🔎\n\n${leader['ticker']}: "
    suffix="\n\n"+str(len(rows))+" fresh research perspective"+('s' if len(rows)!=1 else '')+" for AI-related stocks.\nhttps://tradersecho.com/trending-research"
    available=280-len(prefix)-len(re.sub(r'https://\S+','x'*23,suffix))-4
    summary=leader['summary']
    if len(summary)>available:summary=summary[:available-1].rsplit(' ',1)[0]+'…'
    return {'edition':'research','title':'Research before the bell','date':day,'rows':rows,'text':prefix+summary+suffix}

def artwork(report):
    if report.get('approved_preview'):return Path(__file__).with_name('research_before_bell_approved.png').read_bytes()
    im=Image.new('RGB',(1500,900),BG);d=ImageDraw.Draw(im)
    pulse(d,50,34,88);d.text((157,42),'tradersecho',font=font(43),fill=WHITE)
    d.text((160,99),'ATTENTION / PERSPECTIVE / COMMUNITY',font=font(16),fill=MUTED)
    d.text((1160,62),report['date'],font=font(22),fill=MUTED)
    d.text((60,166),'Research before the bell.',font=font(57),fill=GREEN)
    d.text((63,247),'Fresh AI-stock research. Ratings. Developments. Context.',font=font(27),fill=MUTED)
    def wrap(text,x,y,width,size,max_lines):
        words=text.split();lines=[];line=''
        for word in words:
            trial=(line+' '+word).strip()
            if d.textlength(trial,font=font(size))>width:lines.append(line);line=word
            else:line=trial
        if line:lines.append(line)
        if len(lines)>max_lines:lines=lines[:max_lines];lines[-1]=lines[-1].rsplit(' ',1)[0]+'…'
        for line in lines:d.text((x,y),line,font=font(size),fill=WHITE);y+=size+12
    width=(1380-(len(report['rows'])-1)*20)/len(report['rows'])
    for i,row in enumerate(report['rows']):
        x=60+i*(width+20)
        d.rounded_rectangle((x,320,x+width,773),radius=24,fill=PANEL,outline='#38543d',width=2)
        d.text((x+width-65,350),f'0{i+1}',font=font(25),fill=GREEN)
        d.text((x+28,350),'$'+row['ticker'],font=font(43),fill=GREEN)
        wrap(row['name'],x+29,410,width-60,22,1)
        d.line((x+28,455,x+width-28,455),fill='#38543d',width=2)
        wrap(row['firm'] or 'Research update',x+29,477,width-60,19,1)
        wrap(row['summary'],x+29,521,width-60,24,5)
        if row.get('link_type')=='sector_readthrough':d.text((x+29,713),'Sector read-through',font=font(18),fill=GREEN)
        d.text((x+29,741),'Note date: '+row['report_date'],font=font(18),fill=MUTED)
    d.text((63,825),'Find the conversation. Form your own conviction.',font=font(24),fill=WHITE)
    d.text((1030,825),'tradersecho.com',font=font(32),fill=GREEN)
    return png(im)
