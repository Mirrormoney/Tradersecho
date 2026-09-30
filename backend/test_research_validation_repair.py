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
