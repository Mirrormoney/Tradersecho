"""Editorial context and source-dated milestones; never invented adoption dates."""
from datetime import date
import calendar
import copy
import re

# Questions are editorial research prompts, not predictions or reported facts.
GUIDES = {
 '800-vdc': {
  'thesis':'Follow the path from higher rack power to electrical redesign, supplier qualification and orders. A voltage roadmap is not the same as revenue for every power supplier.',
  'glossary':{'VDC':'Volts of direct current.','SST':'Solid-state transformer: a separate power-conversion architecture, not a synonym for 800 VDC.','Qualification':'A customer verifies that a component meets its operating requirements.'},
  'watch_metrics':['Rack power and deployment architecture','Qualified conversion and protection components','Orders versus design partnerships','Installation timing and conversion efficiency'],
  'debates':['How quickly will existing facilities retrofit rather than wait for new construction?','Which conversion stages retain the most value as voltage changes?'],
  'invalidation':['Rack rollouts are delayed.','Qualification or safety requirements postpone supplier revenue.']},
 'hbm': {
  'thesis':'Separate rising memory content per accelerator from memory pricing and supplier market share. More HBM demand can help revenue, but qualification, yield and capital intensity determine who captures it.',
  'glossary':{'HBM':'High-bandwidth memory: stacked memory placed close to an accelerator.','HBM4':'A generation of HBM; customer qualification and volume production are separate milestones.','Bit demand':'The amount of memory required, distinct from its dollar market value.'},
  'watch_metrics':['HBM capacity per accelerator and accelerator shipments','HBM3E to HBM4 product mix','Customer qualification and usable production yield','Contract prices, wafer allocation and capacity additions'],
  'debates':['Does memory content grow faster than efficiency improvements reduce requirements?','Do additional suppliers ease scarcity or merely meet expanding demand?'],
  'invalidation':['Accelerator shipments or memory configurations fall below expectations.','Pricing weakens or a supplier loses qualification/share.']},
 'advanced-packaging': {
  'thesis':'Packaging brings logic and memory together. Track usable output for the relevant package, not just factory spending: a larger package can consume more capacity even with unchanged chip shipments.',
  'glossary':{'CoWoS':'TSMC packaging that integrates logic and memory through an interposer.','SoIC':'TSMC technology for stacking and connecting chips in three dimensions.','Yield':'The fraction of production that meets specifications.'},
  'watch_metrics':['Package size and capacity by process','Customer qualification and yield','Equipment installation versus volume output','Substrate and testing constraints'],
  'debates':['Which bottleneck moves next: packaging, substrates, memory or testing?','Will alternative packaging win qualified customer programmes?'],
  'invalidation':['Installed capacity ramps faster than demand.','Yield or customer programme delays prevent expected output.']},
 'optical-networking': {
  'thesis':'Track three distinct transitions: faster pluggable modules, optics beside switch silicon, and optical links between accelerators. Each changes the component bill differently; optical demand is not one uniform trade.',
  'glossary':{'800G / 1.6T':'Nominal link speeds: 800 gigabits or 1.6 terabits per second.','CPO':'Co-packaged optics: optical engines integrated close to switch silicon.','InP':'Indium phosphide, a semiconductor material used in optical components.','Scale-up / scale-out':'Links within a tightly coupled compute system versus links across systems.'},
  'watch_metrics':['800G to 1.6T shipment mix','Laser/component orders and capacity reservations','Customer qualification versus product demonstrations','CPO deployment volumes and pluggable demand','InP supply, export permits and margins'],
  'debates':['Where do serviceable pluggable modules retain an advantage over CPO?','Does a design win become material revenue, and on whose timetable?'],
  'invalidation':['Customer deployment slips.','Architecture changes reduce a supplier’s component content.','Capacity expansion or pricing pressure weakens margins.']},
 'liquid-cooling': {
  'thesis':'Follow actual rack designs and facility orders. Direct-to-chip cooling, immersion and heat rejection outside the building solve different problems; water cooling is not a single product category.',
  'glossary':{'Cold plate':'A liquid-cooled plate that removes heat directly from a component.','CDU':'Coolant distribution unit: manages liquid flow and heat exchange.','Immersion':'Electronics placed in a suitable insulating fluid.','Heat rejection':'Moving collected heat from the facility to its surroundings.'},
  'watch_metrics':['Rack density and required cooling architecture','Cold-plate and CDU qualification','Order intake, backlog conversion and service revenue','Facility water, temperature and retrofit constraints'],
  'debates':['Which workloads justify immersion versus direct-to-chip cooling?','How much existing infrastructure can be reused?'],
  'invalidation':['Rack installations are delayed.','Supplier designs fail qualification or competitors compress margins.']},
 'ai-power': {
  'thesis':'A planned datacenter needs delivered power, not simply an announced project. Separate grid connections, bridge generation, permanent generation and electrical equipment; their lead times and commercial risks differ.',
  'glossary':{'Interconnection':'Permission and infrastructure needed to connect to the grid.','Bridge power':'An interim power source while permanent capacity is arranged.','Backlog':'Contracted work not yet delivered; it is not all current revenue.'},
  'watch_metrics':['Energisation dates versus construction announcements','Firm orders versus reserved manufacturing slots','Turbine, transformer and switchgear delivery timing','Permitting, fuel supply and customer commitments'],
  'debates':['Will projects use grid supply, on-site generation or a combination?','Which announced projects have financing and committed customers?'],
  'invalidation':['Permits, fuel or grid access delay energisation.','Reservations fail to convert to firm orders.']},
 'ai-inference': {
  'thesis':'Inference runs trained models. The commercial question is useful output at the required latency and cost, including memory, networking, software and utilisation—not peak chip performance alone.',
  'glossary':{'Inference':'Using a trained model to produce answers or predictions.','Latency':'How long a user waits for a response.','Utilisation':'How much installed compute is productively used.','Custom accelerator':'A processor designed for a narrower set of workloads.'},
  'watch_metrics':['Cost per useful output at comparable quality','Memory bandwidth and capacity','Production availability and customer adoption','Utilisation, power and software portability'],
  'debates':['Will lower cost expand usage enough to increase total infrastructure demand?','Which workloads favour custom chips over general-purpose accelerators?'],
  'invalidation':['Benchmarks do not translate to production workloads.','Software or deployment constraints limit adoption.']},
}

SOURCES = {
 'mu-q3-2026':('Micron','2026-06-24','https://investors.micron.com/news/press-release/2026/Micron-Technology-Inc--Reports-Record-Results-for-the-Third-Quarter-of-Fiscal-2026/default.aspx','HBM4 shipments and HBM4E production outlook'),
 'vrt-dsx-2026':('Vertiv','2026-09-21','https://www.vertiv.com/en-emea/about/news-and-events/news-releases/2026/vertiv-coolant-distribution-unit-qualified-as-nvidia-dsx-ready-for-ai-factory-infrastructure/','2.3 MW CDU qualification'),
 'nv-optics-2025':('NVIDIA','2025-08-18','https://developer.nvidia.com/blog/scaling-ai-factories-with-co-packaged-optics-for-better-power-efficiency/','Photonics availability roadmap'),
 'lite-2026':('Lumentum','2026-03-02','https://investor.lumentum.com/financial-news-releases/news-details/2026/NVIDIA-Announces-Strategic-Partnership-With-Lumentum-to-Develop-State-of-the-Art-Optics-Technology/default.aspx','NVIDIA optics agreement'),
 'cohr-2026':('Coherent','2026-09-20','https://ir.coherent.com/news-releases/news-release-details/coherent-showcases-optical-innovations-scale-ai-infrastructure','ECOC optical technology demonstrations'),
 'axt-2026':('AXT','2026-07-29','https://investors.axt.com/Investors/news/news-details/2026/AXT-Inc--Announces-Long-Term-Supplier-Agreement-with-Lumentum/default.aspx','Lumentum substrate supply and capacity agreement'),
 'tf-hbm-2026':('TrendForce','2026-06-02','https://www.trendforce.com/presscenter/news/20260602-13074.html','HBM wafer allocation forecast'),
 'tf-memory-2026':('TrendForce','2026-07-30','https://www.trendforce.com/presscenter/news/20260730-13158.html','2027 memory supply outlook'),
 'tsm-tech-2026':('TSMC','2026-04-22','https://pr.tsmc.com/english/news/3302','Technology symposium production milestones'),
 'vrt-frontiers':('Vertiv','2026-01-08','https://www.vertiv.com/en-us/about/news-and-events/corporate-news/vertiv-expects-powering-up-for-ai-digital-twins-and-adaptive-liquid-cooling-to-shape-data-center-design-and-operations/','Infrastructure and adaptive cooling outlook'),
 'aws-t3':('AWS','2025-12-02','https://press.aboutamazon.com/2025/12/trainium3-ultraservers-now-available-enabling-customers-to-train-and-deploy-ai-models-faster-at-lower-cost','Trainium3 availability announcement'),
 'aws-t4':('Amazon',None,'https://www.aboutamazon.com/news/company-news/amazon-earnings-q4-2025-report','Q4 2025 results and Trainium4 outlook'),
 'gev-2025':('GE Vernova','2025-12-09','https://www.gevernova.com/sites/default/files/gev_webcast_transcript_12092025.pdf','Investor update: gas orders and bridge power'),
}

# Explicit status is essential: a calendar date passing never proves completion.
EVENTS = {
 'optical-networking':[
  ('nv-optics-2025','2026-06-30','Early 2026','Earlier InfiniBand availability target','NVIDIA’s August 2025 roadmap targeted early 2026 for Quantum-X photonics. This entry records that expectation; it does not establish completed shipments.','forecast','Check subsequent shipment disclosures.'),
  ('nv-optics-2025','2026-12-31','H2 2026','Ethernet photonics rollout window','NVIDIA’s roadmap targeted the second half of 2026 for Spectrum-X photonics Ethernet switches.','forecast','Look for customer deployment and volume evidence, beyond availability.'),
  ('lite-2026','2026-03-02','March 2026','Optics supply partnership announced','Lumentum announced a multiyear NVIDIA optics agreement. The announcement is evidence of a commercial relationship, not a quarterly revenue forecast.','reported_milestone','Track capacity readiness and subsequent revenue commentary.'),
  ('axt-2026','2026-07-29','July 2026','Substrate capacity reservation agreed','AXT announced an indium-phosphide substrate supply and capacity reservation agreement with Lumentum.','reported_milestone','Watch shipments and capacity execution.'),
  ('axt-2026','2028-12-31','During 2028','Second capacity deposit terms to be determined','The agreement specifies a second $43.5 million deposit whose timing and terms are to be determined during 2028. It is not a forecast of 2028 sales.','forecast','Distinguish deposits, shipment credits and recognised revenue.'),
  ('axt-2026','2031-12-31','Through December 2031','Longer-term substrate supply window','AXT describes annual InP commitments under the Lumentum agreement through December 2031.','forecast','Track delivery execution; contract horizon does not guarantee margins.'),
  ('cohr-2026','2026-09-20','September 2026','Optics roadmap showcased at ECOC','Coherent highlighted technologies for AI connectivity, including developments beyond 1.6T. A demonstration does not establish mass adoption.','reported_milestone','Separate showcased products from volume shipments.')],
 'hbm':[
  ('mu-q3-2026','2026-06-24','June 2026','HBM4 volume shipments reported','Micron reported high-volume HBM4 shipments for its lead customer and qualification samples shipped to multiple end-customers.','reported_milestone','Separate one customer’s volume ramp from wider qualification.'),
  ('mu-q3-2026','2027-12-31','Calendar 2027','HBM4E volume production expected','Micron expected volume production of HBM4E, based on its 1-gamma DRAM technology, in calendar 2027.','forecast','Watch customer qualification and later production updates.'),
  ('tf-hbm-2026','2025-12-31','End 2025 comparison','HBM wafer allocation baseline estimate','TrendForce’s June 2026 analysis estimated HBM at about 18% of DRAM wafer input among the three major suppliers at end-2025.','reported_milestone','This is an analyst estimate of wafer allocation, not memory revenue share.'),
  ('tf-hbm-2026','2026-12-31','End 2026','Higher HBM wafer allocation expected','TrendForce projected HBM to represent about 22% of the three leading suppliers’ DRAM wafer input at end-2026.','forecast','Compare later capacity disclosures on the same measurement basis.'),
  ('tf-hbm-2026','2027-12-31','End 2027','Further capacity shift toward HBM','TrendForce projected the HBM share of DRAM wafer input to reach about 30% at end-2027.','forecast','Watch conventional DRAM supply, HBM yield and product mix.'),
  ('tf-memory-2026','2027-12-31','2027','DRAM supply expected to remain constrained','TrendForce’s July outlook expects HBM allocation and server demand to keep DRAM supply tight into 2027.','forecast','New capacity, demand changes and contract prices can alter this outlook.')],
 'advanced-packaging':[
  ('tsm-tech-2026','2026-04-22','April 2026','Larger CoWoS enters production','TSMC stated it was producing 5.5-reticle-size CoWoS at its technology symposium.','reported_milestone','Track usable capacity and customer programmes, not just package dimensions.'),
  ('tsm-tech-2026','2029-12-31','2029','Next stacking milestone on the roadmap','TSMC targeted A14-to-A14 SoIC production availability for 2029.','forecast','Watch qualification and whether later roadmaps revise the date.')],
 'liquid-cooling':[
  ('vrt-dsx-2026','2026-09-21','September 2026','Higher-capacity coolant distribution qualified','Vertiv announced NVIDIA DSX Ready qualification for its 2.3 MW CoolChip coolant distribution unit.','reported_milestone','Qualification is a concrete step; next look for deployment orders and shipment timing.'),
  ('vrt-frontiers','2026-01-08','January 2026','Adaptive liquid cooling becomes a stated design priority','Vertiv’s 2026 outlook identified adaptive liquid cooling among the trends shaping datacenter design and operations.','reported_milestone','Look for named deployments and product orders; this outlook gives no universal adoption percentage.')],
 'ai-power':[
  ('gev-2025','2025-12-09','December 2025','Bridge power demand enters supplier commentary','GE Vernova’s investor update discussed growing demand for smaller gas units and aeroderivatives serving datacenter bridge power.','reported_milestone','Track firm orders and delivery schedules rather than extrapolating all gas demand from AI.')],
 'ai-inference':[
  ('aws-t3','2025-12-02','December 2025','Trainium3 availability announced','AWS announced Trainium3 UltraServers and described production workloads on the platform.','reported_milestone','Compare production adoption and workload-specific economics.'),
  ('aws-t4','2027-12-31','2027','Trainium4 delivery target','Amazon’s Q4 2025 results said Trainium4 was expected to start delivering in 2027.','forecast','Check subsequent availability, memory configuration and customer adoption.')],
}

def enrich(article):
 result=copy.deepcopy(article)
 result['guide']=GUIDES[result['slug']]
 result['reviewed']='2026-09-27'
 extra=EVENTS.get(result['slug'],[])
 ids={e[0] for e in extra}
 if result['slug']=='optical-networking':ids.update(['lite-2026','cohr-2026','axt-2026'])
 for sid in sorted(ids):
  name,day,url,label=SOURCES[sid]
  result['sources'].append({'id':sid,'name':name,'date':day,'url':url,'label':label,'kind':'Industry estimate' if name=='TrendForce' else 'Company disclosure','pages':''})
 result['evidence_through']=max([result.get('evidence_through') or '']+[s.get('date') or '' for s in result['sources']])
 for sid,end,when,title,summary,kind,watch in extra:
  result['timeline'].append({'source':sid,'when':when,'target_end':end,'title':title,'expectation':summary,'kind':kind,'watch':watch,'scope':'Industry estimate' if sid.startswith('tf-') else ('Company outlook' if kind=='forecast' else 'Reported development'),'page':'Public source','report_date':SOURCES[sid][1]})
 if result['slug']=='optical-networking':
  direct=[('LITE','Lumentum','lite-2026','Optical components and lasers; NVIDIA optics agreement.','Capacity readiness, optical product mix and shipment conversion.'),('COHR','Coherent','cohr-2026','Optical components and connectivity for AI datacenters.','Customer qualification and volume adoption of newer optical products.'),('AXTI','AXT','axt-2026','InP substrates upstream of optical devices; Lumentum supply agreement.','Shipment execution, permits, usable capacity and margins.')]
  result['beneficiaries']=[{'ticker':t,'name':n,'source':sid,'short_reason':reason,'why':reason,'timing':'Follow the source-dated milestones below; no inferred quarterly revenue date.','watch':watch,'stage':'Direct supply-chain exposure','page':'Public source'} for t,n,sid,reason,watch in direct]+result['beneficiaries']
 return result

def target_end(value):
 """Parse only explicit year/quarter/half-year windows, never invent a day."""
 text=(value or '').strip()
 years=re.findall(r'\b(20\d{2})\b',text)
 if len(set(years))!=1:return None
 year=int(years[0]);month=12
 quarter=re.search(r'\bQ([1-4])\b',text,re.I)
 if quarter:month=int(quarter[1])*3
 elif re.search(r'\bH1\b|first half|early',text,re.I):month=6
 for i,name in enumerate(calendar.month_name):
  if name and re.search(r'\b'+name+r'\b',text,re.I):month=i
 return date(year,month,calendar.monthrange(year,month)[1]).isoformat()

def organize(article,today=None):
 today=today or date.today();result=copy.deepcopy(article)
 result['outlook']=[];result['history']=[];result['unconfirmed']=[];result['watchlist']=[]
 for event in result['timeline']:
  kind=event.get('kind')
  if not kind:kind='reported_milestone' if event.get('scope') in ('Reported development','Announced availability','Announced milestone','Announced collaboration','Architecture disclosure','Announced design capability') else 'forecast'
  end=event.get('target_end') or target_end(event.get('when'))
  event['target_end']=end
  event['status']='Reported development' if kind=='reported_milestone' else ('Unconfirmed report' if kind=='rumour' else 'Expectation')
  if kind=='reported_milestone':result['history'].append(event)
  elif end and end<today.isoformat():
   event['status']='Past target · confirmation needed';result['unconfirmed'].append(event)
  elif end:result['outlook'].append(event)
  else:result['watchlist'].append(event)
 result['outlook'].sort(key=lambda e:e['target_end'])
 result['history'].sort(key=lambda e:e.get('report_date') or e.get('target_end') or '',reverse=True)
 return result
