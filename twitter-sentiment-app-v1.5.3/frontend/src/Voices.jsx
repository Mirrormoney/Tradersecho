import React,{useEffect,useState} from 'react'
import {api} from './api.js'

export function Voices({admin=false,onChange}){
 const [data,setData]=useState(null),[personal,setPersonal]=useState([]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState('')
 async function load(){
  if(admin)setData(await api('/admin/voices'))
  else {const [curated,mine]=await Promise.all([api('/voices/curated'),api('/handles')]);setData({rows:curated});setPersonal(mine)}
 }
 useEffect(()=>{let active=true;(async()=>{try{if(admin){const d=await api('/admin/voices');if(active)setData(d)}else{const [a,b]=await Promise.all([api('/voices/curated'),api('/handles')]);if(active){setData({rows:a});setPersonal(b)}}}catch(e){if(active)setError(e.message)}})();return()=>{active=false}},[admin])
 async function change(fn,message){setBusy(true);setError('');try{await fn();await load();onChange?.();setNotice(message)}catch(e){setError(e.message)}finally{setBusy(false)}}
 const curated=admin?data?.rows.filter(r=>r.curated):data?.rows
 return <section className="panel">
  <div className="section-head"><h2>{admin?'Shared voice registry':'Tradersecho voices'}</h2><button className="button" disabled={busy} onClick={()=>change(async()=>{},'List refreshed.')}>Refresh voices</button></div>
  <p className="muted">{admin?'Manage the curated accounts shared with Premium members. The registry combines these with eligible members’ personal follows.':'The admin-curated list is included with Premium, in addition to your five personal accounts.'} Each X account is collected once for everyone. Opening this page never buys more posts.</p>
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="positive" role="status">{notice}</p>}
  {!data&&<p>Loading voices…</p>}
  {curated?.map(h=><div className="handle" key={h.handle}><div><strong>@{h.handle}</strong><p>{h.note||'Curated research source'}</p><small>{h.checked_at?'Last checked '+new Date(h.checked_at*1000).toLocaleString():'Waiting for a shared check'}{h.truncated?' · Capped sample':''}</small></div>{admin&&<button className="button" disabled={busy} onClick={()=>change(()=>api('/admin/voices/'+h.handle,'DELETE'),'Removed from curated voices. Personal follows and collected posts are retained.')}>Remove curated @{h.handle}</button>}</div>)}
  {data&&!curated?.length&&<p className="muted">No curated accounts yet.</p>}
  <div className="divider"/><h3>{admin?'Add or update a curated account':`Your personal voices · ${personal.length}/5`}</h3>
  {!admin&&personal.map(h=><div className="handle" key={h.handle}><div><strong>@{h.handle}</strong><p>{h.note||'Private research note'}</p></div><button className="button" disabled={busy} onClick={()=>change(()=>api('/handles/'+h.handle,'DELETE'),'Personal follow removed.')}>Remove @{h.handle}</button></div>)}
  <form className="handle-form" onSubmit={e=>{e.preventDefault();const form=e.currentTarget;const f=new FormData(form);change(async()=>{await api(admin?'/admin/voices':'/handles','POST',{handle:f.get('handle'),note:f.get('note')});form.reset()},admin?'Curated voice saved. Shared collection will pick it up.':'Personal voice saved. Existing collected posts are shared automatically.')}}>
   <label>X handle<input name="handle" placeholder="@username" maxLength={16} required/></label><label>{admin?'Public research note':'Private research note'}<input name="note" maxLength={250}/></label><button className="button primary" disabled={busy}>Save {admin?'curated':'personal'} voice</button>
  </form>
  {!admin&&<p className="muted">Five personal accounts maximum. Saving an existing handle updates its note without using another slot. Curated accounts already appear in your feed.</p>}
  {admin&&data&&<><div className="divider"/><h3>{data.unique_accounts} unique accounts in shared collection</h3><div className="table-scroll"><table><thead><tr><th>Account</th><th>Source</th><th>Personal followers</th><th>Last checked</th></tr></thead><tbody>{data.rows.map(h=><tr key={h.handle}><td>@{h.handle}</td><td>{h.curated?'Curated':'Member-added'}</td><td>{h.followers}</td><td>{h.checked_at?new Date(h.checked_at*1000).toLocaleString():'Pending'}</td></tr>)}</tbody></table></div><p className="muted">Follower counts include active eligible accounts only. Personal notes remain private.</p></>}
  <p className="muted">Checks rotate through groups of up to five accounts under the shared daily budget. Larger lists take longer to refresh. Results are capped samples, not complete account histories.</p>
 </section>
}
