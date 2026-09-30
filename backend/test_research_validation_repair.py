import copy
import pytest
import httpx
from backend import research as r
from backend.test_research import REPORT,TEXT

def test_unique_exact_quote_corrects_page_without_rewriting():
 v=copy.deepcopy(REPORT);v['findings'][0]['page']=2
 result=r.validate_report(v,TEXT,{'NVDA':'NVIDIA'})
 assert result['findings'][0]['page']==1
 assert result['findings'][0]['evidence']=='NVIDIA expects improving demand.'

def test_wrong_page_ambiguous_or_paraphrased_quote_stays_rejected():
 with pytest.raises(ValueError):r.located_quote('NVIDIA expects stronger demand.',TEXT,2)
 repeated=TEXT+'\n[Page 3]\nNVIDIA expects improving demand.'
 with pytest.raises(ValueError):r.located_quote('NVIDIA expects improving demand.',repeated,2)

def test_timeout_error_does_not_expose_request_or_secret():
 assert r.analysis_failure(httpx.ReadTimeout('secret'))=='AI request timed out'
 assert r.analysis_failure(RuntimeError('secret'))=='Analysis needs manual review; response failed validation'

def test_normal_analysis_uses_low_reasoning_and_bounded_output():
 assert r.analysis_generation_limits({})=={'max_tokens':6000,'reasoning_effort':'low'}

def test_company_names_anywhere_are_candidates_not_automatic_findings():
 cat={'FORM':'FormFactor, Inc.','MU':'Micron Technology, Inc.','ON':'ON Semiconductor Corporation'}
 assert 'FORM' in r.mentioned_candidates('FormFactor On good form - initiate with Buy.pdf',cat)
 assert 'FORM' in r.mentioned_candidates('Body text: formfactor expects higher demand.',cat)
 assert 'MU' in r.mentioned_candidates('Body text mentions Micron Technology.',cat)
 assert 'FORM' not in r.mentioned_candidates('A different form factor is needed.',cat)
 assert not r.mentioned_candidates('No covered company here.',cat)
 assert r.coverage_gaps({'findings':[{'ticker':'MU','attribution':'readthrough'}]},'FormFactor initiation',cat)==['FORM']
 assert r.coverage_gaps({'findings':[{'ticker':'FORM','attribution':'original'}]},'FormFactor initiation',cat)==[]

def test_separate_complete_sentences_all_require_exact_same_page_evidence():
 text='[Page 1]\nWe initiate APH with an Outperform rating.\nOther intervening discussion.\nAI demand is increasing rapidly.'
 quote='We initiate APH with an Outperform rating. AI demand is increasing rapidly.'
 verified,page=r.located_quote(quote,text,1)
 assert '[…]' in verified and page==1
 assert r.page_quote(verified,text,1)==verified
 for bad in ['We initiate APH with a Buy rating. AI demand is increasing rapidly.', 'We initiate APH with an Outperform rating. AI demand is increasing rapid']:
  with pytest.raises(ValueError):r.page_quote(bad,text,1)
 with pytest.raises(ValueError):r.page_quote(quote,text.replace('AI demand','[Page 2]\nAI demand'),1)

def test_bad_company_does_not_withhold_independent_valid_company():
 v=copy.deepcopy(REPORT)
 v['findings'].append({**v['findings'][0],'ticker':'MU','evidence':'Micron raised guidance unexpectedly.'})
 result=r.validate_report(v,TEXT,{'NVDA':'NVIDIA','MU':'Micron'})
 assert [f['ticker'] for f in result['findings']]==['NVDA']
 assert result['validation_warnings']=={'held_tickers':['MU']}
 v['findings'][0]['evidence']='NVIDIA raised guidance unexpectedly.'
 with pytest.raises(ValueError):r.validate_report(v,TEXT,{'NVDA':'NVIDIA','MU':'Micron'})
