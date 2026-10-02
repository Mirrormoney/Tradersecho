from datetime import datetime
import re
import pytest
from . import social_research as r, research_feed

def at(day,hour=8,minute=45):
    return datetime.fromisoformat(day).replace(hour=hour,minute=minute,tzinfo=r.NY).timestamp()

def test_schedule():
    for day in ('2026-09-23','2026-12-23'):
        assert r.slots(at(day))[0]['key']=='research:'+day
        assert not r.slots(at(day,8,44))
        assert not r.slots(at(day,9,30))
    assert not r.slots(at('2026-09-26'))

def test_fresh_notes_only(monkeypatch):
    rows=[{'ticker':t,'name':t,'research':[{'report_date':d,'summary':'Clear evidence. '*100,'firm':'Broker'}]} for t,d in [('OLD','2026-09-22'),('MU','2026-09-23'),('LITE','2026-09-23'),('AMD','2026-09-23')]]
    monkeypatch.setattr(research_feed,'shared_overview',lambda:(rows,[],0,0))
    p=r.prepare(at('2026-09-23'))
    assert [x['ticker'] for x in p['rows']]==['MU','LITE','AMD']
    assert re.findall(r'\$[A-Z]+',p['text'])==['$MU']
    assert len(re.sub(r'https://\S+','x'*23,p['text']))<=278
    from .social_caption import validate_ranked_caption
    validate_ranked_caption(p)
    from PIL import ImageDraw
    seen=[]
    original=ImageDraw.ImageDraw.text
    def capture(self,xy,text,*args,**kwargs):
        seen.append(text)
        return original(self,xy,text,*args,**kwargs)
    monkeypatch.setattr(ImageDraw.ImageDraw,'text',capture)
    assert r.artwork(p).startswith(b'\x89PNG')
    for ticker in ('MU','LITE','AMD'):
        assert any(ticker in line for line in seen)
    with pytest.raises(ValueError):r.prepare(at('2026-09-24'))

def test_approved_preview_expiration():
    p=r.prepare(at('2026-09-23'),approved=True)
    assert r.artwork(p).startswith(b'\x89PNG')
    assert len(re.sub(r'https://\S+','x'*23,p['text']))<=278
    with pytest.raises(ValueError):r.prepare(at('2026-09-24'),approved=True)


def test_full_content_is_not_clipped(monkeypatch):
    from PIL import Image, ImageDraw
    text='This complete research sentence must survive the old five-line cutoff. '*30
    row={'ticker':'MU','name':'Micron Technology','summary':text,'report_date':'2026-09-23',
         'catalysts':['Demand improves next year.'],'risks':['Capacity may grow faster.']}
    seen=[]
    original=ImageDraw.ImageDraw.text
    def capture(self,xy,text,*args,**kwargs):
        seen.append(text)
        return original(self,xy,text,*args,**kwargs)
    monkeypatch.setattr(ImageDraw.ImageDraw,'text',capture)
    r.artwork({'date':'2026-09-23','rows':[row]})
    rendered=' '.join(seen)
    assert text.strip() in rendered
    assert 'Catalysts: Demand improves next year.' in rendered
    assert 'Risks: Capacity may grow faster.' in rendered
    assert '…' not in rendered
