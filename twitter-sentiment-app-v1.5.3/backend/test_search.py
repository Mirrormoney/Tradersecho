import json,sqlite3,unittest,time
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
from . import search as m

class SearchTests(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row
  self.c.executescript('''CREATE TABLE stocks(ticker TEXT,name TEXT,active INTEGER);
  CREATE TABLE sec_filings(accession TEXT,cik TEXT,form TEXT,title TEXT,filed TEXT,url TEXT,accepted REAL);
  CREATE TABLE sec_companies(ticker TEXT,cik TEXT);
  CREATE TABLE posts(id TEXT,source TEXT,author TEXT,text TEXT,ts REAL);
  CREATE TABLE mentions(source TEXT,post_id TEXT,ticker TEXT);
  CREATE TABLE research_documents(id TEXT,result TEXT,status TEXT,received REAL);
  CREATE TABLE research_links(document_id TEXT,ticker TEXT);
  INSERT INTO stocks VALUES('NVDA','NVIDIA Corporation',1),('OLD','Old stock',0);
  INSERT INTO sec_companies VALUES('NVDA','1');
  INSERT INTO sec_filings VALUES('123','1','10-Q','Quarterly report','2026-09-20','https://www.sec.gov/',1);
  ''')
  report={'title':'NVIDIA update','firm':'Desk','findings':[{'ticker':'NVDA','summary':'Secret private research demand'}]}
  self.c.execute("INSERT INTO research_documents VALUES('1',?,'draft',1)",(json.dumps(report),))
  self.c.execute("INSERT INTO research_links VALUES('1','NVDA')")
 def tearDown(self):self.c.close()
 def run_search(self,q,user=None):
  @contextmanager
  def db():yield self.c
  with patch.object(m,'core',return_value=SimpleNamespace(db=db,account=lambda *a,**k:user)):
   return m.search(None,q)['results']
 def test_guest_only_stock_identity(self):
  rows=self.run_search('$NVDA');self.assertEqual([r['kind'] for r in rows],['stock'])
 def test_company_name(self):self.assertEqual(self.run_search('Nvidia')[0]['ticker'],'NVDA')
 def test_free_cannot_search_private_research(self):self.assertEqual(self.run_search('Secret',{'role':'member'}),[])
 def test_admin_research(self):self.assertEqual(self.run_search('Secret',{'role':'admin'})[0]['kind'],'research')
 def test_filing_type(self):self.assertEqual(self.run_search('10-Q',{'role':'member'})[0]['kind'],'filing')
 def test_wildcards_literal(self):self.assertEqual(self.run_search('%%',{'role':'admin'}),[])
 def test_inactive_and_short(self):
  self.assertEqual(self.run_search('Old'),[]);self.assertEqual(self.run_search('N'),[])
