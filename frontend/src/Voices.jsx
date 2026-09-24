import {dualTime} from './time.js'
import React,{useEffect,useState} from 'react'
import {api} from './api.js'

export function Voices({admin=false,premium=true,personalLimit=3,onChange,onPlans}){
 const [data,setData]=useState(null),[personal,setPersonal]=useState([]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState('')
 async function load(){
  if(admin)setData(await api('/admin/voices'))
  else {const [curated,mine]=await Promise.all([api('/voices/curated'),premium?api('/handles'):Promise.resolve([])]);setData({rows:curated});setPersonal(mine)}
 }
 useEffect(()=>{let active=true;(async()=>{try{if(admin){const d=await api('/admin/voices');if(active)setData(d)}else{const [a,b]=await Promise.all([api('/voices/curated'),premium?api('/handles'):Promise.resolve([])]);if(active){setData({rows:a});setPersonal(b)}}}catch(e){if(active)setError(e.message)}})();return()=>{active=false}},[admin,premium])
 async function change(fn,message){setBusy(true);setError('');try{const result=await fn();await load();onChange?.();setNotice(result?.message||message)}catch(e){setError(e.message)}finally{setBusy(false)}}
 const curated=admin?data?.rows.filter(r=>r.curated):data?.rows
 return <section className="panel">
  <div className="section-head"><h2>{admin?'Shared voice registry':'Your personal voices'}</h2><button className="button" disabled={busy} onClick={()=>change(async()=>{},'List refreshed.')}>Refresh voices</button></div>
  <p className="muted">{admin?'Manage the curated accounts shared with all signed-in members. There is no account-count limit on this admin list. The registry combines these with eligible members’ personal follows.':`Keep up to ${personalLimit} personal research accounts here. The shared account overview is in Data Sources.`} Each X account is collected once for everyone. Opening this page never buys more posts.</p>
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="positive" role="status">{notice}</p>}
  {!data&&<p>Loading voices…</p>}
  {admin&&curated?.map(h=><div className="handle" key={h.handle}><div><strong>@{h.handle}</strong><p>{h.note||'Admin-selected · shared with all members'}</p><small>{h.checked_at?'Last checked '+dualTime(h.checked_at)+' · ':''}{h.collection_message}{h.retry_at?' · Resets '+dualTime(h.retry_at):''}{h.truncated?' · Capped sample':''}</small></div>{admin&&<button className="button" disabled={busy} onClick={()=>change(()=>api('/admin/voices/'+h.handle,'DELETE'),'Removed from curated voices. Personal follows and collected posts are retained.')}>Remove curated @{h.handle}</button>}</div>)}
  {admin&&data&&!curated?.length&&<p className="muted">No curated accounts yet.</p>}
  {(admin||premium)&&<><div className="divider"/><h3>{admin?'Add or update a curated account':`Your personal voices · ${personal.length}/5`}</h3>

  <form className="handle-form" onSubmit={e=>{e.preventDefault();const form=e.currentTarget;const f=new FormData(form);change(async()=>{const result=await api(admin?'/admin/voices':'/handles','POST',{handle:f.get('handle'),note:f.get('note')});if(!result.already_curated)form.reset();return result},admin?'Curated voice saved. Shared collection will pick it up.':'Personal voice saved. Existing collected posts are shared automatically.')}}>
   <label>X handle<input name="handle" placeholder="@username" maxLength={16} required/></label><label>{admin?'Public research note':'Private research note'}<input name="note" maxLength={250}/></label><button className="button primary" disabled={busy}>Save {admin?'curated':'personal'} voice</button>
  </form>
  {!admin&&personal.map(h=><div className="handle" key={h.handle}><div><strong>@{h.handle}</strong><p>{h.note||'Private research note'}</p></div><button className="button" disabled={busy} onClick={()=>change(()=>api('/handles/'+h.handle,'DELETE'),'Personal follow removed.')}>Remove @{h.handle}</button></div>)}
</>}
  {!admin&&!premium&&<><p>Premium lets you add up to three personal voices.</p><button className="button primary" onClick={onPlans}>Explore Premium</button></>}
  {!admin&&premium&&<p className="muted">Five personal accounts maximum. Saving an existing handle updates its note without using another slot. Curated accounts already appear in your feed.</p>}
  {admin&&data&&<><div className="divider"/><h3>{data.unique_accounts} unique accounts in shared collection</h3><div className="table-scroll"><table><thead><tr><th>Account</th><th>Source</th><th>Personal followers</th><th>Last checked</th></tr></thead><tbody>{data.rows.map(h=><tr key={h.handle}><td>@{h.handle}</td><td>{h.curated?'Curated':'Member-added'}</td><td>{h.followers}</td><td>{h.checked_at?dualTime(h.checked_at):'Pending'}</td></tr>)}</tbody></table></div><p className="muted">Follower counts include active eligible accounts only. Personal notes remain private.</p></>}
  <p className="muted">Accounts have individual hourly checks, with admin voices prioritised. Admin checks collect up to 20 posts at a time and 120 posts per account per day, subject to the shared budget. Replies and reposts are excluded. Results are samples, not complete account histories.</p>
 </section>
}

export function MainVoices({refresh}){
 const [rows,setRows]=useState(null),[error,setError]=useState('')
 useEffect(()=>{let active=true;api('/voices/curated').then(r=>{if(active){setRows(r);setError('')}}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[refresh])
 return <section className="panel universe"><h2>Main X voices</h2><p className="muted">Admin-selected accounts shared with every signed-in member. Each account is collected once across the community; collection budgets and cooldowns apply.</p>{error&&<p className="error" role="alert">{error}</p>}{!rows&&!error&&<p role="status">Loading shared voices…</p>}{rows?.map(h=><div className="handle" key={h.handle}><div><a href={'https://x.com/'+h.handle} target="_blank" rel="noreferrer"><strong>@{h.handle} ↗</strong></a><p>{h.note||'Admin-selected research source'}</p><small>{h.checked_at?'Last checked '+dualTime(h.checked_at)+' · ':''}{h.collection_message}{h.retry_at?' · Next retry '+dualTime(h.retry_at):''}</small></div></div>)}{rows?.length===0&&<p>No shared voices configured yet.</p>}</section>
}
