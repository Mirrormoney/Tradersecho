import copy,json
import pytest
from .research import validated_choice
from .research_partial import complete_prefix,normalize_layout
from .test_research import REPORT,TEXT

CAT={'NVDA':'NVIDIA','AMD':'Advanced Micro Devices'}
def choice(raw,finish='length'):return {'finish_reason':finish,'message':{'content':raw}}
def unfinished(report=REPORT):return json.dumps(report)[:-2]+', {"ticker":"AMD","summary":"unfinished'

def test_complete_finding_survives_truncated_sibling():
 result=validated_choice(choice(unfinished()),TEXT,CAT)
 assert [f['ticker'] for f in result['findings']]==['NVDA']
 assert result['validation_warnings']['partial_response']
 assert result['topic_developments']==[]

def test_escaped_layout_whitespace_loop():
 raw=json.dumps(REPORT,indent=2).replace('\n',r'\n')[:-2]+r',\n\t\n\t'
 assert validated_choice(choice(raw),TEXT,CAT)['findings'][0]['ticker']=='NVDA'

def test_incomplete_finding_never_completed():
 raw=json.dumps(REPORT).split('"evidence"')[0]
 with pytest.raises(ValueError):validated_choice(choice(raw),TEXT,CAT)

@pytest.mark.parametrize('change',[{'date_evidence':'Invented date'},{'report_date':'2099-01-01'}])
def test_invalid_metadata_rejected(change):
 report=copy.deepcopy(REPORT);report.update(change)
 with pytest.raises(ValueError):validated_choice(choice(unfinished(report)),TEXT,CAT)

def test_bad_evidence_not_salvaged():
 report=copy.deepcopy(REPORT);report['findings'][0]['evidence']='NVIDIA invents a nonexistent quote.'
 with pytest.raises(ValueError):validated_choice(choice(unfinished(report)),TEXT,CAT)

def test_valid_sibling_kept_when_complete_other_finding_invalid():
 report=copy.deepcopy(REPORT);bad=copy.deepcopy(report['findings'][0]);bad['ticker']='AMD';bad['evidence']='A fabricated supporting sentence.';report['findings'].insert(0,bad)
 result=validated_choice(choice(json.dumps(report)),TEXT,CAT)
 assert [f['ticker'] for f in result['findings']]==['NVDA']
 assert result['validation_warnings']['held_tickers']==['AMD']

def test_duplicate_ticker_rejected():
 report=copy.deepcopy(REPORT);report['findings']*=2
 with pytest.raises(ValueError):validated_choice(choice(json.dumps(report)),TEXT,CAT)

def test_refusal_is_not_recovered():
 with pytest.raises(ValueError):validated_choice(choice(json.dumps(REPORT),'content_filter'),TEXT,CAT)

def test_string_contents_preserved():
 raw=r'{\n"evidence":"literal \\n and escaped \" quote"}'
 assert r'literal \\n' in normalize_layout(raw)

def test_complete_report_unchanged():
 assert 'validation_warnings' not in validated_choice(choice(json.dumps(REPORT),'stop'),TEXT,CAT)
