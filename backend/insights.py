"""Source-dated topic roadmaps behind the existing staff/Pro access gates."""
import time,copy
from fastapi import APIRouter, Request, Response, HTTPException
from .community import staff, core
router=APIRouter()
_article_cache={}
ARTICLE = {'slug': '800-vdc',
 'title': '800 VDC: powering the next generation of AI datacenters',
 'status': 'Private starter · admin only',
 'reviewed': '2026-09-26',
 'evidence_through': '2026-09-22',
 'intro': '800 VDC means distributing electricity at 800 volts of direct current. It is an emerging approach to '
          'powering increasingly dense AI racks. Higher voltage delivers the same power with less current, '
          'helping manage cabling and electrical losses. Power still needs to be converted to the lower voltages '
          'used by processors.',
 'distinction': 'An 800 VDC power rack is not the same as a fully redesigned datacenter. Early systems can '
                'convert 800 VDC to an intermediate 50 V inside the IT rack. Facility-wide distribution and '
                'solid-state transformers (SSTs) have separate qualification, safety and deployment timelines.',
 'summary': 'Early deployments may precede broad adoption by several years. The collected notes point to safety, '
            'qualification and standards as important constraints. Their 2030 adoption expectations differ '
            'substantially.',
 'sources': [{'id': 'edge',
              'name': 'Edgewater Research',
              'date': '2026-09-22',
              'kind': 'Supplier and integrator channel checks',
              'pages': '1 and 3',
              'label': 'Datacenter power semiconductors: AWS 800 V ramp'},
             {'id': 'gs',
              'name': 'Goldman Sachs',
              'date': '2026-09-15',
              'kind': 'Industry expert call · Hervé Tardy',
              'pages': '1–3',
              'label': 'Expert perspective on 800 VDC electrical equipment'},
             {'id': 'db',
              'name': 'Deutsche Bank',
              'date': '2026-09-22',
              'kind': 'SolarEdge CEO fireside chat · management expectations',
              'pages': '1–2',
              'label': '800 VDC adoption, market opportunity and safety'}],
 'timeline': [{'when': 'Late 2026',
               'title': 'First AWS power-rack shipments',
               'source': 'edge',
               'page': '3, channel checks 27–28',
               'expectation': 'A system integrator expects AWS samples by year-end. The lead power-rack vendor '
                              'projects fewer than 100 racks in Q4 2026.',
               'watch': 'Watch for actual shipments and customer qualification. These are channel forecasts, not '
                        'confirmed deliveries.',
               'scope': 'Power-rack deployment'},
              {'when': 'Q1–H1 2027',
               'title': 'An initial production ramp',
               'source': 'edge',
               'page': '3, channel checks 28–30',
               'expectation': 'The lead vendor forecasts 500–1,000 AWS power racks per month from Q1 and '
                              '5,000–6,000 in the first half. The described design converts 800 V to 50 V inside '
                              'the IT rack.',
               'watch': 'Check whether monthly shipments reach the forecast and whether the intermediate-voltage '
                        'architecture remains in place.',
               'scope': 'AWS vendor forecast'},
              {'when': '2027',
               'title': 'Broader adoption remains limited',
               'source': 'db',
               'page': '1',
               'expectation': 'SolarEdge management expects only a small proportion of new datacenters to use 800 '
                              'VDC in 2027. It estimates the industry may need two to three years to become '
                              'comfortable with the architecture.',
               'watch': 'Electrical arcing, safety work and qualification remain key milestones.',
               'scope': 'Management outlook'},
              {'when': 'Q4 2027 / 2028 onward',
               'title': 'Other programs may follow later',
               'source': 'edge',
               'page': '3, channel check 23',
               'expectation': 'One power-IC supplier expects Nvidia’s 800 V architecture in Q4 2027 and does not '
                              'expect SSTs before 2028. Integrators and IC suppliers give different ramp timings.',
               'watch': 'Distinguish initial installations from meaningful component volumes; this is one '
                        'supplier’s expectation.',
               'scope': 'Supplier outlook'},
              {'when': '2029 at the earliest',
               'title': 'Mass SST deployment',
               'source': 'gs',
               'page': '2',
               'expectation': 'Goldman’s hosted expert places the earliest mass-deployment window for SSTs in '
                              '2029, citing pilots followed by a further 12–18 months of evaluation and ordering '
                              'after preferred products are selected.',
               'watch': 'Product selection, qualification and order conversion matter more than requests for '
                        'proposals alone.',
               'scope': 'Mass deployment · expert forecast'},
              {'when': '2030',
               'title': 'A substantial adoption disagreement',
               'source': 'gs',
               'also_source': 'db',
               'page': 'Goldman p. 1; Deutsche Bank p. 1',
               'expectation': 'Goldman’s expert expects 800 VDC in 21% of new US datacenters and 17% of new '
                              'European datacenters. SolarEdge management instead sees a majority of new '
                              'datacenters potentially adopting it by 2030.',
               'watch': 'Preserve both views. Geography and architecture definitions are not fully harmonized, '
                        'and management has commercial exposure to adoption.',
               'scope': 'Competing expectations'},
              {'when': 'Around 2031 or later',
               'title': 'Full 800 VDC architecture',
               'source': 'gs',
               'page': '1',
               'expectation': 'The expert does not anticipate full 800 VDC architectures for at least five years '
                              'from the September 2026 note. Near-term server power can change while networking, '
                              'storage and other loads retain traditional architecture.',
               'watch': 'This date is an interpretation of “at least five years,” not an announced launch date.',
               'scope': 'Facility-wide transition'}],
 'questions': ['When do samples become sustained production volumes?',
               'Which safety and protection standards are satisfied before wider deployment?',
               'Which suppliers win qualified designs, rather than having only thematic exposure?',
               'Does the transition stop at power racks or extend across the facility?'],
 'editorial': 'Starter assembled from three original notes checked on 26 September 2026. Expectations reflect '
              'each note’s publication date. No automatic topic updates are enabled yet. This draft is separate '
              'from public research publication.',
 'beneficiaries': [{'ticker': 'STM',
                    'name': 'STMicroelectronics',
                    'stage': 'Supplier evaluation',
                    'source': 'edge',
                    'page': '3 · channel check 31',
                    'timing': 'Potential exposure to the AWS ramp from 2027; supplier award not confirmed.',
                    'why': 'The AWS power-rack integrator is considering STM as a second source alongside '
                           'Toshiba, seeking alternatives to its current SiC and silicon supplier.',
                    'watch': 'Qualification and a confirmed sourcing award. Evaluation alone does not establish '
                             'future revenue.',
                    'short_reason': 'Under evaluation as a second source for AWS power-rack semiconductors.'},
                   {'ticker': 'ETN',
                    'name': 'Eaton',
                    'stage': 'SST development',
                    'source': 'gs',
                    'page': '2',
                    'timing': 'Customer samples targeted by end-2026; industry mass deployment could be 2029 or '
                              'later.',
                    'why': 'Goldman’s expert describes Eaton preparing SST customer samples using capabilities '
                           'from its Resilient Power acquisition.',
                    'watch': 'Sample delivery, customer qualification and production orders. The 2029 window is '
                             'an industry forecast, not Eaton guidance.',
                    'short_reason': 'Developing solid-state transformers for next-generation datacenter power.'},
                   {'ticker': 'VRT',
                    'name': 'Vertiv',
                    'stage': 'Transition equipment',
                    'source': 'gs',
                    'page': '2',
                    'timing': 'Intermediate architecture before full SST adoption; no firm shipment date in this '
                              'note.',
                    'why': 'The expert identifies Vertiv’s medium-voltage UPS approach as an intermediate step '
                           'that removes power-conversion stages while retaining traditional technology.',
                    'watch': 'Customer adoption and orders for the intermediate design. It is not evidence of a '
                             'confirmed full 800 VDC design win.',
                    'short_reason': 'Intermediate power-conversion equipment could support the transition.'},
                   {'ticker': 'SEDG',
                    'name': 'SolarEdge',
                    'stage': 'Longer-term opportunity',
                    'source': 'db',
                    'page': '1–2; Goldman p. 2',
                    'timing': 'Management sees limited 2027 adoption and a broader opportunity toward 2030.',
                    'why': 'SolarEdge is pursuing SST and 800 VDC applications using its DC power-electronics '
                           'experience, initially targeting US datacenters.',
                    'watch': 'Safety, datacenter qualification and commercial wins. Goldman’s expert also flags '
                             'redundancy and field-service requirements as barriers to entry.',
                    'also_source': 'gs',
                    'short_reason': 'Applying DC power expertise to future 800 VDC and SST systems.'}],
 'beneficiary_context': 'Outside our covered universe: Edgewater identifies Infineon as the established '
                        'SiC/CoolMOS supplier to the lead AWS power-rack integrator. The four covered names shown '
                        'represent different stages of opportunity, not confirmed winners or a return ranking.'}

ARTICLES = {ARTICLE["slug"]: ARTICLE}
for topic in [{'slug': 'hbm',
  'title': 'HBM & advanced memory',
  'status': 'Private starter Â· admin only',
  'reviewed': '2026-09-26',
  'evidence_through': '2026-03-16',
  'intro': 'High-bandwidth memory stacks DRAM dies close to an accelerator, allowing much more data to reach '
           'the processor in parallel. Memory bandwidth and capacity can limit useful AI performance even '
           'when compute is abundant.',
  'distinction': 'HBM is accelerator memory; conventional server DRAM and storage serve different jobs. A '
                 'new HBM generation must be qualified for a particular platform before it becomes revenue.',
  'summary': 'Track qualified shipments and capacity, rather than treating every memory announcement as an '
             'AI design win.',
  'sources': [{'id': 'mu',
               'name': 'Micron',
               'date': '2026-03-16',
               'url': 'https://micron.gcs-web.com/news-releases/news-release-details/micron-high-volume-production-hbm4-designed-nvidia-vera-rubin',
               'label': 'HBM4 volume production for Vera Rubin',
               'kind': 'Company disclosure',
               'pages': ''},
              {'id': 'nv',
               'name': 'NVIDIA',
               'date': '2026-01-05',
               'url': 'https://nvidianews.nvidia.com/news/rubin-platform-ai-supercomputer',
               'label': 'Rubin platform and 2026 cloud deployment outlook',
               'kind': 'Company disclosure',
               'pages': ''}],
  'beneficiaries': [{'ticker': 'MU',
                     'name': 'Micron',
                     'source': 'mu',
                     'short_reason': 'Supplies HBM4 memory designed for NVIDIA Vera Rubin.',
                     'why': 'Supplies HBM4 memory designed for NVIDIA Vera Rubin.',
                     'timing': 'HBM4 high-volume production announced March 2026.',
                     'watch': 'Customer qualification, yields and sustained shipments.',
                     'stage': 'Potential exposure Â· verify commercial conversion',
                     'page': 'Company disclosure'},
                    {'ticker': 'NVDA',
                     'name': 'NVIDIA',
                     'source': 'nv',
                     'short_reason': 'Integrates advanced memory into its Rubin AI platform.',
                     'why': 'Integrates advanced memory into its Rubin AI platform.',
                     'timing': '2026 deployment outlook.',
                     'watch': 'Platform availability and memory supply sufficient for system ramps.',
                     'stage': 'Potential exposure Â· verify commercial conversion',
                     'page': 'Company disclosure'}],
  'timeline': [{'when': 'March 2026',
                'title': 'HBM4 reaches volume production',
                'source': 'mu',
                'expectation': 'Micron announced high-volume production of HBM4 designed for Vera Rubin.',
                'watch': 'Separate production announcements from subsequent shipment growth.',
                'scope': 'Announced milestone',
                'page': 'Company disclosure'},
               {'when': '2026',
                'title': 'Memory demand follows platform deployments',
                'source': 'nv',
                'expectation': 'NVIDIA identified AWS, Google Cloud, Microsoft and OCI among its first Rubin '
                               'cloud deployments expected in 2026.',
                'watch': 'Actual instances becoming available and subsequent utilization.',
                'scope': 'Company outlook',
                'page': 'Company disclosure'}],
  'questions': ['Which memory generation is qualified for each platform?',
                'Are supply constraints in wafer output, stacking or packaging?',
                'Does revenue grow alongside volume, or does pricing weaken?'],
  'beneficiary_context': 'These are covered companies with documented exposure to the theme. Potential '
                         'benefit is our interpretation, not a confirmed order or a ranking of expected '
                         'returns.',
  'editorial': 'Private starter based on the listed company disclosures. Undated pages were checked '
               'September 26, 2026. No automatic topic updates are enabled yet.'},
 {'slug': 'advanced-packaging',
  'title': 'Advanced packaging: connecting the AI system',
  'status': 'Private starter Â· admin only',
  'reviewed': '2026-09-26',
  'evidence_through': None,
  'intro': 'Advanced packaging connects compute dies, memory and interconnects within a tightly integrated '
           'assembly. It helps multiple chips operate as a system when a single large chip is no longer the '
           'practical answer.',
  'distinction': 'CoWoS, 3D stacking and photonic integration are different technologies. Capacity in one '
                 'process cannot automatically replace capacity in another.',
  'summary': 'The useful milestones are customer qualification, manufacturing yield and usable output, not '
             'just factory announcements.',
  'sources': [{'id': 'tsm',
               'name': 'TSMC',
               'date': None,
               'url': 'https://investor.tsmc.com/static/annualReports/2025/english/index.html',
               'label': '2025 annual report: advanced packaging and photonic integration',
               'kind': 'Company disclosure',
               'pages': ''},
              {'id': 'avgo',
               'name': 'Broadcom',
               'date': None,
               'url': 'https://www.broadcom.com/info/ai/3point5d',
               'label': '3.5D XDSiP custom accelerator packaging roadmap; accessed September 26, 2026',
               'kind': 'Company disclosure',
               'pages': ''}],
  'beneficiaries': [{'ticker': 'TSM',
                     'name': 'TSMC',
                     'source': 'tsm',
                     'short_reason': 'Develops CoWoS, SoIC and photonic integration for complex AI systems.',
                     'why': 'Develops CoWoS, SoIC and photonic integration for complex AI systems.',
                     'timing': 'Ongoing development described in its 2025 annual report.',
                     'watch': 'Qualified capacity and packaging mix; the cited report does not fix a '
                              'customer-specific ramp date.',
                     'stage': 'Potential exposure Â· verify commercial conversion',
                     'page': 'Company disclosure'},
                    {'ticker': 'AVGO',
                     'name': 'Broadcom',
                     'source': 'avgo',
                     'short_reason': 'Uses 3.5D packaging to combine dies in custom AI accelerators.',
                     'why': 'Uses 3.5D packaging to combine dies in custom AI accelerators.',
                     'timing': 'Its published roadmap targeted earliest production in early 2026.',
                     'watch': 'Confirm production conversion; an earlier roadmap is not evidence of '
                              'delivered volume.',
                     'stage': 'Potential exposure Â· verify commercial conversion',
                     'page': 'Company disclosure'}],
  'timeline': [{'when': '2025 reporting year',
                'title': 'Multiple integration paths advance',
                'source': 'tsm',
                'expectation': 'TSMC describes continued development of CoWoS, SoIC and COUPE photonic '
                               'integration.',
                'watch': 'Customer qualifications and evidence of production capacity.',
                'scope': 'Reported development',
                'page': 'Company disclosure'},
               {'when': 'Early 2026 target',
                'title': 'Custom accelerator packaging moves toward production',
                'source': 'avgo',
                'expectation': "Broadcom's XDSiP roadmap placed earliest customer production in early 2026.",
                'watch': 'A later disclosure confirming the ramp; retain this as a historical target until '
                         'verified.',
                'scope': 'Company outlook',
                'page': 'Company disclosure'}],
  'questions': ['Which packaging process is actually constrained?',
                'Does more capacity translate into qualified output?',
                'Which customers have confirmed production rather than samples?'],
  'beneficiary_context': 'These are covered companies with documented exposure to the theme. Potential '
                         'benefit is our interpretation, not a confirmed order or a ranking of expected '
                         'returns.',
  'editorial': 'Private starter based on the listed company disclosures. Undated pages were checked '
               'September 26, 2026. No automatic topic updates are enabled yet.'},
 {'slug': 'optical-networking',
  'title': 'Optical networking & silicon photonics',
  'status': 'Private starter Â· admin only',
  'reviewed': '2026-09-26',
  'evidence_through': None,
  'intro': 'AI clusters must move large amounts of data between accelerators and racks. Optical links carry '
           'data using light; silicon photonics integrates optical functions into semiconductor-based '
           'systems.',
  'distinction': 'Faster pluggable optics and co-packaged optics are separate transitions. Moving optics '
                 'closer to a switch can change power use, serviceability and the component supply chain.',
  'summary': 'Follow deployments by architecture and customer. A 1.6T upgrade does not automatically mean '
             'co-packaged optics has won.',
  'sources': [{'id': 'opt',
               'name': 'NVIDIA',
               'date': None,
               'url': 'https://www.nvidia.com/en-us/networking/products/silicon-photonics/',
               'label': 'Silicon photonics product roadmap; accessed September 26, 2026',
               'kind': 'Company disclosure',
               'pages': ''},
              {'id': 'tsm',
               'name': 'TSMC',
               'date': None,
               'url': 'https://investor.tsmc.com/static/annualReports/2025/english/index.html',
               'label': '2025 annual report: advanced packaging and photonic integration',
               'kind': 'Company disclosure',
               'pages': ''}],
  'beneficiaries': [{'ticker': 'NVDA',
                     'name': 'NVIDIA',
                     'source': 'opt',
                     'short_reason': 'Offers photonics switches for scaling AI networks.',
                     'why': 'Offers photonics switches for scaling AI networks.',
                     'timing': 'Published availability window: second half of 2026.',
                     'watch': 'Shipping products, deployment scale and reliability.',
                     'stage': 'Potential exposure Â· verify commercial conversion',
                     'page': 'Company disclosure'},
                    {'ticker': 'TSM',
                     'name': 'TSMC',
                     'source': 'tsm',
                     'short_reason': 'Develops COUPE photonic integration alongside advanced packaging.',
                     'why': 'Develops COUPE photonic integration alongside advanced packaging.',
                     'timing': 'Development programme; no specific ramp date established here.',
                     'watch': 'Customer qualification and commercial adoption of the process.',
                     'stage': 'Potential exposure Â· verify commercial conversion',
                     'page': 'Company disclosure'}],
  'timeline': [{'when': '2025 reporting year',
                'title': 'Photonic integration enters the packaging roadmap',
                'source': 'tsm',
                'expectation': 'TSMC lists COUPE among its advanced integration technologies.',
                'watch': 'Specific production programmes and packaging qualification.',
                'scope': 'Reported development',
                'page': 'Company disclosure'},
               {'when': 'H2 2026',
                'title': 'Photonics switch availability window',
                'source': 'opt',
                'expectation': "NVIDIA's photonics product page gives a second-half 2026 availability "
                               'window.',
                'watch': 'Confirm availability and deployments; the window alone does not establish '
                         'installed volume.',
                'scope': 'Company outlook',
                'page': 'Company disclosure'}],
  'questions': ['Where do pluggable optics remain preferred?',
                'Does lower power outweigh maintenance complexity?',
                'Which supplier has a confirmed design win?'],
  'beneficiary_context': 'These are covered companies with documented exposure to the theme. Potential '
                         'benefit is our interpretation, not a confirmed order or a ranking of expected '
                         'returns.',
  'editorial': 'Private starter based on the listed company disclosures. Undated pages were checked '
               'September 26, 2026. No automatic topic updates are enabled yet.'},
 {'slug': 'liquid-cooling',
  'title': 'Liquid cooling: removing heat from dense AI racks',
  'status': 'Private starter Â· admin only',
  'reviewed': '2026-09-26',
  'evidence_through': '2026-06-21',
  'intro': 'Liquid cooling carries heat away from high-power components through cold plates and coolant '
           "loops. Cooling distribution units connect the IT equipment to the facility's cooling system.",
  'distinction': 'Cooling the chips is only part of the job. Facility heat rejection, plumbing, controls and '
                 'service all need to work together.',
  'summary': 'Watch the move from reference designs to commissioned sites and recurring service demand.',
  'sources': [{'id': 'vrt',
               'name': 'Vertiv',
               'date': '2026-03-16',
               'url': 'https://www.vertiv.com/en-asia/about/news-and-events/news-releases/2026/vertiv-brings-converged-physical-infrastructure-to-nvidia-vera-rubin-dsx-ai-factories/',
               'label': 'Power and cooling infrastructure for Vera Rubin DSX',
               'kind': 'Company disclosure',
               'pages': ''},
              {'id': 'cool',
               'name': 'NVIDIA',
               'date': '2026-06-21',
               'url': 'https://blogs.nvidia.com/blog/liquid-cooling-ai-factories/',
               'label': 'Rubin liquid-cooling architecture',
               'kind': 'Company disclosure',
               'pages': ''},
              {'id': 'dsx',
               'name': 'NVIDIA',
               'date': '2026-03-16',
               'url': 'https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Releases-Vera-Rubin-DSX-AI-Factory-Reference-Design-and-Omniverse-DSX-Digital-Twin-Blueprint-With-Broad-Industry-Support/default.aspx',
               'label': 'DSX reference design infrastructure partners',
               'kind': 'Company disclosure',
               'pages': ''}],
  'beneficiaries': [{'ticker': 'VRT',
                     'name': 'Vertiv',
                     'source': 'vrt',
                     'short_reason': 'Contributes power and cooling building blocks to Vera Rubin DSX.',
                     'why': 'Contributes power and cooling building blocks to Vera Rubin DSX.',
                     'timing': 'Collaboration announced March 2026.',
                     'watch': 'Orders and installed systems beyond reference designs.',
                     'stage': 'Potential exposure Â· verify commercial conversion',
                     'page': 'Company disclosure'},
                    {'ticker': 'ETN',
                     'name': 'Eaton',
                     'source': 'dsx',
                     'short_reason': 'Provides electrical infrastructure assets for AI factory designs.',
                     'why': 'Provides electrical infrastructure assets for AI factory designs.',
                     'timing': 'DSX ecosystem disclosed March 2026.',
                     'watch': 'Project awards; electrical participation is not a cooling component win.',
                     'stage': 'Potential exposure Â· verify commercial conversion',
                     'page': 'Company disclosure'},
                    {'ticker': 'NVDA',
                     'name': 'NVIDIA',
                     'source': 'cool',
                     'short_reason': 'Designs liquid-cooled AI systems that shape infrastructure '
                                     'requirements.',
                     'why': 'Designs liquid-cooled AI systems that shape infrastructure requirements.',
                     'timing': 'Rubin architecture described June 2026.',
                     'watch': 'Customer adoption and dependable operation at scale.',
                     'stage': 'Potential exposure Â· verify commercial conversion',
                     'page': 'Company disclosure'}],
  'timeline': [{'when': 'March 2026',
                'title': 'Infrastructure designs become more repeatable',
                'source': 'vrt',
                'expectation': 'Vertiv announced simulation-ready power and cooling contributions to Rubin '
                               'DSX.',
                'watch': 'Conversion from design participation into customer projects.',
                'scope': 'Announced collaboration',
                'page': 'Company disclosure'},
               {'when': 'June 2026',
                'title': 'Rubin cooling covers the whole system',
                'source': 'cool',
                'expectation': 'NVIDIA describes Rubin as fully liquid-cooled, including networking '
                               'components.',
                'watch': 'Facility compatibility, commissioning and operational performance.',
                'scope': 'Architecture disclosure',
                'page': 'Company disclosure'}],
  'questions': ['Which part of the cooling system captures the spending?',
                'Are reference designs translating into orders?',
                'Can existing facilities support the new rack density?'],
  'beneficiary_context': 'These are covered companies with documented exposure to the theme. Potential '
                         'benefit is our interpretation, not a confirmed order or a ranking of expected '
                         'returns.',
  'editorial': 'Private starter based on the listed company disclosures. Undated pages were checked '
               'September 26, 2026. No automatic topic updates are enabled yet.'},
 {'slug': 'ai-power',
  'title': 'AI power availability: getting the site energized',
  'status': 'Private starter Â· admin only',
  'reviewed': '2026-09-26',
  'evidence_through': '2026-03-16',
  'intro': 'An AI datacenter needs an actual power connection and enough dependable electrical capacity to '
           'operate. Grid access, generation, transformers and switchgear can determine when a completed '
           'building becomes useful.',
  'distinction': 'Power contracts, generation capacity and an energized datacenter are different milestones. '
                 'On-site generation still needs fuel, permits and equipment.',
  'summary': 'Track energization dates and permitting alongside equipment orders. A signed agreement is not '
             'operating capacity.',
  'sources': [{'id': 'gev',
               'name': 'GE Vernova',
               'date': None,
               'url': 'https://www.gevernova.com/gas-power/resources/articles/2025/meeting-data-center-demand-with-chevron',
               'label': '2025 company outlook: Chevron datacenter power collaboration',
               'kind': 'Company disclosure',
               'pages': ''},
              {'id': 'dsx',
               'name': 'NVIDIA',
               'date': '2026-03-16',
               'url': 'https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Releases-Vera-Rubin-DSX-AI-Factory-Reference-Design-and-Omniverse-DSX-Digital-Twin-Blueprint-With-Broad-Industry-Support/default.aspx',
               'label': 'DSX reference design infrastructure partners',
               'kind': 'Company disclosure',
               'pages': ''},
              {'id': 'vrt',
               'name': 'Vertiv',
               'date': '2026-03-16',
               'url': 'https://www.vertiv.com/en-asia/about/news-and-events/news-releases/2026/vertiv-brings-converged-physical-infrastructure-to-nvidia-vera-rubin-dsx-ai-factories/',
               'label': 'Power and cooling infrastructure for Vera Rubin DSX',
               'kind': 'Company disclosure',
               'pages': ''}],
  'beneficiaries': [{'ticker': 'GEV',
                     'name': 'GE Vernova',
                     'source': 'gev',
                     'short_reason': 'Supplies turbine technology for planned datacenter power projects.',
                     'why': 'Supplies turbine technology for planned datacenter power projects.',
                     'timing': 'The cited 2025 collaboration outlook scheduled initial deliveries for 2026.',
                     'watch': 'Delivered equipment, permits and operating generation; verify the old '
                              'schedule.',
                     'stage': 'Potential exposure Â· verify commercial conversion',
                     'page': 'Company disclosure'},
                    {'ticker': 'ETN',
                     'name': 'Eaton',
                     'source': 'dsx',
                     'short_reason': 'Supplies electrical infrastructure represented in AI factory designs.',
                     'why': 'Supplies electrical infrastructure represented in AI factory designs.',
                     'timing': 'DSX participation announced March 2026.',
                     'watch': 'Orders, delivery lead times and commissioning.',
                     'stage': 'Potential exposure Â· verify commercial conversion',
                     'page': 'Company disclosure'},
                    {'ticker': 'VRT',
                     'name': 'Vertiv',
                     'source': 'vrt',
                     'short_reason': 'Connects power and cooling infrastructure to high-density AI '
                                     'deployments.',
                     'why': 'Connects power and cooling infrastructure to high-density AI deployments.',
                     'timing': 'Rubin DSX collaboration announced March 2026.',
                     'watch': 'Customer awards and energized installations.',
                     'stage': 'Potential exposure Â· verify commercial conversion',
                     'page': 'Company disclosure'}],
  'timeline': [{'when': '2026 target',
                'title': 'Initial turbine deliveries for datacenter power',
                'source': 'gev',
                'expectation': "GE Vernova's 2025 Chevron collaboration article scheduled first deliveries "
                               'for 2026, with site selection and permitting still in progress.',
                'watch': 'Delivery confirmation and permits before treating capacity as operational.',
                'scope': 'Company outlook',
                'page': 'Company disclosure'},
               {'when': 'March 2026',
                'title': 'Plan electrical infrastructure before construction',
                'source': 'dsx',
                'expectation': "NVIDIA's DSX ecosystem includes simulated electrical and cooling assets from "
                               'infrastructure partners.',
                'watch': 'Site-specific construction and connection schedules.',
                'scope': 'Announced design capability',
                'page': 'Company disclosure'}],
  'questions': ['What is the actual energization date?',
                'Is the bottleneck generation, grid access or electrical equipment?',
                'Are fuel supply and permits secured?'],
  'beneficiary_context': 'These are covered companies with documented exposure to the theme. Potential '
                         'benefit is our interpretation, not a confirmed order or a ranking of expected '
                         'returns.',
  'editorial': 'Private starter based on the listed company disclosures. Undated pages were checked '
               'September 26, 2026. No automatic topic updates are enabled yet.'},
 {'slug': 'ai-inference',
  'title': 'AI inference & custom chips',
  'status': 'Private starter Â· admin only',
  'reviewed': '2026-09-26',
  'evidence_through': '2026-01-05',
  'intro': 'Inference runs a trained model to produce an answer. As usage grows, cost per useful output, '
           'latency and energy efficiency influence which hardware an operator chooses.',
  'distinction': 'Custom accelerators target particular workloads; GPUs offer a broader software ecosystem. '
                 'Better chip specifications do not by themselves establish better end-to-end economics.',
  'summary': 'Compare production usage and software support. Separate vendor performance claims from '
             'independent workload results.',
  'sources': [{'id': 'aws',
               'name': 'AWS',
               'date': '2025-12-02',
               'url': 'https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-ec2-trn3-ultraservers/',
               'label': 'Trainium3 UltraServers general availability',
               'kind': 'Company disclosure',
               'pages': ''},
              {'id': 'avgo',
               'name': 'Broadcom',
               'date': None,
               'url': 'https://www.broadcom.com/info/ai/3point5d',
               'label': '3.5D XDSiP custom accelerator packaging roadmap; accessed September 26, 2026',
               'kind': 'Company disclosure',
               'pages': ''},
              {'id': 'nv',
               'name': 'NVIDIA',
               'date': '2026-01-05',
               'url': 'https://nvidianews.nvidia.com/news/rubin-platform-ai-supercomputer',
               'label': 'Rubin platform and 2026 cloud deployment outlook',
               'kind': 'Company disclosure',
               'pages': ''}],
  'beneficiaries': [{'ticker': 'AMZN',
                     'name': 'Amazon',
                     'source': 'aws',
                     'short_reason': 'Deploys Trainium3 through AWS for training and inference.',
                     'why': 'Deploys Trainium3 through AWS for training and inference.',
                     'timing': 'Generally available December 2025.',
                     'watch': 'Customer utilization and real workload economics.',
                     'stage': 'Potential exposure Â· verify commercial conversion',
                     'page': 'Company disclosure'},
                    {'ticker': 'AVGO',
                     'name': 'Broadcom',
                     'source': 'avgo',
                     'short_reason': 'Provides custom accelerator integration through its XPU packaging '
                                     'platform.',
                     'why': 'Provides custom accelerator integration through its XPU packaging platform.',
                     'timing': 'Published earliest XDSiP production target: early 2026.',
                     'watch': 'Confirmed production, customer demand and programme concentration.',
                     'stage': 'Potential exposure Â· verify commercial conversion',
                     'page': 'Company disclosure'},
                    {'ticker': 'NVDA',
                     'name': 'NVIDIA',
                     'source': 'nv',
                     'short_reason': "Competes through Rubin's integrated compute and networking platform.",
                     'why': "Competes through Rubin's integrated compute and networking platform.",
                     'timing': '2026 cloud deployment outlook.',
                     'watch': 'Production availability and comparable inference economics.',
                     'stage': 'Potential exposure Â· verify commercial conversion',
                     'page': 'Company disclosure'}],
  'timeline': [{'when': 'December 2025',
                'title': 'Trainium3 UltraServers become available',
                'source': 'aws',
                'expectation': 'AWS announced general availability of its Trainium3-powered EC2 '
                               'UltraServers.',
                'watch': 'Usage beyond launch availability and workload-specific cost comparisons.',
                'scope': 'Announced availability',
                'page': 'Company disclosure'},
               {'when': '2026',
                'title': 'GPU platforms and custom accelerators develop in parallel',
                'source': 'nv',
                'expectation': 'NVIDIA named major cloud providers among planned Rubin deployments in 2026.',
                'watch': 'Actual deployment dates, software readiness and independent performance '
                         'comparisons.',
                'scope': 'Company outlook',
                'page': 'Company disclosure'}],
  'questions': ['Is performance measured at the same latency and model quality?',
                'How portable is the software workload?',
                'Does lower cost per token lead to more usage or lower margins?'],
  'beneficiary_context': 'These are covered companies with documented exposure to the theme. Potential '
                         'benefit is our interpretation, not a confirmed order or a ranking of expected '
                         'returns.',
  'editorial': 'Private starter based on the listed company disclosures. Undated pages were checked '
               'September 26, 2026. No automatic topic updates are enabled yet.'}]:
    ARTICLES[topic["slug"]] = topic

@router.get('/api/admin/insights')
def topics(request: Request, response: Response):
    staff(request)
    response.headers['Cache-Control']='private, no-store'
    return [{'slug':a['slug'],'title':a['title']} for a in ARTICLES.values()]

@router.get('/api/admin/insights/{slug}')
def starter(slug: str, request: Request, response: Response):
    staff(request)
    response.headers['Cache-Control']='private, no-store'
    return insight_data(slug)

def insight_data(slug):
    if slug not in ARTICLES:
        raise HTTPException(404, 'Topic not found')
    cached=_article_cache.get(slug)
    if cached and time.monotonic()-cached[0]<300:
        return copy.deepcopy(cached[1])
    from .insight_updates import merge_updates
    with core().db() as c:
        rows=c.execute("SELECT result FROM research_documents WHERE status IN ('draft','published','no_match') AND result LIKE ? ORDER BY updated DESC", ('%"topic": "'+slug+'"%',)).fetchall()
        from .insight_worker import migrate
        migrate(c)
        rows=list(rows)+list(c.execute("SELECT result FROM insight_analysis WHERE status='complete' AND result LIKE ? ORDER BY updated DESC",('%"topic": "'+slug+'"%',)).fetchall())
    from .insight_roadmaps import enrich,organize
    result=organize(merge_updates(enrich(ARTICLES[slug]),rows))
    _article_cache[slug]=(time.monotonic(),result)
    return copy.deepcopy(result)

@router.get('/api/insights')
def insight_previews(response:Response):
 response.headers['Cache-Control']='public, max-age=60'
 return [{'slug':a['slug'],'title':a['title'],'intro':a['intro']} for a in ARTICLES.values()]

@router.get('/api/insights/{slug}')
def member_insight(slug:str,request:Request,response:Response):
 from .pro_access import require_pro
 require_pro(request)
 response.headers['Cache-Control']='private, no-store'
 result=insight_data(slug)
 result['editorial']='Source-dated research developments. Earlier forecasts are retained as new information arrives.'
 return result
