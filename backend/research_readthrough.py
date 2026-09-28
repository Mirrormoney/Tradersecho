"""Conservative business-exposure links, separate from direct broker coverage."""
import re
EXPOSURES={'dram':{'MU':'DRAM manufacturer'},'hbm':{'MU':'HBM manufacturer'},'nand':{'MU':'NAND manufacturer','SNDK':'NAND flash business'},'memory':{'MU':'Memory manufacturer','SNDK':'Flash-memory business'}}
PATTERNS={'dram':r'\bDRAM\b','hbm':r'\bHBM\b|high.bandwidth memory','nand':r'\bNAND\b','memory':r'\bmemory\b'}

# Established business exposures; linkage is context, never a broker stock call.
EXPOSURES.update({
 'optical-networking':{'LITE':'Optical components and lasers','COHR':'Optical components and connectivity'},
 'liquid-cooling':{'VRT':'Datacenter thermal-management equipment'},
 'advanced-packaging':{'TSM':'Advanced semiconductor packaging'},
 'semicap':{'AMAT':'Semiconductor manufacturing equipment','LRCX':'Wafer-fabrication equipment','KLAC':'Semiconductor process control'},
})
PATTERNS.update({
 'optical-networking':r'optical|photonics|co.packaged optics|\bCPO\b|800G|1\.6T',
 'liquid-cooling':r'liquid.cool|cold.plate|cooling distribution|direct.to.chip cooling',
 'advanced-packaging':r'CoWoS|SoIC|advanced packaging|chiplet',
 'semicap':r'\bWFE\b|wafer.fab(?:rication)? equipment|semiconductor equipment',
})

def attach_readthroughs(result,catalog):
 direct={f['ticker'] for f in result['findings']};added=set()
 for sector in result.get('sector_findings',[]):
  # Require explicit sector evidence, not just a filename or model-selected topic.
  if sector['topic'] not in PATTERNS or not re.search(PATTERNS[sector['topic']],sector['evidence'],re.I):continue
  for ticker,exposure in EXPOSURES[sector['topic']].items():
   if ticker not in catalog or ticker in direct or ticker in added or len(result['findings'])>=20:continue
   result['findings'].append({'ticker':ticker,'summary':sector['summary'],'stance':'unclear','evidence':sector['evidence'],'page':sector['page'],'catalysts':[],'risks':[],'attribution':'readthrough','event':None,'link_type':'sector_readthrough','topic':sector['topic'],'link_reason':exposure+'; linked by Traders Echo, not a company-specific broker view. Exposure does not establish an order, earnings impact or stock direction.'})
   added.add(ticker)
 return result
