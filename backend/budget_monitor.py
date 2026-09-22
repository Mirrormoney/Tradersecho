"""Persistent daily budget pressure and bounded once-daily allowance adjustment."""
import calendar,json,math,time
from datetime import datetime,timezone

def record_limit(category,kind,now=None):
    from .service import db
    now=time.time() if now is None else now;day=datetime.fromtimestamp(now,timezone.utc).date().isoformat()
    with db() as c:
        c.execute('BEGIN IMMEDIATE');key='x_pressure:'+day
        row=c.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone();data=json.loads(row[0]) if row else {}
        item=data.setdefault(category,{'first_at':now,'last_at':now,'blocked_attempts':0})
        item['last_at']=now;item['blocked_attempts']+=1
        c.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(data)))

def snapshot(c,now=None):
    now=time.time() if now is None else now;month=datetime.fromtimestamp(now,timezone.utc).strftime('%Y-%m')
    history=[{'day':r['key'].split(':',1)[1],'limits':json.loads(r['value'])} for r in c.execute("SELECT key,value FROM meta WHERE key LIKE 'x_pressure:%' ORDER BY key DESC LIMIT 14")]
    today=int(now//86400)*86400
    usage=[dict(r) for r in c.execute('SELECT kind,SUM(COALESCE(actual_estimate,reserved)) AS cost FROM x_spend WHERE ts>=? GROUP BY kind',(today,))]
    decision=c.execute("SELECT value FROM meta WHERE key='x_budget_decision'").fetchone()
    return {'history':history,'today_spend':round(sum(r['cost'] for r in usage),4),'today_breakdown':usage,'decision':json.loads(decision[0]) if decision else None,'note':'First limit time and repeated blocked attempts are recorded; the gap between first and last block is not continuous downtime.'}

def review(now=None):
    from .service import db,CATALOG
    from .community import data_settings
    now=time.time() if now is None else now;dt=datetime.fromtimestamp(now,timezone.utc);day=dt.date().isoformat()
    with db() as c:
        c.execute('BEGIN IMMEDIATE');settings=data_settings(c)
        if not settings.get('adaptive_budget_enabled'):return
        previous=c.execute("SELECT value FROM meta WHERE key='x_budget_decision'").fetchone()
        if previous and json.loads(previous[0]).get('day')==day:return
        history=snapshot(c,now)['history'];changes={}
        # Require early exhaustion on two of the last three completed UTC days.
        for category,field,maximum in [('posts','daily_post_limit',2000),('profiles','daily_profile_limit',100)]:
            hits=[h for h in history if 0<(dt.date()-datetime.fromisoformat(h['day']).date()).days<=3 and category in h['limits'] and datetime.fromtimestamp(h['limits'][category]['first_at'],timezone.utc).hour<18]
            if len(hits)>=2 and settings[field]<maximum:changes[field]=min(maximum,math.ceil(settings[field]*1.2))
        proposed={**settings,**changes};days=calendar.monthrange(dt.year,dt.month)[1]
        extra=(24*proposed['hourly_top']*.005+proposed['on_demand_daily_limit']*.005) if proposed['intraday_enabled'] else 0
        daily=len(CATALOG)*.005+proposed['daily_post_limit']*.005+proposed['daily_profile_limit']*.01+extra
        spent=c.execute('SELECT COALESCE(SUM(COALESCE(actual_estimate,reserved)),0) FROM x_spend WHERE month=?',(dt.strftime('%Y-%m'),)).fetchone()[0]
        fits=daily*days<=settings['monthly_budget']*.95 and spent+daily*(days-dt.day+1)<=settings['monthly_budget']
        result={'day':day,'at':now,'changes':{},'projected_full_month_max':round(daily*days,2),'state':'observing'}
        if changes and fits:
            c.execute("INSERT INTO settings VALUES('x_collection',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(proposed),));result.update(state='adjusted',changes=changes)
        elif changes:result['state']='increase_needs_budget_headroom'
        c.execute("INSERT INTO meta VALUES('x_budget_decision',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(result),))
        c.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('x_budget_review:'+day,json.dumps(result)))
