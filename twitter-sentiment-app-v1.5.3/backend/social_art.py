"""Deterministic brand artwork. No generated imagery or invented market numbers."""
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
BG='#0b1718'; PANEL='#142523'; GREEN='#c4f27a'; WHITE='#f3f6ef'; MUTED='#a5bbb2'
def font(n):return ImageFont.load_default(size=n)
def pulse(d,x,y,size):
    def pt(a,b):return (x+a*size/100,y+b*size/100)
    for r in (45,33):d.ellipse([pt(50-r,50-r),pt(50+r,50+r)],outline='#38543d',width=2)
    d.line([pt(a,b) for a,b in [(12,52),(30,52),(40,26),(58,76),(70,46),(88,46)]],fill=GREEN,width=max(3,int(size*.025)),joint='curve')
def png(im):
    out=BytesIO();im.save(out,format='PNG');return out.getvalue()
def banner():
    im=Image.new('RGB',(1500,500),BG);d=ImageDraw.Draw(im)
    for x in range(0,1500,70):d.line([(x,0),(x,500)],fill='#10201f')
    for y in range(0,500,70):d.line([(0,y),(1500,y)],fill='#10201f')
    pulse(d,1080,95,310)
    d.text((330,96),'tradersecho',font=font(67),fill=GREEN)
    d.text((333,181),'ATTENTION  /  PERSPECTIVE  /  COMMUNITY',font=font(18),fill=MUTED)
    d.text((330,245),'Find the AI stock conversation.',font=font(39),fill=WHITE)
    d.text((332,304),'From chips to infrastructure. From power to possibility.',font=font(22),fill=MUTED)
    d.rounded_rectangle((332,365,552,414),radius=22,fill=GREEN)
    d.text((357,379),'tradersecho.com',font=font(22),fill=BG)
    return png(im)
def card(report):
    im=Image.new('RGB',(1200,675),BG);d=ImageDraw.Draw(im)
    pulse(d,40,30,80);d.text((134,46),'tradersecho',font=font(34),fill=WHITE)
    d.text((134,88),'ATTENTION / PERSPECTIVE / COMMUNITY',font=font(12),fill=MUTED)
    d.text((930,56),report.get('date',''),font=font(21),fill=MUTED)
    d.text((48,150),report['title'],font=font(44),fill=GREEN)
    d.text((50,208),report['label'],font=font(20),fill=MUTED)
    for i,r in enumerate(report['rows'][:3]):
        x=48+i*374;d.rounded_rectangle((x,261,x+354,532),radius=18,fill=PANEL,outline='#2e4640',width=2)
        d.text((x+26,285),f'0{i+1}',font=font(24),fill=GREEN)
        d.text((x+26,330),'$'+r['ticker'],font=font(43),fill=WHITE)
        name=r['name'];name=name if len(name)<28 else name[:25]+'...'
        d.text((x+26,390),name,font=font(17),fill=MUTED)
        d.text((x+26,435),f"{r['mentions']:,} mentions",font=font(25),fill=WHITE)
        change=r.get('change');value=f'{change:+g}% attention' if change is not None else 'Comparison unavailable'
        d.text((x+26,481),value,font=font(19),fill=GREEN if change is not None and change>=0 else MUTED)
    d.text((50,566),'AI-related stocks ranked by conversation heat',font=font(20),fill=WHITE)
    d.text((50,603),'X attention, not price performance or investment advice.',font=font(16),fill=MUTED)
    d.text((934,605),'tradersecho.com',font=font(23),fill=GREEN)
    return png(im)
