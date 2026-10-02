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
    text=(f"Research before the bell 🔎\n\n${rows[0]['ticker']} leads today's research selection."
          "\n\nRead the full published summaries in the image."
          "\nhttps://tradersecho.com/trending-research")
    if len(re.sub(r'https://\S+','x'*23,text))>280:
        raise ValueError('Research caption exceeds standard post length')
    return {'edition':'research','title':'Research before the bell','date':day,'rows':rows,'text':text}


def full_tile_text(row):
    parts=[row['summary']]
    for key,label in (('catalysts','Catalysts'),('risks','Risks')):
        for item in row.get(key,[]):
            parts.append(label+': '+item)
    if row.get('link_type')=='sector_readthrough' and row.get('link_reason'):
        parts.append('Sector read-through: '+row['link_reason'])
    return parts


def wrapped_lines(draw,text,width,size):
    lines=[]
    line=''
    for word in text.split():
        trial=(line+' '+word).strip()
        if line and draw.textlength(trial,font=font(size))>width:
            lines.append(line);line=word
        else:line=trial
    if line:lines.append(line)
    return lines


def artwork(report):
    if report.get('approved_preview'):return Path(__file__).with_name('research_before_bell_approved.png').read_bytes()
    # Full published content, never the collapsed website excerpt. Measure before
    # drawing so longer notes expand the card rather than disappearing at its edge.
    probe=ImageDraw.Draw(Image.new('RGB',(1500,1)))
    layouts=[]
    for row in report['rows']:
        name=wrapped_lines(probe,row['name'],1160,26)
        paragraphs=[wrapped_lines(probe,text,1300,28) for text in full_tile_text(row)]
        height=130+len(name)*34+sum(len(lines)*39+16 for lines in paragraphs)+44
        layouts.append((row,name,paragraphs,height))
    height=340+sum(item[3]+20 for item in layouts)+90
    if height>8000:raise ValueError('Full research artwork exceeds readable image size; no text was clipped')
    im=Image.new('RGB',(1500,height),BG);d=ImageDraw.Draw(im)
    pulse(d,50,34,88);d.text((157,42),'tradersecho',font=font(43),fill=WHITE)
    d.text((160,99),'ATTENTION / PERSPECTIVE / COMMUNITY',font=font(16),fill=MUTED)
    d.text((1160,62),report['date'],font=font(22),fill=MUTED)
    d.text((60,166),'Research before the bell.',font=font(57),fill=GREEN)
    d.text((63,247),'Fresh AI-stock research. Ratings. Developments. Context.',font=font(27),fill=MUTED)
    y=320
    for i,(row,name,paragraphs,h) in enumerate(layouts):
        d.rounded_rectangle((60,y,1440,y+h),radius=24,fill=PANEL,outline='#38543d',width=2)
        d.text((1370,y+26),f'0{i+1}',font=font(25),fill=GREEN)
        d.text((90,y+25),'$'+row['ticker'],font=font(43),fill=GREEN)
        cursor=y+83
        for line in name:d.text((90,cursor),line,font=font(26),fill=MUTED);cursor+=34
        d.line((90,cursor+8,1410,cursor+8),fill='#38543d',width=2);cursor+=30
        for lines in paragraphs:
            for line in lines:d.text((90,cursor),line,font=font(28),fill=WHITE);cursor+=39
            cursor+=16
        d.text((90,y+h-38),'Note date: '+row['report_date'],font=font(20),fill=MUTED)
        y+=h+20
    d.text((63,y+20),'Find the conversation. Form your own conviction.',font=font(24),fill=WHITE)
    d.text((1030,y+20),'tradersecho.com',font=font(32),fill=GREEN)
    result=png(im)
    if len(result)>5_000_000:raise ValueError('Full research image exceeds upload allowance; no text was clipped')
    return result
