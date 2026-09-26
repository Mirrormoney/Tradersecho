import React,{useEffect,useRef,useState} from 'react'
import {api} from './api.js'
import {SignalRadar} from './SignalLab.jsx'
import {dualTime} from './time.js'
const fmt=v=>v==null?'—':Number(v.toFixed(1))
const cache=new Map()
function HistoryChart({points,name}){
 const valid=points.filter(p=>p.value!=null)
 if(!valid.length)return <p className="muted">No numeric history yet for this indicator.</p>
 const stamp=d=>Date.parse(d+'T12:00:00Z'),first=stamp(points[0].day),last=stamp(points.at(-1).day)
 const x=p=>last===first?350:45+(stamp(p.day)-first)/(last-first)*610,y=p=>170-p.value*1.4
 return <><svg className="lab-history-chart" viewBox="0 0 700 215" role="img" aria-label={`${name}: daily averages from ${points[0].day} to ${points.at(-1).day}`}>
 {[0,50,100].map(v=><g key={v}><line x1="45" x2="655" y1={170-v*1.4} y2={170-v*1.4} stroke="currentColor" opacity=".18"/><text x="12" y={174-v*1.4}>{v}</text></g>)}
 {points.map((p,i)=>p.value!=null&&i>0&&points[i-1].value!=null?<line key={p.day} x1={x(points[i-1])} y1={y(points[i-1])} x2={x(p)} y2={y(p)} stroke="#c9ef83" strokeWidth="3"/>:null)}
 {valid.map(p=><circle key={p.day} cx={x(p)} cy={y(p)} r="5" fill={p.partial_day?'#e8c68d':'#c9ef83'}><title>{p.day}: {fmt(p.value)} · {p.samples} observations{p.partial_day?' · Today so far':''}</title></circle>)}
 <text x="45" y="204">{points[0].day}</text><text x="655" y="204" textAnchor="end">{points.at(-1).day}</text></svg><p className="muted">Daily averages · {valid.length} days with values{valid.some(p=>p.partial_day)?' · Amber point: today so far':''}</p></>
}
export function SignalStockDetail({ticker,initialAxis=0,onBack}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[axis,setAxis]=useState(initialAxis),[days,setDays]=useState(30),[refresh,setRefresh]=useState(0)
 const heading=useRef(null)
 useEffect(()=>{heading.current?.focus()},[ticker])
 useEffect(()=>{let active=true;setError('');setData(null);const saved=cache.get(ticker);if(!refresh&&saved&&Date.now()-saved.at<120000){setData(saved.data);return}api('/admin/signal-lab-detail/'+encodeURIComponent(ticker)).then(d=>{if(active){setData(d);cache.set(ticker,{at:Date.now(),data:d});if(cache.size>50)cache.delete(cache.keys().next().value)}}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[ticker,refresh])
 const a=data?.axes[axis],today=data?new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(data.server_at*1000)):null
 const cutoff=today?new Date(Date.parse(today+'T12:00:00Z')-days*86400000).toISOString().slice(0,10):''
 return <section className="lab-stock-detail"><button className="button" onClick={onBack}>← Signal overview</button><div className="section-head" style={{marginTop:24}}><div><span className="eyebrow">SIGNAL LAB · ADMIN DETAIL PREVIEW</span><h1 ref={heading} tabIndex={-1}>${ticker}{data&&<span className="muted"> · {data.name}</span>}</h1></div><button className="button" onClick={()=>setRefresh(v=>v+1)}>Refresh saved view</button></div>{error&&<p className="error" role="alert">{error}</p>}{!data&&!error&&<p>Loading indicator history…</p>}{data&&<><p className="muted">{data.stale?'Last saved observation':'Latest observation'} · {dualTime(data.observed)} · Scoring version {data.version}</p><div className="lab-detail-top"><section className="panel"><SignalRadar axes={data.axes}/></section><div className="lab-axis-picker" role="group" aria-label="Choose indicator">{data.axes.map((item,i)=><button key={item.name} aria-pressed={axis===i} className={'panel '+(axis===i?'selected':'')} onClick={()=>setAxis(i)}><span>{item.name}<small>{item.direction|| (item.score==null?'Unavailable':'Activity / strength')}</small></span><strong>{fmt(item.score)}<small> / 100</small></strong></button>)}</div></div><section className="panel lab-history-panel"><div className="section-head"><h2>{a.name} · Development</h2><div className="tabs">{[7,30].map(n=><button key={n} aria-pressed={days===n} className={days===n?'selected':''} onClick={()=>setDays(n)}>{n} days</button>)}</div></div><div className="lab-history-stats"><div><small>Last saved score</small><strong>{fmt(a.score)}</strong><span>{a.direction||a.state}</span></div>{[7,30].map(n=><div key={n}><small>{n}-day average</small><strong>{fmt(a.windows[n].average)}</strong><span>{a.windows[n].days} observed days · {a.windows[n].samples} samples</span><span>{a.windows[n].delta==null?'Comparison unavailable':`${a.windows[n].delta>0?'+':''}${fmt(a.windows[n].delta)} points vs average`}</span></div>)}</div><HistoryChart points={a.points.filter(p=>p.day>=cutoff)} name={a.name}/><h3>What drives this indicator</h3><p>{a.reason}</p><details><summary>How the comparison works</summary><p className="muted">{data.method} A short history is shown as available-day coverage, not a complete 7- or 30-day track record. Lines describe the saved score’s development, not a stock-price chart.</p></details></section></>}</section>
}
