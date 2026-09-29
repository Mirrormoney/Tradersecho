import {signalStatus} from './signalStatus.mjs'
import React,{useEffect,useState} from 'react'
import {api} from './api.js'
import {dualTime} from './time.js'
import './signal-lab.css'
const names=['Price','Volume','Options','X activity','Catalyst']
export function SignalRadar({axes=[],compact=false}){
 const point=(i,v)=>{const a=-Math.PI/2+i*Math.PI*2/5;return [(compact?140:150)+Math.cos(a)*(compact?82:78)*v/100,(compact?100:122)+Math.sin(a)*(compact?82:78)*v/100]}
 const poly=v=>names.map((_,i)=>point(i,v).join(',')).join(' ')
 const visible=axes.flatMap((a,i)=>a.strength==null?[]:[{i,p:point(i,a.strength)}])
 return <svg className="signal-pentagon" viewBox={compact?"0 0 280 200":"0 0 300 245"} role="img" aria-label={axes.map(a=>a.name+': '+(a.score??'not ready')).join(', ')}>
 {[25,50,75,100].map(v=><polygon key={v} points={poly(v)} fill="none" stroke="currentColor" opacity=".2"/>)}
 {names.map((n,i)=>{const p=compact?[[140,10],[244,66],[205,186],[75,186],[36,66]][i]:point(i,133);return <text key={n} x={p[0]} y={p[1]} textAnchor="middle" dominantBaseline="middle">{n}</text>})}
 {visible.length>=3&&<polygon points={visible.map(a=>a.p.join(',')).join(' ')} fill="currentColor" opacity=".23"/>}
 {visible.length>1&&visible.map((a,i)=>{const b=visible[(i+1)%visible.length];return <line key={a.i} x1={a.p[0]} y1={a.p[1]} x2={b.p[0]} y2={b.p[1]} stroke="currentColor" strokeWidth="2" strokeDasharray={(b.i-a.i+5)%5>1?'4 4':undefined}/>})}
 {visible.map(a=><circle key={a.i} cx={a.p[0]} cy={a.p[1]} r="4" fill="currentColor"/>)}
 </svg>
}
function useSignals(){
 const [data,setData]=useState(null),[error,setError]=useState('')
 useEffect(()=>{let active=true;const load=()=>api('/signal-lab').then(d=>{if(active){setData(d);setError('')}}).catch(e=>{if(active)setError(e.message)});load();const timer=setInterval(()=>{if(document.visibilityState==='visible')load()},120000);return()=>{active=false;clearInterval(timer)}},[])
 return {data,error}
}
export function SignalTeaser({compact=false}){
 const {data,error}=useSignals()
 return <section className={'signal-teaser '+(compact?'signal-compact':'')} aria-label="Signal Lab preview"><div className="section-head"><div><span className="eyebrow">SIGNAL LAB · EARLY PREVIEW</span><h2>Compare the signals.</h2></div><a className="text-link" href="/signal-lab">Explore Signal Lab ↗</a></div>{!compact&&<p className="muted">Three test names, ordered by saved X activity.</p>}
 <div className="signal-cards">{data?.stocks.map((s,i)=><a className="signal-card" href={'/signal-lab?ticker='+s.ticker} key={s.ticker}><div className="signal-card-title"><span><strong>${s.ticker}</strong><small>{s.name}</small></span><span className="signal-rank">0{i+1}</span></div><SignalRadar axes={s.axes} compact={compact}/><span className="signal-card-foot">{s.stale?'Last saved view':'Latest saved view'}<span>Explore ↗</span></span></a>)}</div>
 {!data&&<p role="status">{error||'Loading Signal Lab…'}</p>}{data&&!data.stocks.length&&<p>First observations are being prepared.</p>}
 </section>
}
export function SignalLab({admin=false}){
 const {data,error}=useSignals(),[selected,setSelected]=useState(new URLSearchParams(location.search).get('ticker')||'')
 const stock=data?.stocks.find(s=>s.ticker===selected)||data?.stocks[0]
 return <section className="signal-page"><span className="eyebrow">SIGNAL LAB · 3-STOCK EARLY PREVIEW</span><h1>One stock. Five perspectives.</h1><p>Compare price strength, volume, options pressure, X activity and broker catalysts.</p>
 <div className="tabs">{data?.stocks.map(s=><button key={s.ticker} className={s===stock?'selected':''} onClick={()=>{setSelected(s.ticker);if(!admin)history.replaceState(history.state,'','/signal-lab?ticker='+s.ticker)}}>${s.ticker}</button>)}</div>
 {error&&<p role="alert">{error}</p>}{!stock&&!error&&<p role="status">Waiting for saved observations…</p>}
 {stock&&<><div className="section-head"><div><h2>{stock.name} <span className="muted">${stock.ticker}</span></h2><p className="muted">{stock.stale?'Last saved observation':'Observed'} · {dualTime(stock.observed)}</p></div></div><div className="signal-detail-grid"><div className="panel"><SignalRadar axes={stock.axes}/><p className="muted">Catalyst shows research significance; zero means no recent catalyst. Bullish or bearish direction is shown separately. Price and options show strength, with direction alongside. X activity measures attention. Dashed edges bridge unavailable indicators.</p></div><div className="signal-indicators">{stock.axes.map(a=><details className="panel" key={a.name}><summary><span>{a.name}<small>{a.state==='no_research'?'No recent research · no catalyst':a.direction|| (a.score==null?signalStatus(a):'Activity')}</small></span><strong>{a.score==null?'—':a.score+' / 100'}</strong></summary><p>{a.reason}</p>{a.as_of&&<p className="muted">Price comparison · {dualTime(a.as_of)}</p>}</details>)}</div></div></>}
 </section>
}

export function SignalAnnouncement(){
 const axes=['Price strength','Volume','Options pressure','X activity','Catalyst strength'].map((name,i)=>({name,strength:[78,62,71,88,54][i],score:[78,62,71,88,54][i]}))
 return <section className="signal-page" aria-label="Signal Lab announcement"><span className="tag">COMING OCTOBER 1</span><h1>Signal Lab</h1><h2>One stock. Five perspectives.</h2><p>Connect X activity, options pressure and broker research with price and volume—all in one clear view.</p><div className="signal-detail-grid"><div className="panel"><span className="eyebrow">A FIRST LOOK</span><h2>Compare the signals.</h2><SignalRadar axes={axes}/><small className="muted">Illustrative preview · Example values</small></div><div className="panel"><h2>See the bigger picture.</h2><p>Explore five indicators together, then open each one to understand what is driving it.</p><ul style={{lineHeight:2.2}}><li>Price strength and volume</li><li>Options pressure and direction</li><li>Conversation activity on X</li><li>Broker research and catalysts</li></ul><p className="muted">The full experience arrives October 1.</p><a className="button primary" href="/home">Explore Traders Echo ↗</a></div></div></section>
}
