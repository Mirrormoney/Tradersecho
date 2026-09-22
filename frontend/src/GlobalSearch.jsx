import './GlobalSearch.css'
import React,{useEffect,useRef,useState} from 'react'
import {api} from './api.js'
export default function GlobalSearch({user,onSelect,onLogin}){
 const [query,setQuery]=useState(''),[open,setOpen]=useState(false),[data,setData]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(false)
 const root=useRef(null)
 useEffect(()=>{let active=true;setData(null);setError('');setLoading(query.trim().length>=1)
  const timer=setTimeout(()=>{if(query.trim().length<1)return;api('/search?q='+encodeURIComponent(query.trim())).then(d=>{if(active)setData(d)}).catch(e=>{if(active)setError(e.message)}).finally(()=>{if(active)setLoading(false)})},300)
  return()=>{active=false;clearTimeout(timer)}
 },[query,user?.id])
 useEffect(()=>{function close(e){if(!root.current?.contains(e.target))setOpen(false)}document.addEventListener('pointerdown',close);return()=>document.removeEventListener('pointerdown',close)},[])
 return <div className="global-search" ref={root} onKeyDown={e=>{if(e.key==='Escape')setOpen(false)}}>
  <label className="global-search-field"><span aria-hidden="true">⌕</span><input aria-label="Search stocks, SEC filings and research" placeholder="Search stocks, filings, research…" value={query} onFocus={()=>setOpen(true)} onChange={e=>{setQuery(e.target.value);setOpen(true)}} aria-expanded={open} aria-controls="global-search-results"/></label>
  {open&&<section id="global-search-results" className="global-search-results" aria-label="Search results">
   {query.trim().length<1?<p>Search a ticker or company. Use 2+ characters for filing types and research topics.</p>:loading?<p role="status">Searching saved data…</p>:error?<p role="alert">{error}</p>:<>
    {!data?.results.length&&<p>No matching results in our covered universe.</p>}
    {['stock','filing','take','research'].map(kind=>{const rows=data?.results.filter(r=>r.kind===kind)||[];return rows.length>0&&<div key={kind}><h3>{{stock:'Stocks',filing:'SEC filings',take:'Collected X takes',research:'Private research · admins only'}[kind]}</h3>{rows.map((r,i)=><article key={kind+r.ticker+i}><button onClick={()=>{setOpen(false);onSelect(r)}}><strong>${r.ticker} · {r.title}</strong><span>{r.text}</span></button>{r.url&&<a href={r.url} target="_blank" rel="noreferrer">Open original ↗</a>}</article>)}</div>})}
    {data?.sign_in&&<button className="button" onClick={()=>{setOpen(false);onLogin()}}>Log in to search filings and collected research</button>}
   </>}
   <small>SEC search covers saved filing titles, forms and companies—not full document text.</small>
  </section>}
 </div>
}
