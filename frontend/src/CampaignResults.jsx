import React, {useEffect, useState} from 'react'
import {api} from './api.js'
export function CampaignResults() {
 const [data,setData]=useState(null),[error,setError]=useState('')
 useEffect(()=>{api('/admin/campaign-results').then(setData).catch(e=>setError(e.message))},[])
 return <section className="panel"><h2>Campaign signups</h2><p>New accounts attributed to the latest eligible X ad link opened in the same browser tab. Email verification and Pro trial activation are checked against account records.</p>{error?<p role="alert">{error}</p>:!data?<p>Loading…</p>:<div className="table-scroll"><table><thead><tr><th>Campaign</th><th>Signups</th><th>Verified emails</th><th>Pro trials started</th></tr></thead><tbody>{data.campaigns.map(r=><tr key={r.campaign}><td>{r.name}</td><td>{r.signups}</td><td>{r.verified}</td><td>{r.trials}</td></tr>)}</tbody></table></div>}<p className="muted">First-party attribution, not X-reported conversions. No account data is sent to X. Privacy opt-outs, closed tabs, copied links and cross-device visits can affect attribution. Compare these counts with X spend and clicks; a tagged visit alone is not a signup.</p></section>
}
