import sqlite3,json
from datetime import datetime
from . import signal_history as h,signal_lab as lab

def test_daily_means_versions_missing_zero_and_today():
 c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row;lab.migrate(c)
 def add(day,hour,score,version=lab.VERSION,ticker='MU'):
  at=datetime(2026,9,day,hour,tzinfo=lab.NY).timestamp()
  axes=[dict(name=n,score=score,strength=score,direction=None,state='ready',reason='test') for n in lab.TITLES]
  c.execute('INSERT INTO signal_lab_snapshots(ticker,slot,version,observed,payload) VALUES(?,?,?,?,?)',(ticker,int(at//600),version,at,json.dumps({'axes':axes})))
 add(24,12,0);add(24,13,100);add(25,12,100);add(26,12,20)
 add(25,13,None);add(25,14,1,'old');add(25,14,1,ticker='AMD')
 now=datetime(2026,9,26,13,tzinfo=lab.NY).timestamp();d=h.detail(c,'MU',now);a=d['axes'][0]
 assert a['score']==20
 assert a['windows']['7']==dict(average=75.0,days=2,samples=3,delta=-55.0)
 assert a['points'][-1]['partial_day']
 assert len(a['points'])==3
 assert h.detail(c,'UNKNOWN',now) is None

def test_empty_indicators_do_not_become_zero():
 c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row;lab.migrate(c)
 now=datetime(2026,9,26,13,tzinfo=lab.NY).timestamp()
 axes=[dict(score=None) for _ in range(5)]
 c.execute('INSERT INTO signal_lab_snapshots(ticker,slot,version,observed,payload) VALUES(?,?,?,?,?)',('MU',int(now//600),lab.VERSION,now,json.dumps({'axes':axes})))
 d=h.detail(c,'MU',now)
 assert d['axes'][0]['windows']['30']['average'] is None
 assert d['axes'][0]['points'][0]['value'] is None


def test_x_ingestion_scores_without_options_and_merges_history(monkeypatch):
 c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row;lab.migrate(c)
 now=datetime(2026,9,26,13,tzinfo=lab.NY).timestamp()
 axes=[lab.axis(n,10) for n in lab.TITLES];axes[3]=lab.axis(lab.TITLES[3])
 panel=dict(ticker='MARA',axes=axes,observed=now-3600)
 c.execute('INSERT INTO signal_lab_snapshots(ticker,slot,version,observed,payload) VALUES(?,?,?,?,?)',('MARA',int((now-3600)//600),lab.VERSION,now-3600,json.dumps(panel)))
 monkeypatch.setattr(lab,'read_attention_counts',lambda *args:dict(end=now,current=100,previous=50,baseline=50,baseline_days=12))
 monkeypatch.setattr(lab,'read_posts',lambda *args:[])
 assert lab.record_x(c,'MARA',now)
 assert lab.record_x(c,'MARA',now+1)
 assert c.execute('SELECT count(*) FROM signal_x_history').fetchone()[0]==1
 d=h.detail(c,'MARA',now+2)
 assert d['axes'][3]['score']==100
 assert d['axes'][3]['points'][-1]['value']==100
 assert d['axes'][3]['as_of']==now
 assert d['axes'][0]['score']==10
 # A later market snapshot with missing X must not erase valid saved X.
 panel['observed']=now+300
 lab.overlay_x(c,[panel],now+8000)
 assert panel['axes'][3]['score']==100 and panel['axes'][3]['stale']


def test_x_missing_counts_does_not_save_a_fake_zero(monkeypatch):
 c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
 monkeypatch.setattr(lab,'read_attention_counts',lambda *args:{'error':'No fresh counts'})
 assert not lab.record_x(c,'MARA',123)
 assert c.execute('SELECT count(*) FROM signal_x_history').fetchone()[0]==0
