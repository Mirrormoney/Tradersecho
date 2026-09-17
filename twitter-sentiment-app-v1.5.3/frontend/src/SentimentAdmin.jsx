import React,{useEffect,useState} from 'react'
import {api} from './api.js'
export function SentimentAdmin(){
 const [data,setData]=useState(null),[error,setError]=useState('')
 useEffect(()=>{let active=true;api('/admin/sentiment').then(d=>{if(active)setData(d)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[])
 return <section className="panel"><h2>Contextual sentiment</h2>{error?<p className="error">{error}</p>:!data?<p>Loading analysis status…</p>:<><p>{data.enabled?'Automatic analysis enabled':'Analysis paused'} · {data.model}</p><p className="muted">Shared results, analyzed once per post version. No AI requests are made when members open a page. The monthly allowance is separate from X collection.</p><p>${data.spent.toFixed(3)} / ${data.budget.toFixed(2)} this month</p><p>{data.done} analyzed · {data.pending} awaiting analysis · {data.errors} delayed · {data.unsupported} outside size limits</p>{data.last_run&&<p className="muted">Last run: {new Date(data.last_run.at*1000).toLocaleString()} · {data.last_run.state}</p>}</>}</section>
}
