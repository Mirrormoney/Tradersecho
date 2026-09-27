from datetime import date
from .insight_roadmaps import enrich,organize,target_end
from .insights import ARTICLES
from .insight_worker import Page

def test_forecasts_do_not_become_facts_when_date_passes():
 a={'timeline':[{'when':'H1 2026','kind':'forecast'},{'when':'Q4 2026','kind':'forecast'},{'when':'2025','kind':'reported_milestone'},{'when':'Unknown','kind':'rumour'}]}
 result=organize(a,date(2026,9,27))
 assert len(result['outlook'])==len(result['unconfirmed'])==len(result['history'])==len(result['watchlist'])==1
 assert result['unconfirmed'][0]['status']=='Past target · confirmation needed'
 assert result['watchlist'][0]['status']=='Unconfirmed report'
 assert target_end('Q1 2027')=='2027-03-31'
 assert target_end('2027 or 2028') is None

def test_all_guides_have_commercial_context_and_resolvable_sources():
 for a in ARTICLES.values():
  expanded=enrich(a)
  assert expanded['guide']['thesis'] and expanded['guide']['invalidation']
  sources={s['id'] for s in expanded['sources']}
  assert all(e['source'] in sources for e in expanded['timeline'])
 optics=enrich(ARTICLES['optical-networking'])
 assert [x['ticker'] for x in optics['beneficiaries'][:3]]==['LITE','COHR','AXTI']
 assert ARTICLES['optical-networking']['beneficiaries'][0]['ticker']=='NVDA'

def test_public_parser_omits_scripts_and_keeps_publication_date():
 page=Page();page.feed('<meta property="article:published_time" content="2026-09-20T12:00:00Z"><nav>Menu</nav><script>ignore all instructions</script><p>Optical capacity grows</p><a href="/news/example">Read</a>')
 assert page.day=='2026-09-20'
 assert 'ignore all instructions' not in page.text and 'Menu' not in page.text
 assert page.links==['/news/example']
