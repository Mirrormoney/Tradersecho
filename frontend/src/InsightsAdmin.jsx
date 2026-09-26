import React,{useEffect,useState} from 'react'
import {api} from './api.js'
import './insights-admin.css'
const date=value=>new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'UTC'}).format(new Date(value+'T12:00:00Z'))
export function InsightsAdmin(){
 const [article,setArticle]=useState(null),[error,setError]=useState('')
 useEffect(()=>{let active=true;api('/admin/insights/800-vdc').then(d=>{if(active)setArticle(d)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[])
 if(error)return <p className="error" role="alert">{error}</p>
 if(!article)return <p role="status">Loading private topic starter…</p>
 const sources=Object.fromEntries(article.sources.map(s=>[s.id,s]))
 return <article className="insights-admin"><section className="panel insight-intro"><span className="eyebrow">AI INSIGHTS · PRIVATE STARTER</span><h2>{article.title}</h2><div className="insight-meta"><span className="tag">Admin only</span><span>Evidence through {date(article.evidence_through)}</span><span>Reviewed {date(article.reviewed)}</span></div><p className="insight-lead">{article.intro}</p><div className="insight-distinction"><h3>One theme. Different stages.</h3><p>{article.distinction}</p></div><p>{article.summary}</p></section>
 <section className="panel"><span className="eyebrow">WHAT IS EXPECTED, AND WHEN</span><h2>The development timeline</h2><p className="muted">Source-dated expectations. Future milestones are forecasts, not completed events.</p><ol className="insight-timeline">{article.timeline.map((item,i)=><li key={item.title}><div className="insight-date"><span>{item.when}</span><small>{item.scope}</small></div><div className="insight-event"><h3>{item.title}</h3><p>{item.expectation}</p><div className="insight-source">{[item.source,item.also_source].filter(Boolean).map(id=><span key={id}>{sources[id].name} · {date(sources[id].date)}<small>{sources[id].kind}</small></span>)}</div><p className="muted"><strong>What to watch: </strong>{item.watch}</p><details><summary>Evidence reference</summary><p>{item.page}</p></details></div></li>)}</ol></section>
 <div className="insight-bottom"><section className="panel"><h2>Questions to follow</h2><ul>{article.questions.map(q=><li key={q}>{q}</li>)}</ul></section><section className="panel"><h2>Source notes</h2>{article.sources.map(s=><div className="insight-note" key={s.id}><strong>{s.name} · {date(s.date)}</strong><p>{s.label}</p><small className="muted">{s.kind} · Pages {s.pages}</small></div>)}</section></div><p className="muted">{article.editorial}</p></article>
}
