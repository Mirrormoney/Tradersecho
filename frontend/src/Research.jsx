import React,{useEffect,useState} from 'react'
import {api} from './api.js'
import {DriveResearchAdmin} from './ResearchDrive.jsx'
function Findings({report}){return <><h3>{report.title}</h3><p className="muted">{report.firm||'Source not identified'} · Report date: {report.report_date||'Needs verification'}</p>{report.findings.map(f=><article className="panel" key={f.ticker}><strong>${f.ticker}</strong> <span className="tag">{f.stance} · author’s stance</span><p>{f.summary}</p>{f.catalysts.length>0&&<p><strong>Catalysts: </strong>{f.catalysts.join(' · ')}</p>}{f.risks.length>0&&<p><strong>Risks: </strong>{f.risks.join(' · ')}</p>}<details><summary>Source evidence · page {f.page}</summary><blockquote>{f.evidence}</blockquote></details></article>)}</>}
export function ResearchAdmin(){
 const [data,setData]=useState(null),[error,setError]=useState('')
 async function load(){try{setData(await api('/admin/research'));setError('')}catch(e){setError(e.message)}}
 useEffect(()=>{load()},[])
 return <section className="panel"><div className="section-head"><h2>Research imports</h2><button className="button" onClick={load}>Refresh status</button></div><DriveResearchAdmin/><p className="muted">Email and Drive imports run automatically. Validated recent summaries appear in Trending Research. Individual failed files are skipped without blocking other notes.</p>{error&&<p className="error" role="alert">{error}</p>}{data&&<><p>Mailbox: {data.configured?'credential saved':'password required'} · Worker: {data.worker?.state||'not run yet'}</p><div className="research-actions">{Object.entries(data.health?.counts||{}).map(([status,count])=><span className="tag" key={status}>{status==='needs_review'?'Held / skipped':status==='draft'?'Validated':status.replaceAll('_',' ')}: {count}</span>)}</div><p className="muted">Last check: {data.health?.checked_at?new Date(data.health.checked_at*1000).toLocaleString():'Pending'}. Operational problems trigger an owner email; individual held notes need no action to keep imports running.</p>{!!data.health?.operational_issues?.length&&<div className="error" role="status"><ul>{data.health.operational_issues.map(issue=><li key={issue}>{issue}</li>)}</ul></div>}</>}</section>
}
export function TickerResearch({ticker}){
 const [docs,setDocs]=useState([])
 useEffect(()=>{let active=true;setDocs([]);api('/research/'+encodeURIComponent(ticker)).then(d=>{if(active)setDocs(d.documents)}).catch(()=>{});return()=>{active=false}},[ticker])
 if(!docs.length)return null
 return <details className="ticker-filings"><summary>Desk research · private admin preview ({docs.length})</summary><p className="muted">AI-generated drafts. Verify against the original report before publication. Newest report dates first.</p>{docs.map(d=><Findings key={d.id} report={d}/>)}</details>
}
