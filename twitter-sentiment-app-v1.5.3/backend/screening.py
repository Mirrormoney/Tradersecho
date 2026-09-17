"""Transparent sample screening, not a claim that accounts are human."""
import re, hashlib
from difflib import SequenceMatcher

def fingerprint(text):
    text=re.sub(r'https?://\S+|\$[A-Z]{1,6}\b|@[\w]+|\d+',' ',text,flags=re.I)
    return ' '.join(re.findall(r'[a-z]+',text.lower()))

def ticker_sentiment(text,ticker,classifier):
    from .post_quality import language_label
    return language_label(text,ticker)

def screen(posts,classifier,ticker):
    seen_author_days=set();templates=[];retained=[];duplicates=0;repeated=0
    from .post_quality import research_text
    for p in sorted(posts,key=lambda p:(p['ts'],p['id'])):
        key=(p.get('author_id') or p['author'],int(p['ts']//86400))
        text=fingerprint(p['text'])
        if not research_text(p['text']):duplicates+=1;continue
        if key in seen_author_days: repeated+=1;continue
        seen_author_days.add(key)
        if not text or any(text==other or (len(text)>30 and SequenceMatcher(None,text,other).ratio()>.9) for other in templates):
            duplicates+=1;continue
        templates.append(text)
        retained.append({**p,'label':ticker_sentiment(p['text'],ticker,classifier)})
    authors=len({p.get('author_id') or p['author'] for p in retained})
    labels={label:sum(p['label']==label for p in retained) for label in ['bullish','bearish','neutral','unclear']}
    return {'sample_posts':len(posts),'screened_posts':len(retained),'independent_authors':authors,
            'duplicate_posts':duplicates,'repeat_author_posts':repeated,
            'sufficient':len({p.get('author_id') or p['author'] for p in retained if p['label']!='unclear'})>=20,'labels':labels,
            'suspicious_share':round((duplicates+repeated)/len(posts),3) if posts else 0}

def enrich(c,rows,now,window,classifier):
    grouped={}
    for p in c.execute('SELECT p.*,i.author_id,m.ticker FROM posts p JOIN mentions m ON p.source=m.source AND p.id=m.post_id LEFT JOIN post_identity i ON p.source=i.source AND p.id=i.post_id WHERE p.source=? AND p.ts>? AND p.ts<=? ORDER BY p.ts DESC LIMIT 20000',('x',now-window*86400,now)):
        group=grouped.setdefault(p['ticker'],[])
        if len(group)<500:group.append(dict(p))
    for row in rows:
        posts=grouped.get(row['ticker'],[])
        quality=screen(posts,classifier,row['ticker'])
        row['quality']=quality
        row['sample_mentions']=quality['screened_posts']
        row.update(quality['labels'])
        row['sentiment']=round((row['bullish']-row['bearish'])/max(1,row['sample_mentions'])*100) if quality['sufficient'] else None
    return rows
