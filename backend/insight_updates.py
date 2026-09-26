"""Evidence-checked private topic developments from the shared research analysis."""
import copy,hashlib,json,re
from datetime import date,timedelta
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field

PATTERNS={
 '800-vdc':r'800\s*V|solid.state transformer|\bSST\b',
 'hbm':r'\bHBM\d*\b|high.bandwidth memory',
 'advanced-packaging':r'CoWoS|SoIC|advanced packaging|chiplet|3D.stack|XDSiP',
 'optical-networking':r'photonics|optical|co.packaged optics|\bCPO\b|800G|1\.6T',
 'liquid-cooling':r'liquid.cool|cold.plate|coolant|cooling distribution',
 'ai-power':r'data.?cent|grid|gas turbine|power generation|energiz',
 'ai-inference':r'inference|custom accelerator|Trainium|\bXPU\b|\bTPU\b',
}
class Development(BaseModel):
 model_config=ConfigDict(extra='forbid')
 topic:Literal['800-vdc','hbm','advanced-packaging','optical-networking','liquid-cooling','ai-power','ai-inference']
 summary:str=Field(min_length=20,max_length=420)
 evidence:str=Field(min_length=20,max_length=600)
 page:int=Field(ge=1,le=4)
 timing:str|None=Field(default=None,max_length=80)
 kind:Literal['forecast','revision','reported_milestone','risk']

PROMPT=''' Also return topic_developments, at most three material AI infrastructure developments across these topic IDs: 800-vdc, hbm, advanced-packaging, optical-networking, liquid-cooling, ai-power, ai-inference. Each item contains topic, summary (one short factual paraphrase), evidence (one continuous exact quote of 20-600 characters supporting the entire summary), page, timing (exact timing words from that quote, or null), and kind (forecast, revision, reported_milestone, risk). Require concrete new expectations, changed timing, qualification, capacity, orders, deployments or a material obstacle. A keyword or generic market commentary is insufficient. Return [] if absent. Keep every number, named entity, timing and assertion supported by that same quote. Preserve uncertainty and distinguish a broker's expectation from a reported event; never present an expected milestone as completed. Do not infer beneficiaries, company links, completed events, or dates. A revision must be explicitly described as a change in the source. Topic developments are optional: prioritize complete stock findings and return fewer developments if output space is limited.'''

def validate_updates(items,text,page_quote):
 accepted=[]
 for item in items[:3] if isinstance(items,list) else []:
  try:
   d=Development.model_validate(item)
   d.evidence=page_quote(d.evidence,text,d.page)
   if not re.search(PATTERNS[d.topic],d.evidence,re.I):continue
   if d.timing and d.timing.casefold() not in d.evidence.casefold():continue
   # Do not allow unsupported numeric claims in the paraphrase.
   if not set(re.findall(r'\d+(?:[.,]\d+)*',d.summary))<=set(re.findall(r'\d+(?:[.,]\d+)*',d.evidence)):continue
   accepted.append(d.model_dump())
  except (ValueError,TypeError):continue
 return accepted

def merge_updates(article,rows,today=None):
 """Append source-dated expectations; never overwrite previous forecasts."""
 result=copy.deepcopy(article);events=[];seen=set();today=today or date.today()
 for row in rows:
  try:
   report=json.loads(row['result']);published=date.fromisoformat(report['report_date'])
   if published>today or not report.get('firm'):continue
   for d in report.get('topic_developments',[]):
    if d['topic']!=article['slug']:continue
    # Collapse repeated source passages even across forwarded/renamed documents.
    key=hashlib.sha256(re.sub(r'\W+','',d['evidence'].casefold()).encode()).hexdigest()
    if key in seen:continue
    seen.add(key);sid='research-'+key[:20]
    result['sources'].append({'id':sid,'name':report['firm'],'date':published.isoformat(),'kind':'Imported research','label':'Research development','pages':''})
    events.append({'when':d.get('timing') or 'Timing not specified','title':{'forecast':'New expectation','revision':'Revised expectation','reported_milestone':'Reported development','risk':'Development to watch'}[d['kind']], 'source':sid,'expectation':d['summary'],'scope':'Research dated '+published.isoformat(),'watch':'','page':'','report_date':published.isoformat()})
  except (ValueError,TypeError,KeyError):continue
 events.sort(key=lambda e:e['report_date'],reverse=True)
 result['timeline']=events+result['timeline']
 result['automatic_updates']=len(events)
 if events:result['evidence_through']=max(result.get('evidence_through') or '',events[0]['report_date'])
 result['editorial']='Private starter with automatic, evidence-checked developments from incoming research. Original PDFs and evidence remain private. Earlier forecasts are retained; new research does not automatically confirm them.'
 return result
