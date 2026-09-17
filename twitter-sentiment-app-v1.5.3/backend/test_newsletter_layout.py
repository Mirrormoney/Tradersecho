from .newsletter import render

def test_top_three_then_posts_then_ranks_four_to_ten():
    rows=[{'ticker':'ST'+str(i),'name':'Company '+str(i),'mentions':100+i,'change':i} for i in range(1,12)]
    report={'ready':True,'date':'2026-09-16','tracked_stocks':357,'rows':rows,'posts':[{'id':'123','author':'voice','text':'A relevant collected take','tickers':'ST1'}]}
    html=render(report,preview=True)['html']
    assert html.count('class="top-stock"')==3
    assert html.index('Behind the top three.')<html.index('More on the radar')<html.index('$ST10')
    assert '$ST11' not in html and 'A relevant collected take' in html
    assert 'href=' not in html.replace('data-preview-href=','')
