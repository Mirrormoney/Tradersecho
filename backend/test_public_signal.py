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
