from datetime import datetime
import re
from . import social_promos as p

def ts(day,h=15,m=0,month=9):return datetime(2026,month,day,h,m,tzinfo=p.NY).timestamp()

def test_campaign_exact_dates_count_and_unique_captions():
    found=[];captions=[]
    for day in range(24,31):
        slots=p.signal_slots(ts(day,10,30))+p.signal_slots(ts(day))
        assert len(slots)==(1 if day<28 else 2)
        for slot in slots:
            found.append(slot['key'])
            text=p.prepare_signal(slot,slot['at'])['text'];captions.append(text)
            assert len(re.sub(r'https://\S+','x'*23,text))<=280
    assert len(found)==len(set(found))==10
    assert len(set(captions))==10
    assert not p.signal_slots(ts(23))
    assert not p.signal_slots(ts(1,month=10))
    assert not p.signal_slots(ts(24,14,59))
    assert not p.signal_slots(ts(24,16))

def test_artwork_packaged():
    assert p.signal_artwork().startswith(b'\x89PNG')
