from .newsletter import render

def test_top_three_then_posts_then_ranks_four_to_ten():
    rows=[{'ticker':'ST'+str(i),'name':'Company '+str(i),'mentions':100+i,'change':i} for i in range(1,12)]
    report={'ready':True,'date':'2026-09-16','tracked_stocks':357,'rows':rows,'posts':[{'id':'123','author':'voice','text':'A relevant collected take','tickers':'ST1'}]}
    html=render(report,preview=True)['html']
    assert html.count('class="top-stock"')==3
    assert html.index('Today’s collected takes.')<html.rindex('In focus · 24 hours')<html.index('$ST10')
    assert '$ST11' not in html and 'A relevant collected take' in html
    assert 'href=' not in html.replace('data-preview-href=','')

def test_focus_rows_branding_escaping_and_periods():
    rows=[{'ticker':'MU','name':'Micron','mentions':30,'change':5} for _ in range(3)]
    post={'id':'123','author':'voice','text':'<script>Not HTML</script>','ts':1790078400}
    for labels in [('Intraday','24 hours'),('7 days',),('30 days',)]:
        windows=[{'label':label,'period_label':'3 hours' if label=='Intraday' else label,'rows':[{**r,**({'featured_post':post} if i==0 and n==0 else {})} for i,r in enumerate(rows)]} for n,label in enumerate(labels)]
        report={'ready':True,'date':'2026-09-22','tracked_stocks':363,'rows':rows,'focus_windows':windows}
        content=render(report)
        html=content['html']
        assert html.count('class="top-stock"')==3
        assert 'cid:tradersecho-pulse' in html and len(content['attachments'])==1
        assert html.count('Read the original on X')==1
        assert '&lt;script&gt;' in html and '<script>' not in html
        assert 'display:block!important' in html and 'table-layout:fixed' in html
        assert 'In focus · Intraday' in html if len(labels)==2 else 'In focus · Intraday' not in html
        assert 'IN FOCUS / '+labels[0] in content['text']


def test_research_section_order_redaction_and_empty():
    row={'ticker':'MU','name':'Micron','mentions':30,'change':5}
    report={'ready':True,'date':'2026-09-22','tracked_stocks':1,'rows':[row], 'latest_research':[{'ticker':'MU','firm':'UBS','report_date':'2026-09-22','summary':'UBS raises its HBM forecast.'}]}
    content=render(report)
    h=content['html']
    assert h.index('Today’s collected takes')<h.index('Latest trending research')<h.rindex('In focus · 24 hours')
    assert 'UBS raises its HBM forecast.' in content['text']
    assert 'view=research' in h
    report['latest_research']=[]
    assert 'Latest trending research' not in render(report)['html']
