from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw
from .social_design import attention_card, research_card, research_label, ASSETS


def test_zero_volume_unknown_logos_and_long_names(monkeypatch):
    seen=[]
    original=ImageDraw.ImageDraw.text
    def capture(self,xy,text,*args,**kwargs):
        seen.append(text)
        return original(self,xy,text,*args,**kwargs)
    monkeypatch.setattr(ImageDraw.ImageDraw,'text',capture)
    rows=[{'ticker':t,'name':'A particularly long company name with a share class description',
           'mentions':0,'change':change} for t,change in [('NVDA',None),('AMD',-80),('MU',0)]]
    im=Image.open(BytesIO(attention_card({'rows':rows,'title':'The month in AI attention','label':'30 days','date':'Oct 02, 2026'})))
    assert im.size==(1200,1250)
    assert 'Comparison unavailable' in seen and '-80% attention' in seen
    assert all('$'+r['ticker'] in seen for r in rows)
    assert '30 days' in seen and 'Oct 02, 2026' in seen


def test_research_labels_use_evidence_and_unclear_falls_back():
    assert research_label({'summary':'Initiating coverage at Buy.'})=='COVERAGE INITIATION'
    assert research_label({'summary':'Updated thoughts.'})=='RESEARCH UPDATE'
    assert research_label({'summary':'Earnings guidance.', 'link_type':'sector_readthrough'})=='SECTOR READ-THROUGH'


def test_runtime_assets_are_in_deployment_allowlist():
    rules=(Path(__file__).parents[1]/'.vercelignore').read_text()
    assert '!backend/social_design.py' in rules
    assert '!backend/social_assets/**' in rules
    assert (ASSETS/'Manrope.ttf').is_file() and (ASSETS/'OFL.txt').is_file()


def test_research_height_expands_without_clipping():
    row={'ticker':'MU','name':'Micron Technology','summary':'A complete sentence about research. '*70,
         'report_date':'2026-10-02','catalysts':[],'risks':[]}
    image=Image.open(BytesIO(research_card({'rows':[row]*3,'date':'2026-10-02'})))
    assert 2000<image.height<8000 and image.width==1200


def test_missing_asset_directory_still_renders(monkeypatch):
    from . import social_design as design
    monkeypatch.setattr(design,'ASSETS',Path('missing-runtime-assets'))
    design.ft.cache_clear()
    try:
        rows=[{'ticker':t,'name':t,'mentions':100,'change':10} for t in ['MU','AMD','NVDA']]
        assert Image.open(BytesIO(design.attention_card({'rows':rows,'label':'3 hours','date':'Oct 02, 2026'}))).size==(1200,1250)
    finally:
        design.ft.cache_clear()


def test_bundled_logos_cover_website_universe():
    import json,base64
    from .social_logos import LOGOS
    manifest=json.loads((Path(__file__).parents[1]/'frontend/src/companyLogos.json').read_text())
    assert set(manifest)==set(LOGOS)
    for encoded in LOGOS.values():
        with Image.open(BytesIO(base64.b64decode(encoded))) as image:
            assert image.size==(164,164)
            image.verify()
