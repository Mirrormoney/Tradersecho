import React,{useEffect,useLayoutEffect,useRef,useState} from 'react'
import {createPortal} from 'react-dom'
import {api} from './api.js'
import './welcome-tour.css'

const steps=[
 {menu:['market'],title:'Start with Market pulse.',text:'Find the AI stocks gaining attention on X. Open Market pulse to see how the first tile works.',next:'Open Market pulse →'},
 {page:'market',target:'.intraday-leader',title:'Meet the most active name.',text:'The 01 badge marks the leader in this timeframe. Mentions, their change and the activity chart show how attention developed. Click the tile after the tour to explore its posts, research and filings.'},
 {menu:['signal'],title:'Compare the signals in Signal Lab.',text:'Bring price, volume, options pressure, X activity and research catalysts together in one view.',next:'Open Signal Lab →'},
 {page:'signal',target:'.lab-leader, .signal-connected-preview .signal-card',title:'Five indicators, one stock.',text:'The pentagon shows the balance between five indicators. With Pro, open a stock to explore its drivers and history. Free and Premium accounts see a preview; eligible new users can explore full access with the 7-day Pro trial after verifying their email.'},
 {menu:['supply'],title:'Next: the AI Supply Chain.',text:'Explore the sectors powering AI, from chips and memory to infrastructure and power.',next:'Open AI Supply Chain →'},
 {page:'supply',target:'.supply-cell',title:'A sector at a glance.',text:'Each tile groups companies in one part of the AI economy. Attention metrics are included with every account. Below are the top three per sector; selecting a tile opens the full sector ranking.'},
 {menu:['insights'],title:'Understand what comes next.',text:'AI Insights connects AI technologies with changing expectations, upcoming milestones and potential beneficiaries.',next:'Open AI Insights →'},
 {page:'insights',target:'.insight-topic-tile, [data-tour-insight-preview]',title:'Explore a technology and its roadmap.',text:'Choose a theme such as HBM, optical networking or 800 VDC. Pro opens the topic explanation, research-driven timeline and potential beneficiaries. Expectations and rumours are distinguished from confirmed developments; other plans can browse the introduction.'},
 {menu:['research'],title:'Then: Trending Research.',text:'Find concise research linked to the stocks we cover. Let’s look at a featured note.',next:'Open Trending Research →'},
 {page:'research',target:'.research-featured-card',title:'The newest research, easy to scan.',text:'Each tile shows a stock, its summary and the note’s publication date. Expand it for detail or open the stock and its TradingView chart. The list below is ordered by research freshness. Premium unlocks the full selection.'},
 {menu:['voices','community','filings'],title:'And much more to explore.',text:'Follow collected X takes in Tracked voices, exchange ideas in the Trading room, and check original company disclosures in SEC Filings.',next:'Finish tour →'}
]
export function WelcomeTour({user,ready,modal,replay,navigate}){
 const [step,setStep]=useState(null),[visibleStep,setVisibleStep]=useState(null),[checked,setChecked]=useState(false),[rect,setRect]=useState(null),[position,setPosition]=useState({left:16,top:100}),[missing,setMissing]=useState(false)
 const nav=useRef(navigate),dialog=useRef(null),lastReplay=useRef(replay),finished=useRef(false)
 nav.current=navigate
 useEffect(()=>{let active=true;setStep(null);setChecked(false);finished.current=false;if(!user?.id||user.demo)return;api('/welcome-tour').then(r=>{if(active)setChecked(!r.completed)}).catch(()=>{});return()=>{active=false}},[user?.id,user?.demo])
 useEffect(()=>{if(checked&&ready&&!modal&&!finished.current){setStep(0);setChecked(false)}},[checked,ready,modal])
 useEffect(()=>{if(replay!==lastReplay.current){lastReplay.current=replay;if(user){finished.current=false;setStep(0)}}},[replay,user])
 function close(){finished.current=true;setChecked(false);setStep(null);api('/welcome-tour','PUT',{}).catch(()=>{})}
 useEffect(()=>{if(step==null)return;const s=steps[step];if(s.page)nav.current(s.page)},[step])
 useEffect(()=>{
  if(step==null)return
  const previous=document.activeElement,app=document.querySelector('.app'),oldInert=app?.inert
  if(app)app.inert=true
  dialog.current?.querySelector('button')?.focus()
  function key(e){if(e.key==='Escape'){e.preventDefault();close()}if(e.key==='Tab'){const buttons=[...dialog.current.querySelectorAll('button:not(:disabled)')];const first=buttons[0],last=buttons.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}}}
  document.addEventListener('keydown',key)
  return()=>{if(app)app.inert=oldInert;document.removeEventListener('keydown',key);previous?.focus?.()}
 },[step!=null])
 useLayoutEffect(()=>{
  setVisibleStep(null)
  if(step==null)return
  const s=steps[step];document.body.classList.toggle('welcome-menu-open',!!s.menu)
  let scrolled=false,raf,revealTimer,allowFallback=false
  const fallbackTimer=setTimeout(()=>{allowFallback=true;measure()},8000)
  const measure=()=>{cancelAnimationFrame(raf);raf=requestAnimationFrame(()=>{
   const selectors=s.menu?s.menu.map(k=>`[data-tour-nav="${k}"]`):[s.target]
   const elements=selectors.map(sel=>document.querySelector(sel)).filter(el=>el&&el.getClientRects().length)
   if(elements.length&&!scrolled){elements[0].scrollIntoView({block:'nearest',behavior:'instant'});scrolled=true}
   const boxes=elements.map(el=>el.getBoundingClientRect()),w=window.innerWidth,h=window.innerHeight
   const r=boxes.length?{left:Math.max(4,Math.min(...boxes.map(b=>b.left))-5),top:Math.max(4,Math.min(...boxes.map(b=>b.top))-5),right:Math.min(w-4,Math.max(...boxes.map(b=>b.right))+5),bottom:Math.min(h-4,Math.max(...boxes.map(b=>b.bottom))+5)}:null
   setRect(r);setMissing(!r&&!s.menu)
   const dw=Math.min(380,w-24,r?Math.max(280,w-r.right-28):380),dh=dialog.current?.offsetHeight||260
   let left=r&&r.right+dw+24<w?r.right+16:Math.max(12,Math.min(r?.left||24,w-dw-12))
   let top=r&&r.right+dw+24<w?r.top: r?r.bottom+18:80
   if(top+dh>h-12)top=r&&!s.menu&&r.top>dh+24?r.top-dh-18:Math.max(12,h-dh-12)
   setPosition({left,top,width:dw})
   clearTimeout(revealTimer)
   if(r||allowFallback)revealTimer=setTimeout(()=>setVisibleStep(step),120)
  })}
  measure();const sizeObserver=new ResizeObserver(measure);if(dialog.current)sizeObserver.observe(dialog.current);const observer=new MutationObserver(measure);const app=document.querySelector('.app');if(app)observer.observe(app,{childList:true,subtree:true});window.addEventListener('resize',measure);window.addEventListener('scroll',measure,true)
  return()=>{clearTimeout(fallbackTimer);clearTimeout(revealTimer);cancelAnimationFrame(raf);sizeObserver.disconnect();observer.disconnect();window.removeEventListener('resize',measure);window.removeEventListener('scroll',measure,true);document.body.classList.remove('welcome-menu-open')}
 },[step])
 useEffect(()=>{if(step!=null&&visibleStep===step)dialog.current?.querySelector('button')?.focus()},[step,visibleStep])
 if(step==null||!user)return null
 const s=steps[step],w=window.innerWidth,h=window.innerHeight
 const shown=visibleStep===step
 const panels=shown&&rect?[{left:0,top:0,width:w,height:rect.top},{left:0,top:rect.bottom,width:w,height:Math.max(0,h-rect.bottom)},{left:0,top:rect.top,width:rect.left,height:Math.max(0,rect.bottom-rect.top)},{left:rect.right,top:rect.top,width:Math.max(0,w-rect.right),height:Math.max(0,rect.bottom-rect.top)}]:[{inset:0}]
 return createPortal(<div className="welcome-tour-layer">{panels.map((p,i)=><div key={i} className="welcome-tour-shade" style={p}/>)}{shown&&rect&&<div className="welcome-tour-ring" style={{left:rect.left,top:rect.top,width:rect.right-rect.left,height:rect.bottom-rect.top}}/>}<section ref={dialog} className="welcome-tour-card" style={{...position,visibility:shown?'visible':'hidden'}} role="dialog" aria-modal="true" aria-labelledby="welcome-tour-title"><small>STEP {step+1} OF {steps.length}</small><h2 id="welcome-tour-title">{s.title}</h2><p>{s.text}</p>{missing&&<p className="welcome-tour-wait">The first tile will be highlighted when it is available.</p>}<div className="welcome-tour-progress" aria-hidden="true"><i style={{width:(step+1)/steps.length*100+'%'}}/></div><footer><button onClick={close}>Skip tour</button><button disabled={step===0} onClick={()=>setStep(n=>n-1)}>Back</button><button className="welcome-tour-next" onClick={()=>step===steps.length-1?close():setStep(n=>n+1)}>{s.next||'Next →'}</button></footer></section></div>,document.body)
}
