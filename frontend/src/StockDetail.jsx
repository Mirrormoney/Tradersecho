import {signalStatus} from './signalStatus.mjs'
import {SignalRadar} from './SignalLab.jsx'
import {StockActions} from './Engagement.jsx'
import {ProLock} from './ProFeatures.jsx'
import React,{useEffect,useState} from 'react'
import {api} from './api.js'
import {dualTime} from './time.js'
import {Filings} from './Filings.jsx'
import {LiveTicker} from './LiveTicker.jsx'
import {TradingViewLink,TradingViewDisclosure} from './TradingView.jsx'
import './stock-detail.css'

const fmt=n=>Intl.NumberFormat('en-US').format(n)
export function DetailSection({title,initialOpen=true,children}){
 const [open,setOpen]=useState(initialOpen)
 return <details className="stock-detail-section" open={open} onToggle={e=>setOpen(e.currentTarget.open)}><summary>{title}</summary><div className="stock-detail-content">{children}</div></details>
}
function MorePosts({rows,source,Posts}){
 const [shown,setShown]=useState(5)
 return <DetailSection title={`View more X posts · ${rows.length} more`} initialOpen={false}><Posts rows={rows.slice(0,shown)} source={source}/>{shown<rows.length&&<button className="button" onClick={()=>setShown(n=>n+5)}>Show {Math.min(5,rows.length-shown)} more posts</button>}</DetailSection>
}
export function StockDetail({onBack,ticker,name,row,intraday,windowDays,asOf,coverageDays,source,user,refresh,posts,postsLoading,postsError,postOrder,setPostOrder,postFeed,setPostFeed,Posts,Spark,Sentiment,watchlist,toggleWatch}){
 const [signal,setSignal]=useState(null),[signalLoading,setSignalLoading]=useState(true),[signalError,setSignalError]=useState('')
 useEffect(()=>{let active=true;setSignal(null);setSignalError('');setSignalLoading(Boolean(user?.pro_access));if(!user?.pro_access)return;api('/signal-lab/detail/'+encodeURIComponent(ticker)).then(d=>{if(active)setSignal(d)}).catch(()=>{if(active)setSignalError('Signal Lab could not be loaded. Please retry.')}).finally(()=>{if(active)setSignalLoading(false)});return()=>{active=false}},[ticker,refresh,user?.pro_access])
 const [research,setResearch]=useState([]),[researchError,setResearchError]=useState(''),[researchLoading,setResearchLoading]=useState(true)
 const staff=['owner','admin'].includes(user?.role)
 const canResearch=staff||['premium','pro'].includes(user?.plan)
 useEffect(()=>{let active=true;setResearch([]);setResearchError('');setResearchLoading(canResearch);if(!canResearch)return;api('/member-research/'+encodeURIComponent(ticker)).then(d=>{if(active){setResearch(d.documents||[]);setResearchError('');setResearchLoading(false)}}).catch(()=>{if(active){setResearchError('Research is temporarily unavailable.');setResearchLoading(false)}});return()=>{active=false}},[ticker,canResearch,refresh])
 const findings=research.flatMap(d=>(d.findings||[]).filter(f=>f.ticker===ticker).map(f=>({report:d,finding:f})))
 findings.sort((a,b)=>(b.report.report_date||'').localeCompare(a.report.report_date||''))
 const latest=findings[0]
 const period=intraday?'latest three completed hours':windowDays===1?'24-hour snapshot':`${windowDays}-day snapshot`
 const measured=row&&Number.isFinite(row.mentions)&&(!intraday||row.state==='measured')
 const curated=posts.filter(p=>p.curated)
 const contextualPost=curated.find(p=>p.sentiment_status==='done'&&p.sentiment_reason)
 return <article className="stock-detail stock-page"><button className="text-link stock-back" onClick={onBack}>← Back to overview</button><header className="stock-page-heading"><div><span className="eyebrow">STOCK RESEARCH</span><h1>${ticker}</h1><p>{name||ticker}</p></div><div className="stock-page-actions"><button className="button" onClick={()=>toggleWatch(ticker)}>{watchlist.includes(ticker)?'★ Saved':'☆ Watchlist'}</button><TradingViewLink ticker={ticker} name={name} detail/><StockActions key={`${ticker}-${intraday}-${windowDays}`} ticker={ticker} intraday={intraday} windowDays={windowDays} source={source}/></div></header><TradingViewDisclosure/><div className="stock-page-columns"><div className="stock-page-main">

  <DetailSection title="Why it’s trending · Evidence check">
   {measured&&<><p>{fmt(row.mentions)} mentions in the {period}{row.change!=null?`, ${row.change>0?'up':row.change<0?'down':'unchanged'}${row.change===0?'':` ${fmt(Math.abs(row.change))}%`} versus the preceding comparable period`:'. A comparable growth figure is not available'}.</p><p className="muted">{Number.isFinite(row.heat)?`Attention heat score: ${row.heat}. `:''}Rankings combine mention volume and acceleration; they do not measure price performance.{!intraday&&coverageDays<windowDays?` History covers ${coverageDays} of ${windowDays} days.`:''}</p>{(row.as_of||asOf)&&<small className="muted">Snapshot · {dualTime(row.as_of||asOf)}</small>}</>}
   {latest&&<div className="detail-evidence"><span className="tag">{latest.finding.link_type==='sector_readthrough'?'Sector read-through':'Research context'}</span><p>{latest.finding.summary}</p><small className="muted">{latest.report.firm||''}{latest.report.report_date?` · ${latest.report.report_date}`:''}</small></div>}
   {contextualPost&&<div className="detail-evidence"><strong>Tracked voice context</strong><p>{contextualPost.sentiment_reason}</p><a href={'https://x.com/i/web/status/'+contextualPost.id} target="_blank" rel="noreferrer">@{contextualPost.author} · {dualTime(contextualPost.ts)} ↗</a></div>}
   {!measured&&!latest&&!contextualPost&&<p className="muted">{postsLoading?'Loading collected context…':curated.length?`${curated.length} collected tracked-voice posts are available below.`:'No measured ranking activity or supporting research is available in this view yet.'}</p>}
   {postsError&&<p className="error">X context could not be loaded.</p>}
   <small className="muted block">Research and posts provide context; they do not prove what caused attention to change.</small>
  </DetailSection>
  <DetailSection title={`Latest research${findings.length?' · '+findings.length:''}`}>
   {researchError&&<p className="error">{researchError}</p>}
   {!canResearch?<p className="muted">Broker research is included with Premium. <a href="/plans">Explore plans ↗</a></p>:researchLoading?<p className="muted" role="status">Loading latest research…</p>:!researchError&&!findings.length&&<p className="muted">No recent research available.</p>}
   {findings.slice(0,1).map(({report,finding},i)=><article className="detail-research" key={report.id+'-'+i}><div className="section-head">{report.firm&&<strong>{report.firm}</strong>}<span className="tag">{finding.link_type==='sector_readthrough'?'Sector read-through · no stock rating':`${finding.stance} · author’s stance`}</span></div>{report.report_date&&<small className="muted">Report date · {report.report_date}</small>}{finding.link_type==='sector_readthrough'&&<p className="muted">{finding.link_reason}</p>}<p>{finding.summary}</p>{finding.catalysts?.length>0&&<p><strong>What to watch: </strong>{finding.catalysts.join(' · ')}</p>}{finding.risks?.length>0&&<p><strong>Risks: </strong>{finding.risks.join(' · ')}</p>}</article>)}
   {findings.length>1&&<DetailSection title={`More research · ${findings.length-1}`} initialOpen={false}>{findings.slice(1).map(({report,finding},i)=><article className="detail-research" key={report.id+'-'+i}><strong>{report.firm}</strong><small className="muted"> · {report.report_date}</small><p>{finding.summary}</p></article>)}</DetailSection>}
  </DetailSection>
  <DetailSection title="Behind the mentions · X posts">
   <div className="detail-post-controls"><label>Post order<select value={postOrder} onChange={e=>setPostOrder(e.target.value)}><option value="latest">Latest posts</option><option value="engagement">Most liked takes</option></select></label><label>Post selection<select value={postFeed} onChange={e=>setPostFeed(e.target.value)}><option value="research">Research · curated first</option><option value="all">All collected posts · unfiltered</option></select></label></div>
   <Posts rows={posts.slice(0,2)} source={source} loading={postsLoading} error={postsError}/>
   {!postsLoading&&!postsError&&posts.length>2&&<MorePosts key={postOrder+postFeed} rows={posts.slice(2)} source={source} Posts={Posts}/>}
  </DetailSection>
</div><aside className="stock-page-side">
 <DetailSection title="Signal Lab">{!user?.pro_access?<ProLock title="Individual stock signals"/>:signal?<><SignalRadar axes={signal.axes}/><div className="stock-signal-values">{signal.axes.map(a=><div key={a.name}><span>{a.name}</span><strong title={a.reason}>{a.score==null?signalStatus(a):a.score+' / 100'}</strong></div>)}</div><small className="muted">Saved · {dualTime(signal.observed)}</small><a className="text-link" href={'/signal-lab/'+encodeURIComponent(ticker)}>Explore the five indicators ↗</a></>:<p className={signalError?"error":"muted"} role={signalError?"alert":"status"}>{signalLoading?"Loading Signal Lab…":signalError||"No saved Signal Lab observations available."}</p>}</DetailSection>
  <DetailSection title="Attention metrics">
   {measured?<><div className="detail-stats"><div><small>Mentions · {intraday?'3 hours':windowDays===1?'24 hours':windowDays+' days'}</small><strong>{fmt(row.mentions)}</strong></div><div><small>Heat score</small><strong>{row.heat??'—'}</strong></div><div><small>{intraday?'Previous 3 hours':'Sample authors'}</small><strong>{intraday?(row.previous??'—'):(row.quality?.independent_authors??row.authors??'—')}</strong></div></div>{row.spark?.length>0&&<Spark values={row.spark} large/>}<p className="muted">{intraday?'Latest three completed hours compared with the preceding three.':`Selected ${windowDays===1?'24-hour':windowDays+'-day'} ranking snapshot.`}{!intraday&&coverageDays<windowDays?` Only ${coverageDays} days of history available.`:''}</p>{!intraday&&<Sentiment row={row}/>}</>:<p className="muted">No measured ranking row is available in the selected period. The latest shared check below may cover a different window.</p>}

  </DetailSection>
</aside></div><div className="stock-page-bottom">
  <DetailSection title="SEC EDGAR filings" initialOpen={false}><Filings ticker={ticker} compact refresh={refresh}/></DetailSection>
  {source==='x'&&<DetailSection title="Latest attention check" initialOpen={false}><LiveTicker ticker={ticker} premium={['premium','pro'].includes(user?.plan)||staff} refresh={refresh}/></DetailSection>}
 </div></article>
}
