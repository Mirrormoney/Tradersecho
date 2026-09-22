import React from 'react'
export function SentimentBadge({post:p}){
 const waiting=p.sentiment==='pending'
 return <span className={'tag '+p.sentiment}>{waiting?(p.sentiment_status==='error'?'Analysis delayed':p.sentiment_status==='unsupported'?'Context unavailable':'Awaiting analysis'):p.sentiment+' · '+(p.sentiment_method==='contextual_ai'?'AI':'sample')}</span>
}
// Keep the shared interface; interpretation text is intentionally not shown on post cards.
export function SentimentContext(){return null}
