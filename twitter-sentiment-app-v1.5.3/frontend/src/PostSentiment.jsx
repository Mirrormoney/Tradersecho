import React from 'react'
export function SentimentBadge({post:p}){
 const waiting=p.sentiment==='pending'
 return <span className={'tag '+p.sentiment}>{waiting?(p.sentiment_status==='error'?'Analysis delayed':p.sentiment_status==='unsupported'?'Context unavailable':'Awaiting analysis'):p.sentiment+' · '+(p.sentiment_method==='contextual_ai'?'AI':'sample')}</span>
}
export function SentimentContext({post:p}){
 if(p.sentiment_status!=='done')return null
 return <details className="sentiment-context"><summary>Why this label? <span>AI interpretation</span></summary><p>{p.sentiment_reason}</p>{p.sentiment_evidence&&<blockquote>{p.sentiment_evidence}</blockquote>}{p.ticker_sentiments?.length>0&&<div className="ticker-interpretations">{p.ticker_sentiments.map(t=><div key={t.ticker}><span className={'tag '+t.label}>${t.ticker} · {t.label}</span><p>{t.reason}</p></div>)}</div>}<small>Based on the collected text, not a verified fact or trading recommendation. Images and linked context are not analyzed.</small></details>
}
