"""Conservative research filtering. Labels describe language, never investment advice."""
import re
from .screening import fingerprint

PROMOTION=re.compile(r'join.{0,45}(group|chat|telegram|whatsapp)|(?:stock|learning|trading|whatsapp|telegram).{0,25}group|copy\s*trading|(?:t\.me|wa\.me)/|guaranteed.{0,20}(profit|return)',re.I|re.S)

def research_text(text):
    clean=re.sub(r'https?://\S+|@[\w]+',' ',text)
    # Ticker-stuffed promotions inflate relevance without offering stock research.
    # Preserve short, specific takes such as "$MU buying" and multi-stock analysis.
    tickers=set(re.findall(r'\$[A-Za-z]{1,5}\b',clean))
    prose=re.sub(r'\$[A-Za-z]{1,5}\b',' ',clean)
    if len(tickers)>=8 and len(re.findall(r'[A-Za-z]{2,}',prose))<len(tickers)*4:return False
    return (len(re.findall(r'[A-Za-z]+',clean))>=7 or bool(re.search(r'\$[A-Za-z]',clean)) and len(re.findall(r'[A-Za-z]+',clean))>=2) and not PROMOTION.search(text)

def language_label(text,ticker=''):
    clauses=re.split(r'[.!?;\n]|\bbut\b|\bwhile\b',text,flags=re.I)
    labels=[]
    for clause in clauses:
        tickers=set(re.findall(r'\$([A-Z]{1,5}(?:\.[A-Z])?)\b',clause,re.I))
        if ticker and ticker.upper() not in {t.upper() for t in tickers}:continue
        if len(tickers)>1:continue
        clause=re.sub(r'\b(short|long)[ -]term\b','term',clause,flags=re.I)
        words=re.findall(r'[a-z]+',clause.lower());score=0
        positive={'bullish','buy','buying','breakout','upside','outperform','tailwind','tailwinds','undervalued'}
        negative={'bearish','sell','selling','downside','underperform','headwind','headwinds','overvalued'}
        for i,w in enumerate(words):
            v=int(w in positive)-int(w in negative)
            if any(n in {'not','no','never'} for n in words[max(0,i-3):i]):v=-v
            score+=v
        if score:labels.append('bullish' if score>0 else 'bearish')
        elif re.search(r'\b(neutral|no position|on the sidelines)\b',clause,re.I):labels.append('neutral')
    return labels[0] if labels and len(set(labels))==1 else 'unclear'

def prepare_feed(rows,ticker,curated,feed,order):
    ordered=sorted(rows,key=lambda p:(p['author'] in curated,p['likes'] if order=='engagement' else p['ts'],p['ts']),reverse=True)
    result=[];seen=set()
    for p in ordered:
        text=p['text'];fp=fingerprint(text)
        if feed=='research' and (not research_text(text) or fp in seen):continue
        seen.add(fp)
        result.append({**p,'sentiment':p.get('sentiment','pending') if p.get('source')=='x' else language_label(text,ticker),'curated':p['author'] in curated,'sample_note':'AI interpretation of collected text; images, linked pages and thread context may be missing.' if p.get('sentiment_status')=='done' else 'Collected excerpt; open X for full context.'})
    return result
