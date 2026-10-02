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
    from .social_design import attention_card
    return attention_card(report)
