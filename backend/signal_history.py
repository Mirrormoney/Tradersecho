"""Small on-demand Signal Lab history responses; no extra provider calls or writes."""
import json,math
from datetime import datetime,timedelta,time as daytime
from .signal_lab import VERSION,NY,TITLES
from .database import Postgres


def detail(c,ticker,now):
    today=datetime.fromtimestamp(now,NY).date()
    start=datetime.combine(today-timedelta(days=30),daytime.min,tzinfo=NY).timestamp()
    latest=c.execute('SELECT observed,payload FROM signal_lab_snapshots WHERE ticker=? AND version=? AND observed<=? ORDER BY slot DESC LIMIT 1',(ticker,VERSION,now)).fetchone()
    if not latest:return None
    # Extract only numeric scores and aggregate in Neon, never transfer 30 days of raw payloads.
    if isinstance(c,Postgres):
        day="to_char(to_timestamp(observed) AT TIME ZONE 'America/New_York','YYYY-MM-DD')"
        score=lambda i:f"CAST(payload::jsonb->'axes'->{i}->>'score' AS DOUBLE PRECISION)"
    else:
        c.create_function('ny_day',1,lambda ts:datetime.fromtimestamp(ts,NY).date().isoformat())
        day='ny_day(observed)'
        score=lambda i:f"json_extract(payload,'$.axes[{i}].score')"
    fields=','.join(f'AVG({score(i)}) AS avg{i},COUNT({score(i)}) AS n{i}' for i in range(5))
    rows=c.execute(f'SELECT {day} AS day, {fields} FROM signal_lab_snapshots WHERE ticker=? AND version=? AND slot>=? AND observed>=? AND observed<=? GROUP BY 1 ORDER BY 1',(ticker,VERSION,int(start//600),start,now)).fetchall()
    panel=json.loads(latest['payload']);axes=[]
    for i,name in enumerate(TITLES):
        source=panel['axes'][i]
        points=[dict(day=r['day'],value=round(float(r[f'avg{i}']),2) if r[f'avg{i}'] is not None else None,samples=r[f'n{i}'],partial_day=r['day']==today.isoformat()) for r in rows]
        windows={}
        for days in (7,30):
            cutoff=(today-timedelta(days=days)).isoformat()
            valid=[p for p in points if cutoff<=p['day']<today.isoformat() and p['value'] is not None]
            mean=round(sum(p['value'] for p in valid)/len(valid),2) if valid else None
            windows[str(days)]=dict(average=mean,days=len(valid),samples=sum(p['samples'] for p in valid),delta=round(source['score']-mean,2) if mean is not None and source.get('score') is not None else None)
        axes.append(dict(name=name,score=source.get('score'),strength=source.get('strength'),direction=source.get('direction'),state=source.get('state'),reason=source.get('reason'),points=points,windows=windows))
    return dict(ticker=ticker,version=VERSION,observed=latest['observed'],stale=now-latest['observed']>1200,axes=axes,server_at=now,method='Daily mean scores, equally weighted across available completed New York days. Today is plotted separately and excluded from averages. Current scoring version only; missing values are excluded, genuine zero values included.')
