"""Approved promotional copy and a two-day New York publishing cadence."""
from datetime import date,datetime
import re
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

def artwork(report):
    if report['variant']==5:
        with Image.open(Path(__file__).with_name('trending_research_promo.png')) as screenshot:
            return png(screenshot.convert('RGB'))
    im=Image.new('RGB',(1200,675),BG);d=ImageDraw.Draw(im)
    pulse(d,42,30,80);d.text((140,45),'tradersecho',font=font(36),fill=WHITE)
    d.text((142,92),'ATTENTION / PERSPECTIVE / COMMUNITY',font=font(15),fill=MUTED)
    d.text((50,180),report['title'],font=font(48),fill=GREEN)
    index=report['variant']
    labels=[['AI-stock rankings','Tracked X voices','Sentiment in context'],['Chips + memory','Data centres + networks','Power + software'],['Check attention','Explore the conversation','Build your watchlist'],['Find active names','Check SEC filings','Read the source'],['Chips + memory','Networks + power','Software + opportunity']][index]
    for i,label in enumerate(labels):
        x=50+i*370
        d.rounded_rectangle((x,310,x+350,490),radius=20,fill=PANEL,outline='#38543d',width=2)
        d.text((x+24,333),['01','02','03'][i] if index==2 else ['ATTENTION','PERSPECTIVE','COMMUNITY'][i] if index==0 else ['COMPUTE','INFRASTRUCTURE','ENABLEMENT'][i],font=font(18),fill=GREEN)
        d.text((x+24,402),label,font=font(22),fill=WHITE)
    d.text((50,552),'Find the conversation. Form your own conviction.',font=font(25),fill=WHITE)
    d.text((50,602),'7 days of Premium free. No card required.',font=font(20),fill=MUTED)
    d.text((915,601),'tradersecho.com',font=font(25),fill=GREEN)
    return png(im)
