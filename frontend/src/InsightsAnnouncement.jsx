import React from 'react'

// Public announcement only. Research articles stay behind the admin API.
export function InsightsAnnouncement(){return <section className="panel" aria-label="AI Insights announcement" style={{maxWidth:960,margin:'24px auto',padding:'clamp(24px,5vw,64px)'}}>
 <span className="tag">COMING OCTOBER 1</span>
 <h1 style={{fontSize:'clamp(32px,5vw,58px)',lineHeight:1.12,margin:'24px 0 16px'}}>AI Insights</h1>
 <h2>Understand what comes next.</h2>
 <p className="muted" style={{maxWidth:640,lineHeight:1.8}}>Explore the technologies shaping the AI economy. Understand each theme, follow expected milestones and discover potential beneficiaries as new research develops.</p>
 <div className="ticker-chips" style={{margin:'28px 0'}}>{['800 VDC','HBM & memory','Advanced packaging','Optical networking','Liquid cooling','AI power','Inference & custom chips'].map(topic=><span key={topic}>{topic}</span>)}</div>
 <p className="muted">The full experience is coming October 1. Until then, explore the tools already available on Traders Echo.</p>
 <a className="button primary" href="/home">Explore Traders Echo ↗</a>
 </section>}
