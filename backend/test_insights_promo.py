from datetime import datetime
from io import BytesIO
from PIL import Image
from . import social_promos as p

def test_insights_announcement_window_and_asset():
 at=datetime(2026,9,26,12,tzinfo=p.NY).timestamp()
 assert not p.insights_slots(at-1)
 slots=p.insights_slots(at)
 assert len(slots)==1 and p.insights_slots(at+300)==slots
 assert not p.insights_slots(at+3600)
 assert not p.insights_slots(datetime(2026,10,1,12,tzinfo=p.NY).timestamp())
 assert p.prepare_insights(slots[0],at)['text'].endswith('/ai-insights')
 with Image.open(BytesIO(p.insights_artwork())) as im:
  assert im.width>1000 and im.width>im.height


def test_daily_then_alternating_campaign():
 for day in range(26,31):
  noon=datetime(2026,9,day,12,tzinfo=p.NY).timestamp()
  afternoon=datetime(2026,9,day,15,tzinfo=p.NY).timestamp()
  assert len(p.insights_slots(noon))==1
  assert len(p.signal_slots(afternoon))==1
  assert not p.signal_slots(datetime(2026,9,day,10,30,tzinfo=p.NY).timestamp())
 for day in range(1,16):
  now=datetime(2026,10,day,15,tzinfo=p.NY).timestamp()
  si=p.signal_slots(now);ai=p.insights_slots(now)
  assert len(si)+len(ai)==1
  assert bool(ai)==(day%2==1)
  report=p.prepare_signal(si[0],now) if si else p.prepare_insights(ai[0],now)
  assert 'October' not in report['text'] and 'to go' not in report['text']
  assert (p.signal_artwork(now) if si else p.insights_artwork(now)).startswith(b'\x89PNG')
