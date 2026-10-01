import unittest
from .research_feed import clean_finding,deduplicate,restrict_feed,premium,public_item

class FeedTests(unittest.TestCase):
 def finding(self,original=False):
  return clean_finding({'id':'ubs' if original else 'gs','firm':'UBS' if original else 'Goldman Sachs','report_date':'2026-09-18'}, {'ticker':'ARRY','summary':'Our downgrade reflects demand.' if original else 'The author is reporting a third-party downgrade.','attribution':'original' if original else 'relayed','stance':'bearish','event':{'broker':'UBS','action':'downgrade','rating':'Neutral','date':'2026-09-18'}})
 def test_original_uses_broker_instead_of_report(self):
  result=clean_finding({'id':'x','firm':'Morgan Stanley'}, {'ticker':'ACMR','summary':'The report identifies ACMR as a beneficiary.','attribution':'original'})
  self.assertEqual(result['summary'],'Morgan Stanley identifies ACMR as a beneficiary.')
 def test_relay_not_credited_to_compiling_broker(self):
  result=clean_finding({'id':'x','firm':'Goldman Sachs'}, {'ticker':'ACMR','summary':'UBS downgrades ACMR.','attribution':'relayed'})
  self.assertEqual(result['summary'],'UBS downgrades ACMR.')
 def test_relay_has_no_compiler_badge(self):
  self.assertEqual(self.finding()['firm'],'')
 def test_original_replaces_relay_in_both_orders(self):
  a,b=self.finding(),self.finding(True)
  for items in ([a,b],[b,a]):self.assertEqual([r['firm'] for r in deduplicate(items)],['UBS'])
 def test_distinct_dates_not_merged(self):
  a,b=self.finding(),self.finding(True);b['event_key']+='next-day'
  self.assertEqual(len(deduplicate([a,b])),2)
 def test_uncertain_events_and_own_comments_preserved(self):
  a,b=self.finding(),self.finding(True);a['event_key']=None;b['event_key']=None
  self.assertEqual(len(deduplicate([a,b])),2)
 def test_free_receives_only_three_rows(self):
  rows=[{'ticker':t} for t in ['AES','FLNC','ARRY','MU']]
  r=restrict_feed(rows,[{'ticker':'NVDA'}],False)
  self.assertEqual(r['rows'],rows[:3]);self.assertEqual(r['other'],[])
  self.assertTrue(r['locked'])
 def test_free_fallback_only_three(self):
  rows=[{'ticker':t} for t in ['AES','FLNC','ARRY','MU']]
  r=restrict_feed([],rows,False)
  self.assertEqual(r['other'],rows[:3])
 def test_three_row_limit_spans_sections(self):
  r=restrict_feed([{'ticker':'AES'}],[{'ticker':'ARRY'},{'ticker':'FLNC'},{'ticker':'MU'}],False)
  self.assertEqual(r['rows'],[{'ticker':'AES'}])
  self.assertEqual(r['other'],[{'ticker':'ARRY'},{'ticker':'FLNC'}])
  self.assertEqual(r['total'],4)
 def test_premium_access_and_demo(self):
  self.assertTrue(premium({'plan':'premium'}));self.assertFalse(premium({'plan':'free'}));self.assertFalse(premium({'plan':'premium','demo':True}))
 def test_no_internal_keys(self):
  self.assertNotIn('event_key',public_item(self.finding()))

def test_today_spotlights_use_daily_rank_and_rest_is_chronological():
 from .research_feed import order_research
 catalog={t:(t,'Sector') for t in ['A','B','C','D','E','F']}
 def item(t,date,received):return {'ticker':t,'id':t+str(received),'report_date':date,'received':received,'summary':t}
 items=[item('A','2026-09-03',999),item('B','2026-09-21',1),item('C','2026-09-21',2),item('D','2026-09-20',4),item('E','2026-09-19',5),item('F','2026-09-21',3)]
 ranked=[{'ticker':t} for t in ['A','C','B','E','F','D']]
 top,rest=order_research(items,ranked,catalog,'2026-09-21')
 assert [r['ticker'] for r in top]==['C','B','F']
 assert [r['daily_rank'] for r in top]==[2,3,5]
 assert [r['ticker'] for r in rest]==['D','E','A']
 assert all('daily_rank' not in r for r in rest)
 assert all('received' not in i for r in top+rest for i in r['research'])
 top,rest=order_research(items,ranked,catalog,'2026-09-22')
 assert [r['ticker'] for r in top]==['F','C','B']
 assert all('daily_rank' not in r for r in top)


def test_partial_today_fills_tiles_with_newest_and_keeps_latest_note_first():
 from .research_feed import order_research
 items=[{'ticker':t,'id':str(i),'report_date':d,'received':i} for i,(t,d) in enumerate([('A','2026-09-03'),('A','2026-09-21'),('B','2026-09-20'),('C','2026-09-19'),('D','2026-09-18')])]
 top,rest=order_research(items,[{'ticker':'A'}],{t:(t,'s') for t in 'ABCD'},'2026-09-21')
 assert [r['ticker'] for r in top]==['A','B','C']
 assert top[0]['research'][0]['report_date']=='2026-09-21'
 assert [r['ticker'] for r in rest]==['D']

def test_published_ticker_filter_happens_in_database(monkeypatch):
 from backend import research_feed as f
 from types import SimpleNamespace
 class DB:
  def execute(self,sql,args=()):
   if sql.startswith('SELECT'):
    assert 'research_links' in sql and 'l.ticker=?' in sql
    assert args==('PANW',)
   return self
  def fetchall(self):return []
 monkeypatch.setattr(f,'core',lambda:SimpleNamespace(CATALOG={}))
 assert f.published(DB(),'PANW')==[]

def test_cached_feed_still_restricts_each_user(monkeypatch):
 from backend import research_feed as f
 from types import SimpleNamespace
 rows=[{'ticker':x} for x in ['PANW','MU','AES','ARRY']]
 monkeypatch.setattr(f,'shared_overview',lambda:(rows,[],123,'2026-09-23'))
 monkeypatch.setattr(f,'core',lambda:SimpleNamespace(account=lambda req:{'plan':req}))
 assert len(f.feed('premium')['rows'])==4
 assert len(f.feed('free')['rows'])==3
 assert f.feed('free')['locked']


def test_private_scoring_metadata_not_public():
 assert public_item({'ticker':'NVDA','_rating_event':{'broker':'Test'},'_price_target':{'current':100}})=={'ticker':'NVDA'}


def test_landing_latest_research_date_and_privacy():
 from .research_feed import latest_preview_item
 old={'summary':'Older note','report_date':'2026-09-20','received':999}
 new={'summary':'Latest full sentence. Another complete sentence.','report_date':'2026-10-01','received':1,'evidence':'PRIVATE','pdf':'PRIVATE','ticker':'MU'}
 item=latest_preview_item([old,new])
 assert item['summary']==new['summary']
 assert item['report_date']=='2026-10-01'
 assert set(item)=={'summary','report_date','link_type','link_reason'}
 assert latest_preview_item([]) is None
 assert latest_preview_item([{'summary':'Undated'}]) is None
