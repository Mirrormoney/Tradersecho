from .test_service import s,isolate_tests
from .research import validate_report,queue_email_backlog,response_format
from .research_readthrough import attach_readthroughs
from .research_feed import clean_finding
import json,time

def test_sector_links_are_explicit_and_allowlisted():
 value={'title':'Memory outlook','firm':'UBS','report_date':None,'date_evidence':'','findings':[],'sector_findings':[{'topic':'dram','summary':'UBS expects DRAM supply to remain tight into the next quarter.','evidence':'DRAM supply remains tight into the next quarter.','page':1}]}
 result=validate_report(value,'[Page 1]\nDRAM supply remains tight into the next quarter.',{'MU':'Micron','SNDK':'Sandisk','WDC':'Western Digital'})
 assert [f['ticker'] for f in result['findings']]==['MU']
 f=result['findings'][0];assert f['stance']=='unclear' and f['event'] is None
 public=clean_finding({**result,'id':'test'},f)
 assert public['link_type']=='sector_readthrough' and public['firm']=='UBS'
 assert 'not a company-specific' in public['link_reason']
 value['sector_findings'][0]['topic']='nand'
 assert validate_report(value,'[Page 1]\nDRAM supply remains tight into the next quarter.',{'MU':'Micron'})['findings']==[]

def test_direct_comment_wins_and_schema_complete():
 result={'findings':[{'ticker':'MU','summary':'Direct view'}],'sector_findings':[{'topic':'nand','evidence':'NAND demand is growing','summary':'NAND demand is growing across memory applications.','page':1}]}
 got=attach_readthroughs(result,{'MU':'Micron','SNDK':'Sandisk'})
 assert len(got['findings'])==2 and got['findings'][0]['summary']=='Direct view'
 schema=response_format({'MU':'Micron'})['json_schema']['schema']
 assert set(schema['required'])==set(schema['properties'])

def test_email_backlog_enters_queue():
 with s.db() as c:
  c.execute("INSERT INTO research_documents(id,filename,sender,received,text,pages,status,updated) VALUES('email-auto','Memory.pdf','test',?,'[Page 1]\nMemory demand is rising.',1,'awaiting_analysis',?)",(time.time(),time.time()))
 queue_email_backlog()
 with s.db() as c:assert c.execute("SELECT status FROM research_documents WHERE id='email-auto'").fetchone()[0]=='queued'

def test_pdf_column_evidence_stays_exact():
 from .research import page_quote
 import pytest
 text='[Page 1]\nDRAM demand is growing        Analyst contact\nand supply is constrained.        contact@example.com'
 assert page_quote('DRAM demand is growing and supply is constrained.',text,1)=='DRAM demand is growing\nand supply is constrained.'
 with pytest.raises(ValueError):page_quote('DRAM demand is falling and supply is constrained.',text,1)
 with pytest.raises(ValueError):page_quote('DRAM demand is growing',text,2)

def test_optical_readthrough_does_not_invent_rating_or_link_uncovered_stock():
 value={'title':'Optical demand','firm':'UBS','report_date':None,'date_evidence':'','findings':[], 'sector_findings':[{'topic':'optical-networking','summary':'UBS expects optical component demand to rise in 2027.','evidence':'Optical component demand should rise in 2027.','page':1}]}
 result=validate_report(value,'[Page 1]\nOptical component demand should rise in 2027.',{'LITE':'Lumentum','NVDA':'NVIDIA'})
 assert [f['ticker'] for f in result['findings']]==['LITE']
 assert result['findings'][0]['stance']=='unclear'
 assert result['findings'][0]['event'] is None
 assert result['analysis_version']=='research-context-v2'


def test_exposure_requires_actual_company_evidence_and_keeps_healthy_items():
 value={'title':'Optics','firm':'UBS','report_date':None,'date_evidence':'','findings':[], 'exposures':[
 {'topic':'optical-networking','ticker':'LITE','reason':'Lumentum supplies optical components for datacenters.','evidence':'Lumentum supplies optical components for datacenters.','page':1},
 {'topic':'optical-networking','ticker':'NVDA','reason':'NVIDIA supplies optical components for datacenters.','evidence':'Lumentum supplies optical components for datacenters.','page':1}]}
 result=validate_report(value,'[Page 1]\nLumentum supplies optical components for datacenters.',{'LITE':'Lumentum','NVDA':'NVIDIA'})
 assert [e['ticker'] for e in result['exposures']]==['LITE']


def test_extra_pages_stop_at_disclosure_and_low_information_stays_short():
 from .research import research_excerpt
 calls=[]
 def read(i):
  calls.append(i)
  return ('Demand forecast remains strong. '*12) if i<5 else 'Important disclosures\n'+('Legal text. '*20)
 text,pages=research_excerpt(read,20)
 assert pages==5 and len(calls)==6 and 'Legal text' not in text
 calls.clear()
 def short(i):
  calls.append(i);return 'Analyst contacts and office information. '*12
 text,pages=research_excerpt(short,20)
 assert pages==4 and len(calls)==4

def test_bad_optional_sector_does_not_block_valid_direct_summary():
 from .test_research import REPORT,TEXT
 import copy
 value=copy.deepcopy(REPORT)
 value['sector_findings']=[{'topic':'hbm','summary':'HBM demand will double in 2027.','evidence':'This quote does not exist in the document.','page':1}]
 result=validate_report(value,TEXT,{'NVDA':'NVIDIA'})
 assert len(result['findings'])==1 and result['sector_findings']==[]


def test_evidence_from_extended_pages_supported():
 from .test_research import REPORT,TEXT
 import copy
 value=copy.deepcopy(REPORT);value['findings'][0]['page']=8
 result=validate_report(value,TEXT+'\n[Page 8]\nNVIDIA expects improving demand.',{'NVDA':'NVIDIA'})
 assert result['findings'][0]['page']==8
