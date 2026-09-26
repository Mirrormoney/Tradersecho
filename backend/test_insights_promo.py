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
