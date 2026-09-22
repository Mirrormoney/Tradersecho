import React,{useState} from 'react'
import {api} from './api.js'

export function PasswordSettings({user}){
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('')
 async function submit(e){
  e.preventDefault();const form=e.currentTarget,data=new FormData(form)
  setError('');setNotice('')
  if(data.get('new_password')!==data.get('confirm_password')){setError('Your new passwords do not match.');return}
  setBusy(true)
  try{
   await api('/auth/change-password','POST',{current_password:data.get('current_password'),new_password:data.get('new_password')})
   form.reset();setNotice('Password changed. You are still signed in here; all other sessions have been signed out.')
  }catch(e){setError(e.message)}finally{setBusy(false)}
 }
 return <section className="panel"><span className="eyebrow">ACCOUNT SECURITY</span><h2>Change password</h2><p className="muted">Choose a new password for this account. Updating it signs out your other devices.</p>{user.demo?<p className="muted">Sample accounts do not have passwords. Create your own account to use this feature.</p>:<form onSubmit={submit}>
  <input type="text" name="username" autoComplete="username" value={user.email} readOnly hidden/>
  <label>Current password<input name="current_password" type="password" autoComplete="current-password" maxLength={128} required disabled={busy}/></label>
  <label>New password<input name="new_password" type="password" autoComplete="new-password" minLength={10} maxLength={128} required disabled={busy} aria-describedby="password-help"/></label>
  <small id="password-help" className="muted">Use 10–128 characters. A unique passphrase works well.</small>
  <label>Confirm new password<input name="confirm_password" type="password" autoComplete="new-password" minLength={10} maxLength={128} required disabled={busy}/></label>
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="positive" role="status">{notice}</p>}
  <button className="button primary" disabled={busy}>{busy?'Updating password…':'Update password'}</button>
 </form>}</section>
}
