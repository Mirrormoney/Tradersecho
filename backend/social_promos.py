"""Approved promotional copy and a two-day New York publishing cadence."""
from datetime import date,datetime
import re, math
from pathlib import Path
from .newsletter_schedule import NY
from .social_art import BG,PANEL,GREEN,WHITE,MUTED,font,pulse,png
from PIL import Image,ImageDraw

START=date(2026,9,19)
COPY=[
"Too many stock takes. Too little time.\n\nTraders Echo brings AI-stock rankings, tracked X voices and sentiment into one dashboard—so you can spend less time scrolling and more time researching.\n\nFind the conversation. Form your own conviction.\n\nhttps://tradersecho.com",
"AI investing goes beyond the biggest chip names.\n\nMemory. Data centres. Networking. Power. Software.\n\nExplore the AI supply chain with Traders Echo: see which stocks are attracting attention and read collected takes from tracked X accounts.\n\nhttps://tradersecho.com/ai-supply-chain",
"Make your next research session less scattered.\n\nCheck AI-stock attention.\nCompare intraday, daily and weekly rankings.\nExplore tracked voices.\nBuild your watchlist.\n\nYour starting point: Traders Echo.\n\nTry Premium free for 7 days. No card required.\n\nhttps://tradersecho.com",
"Find the names gaining attention and immediately check their latest available SEC filings.\n\nGo beyond the conversation. Explore the source.\n\nhttps://tradersecho.com/sec-filings",
"Everyone watches the AI giants. What about the companies behind them?\n\nExplore chips, memory, networking, power and software—and see where X attention is building across the AI supply chain.\n\nFind your next research idea.\n\nhttps://tradersecho.com/ai-supply-chain",
'Connect what’s trending on X with what analysts are saying.\n\nFind concise broker research summaries for AI-related stocks - from Rating Changes to Channel checks\n\nExplore Trending Research:\nhttps://tradersecho.com/trending-research',
]

def slots(now):
    local=datetime.fromtimestamp(now,NY);days=(local.date()-START).days
    at=datetime.combine(local.date(),datetime.min.time(),NY).replace(hour=13).timestamp()
    if days>=0 and days%2==0 and 0<=now-at<7200:
        return [{'edition':'promo','at':at,'key':'promo:'+local.date().isoformat()}]
    return []

def prepare(index):
    text=COPY[index]
    # X counts a URL as 23 characters; allow extra weight for the em dash.
    if len(re.sub(r'https://\S+', 'x'*23, text))+2>280:raise ValueError('Promotional caption exceeds limit')
    return {'edition':'promo','variant':index,'title':['Less scrolling. More context.','AI is an entire supply chain.','Your daily research rhythm.','Attention meets disclosures.','Beyond the AI giants.','Connect attention with research.'][index],'text':text,'rows':[]}

def illustration(d,x,y,kind):
    """Feature illustrations, deliberately without invented market figures."""
    edge='#38543d';soft='#213c32'
    if kind=='chart':
        for yy in (y+20,y+55,y+90):d.line((x,yy,x+290,yy),fill=soft,width=1)
        points=[(x,y+90),(x+40,y+74),(x+75,y+82),(x+115,y+46),(x+153,y+56),(x+197,y+27),(x+237,y+36),(x+282,y+6)]
        d.polygon(points+[(x+282,y+110),(x,y+110)],fill=soft)
        d.line(points,fill=GREEN,width=4,joint='curve')
        d.ellipse((x+277,y+1,x+287,y+11),fill=GREEN)
        for i,w in enumerate((145,110,76)):
            d.rounded_rectangle((x+i*96,y+124,x+i*96+78,y+139),radius=5,fill=edge)
    elif kind=='chat':
        for xx,yy,w in ((x,y,220),(x+48,y+65,238)):
            d.rounded_rectangle((xx,yy,xx+w,yy+61),radius=12,fill=soft,outline=edge,width=2)
            d.polygon([(xx+20,yy+59),(xx+20,yy+73),(xx+38,yy+59)],fill=soft)
            d.ellipse((xx+14,yy+15,xx+36,yy+37),outline=GREEN,width=2)
            d.rounded_rectangle((xx+49,yy+17,xx+w-20,yy+24),radius=3,fill=MUTED)
            d.rounded_rectangle((xx+49,yy+35,xx+w-48,yy+41),radius=3,fill=edge)
    elif kind=='watch':
        for i,label in enumerate(('Chips','Memory','Power')):
            yy=y+i*48
            d.rounded_rectangle((x,yy,x+290,yy+39),radius=8,fill=soft)
            d.text((x+15,yy+10),label,font=font(18),fill=WHITE)
            d.polygon([(x+266+(11 if j%2==0 else 5)*math.cos(-math.pi/2+j*math.pi/5),yy+20+(11 if j%2==0 else 5)*math.sin(-math.pi/2+j*math.pi/5)) for j in range(10)],fill=GREEN)
            d.line([(x+162,yy+28),(x+184,yy+21),(x+206,yy+26),(x+232,yy+11)],fill=GREEN,width=2)
    elif kind in ('document','source'):
        for dx,dy in ((75,0),(48,12)):
            d.rounded_rectangle((x+dx,y+dy,x+dx+153,y+dy+133),radius=9,fill=BG,outline=edge,width=2)
        d.text((x+67,y+28),'SEC EDGAR',font=font(21),fill=GREEN)
        for i,w in enumerate((109,89,103,73)):
            d.rounded_rectangle((x+67,y+65+i*17,x+67+w,y+70+i*17),radius=2,fill=MUTED if i==0 else edge)
        d.ellipse((x+204,y+93,x+246,y+135),fill=GREEN)
        if kind=='source':
            d.line([(x+216,y+122),(x+235,y+104),(x+235,y+119)],fill=BG,width=3)
            d.line((x+220,y+104,x+235,y+104),fill=BG,width=3)
        else:d.line([(x+215,y+115),(x+222,y+122),(x+237,y+106)],fill=BG,width=3)
    else:
        labels={'compute':('CHIPS','MEMORY'),'network':('CLOUD','NETWORKS'),'power':('POWER','COOLING'),'software':('SOFTWARE','AI TOOLS'),'network_power':('NETWORKS','POWER')}[kind]
        for i,label in enumerate(labels):
            xx=x+4+i*160
            d.rounded_rectangle((xx,y+22,xx+122,y+116),radius=12,fill=soft,outline=edge,width=2)
            d.rounded_rectangle((xx+43,y+38,xx+79,y+69),radius=5,outline=GREEN,width=3)
            for offset in (48,61,74):d.line((xx+offset,y+31,xx+offset,y+37),fill=GREEN,width=2)
            d.text((xx+61,y+86),label,font=font(15),fill=WHITE,anchor='mt')
        d.line((x+127,y+68,x+158,y+68),fill=GREEN,width=3)
        d.polygon([(x+152,y+62),(x+160,y+68),(x+152,y+74)],fill=GREEN)


def artwork(report):
    if report['variant']==5:
        with Image.open(Path(__file__).with_name('trending_research_promo.png')) as screenshot:
            return png(screenshot.convert('RGB'))
    im=Image.new('RGB',(1200,675),BG);d=ImageDraw.Draw(im)
    pulse(d,42,25,80);d.text((140,40),'tradersecho',font=font(36),fill=WHITE)
    d.text((142,87),'ATTENTION / PERSPECTIVE / COMMUNITY',font=font(15),fill=MUTED)
    d.text((50,151),report['title'],font=font(46),fill=GREEN)
    index=report['variant']
    scenes=[
        [('AI-stock rankings','chart','Find the active names'),('Tracked X voices','chat','Explore collected takes'),('Context in one place','document','Go beyond the headline')],
        [('Chips + memory','compute','Start at the core'),('Cloud + networks','network','Follow the connections'),('Power + cooling','power','Explore the infrastructure')],
        [('Check attention','chart','Follow the conversation heat'),('Explore the conversation','chat','Read collected X takes'),('Build your watchlist','watch','Keep your research in view')],
        [('Find active names','chart','Start with market attention'),('Check SEC filings','document','Explore company disclosures'),('Read the source','source','Open the original filing')],
        [('Chips + memory','compute','Beyond the biggest names'),('Networks + power','network_power','Connect the AI economy'),('Software + AI tools','software','Find your next research idea')],
    ][index]
    for i,(label,kind,detail) in enumerate(scenes):
        x=50+i*370
        d.rounded_rectangle((x,239,x+350,530),radius=20,fill=PANEL,outline='#38543d',width=2)
        d.text((x+24,260),f'0{i+1}',font=font(18),fill=GREEN)
        illustration(d,x+30,296,kind)
        d.text((x+24,460),label,font=font(22),fill=WHITE)
        d.text((x+24,495),detail,font=font(17),fill=MUTED)
    d.text((50,558),'Find the conversation. Form your own conviction.',font=font(25),fill=WHITE)
    d.text((50,610),'7 days of Premium free. No card required.',font=font(20),fill=MUTED)
    d.text((915,609),'tradersecho.com',font=font(25),fill=GREEN)
    return png(im)


# Owner-approved launch countdown. Closed interval: never advertise "coming" after launch.
SIGNAL_START=date(2026,9,24)
SIGNAL_END=date(2026,9,30)
SIGNAL_COPY=(
    "Compare the signals before your next move.\n\nX activity. Options flow. Broker research. Price and volume.\n\nMeet Signal Lab: five indicators in one clear view for your AI-stock research.",
    "A stock is trending. Do the other signals agree?\n\nCompare X activity, options pressure and broker commentary alongside price and volume.\n\nMore context. Your own conviction.",
)

LAUNCH_DATE=date(2026,10,1)

def signal_slots(now):
    local=datetime.fromtimestamp(now,NY)
    if local.date()<SIGNAL_START:return []
    if local.date()>=LAUNCH_DATE and (local.date()-LAUNCH_DATE).days%2!=1:return []
    at=local.replace(hour=15,minute=0,second=0,microsecond=0).timestamp()
    if not 0<=now-at<3600:return []
    day=(local.date()-SIGNAL_START).days
    variant=day%2 if local.date()<LAUNCH_DATE else ((local.date()-LAUNCH_DATE).days//2)%2
    return [dict(edition='signal_launch',at=at,key=f'signal_launch:{local.date().isoformat()}:1500',variant=variant)]

def prepare_signal(slot,now):
    if slot not in signal_slots(now):raise ValueError('Signal Lab campaign is outside its approved slot')
    days=(date(2026,10,1)-datetime.fromtimestamp(now,NY).date()).days
    text=SIGNAL_COPY[slot['variant']]+(f"\n\nSignal Lab arrives October 1st. {days} day{'s' if days!=1 else ''} to go." if days>0 else "\n\nExplore Signal Lab.")+("\nhttps://tradersecho.com" if days>0 else "\nhttps://tradersecho.com/signal-lab")
    if len(re.sub(r'https://\S+','x'*23,text))>280:raise ValueError('Signal Lab caption exceeds X limit')
    return dict(edition='signal_launch',title='Signal Lab countdown' if days>0 else 'Explore Signal Lab',text=text,rows=[])

def signal_artwork(now=None):
    evergreen=now is not None and datetime.fromtimestamp(now,NY).date()>=LAUNCH_DATE
    return Path(__file__).with_name('signal_evergreen_promo.png' if evergreen else 'signal_launch_promo.png').read_bytes()

# Approved daily feature campaign, alternating from October 1.
INSIGHTS_COPY="From HBM to 800 VDC: understand what’s changing in AI infrastructure.\n\nExplore key developments, expected milestones and potential beneficiaries—all in one place.\n\nAI Insights Lab arrives October 1.\n\nhttps://tradersecho.com/ai-insights"

def insights_slots(now):
    local=datetime.fromtimestamp(now,NY)
    if local.date()<date(2026,9,26):return []
    if local.date()>=LAUNCH_DATE and (local.date()-LAUNCH_DATE).days%2!=0:return []
    hour=12 if local.date()<LAUNCH_DATE else 15
    at=local.replace(hour=hour,minute=0,second=0,microsecond=0).timestamp()
    return [dict(edition='insights_launch',at=at,key=f'insights_launch:{local.date().isoformat()}:{hour:02}00')] if 0<=now-at<3600 else []

def prepare_insights(slot,now):
    if slot not in insights_slots(now):raise ValueError('AI Insights announcement is outside its approved slot')
    if len(re.sub(r'https://\S+','x'*23,INSIGHTS_COPY))>280:raise ValueError('AI Insights caption exceeds X limit')
    evergreen=datetime.fromtimestamp(now,NY).date()>=LAUNCH_DATE
    text=INSIGHTS_COPY.replace('AI Insights Lab arrives October 1.','Explore AI Insights Lab.') if evergreen else INSIGHTS_COPY.replace('https://tradersecho.com/ai-insights','https://tradersecho.com')
    return dict(edition='insights_launch',title='Explore AI Insights Lab' if evergreen else 'AI Insights Lab arrives October 1',text=text,rows=[])

def insights_artwork(now=None):
    evergreen=now is not None and datetime.fromtimestamp(now,NY).date()>=LAUNCH_DATE
    return Path(__file__).with_name('insights_evergreen_promo.png' if evergreen else 'insights_launch_promo.png').read_bytes()
