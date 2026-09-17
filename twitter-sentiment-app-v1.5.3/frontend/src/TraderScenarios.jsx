import React,{useState} from 'react'

const scenarios=[
 ['Alex M.','“There is so much noise. I want one place to find the names worth researching, then read the original posts.”','01','DISCOVER'],
 ['Sophie R.','“A bullish take is more useful when I can see the other side too. That is how I want to build conviction.”','02','PERSPECTIVE'],
 ['Daniel K.','“My ideal morning routine: the voices I follow, their latest takes, and the stocks they are talking about.”','03','FOLLOW'],
 ['Maya L.','“I want to see whether a stock has lasting attention or just one very loud day.”','04','CONTEXT'],
 ['Chris T.','“Discovering an unfamiliar ticker is only the start. Show me the reasoning so I can do my own homework.”','05','EXPLORE'],
 ['Jordan P.','“I would rather save an interesting idea and revisit it than feel rushed into a trade.”','06','WATCHLIST'],
]
export function TraderScenarios(){
 const [paused,setPaused]=useState(false)
 return <section className={'trader-scenarios '+(paused?'is-paused':'')} aria-labelledby="scenarios-title">
  <div className="section-head"><div><span className="eyebrow">DIFFERENT ROUTINES. A SHARED CURIOSITY.</span><h2 id="scenarios-title">Make room for a better research habit.</h2><p className="muted">Fictional trader perspectives: illustrative names and quotes, not customer reviews.</p></div><button className="icon-button" aria-label={paused?'Resume carousel':'Pause carousel'} aria-pressed={paused} onClick={()=>setPaused(!paused)}><span aria-hidden="true">{paused?'▶':'Ⅱ'}</span></button></div>
  <div className="scenario-window"><div className="scenario-track">{[0,1].map(copy=><div className="scenario-group" key={copy} aria-hidden={copy===1?true:undefined}>{scenarios.map(([title,body,n,tag])=><article className="scenario-card" key={title}><div className="scenario-card-top"><span className="scenario-mark">↗</span><span>{tag}</span></div><p>{body}</p><div className="scenario-person"><span className="avatar">{n}</span><div><h3>{title}</h3></div></div></article>)}</div>)}</div></div>
 </section>
}
