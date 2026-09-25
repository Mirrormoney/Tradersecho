from contextlib import contextmanager
from types import SimpleNamespace
from fastapi import Response
from . import uw_pilot,signal_lab

def test_public_response_strips_private_provider_data(monkeypatch):
 @contextmanager
 def db():yield object()
 monkeypatch.setattr(uw_pilot,'core',lambda:SimpleNamespace(db=db,CATALOG={'NVDA':('NVIDIA',)}))
 axes=[dict(name=str(i),score=65,strength=65,direction=None,state='ready',reason='Derived explanation',details={'secret':'private'}) for i in range(5)]
 monkeypatch.setattr(signal_lab,'saved',lambda c:{'stocks':[dict(ticker='NVDA',observed=1,axes=axes,options_observation={'raw':'trades'},price=123)]})
 response=Response();result=uw_pilot.public_signals(response)
 assert len(result['stocks'])==1
 row=result['stocks'][0]
 assert 'price' not in row and 'options_observation' not in row
 assert all('details' not in a for a in row['axes'])
 assert row['stale'] and row['activity']==65
 assert 'public' in response.headers['Cache-Control']
