from datetime import datetime,timezone
from .test_service import isolate_tests,s,make_account
from . import digest

def test_todays_takes_exclude_yesterday_even_with_more_likes():
    _,u=make_account('freshness@example.invalid');u={**u,'plan':'premium'}
    now=datetime(2026,9,17,15,tzinfo=timezone.utc).timestamp()
    with s.db() as c:c.execute('INSERT INTO handles(user_id,handle) VALUES(?,?)',(u['id'],'researcher'))
    s.ingest([{'id':'8001','author':'researcher','text':'$MU demand is accelerating and margins are expanding.','created_at':'2026-09-16T20:00:00Z','likes':9999},{'id':'8002','author':'researcher','text':'$MU guidance increased again as memory demand grows.','created_at':'2026-09-17T10:00:00Z','likes':2}])
    report={'ready':True,'date':'2026-09-16','rows':[{'ticker':'MU','name':'Micron','mentions':100,'previous':50,'change':100}],'window_start':now-172800,'window_end':now-86400}
    result=digest.personalized(report,u,now=now)
    assert [p['id'] for p in result['posts']]==['8002']
    assert result['post_date']=='2026-09-17' and result['date']=='2026-09-16'
    assert digest.personalized(report,u,now=now+86400)['posts']==[]
