from contextlib import contextmanager
from types import SimpleNamespace
from fastapi import Response
from . import uw_pilot,signal_lab

def test_public_response_strips_private_provider_data(monkeypatch):
 @contextmanager
 def db():yield object()
 monkeypatch.setattr(uw_pilot,'core',lambda:SimpleNamespace(db=db,account=lambda request,required:None,CATALOG={'NVDA':('NVIDIA',)}))
 axes=[dict(name=str(i),score=65,strength=65,direction=None,state='ready',reason='Derived explanation',details={'secret':'private'}) for i in range(5)]
 monkeypatch.setattr(signal_lab,'saved',lambda c:{'stocks':[dict(ticker='NVDA',observed=1,axes=axes,options_observation={'raw':'trades'},price=123)]})
 response=Response();result=uw_pilot.public_signals(response,object())
 assert len(result['stocks'])==1
 row=result['stocks'][0]
 assert 'price' not in row and 'options_observation' not in row
 assert all('details' not in a for a in row['axes'])
 assert row['stale'] and row['activity']==65
 assert response.headers['Cache-Control']=='private, no-store'
 assert all('reason' not in a for a in row['axes'])

def test_admin_overview_keeps_expanded_coverage_private(monkeypatch):
 @contextmanager
 def db():yield object()
 calls=[]
 monkeypatch.setattr(uw_pilot,'staff',lambda request,owner=False:calls.append(owner))
 monkeypatch.setattr(uw_pilot,'core',lambda:SimpleNamespace(db=db,CATALOG={'NVDA':('NVIDIA',),'AVGO':('Broadcom',)}))
 axes=[dict(name=str(i),score=None,strength=None,details={'raw':'private'}) for i in range(5)]
 monkeypatch.setattr(signal_lab,'saved',lambda c:{'stocks':[dict(ticker=t,observed=1,axes=axes) for t in ('NVDA','AVGO','OUTSIDE')]})
 response=Response();result=uw_pilot.admin_signal_overview(object(),response)
 assert calls==[True]
 assert [r['ticker'] for r in result['stocks']]==['NVDA','AVGO']
 assert response.headers['Cache-Control']=='private, no-store'
 assert all('details' not in a for r in result['stocks'] for a in r['axes'])


def test_home_launch_coverage_ranking_and_overnight_freeze(monkeypatch):
 import sqlite3
 from datetime import datetime
 from .pro_access import LAUNCH_AT
 c=sqlite3.connect(':memory:');c.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
 names=['NVDA','AMD','MU','MARA','NVTS','META','AVGO']
 monkeypatch.setattr(uw_pilot,'core',lambda:SimpleNamespace(CATALOG={t:(t,) for t in names}))
 def panel(t,x,ready):
  values=[None]*5;values[3]=x
  for i in ready:values[i]=0 if i==4 else 50
  return {'ticker':t,'axes':[{'score':v} for v in values]}
 panels=[panel('MARA',100,[]),panel('NVTS',90,[0,4]),panel('META',80,[0,1]),panel('AVGO',70,[1,4])]
 assert uw_pilot.home_preview_tickers(c,panels,LAUNCH_AT-1)==list(uw_pilot.FOCUS)
 during=datetime(2026,10,1,11,tzinfo=uw_pilot.NY).timestamp()
 assert uw_pilot.home_preview_tickers(c,panels[:2],during)==list(uw_pilot.FOCUS)
 assert uw_pilot.home_preview_tickers(c,panels,during)==['NVTS','META','AVGO']
 panels[0]=panel('MARA',100,[0,4])
 night=datetime(2026,10,1,20,tzinfo=uw_pilot.NY).timestamp()
 assert uw_pilot.home_preview_tickers(c,panels,night)==['NVTS','META','AVGO']
 tomorrow=datetime(2026,10,2,11,tzinfo=uw_pilot.NY).timestamp()
 assert uw_pilot.home_preview_tickers(c,panels,tomorrow)==['MARA','NVTS','META']
