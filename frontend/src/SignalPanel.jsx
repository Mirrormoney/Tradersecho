import React,{useState} from 'react'
import {dualTime} from './time.js'

const short=['Price','Volume','Options','X attention','Catalyst']
const fmt=v=>v==null?'—':`${v>0?'+':''}${v.toFixed(2)}%`
export function SignalPanel({panel,history=[],now,error}){
 const [selected,setSelected]=useState(0)
 if(!panel)return <section className="uw-signals"><h3>Five-indicator engine</h3><p>{error?'Evaluation needs attention; collection runs independently.':'Waiting for the next hosted collection to save the first calculation.'}</p></section>
 const stale=now-panel.observed>1200,axes=panel.axes,detail=axes[selected]
 const point=(i,value)=>{const a=-Math.PI/2+i*2*Math.PI/5;return [190+Math.cos(a)*105*value/100,155+Math.sin(a)*105*value/100]}
 const points=value=>axes.map((_,i)=>point(i,value).join(',')).join(' ')
 const full=axes.every(a=>a.strength!=null)
 return <section className="uw-signals"><div className="section-head"><div><span className="eyebrow">FIVE INDICATORS · {panel.version} · EXPERIMENTAL</span><h3>{stale?'Saved observation — waiting for fresh data':panel.setup}</h3><p>{panel.ready} / 5 indicators ready · {dualTime(panel.observed)}</p></div><span className="uw-status">Private evaluation</span></div>
 <div className="uw-signal-grid"><div><svg className="uw-radar" viewBox="0 0 380 310" role="img" aria-label={`Five indicator strengths. ${axes.map(a=>`${a.name}: ${a.score==null?'unavailable':`${a.score} out of 100${a.direction?', '+a.direction:''}`}`).join('. ')}`}>
 {[25,50,75,100].map(v=><polygon key={v} points={points(v)} fill="none" stroke="#a8c6ad" opacity=".18"/>)}
 {axes.map((a,i)=>{const p=point(i,100),label=point(i,128);return <g key={a.name}><line x1="190" y1="155" x2={p[0]} y2={p[1]} stroke="#a8c6ad" opacity=".2"/><text x={label[0]} y={label[1]} textAnchor="middle" fill="#d4e8d4" fontSize="11">{short[i]}</text></g>})}
 {full&&<polygon points={axes.map((a,i)=>point(i,a.strength).join(',')).join(' ')} fill="#c9ef83" fillOpacity=".15" stroke="#c9ef83" strokeWidth="2"/>}
 {axes.map((a,i)=>a.strength!=null&&<circle key={a.name} cx={point(i,a.strength)[0]} cy={point(i,a.strength)[1]} r="5" fill={a.direction==='bearish'?'#e0b890':'#c9ef83'}/>)}
 </svg><p className="muted">Distance shows strength. Price and options show bullish or bearish direction separately. X attention measures interest, not direction. A missing indicator leaves the shape open; it is never filled with a made-up neutral value.</p></div>
 <div className="uw-axis-list">{axes.map((a,i)=><button key={a.name} className={selected===i?'selected':''} onClick={()=>setSelected(i)} aria-pressed={selected===i}><span>{a.name}<small>{a.direction|| (i===3&&a.score!=null?`Activity · ${a.details.coverage}`:a.score!=null?'Participation / evidence':'Waiting for evidence')}</small></span><strong>{a.score==null?'—':a.score}<small>{a.score==null?'unavailable':'/ 100'}</small></strong></button>)}</div></div>
 <div className="uw-explanation"><span className="eyebrow">HOW THIS IS CALCULATED</span><h4>{detail.name}</h4><p>{detail.reason}</p>{detail.details.summary&&<blockquote>{detail.details.summary}<small>{detail.details.firm||'Published research'} · {detail.details.report_date} · {detail.details.stance}</small></blockquote>}<dl>{Object.entries(detail.details).filter(([k])=>!['summary','firm','report_date','stance','id'].includes(k)).map(([k,v])=><div key={k}><dt>{k.replaceAll('_',' ')}</dt><dd>{k==='window_end'?dualTime(v):v==null?'Unavailable':typeof v==='object'?JSON.stringify(v):String(v)}</dd></div>)}</dl></div>
 <details><summary>Forward results · latest saved checks</summary><p>Observed one-hour price change, not a backtest or a win probability. Cost examples subtract 10 basis points per round trip. Overlapping checks are not independent trades. Missing overnight outcomes are not filled in.</p><div className="table-scroll"><table><thead><tr><th>Observed</th><th>State</th><th>Price / volume only</th><th>1h return</th><th>Long after costs</th><th>Short after costs</th></tr></thead><tbody>{history.map(r=><tr key={r.observed}><td>{dualTime(r.observed)}</td><td>{r.setup}</td><td>{r.baseline}</td><td title={r.outcome?.reason}>{fmt(r.outcome?.return_1h)}</td><td>{fmt(r.outcome?.cost_adjusted_long)}</td><td>{fmt(r.outcome?.cost_adjusted_short)}</td></tr>)}</tbody></table></div></details>
 </section>
}
