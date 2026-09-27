import json
from datetime import date
from .insight_updates import validate_updates,merge_updates
from .research import page_quote,validate_report

TEXT='[Page 1]\nSeptember 26, 2026\nHBM4 qualification is expected in 2027.'
EVENT={'topic':'hbm','summary':'HBM4 qualification is expected in 2027.','evidence':'HBM4 qualification is expected in 2027.','page':1,'timing':'2027','kind':'forecast'}

def test_optional_bad_updates_do_not_block_other_updates_or_report():
 bad=dict(EVENT,evidence='HBM4 qualification completed in 2026.')
 assert validate_updates([bad,EVENT],TEXT,page_quote)==[EVENT]
 report={'title':'Memory','firm':'Broker','report_date':'2026-09-26','date_evidence':'September 26, 2026','findings':[],'topic_developments':[bad,EVENT]}
 assert len(validate_report(report,TEXT,{},'')['topic_developments'])==1

def test_unsupported_timing_numbers_and_topic_are_dropped():
 for d in [dict(EVENT,timing='2028'),dict(EVENT,summary='HBM4 grows 50% in 2027.'),dict(EVENT,topic='liquid-cooling'),dict(EVENT,page=2)]:
  assert validate_updates([d],TEXT,page_quote)==[]

def test_extended_memory_generation_is_recognised():
 d=dict(EVENT,summary='HBM4E qualification is expected in 2027.',evidence='HBM4E qualification is expected in 2027.')
 assert validate_updates([d],TEXT.replace('HBM4','HBM4E'),page_quote)==[d]

def test_liquid_to_liquid_architecture_is_recognised():
 quote='Liquid-to-liquid cooling is expected to gain traction in 2027.'
 d=dict(EVENT,topic='liquid-cooling',summary=quote,evidence=quote)
 assert validate_updates([d],'[Page 1]\n'+quote,page_quote)==[d]

def test_merge_deduplicates_preserves_old_forecasts_and_private_evidence():
 base={'slug':'hbm','sources':[],'timeline':[{'title':'Starter'}],'evidence_through':'2026-01-01'}
 row={'result':json.dumps({'firm':'Broker','report_date':'2026-09-26','topic_developments':[EVENT]})}
 result=merge_updates(base,[row,row],date(2026,9,26))
 assert result['automatic_updates']==1 and len(result['timeline'])==2
 assert result['timeline'][0]['when']=='2027'
 assert result['timeline'][1]['title']=='Starter'
 assert 'evidence' not in result['timeline'][0]
 assert base['sources']==[]
 future={'result':json.dumps({'firm':'Broker','report_date':'2026-09-27','topic_developments':[EVENT]})}
 assert merge_updates(base,[future,{'result':'bad json'}],date(2026,9,26))['automatic_updates']==0
