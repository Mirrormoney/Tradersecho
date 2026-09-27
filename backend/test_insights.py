import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from . import insights, community
import sqlite3
from contextlib import contextmanager
@contextmanager
def empty_db():
 c=sqlite3.connect(':memory:');c.execute('CREATE TABLE research_documents(result TEXT,status TEXT,updated REAL)')
 try:yield c
 finally:c.close()

def test_topic_requires_staff_and_never_caches(monkeypatch):
 app=FastAPI();app.include_router(insights.router);client=TestClient(app)
 class Core:
  db=staticmethod(empty_db)
  def account(self,request):return {'demo':False,'role':request.headers.get('test-role','member')}
 monkeypatch.setattr(community,'core',lambda:Core())
 for role in ('member','premium','founder'):
  r=client.get('/api/admin/insights/800-vdc',headers={'test-role':role});assert r.status_code==403
  assert 'AWS' not in r.text
 for role in ('owner','admin'):
  r=client.get('/api/admin/insights/800-vdc',headers={'test-role':role});assert r.status_code==200
  assert r.headers['cache-control']=='private, no-store'
  assert len(r.json()['timeline'])==7
 assert client.get('/api/insights/800-vdc').status_code==401

def test_starter_evidence_references():
 a=insights.ARTICLE;sources={s['id'] for s in a['sources']}
 for event in a['timeline']:
  assert event['source'] in sources and event['page']
  if event.get('also_source'):assert event['also_source'] in sources
 assert 'automatic topic updates are enabled yet' in a['editorial']

def test_beneficiary_links_and_sources():
 import json
 from pathlib import Path
 universe=json.loads(Path(__file__).with_name('stock_universe.json').read_text(encoding='utf-8'))
 tickers={r['ticker'] for r in universe}
 sources={s['id'] for s in insights.ARTICLE['sources']}
 for b in insights.ARTICLE['beneficiaries']:
  assert b['ticker'] in tickers
  assert b['source'] in sources
  assert b['why'] and b['watch'] and b['timing'] and b['page']

def test_all_topics_private_and_complete(monkeypatch):
 import json
 from pathlib import Path
 tickers={r['ticker'] for r in json.loads(Path(__file__).with_name('stock_universe.json').read_text())}
 class Core:
  db=staticmethod(empty_db)
  def account(self,request):return {'demo':False,'role':request.headers.get('test-role','member')}
 monkeypatch.setattr(community,'core',lambda:Core())
 app=FastAPI();app.include_router(insights.router);client=TestClient(app)
 assert client.get('/api/admin/insights').status_code==403
 listing=client.get('/api/admin/insights',headers={'test-role':'admin'})
 assert listing.headers['cache-control']=='private, no-store'
 assert len(listing.json())==7
 for slug,a in insights.ARTICLES.items():
  path='/api/admin/insights/'+slug
  assert client.get(path).status_code==403
  assert client.get(path,headers={'test-role':'admin'}).status_code==200
  assert client.get('/api/insights/'+slug).status_code==401
  refs={s['id'] for s in a['sources']}
  assert len(a['timeline'])>=2 and a['intro'] and a['questions']
  for b in a['beneficiaries']:
   assert b['ticker'] in tickers and b['source'] in refs
  for event in a['timeline']:assert event['source'] in refs
 assert client.get('/api/admin/insights/missing',headers={'test-role':'admin'}).status_code==404
