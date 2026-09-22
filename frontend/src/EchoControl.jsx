import React,{useEffect,useState} from 'react'
import {api} from './api.js'
export function EchoControl({user}){
 const [state,setState]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('')
 const admin=['owner','admin'].includes(user?.role)
 useEffect(()=>{if(admin)api('/admin/echo-assistant').then(setState).catch(e=>setError(e.message))},[admin])
 return <section className="echo-control"><h3>Echo Assistant <span className="tag">Automated</span></h3><p className="muted">Occasional conversation starters from saved X activity and SEC filings. No invented opinions or automatic replies. It pauses while members are chatting.</p>{admin&&<><button className="button" disabled={!state||busy} onClick={async()=>{setBusy(true);setError('');try{setState(await api('/admin/echo-assistant','PUT',{enabled:!state.enabled}))}catch(e){setError(e.message)}finally{setBusy(false)}}}>{!state?'Loading…':state.enabled?'Pause Echo Assistant':'Enable Echo Assistant'}</button>{error&&<p role="alert">{error}</p>}</>}</section>
}
