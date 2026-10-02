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
    from .social_design import research_card
    return research_card(report)
