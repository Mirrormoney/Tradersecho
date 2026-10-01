from datetime import datetime
from pathlib import Path
import re
from . import social_promos as p
from . import social

def at(day,hour):return datetime(2026,10,day,hour,tzinfo=p.NY).timestamp()

def test_launch_day_only_two_advertisements_and_no_collisions():
    ads=[];all_times=[]
    from . import social_research
    for hour in range(24):
        for minute in range(0,60,5):
            now=at(1,hour)+minute*60
            promo=p.slots(now)+p.signal_slots(now)+p.insights_slots(now)
            ads.extend(promo)
            all_times.extend(promo+social.market_slots(now)+social_research.slots(now))
    unique={s['key']:s for s in ads}
    assert set(unique)=={'signal_launch:2026-10-01:1300','insights_launch:2026-10-01:1500'}
    times={s['key']:s['at'] for s in all_times}
    assert len(set(times.values()))==len(times)
    ordered=sorted(times.values())
    assert all(b-a>=45*60 for a,b in zip(ordered,ordered[1:]))
    for slot in unique.values():
        report=(p.prepare_signal if slot['edition']=='signal_launch' else p.prepare_insights)(slot,slot['at'])
        assert 'live starting today' in report['text']
        assert len(re.sub(r'https://\S+','x'*23,report['text']))<=280

def test_launch_week_expires_and_returns_to_original_art():
    for day in (2,3,4,5,6):
        now=at(day,15)
        si=p.signal_slots(now);ai=p.insights_slots(now)
        assert len(si)+len(ai)==1
        text=(p.prepare_signal(si[0],now) if si else p.prepare_insights(ai[0],now))['text']
        assert ('live now' in text)==(day<5)
        assert 'live starting today' not in text
        name='signal' if si else 'insights'
        image=(p.signal_artwork if si else p.insights_artwork)(now)
        expected=Path(p.__file__).with_name(name+('_live_week_promo.png' if day<5 else '_evergreen_promo.png')).read_bytes()
        assert image==expected and len(image)<5_000_000
