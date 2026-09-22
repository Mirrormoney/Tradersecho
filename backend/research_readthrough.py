"""Conservative business-exposure links, separate from direct broker coverage."""
import re
EXPOSURES={'dram':{'MU':'DRAM manufacturer'},'hbm':{'MU':'HBM manufacturer'},'nand':{'MU':'NAND manufacturer','SNDK':'NAND flash business'},'memory':{'MU':'Memory manufacturer','SNDK':'Flash-memory business'}}
PATTERNS={'dram':r'\bDRAM\b','hbm':r'\bHBM\b|high.bandwidth memory','nand':r'\bNAND\b','memory':r'\bmemory\b'}

def attach_readthroughs(result,catalog):
 direct={f['ticker'] for f in result['findings']};added=set()
 for sector in result.get('sector_findings',[]):
  # Require explicit sector evidence, not just a filename or model-selected topic.
  if not re.search(PATTERNS[sector['topic']],sector['evidence'],re.I):continue
  for ticker,exposure in EXPOSURES[sector['topic']].items():
   if ticker not in catalog or ticker in direct or ticker in added:continue
   result['findings'].append({'ticker':ticker,'summary':sector['summary'],'stance':'unclear','evidence':sector['evidence'],'page':sector['page'],'catalysts':[],'risks':[],'attribution':'readthrough','event':None,'link_type':'sector_readthrough','topic':sector['topic'],'link_reason':exposure+'; linked by Traders Echo, not a company-specific broker view.'})
   added.add(ticker)
 return result
