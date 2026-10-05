import React from 'react'

const themes={
 '800-vdc':{title:'800 VDC',tag:'POWER ARCHITECTURE',color:'#d7ed76',bg:'#30452c',copy:'Higher voltage. A different blueprint for the AI datacenter.'},
 hbm:{title:'HBM & advanced memory',tag:'FEEDING THE ACCELERATOR',color:'#c5a2ff',bg:'#342650',copy:'The stacked memory behind the next leap in AI performance.'},
 'advanced-packaging':{title:'Advanced packaging',tag:'CONNECTING THE CHIPS',color:'#f5bd80',bg:'#4a3328',copy:'Where compute, memory and interconnect become one system.'},
 'optical-networking':{title:'Optical networking',tag:'DATA AT THE SPEED OF LIGHT',color:'#84dafa',bg:'#173e53',copy:'Follow the move from electrical connections to silicon photonics.'},
 'liquid-cooling':{title:'Liquid cooling',tag:'TAMING THE HEAT',color:'#75e6ca',bg:'#17483f',copy:'Dense AI racks need a new way to keep their cool.'},
 'ai-power':{title:'AI power availability',tag:'THE RACE TO ENERGIZE',color:'#efcd76',bg:'#4b4224',copy:'Grid connections, generation and the path to operating capacity.'},
 'ai-inference':{title:'AI inference & custom chips',tag:'FROM MODELS TO ANSWERS',color:'#f5a8c4',bg:'#4b2940',copy:'The hardware race to deliver more intelligence per watt.'},
}

export function InsightArtwork({slug}){
 const chip=(x,y,w=60,h=42)=><g><rect x={x} y={y} width={w} height={h} rx="5" fill="currentColor" fillOpacity=".12" stroke="currentColor"/>{[0,1,2,3].map(i=><path key={i} d={`M${x+10+i*12} ${y-8}v8 M${x+10+i*12} ${y+h}v8`} stroke="currentColor"/>)}</g>
 return <svg viewBox="0 0 420 190" aria-hidden="true" className="insight-art"><path d="M0 158H420 M0 130H420 M0 102H420 M50 0V190 M130 0V190 M210 0V190 M290 0V190 M370 0V190" stroke="currentColor" opacity=".07"/><ellipse cx="215" cy="153" rx="130" ry="18" fill="currentColor" opacity=".06"/>
 {slug==='800-vdc'&&<g stroke="currentColor" fill="none"><rect x="68" y="40" width="75" height="114" rx="8"/><rect x="278" y="40" width="75" height="114" rx="8"/>{[62,86,110,134].map(y=><path key={y} d={`M82 ${y}h45 M292 ${y}h45`} opacity=".5"/>)}<path d="M143 98h35m66 0h34" strokeWidth="3"/><path d="M218 38l-35 63h29l-9 53 38-70h-29z" fill="currentColor" fillOpacity=".3" strokeWidth="2"/></g>}
 {slug==='hbm'&&<g stroke="currentColor">{[0,1,2,3,4].map(i=><g key={i} transform={`translate(0,${-i*17})`}><path d="M120 132l90-38 90 38-90 38z" fill="#191827"/><path d="M120 132v11l90 38 90-38v-11l-90 38z" fill="currentColor" fillOpacity=".2"/></g>)}<path d="M173 47l37-16 37 16-37 16z" fill="currentColor" fillOpacity=".65"/></g>}
 {slug==='advanced-packaging'&&<g><path d="M65 120l145-68 145 68-145 60z" fill="currentColor" fillOpacity=".1" stroke="currentColor"/>{chip(136,65)}{chip(225,85,48,35)}<path d="M196 88h17v14h12 M165 107v26h80v-13" stroke="currentColor" fill="none" strokeWidth="2"/>{[95,115,305,325].map(x=><circle key={x} cx={x} cy="123" r="3" fill="currentColor"/>)}</g>}
 {slug==='optical-networking'&&<g fill="none" stroke="currentColor">{[-34,-17,0,17,34].map((v,i)=><g key={v}><path d={`M35 ${95+v}C120 ${95+v} 120 95 205 95S300 ${95+v} 385 ${95+v}`} strokeWidth={i===2?3:1.5} opacity={.4+i*.12}/><circle cx={90+i*57} cy={95+v/2} r="4" fill="currentColor"/></g>)}<rect x="180" y="68" width="60" height="54" rx="9" fill="#142733"/><path d="M195 95h30 M210 80v30" strokeWidth="2"/></g>}
 {slug==='liquid-cooling'&&<g fill="none" stroke="currentColor"><path d="M125 48H80v96h100v-30h60v30h100V48h-45" strokeWidth="8" opacity=".3"/>{chip(180,70)}<path d="M210 23c-14 19-22 28-22 38a22 22 0 0044 0c0-10-8-19-22-38z" fill="currentColor" fillOpacity=".3"/><path d="M82 75v30m0 0-7-9m7 9 7-9 M339 113V83m0 0-7 9m7-9 7 9" strokeWidth="2"/></g>}
 {slug==='ai-power'&&<g fill="none" stroke="currentColor"><path d="M88 155l36-120 36 120 M105 100h38 M112 75h25 M80 60h88 M72 87h104 M104 105l39 24m-48 0 39-24" strokeWidth="2"/><path d="M168 60c48 35 65 36 119 8 M176 87c41 26 68 25 111 9" opacity=".7"/><rect x="279" y="70" width="76" height="85" rx="5"/>{[90,110,130].map(y=><path key={y} d={`M292 ${y}h49`}/>)}<path d="M233 90l-23 33h20l-9 30 30-43h-23z" fill="currentColor" stroke="none"/></g>}
 {slug==='ai-inference'&&<g stroke="currentColor" fill="none">{chip(180,70)}{[[85,45],[75,140],[335,42],[345,142]].map(([x,y],i)=><g key={x}><path d={`M${x} ${y}L${i<2?180:240} 91`} opacity=".5"/><circle cx={x} cy={y} r="16" fill="currentColor" fillOpacity=".1"/><circle cx={x} cy={y} r="4" fill="currentColor"/></g>)}<path d="M196 98l10-18 10 18 9-14" strokeWidth="2"/><path d="M260 155h53m-8-6 8 6-8 6" strokeWidth="2"/></g>}
 </svg>
}

export function InsightGallery({topics,onSelect}){
 return <section className="insights-admin"><div className="insight-gallery-header"><span className="eyebrow">AI INSIGHTS</span><h2>Understand what comes next.</h2><p>Explore the technologies reshaping AI. Follow the milestones, the changing expectations and the companies behind them.</p></div><div className="insight-gallery">{topics.map((topic,i)=>{const theme=themes[topic.slug];return <button type="button" className="insight-topic-tile" key={topic.slug} style={{'--topic-accent':theme.color,'--topic-bg':theme.bg}} onClick={()=>onSelect(topic.slug)}><div className="insight-topic-visual"><span className="insight-topic-number">0{i+1}</span><InsightArtwork slug={topic.slug}/></div><div className="insight-topic-copy"><span className="eyebrow">{theme.tag}</span><h3>{theme.title}</h3><p>{theme.copy}</p><span className="insight-topic-cta">Explore the theme <span aria-hidden="true">↗</span></span></div></button>})}</div></section>
}
