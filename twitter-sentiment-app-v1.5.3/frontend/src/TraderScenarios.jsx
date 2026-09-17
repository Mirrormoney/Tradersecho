import React,{useState} from 'react'

const scenarios=[
 ['The morning scan','Start with the names gaining attention, then open the original posts before building a watchlist.','01','DISCOVER'],
 ['The second opinion','Put a promising thesis beside the counterargument. A useful feed leaves room for both.','02','PERSPECTIVE'],
 ['The research routine','Keep the voices you follow in one place, with their collected takes connected to the stocks they mention.','03','FOLLOW'],
 ['The bigger picture','Compare today’s conversation with the past week. One loud day is only part of the story.','04','CONTEXT'],
 ['The curious investor','Find an unfamiliar ticker, read the reasoning, and decide whether it deserves a closer look.','05','EXPLORE'],
 ['The patient trader','Save an interesting name now and come back as the conversation develops. Research at your own pace.','06','WATCHLIST'],
]
export function TraderScenarios(){
 const [paused,setPaused]=useState(false)
 return <section className={'trader-scenarios '+(paused?'is-paused':'')} aria-labelledby="scenarios-title">
  <div className="section-head"><div><span className="eyebrow">DIFFERENT ROUTINES. A SHARED CURIOSITY.</span><h2 id="scenarios-title">Make room for a better research habit.</h2><p className="muted">Illustrative trader scenarios — not customer testimonials or performance claims.</p></div><button className="button" aria-pressed={paused} onClick={()=>setPaused(!paused)}>{paused?'Play cards':'Pause cards'}</button></div>
  <div className="scenario-window"><div className="scenario-track">{[0,1].map(copy=><div className="scenario-group" key={copy} aria-hidden={copy===1?true:undefined}>{scenarios.map(([title,body,n,tag])=><article className="scenario-card" key={title}><div className="scenario-card-top"><span className="scenario-mark">↗</span><span>{tag}</span></div><p>{body}</p><div className="scenario-person"><span className="avatar">{n}</span><div><h3>{title}</h3><small>Example research routine</small></div></div></article>)}</div>)}</div></div>
 </section>
}
