import React,{useState} from 'react'
import {api} from './api.js'
import './pricing.css'

const features=[
 ['Stock rankings','Top 5','Full rankings'],
 ['Day, week & month views','Included','Included'],
 ['Saved stocks','5 stocks','50 stocks'],
 ['Shared tracked voices','Included','Included'],
 ['Personal tracked voices','Not included','Up to 5 accounts'],
 ['Daily web briefing','Top 3 stocks','Top 10 + your watchlist'],
 ['Trading room','Not included','Included'],
 ['Ticker refresh requests','Not included','Up to 5 per day'],
]
export function Pricing({user,status,onSignup,onAccount}){
 const [annual,setAnnual]=useState(true),[busy,setBusy]=useState(''),[error,setError]=useState('')
 const premium=user?.plan==='premium'||['admin','owner'].includes(user?.role)
 async function choose(tier){
  if(!user||user.demo){onSignup();return}
  setBusy(tier);setError('')
  try{const result=await api('/billing/checkout','POST',{tier});location.assign(result.url)}catch(e){setError(e.message)}finally{setBusy('')}
 }
 return <div className="pricing-content">
  {status?.billing_sandbox&&<div className="payment-sandbox-banner"><strong>Test checkout only.</strong> Use Stripe test card 4242 4242 4242 4242, any future expiry and any three-digit CVC. Do not enter a real card. Test purchases affect only this sandbox account.</div>}<p className="pricing-intro">Start with the pulse. Build your own research edge.</p>
  <div className="pricing-switch" role="group" aria-label="Premium billing interval">
   <button aria-pressed={!annual} onClick={()=>setAnnual(false)}>Monthly</button>
   <button aria-pressed={annual} onClick={()=>setAnnual(true)}>Yearly <span>2 months free</span></button>
  </div>
  <div className="pricing-grid">
   {['free','premium','founder'].map(tier=>{
    const paid=tier!=='free',founder=tier==='founder',selected=tier==='free'?!premium:founder?user?.billing_tier==='founder':premium&&user?.billing_tier!=='founder'
    const choice=founder?'founder':annual?'yearly':'monthly'
    const available=Boolean(status?.billing_options?.[choice])
    return <section key={tier} className={'pricing-card '+tier} aria-label={tier+' plan'}>
     <div className="pricing-card-top"><span className="eyebrow">{tier}</span>{tier==='premium'&&<span className="pricing-recommended">Best for active research</span>}</div>
     <h3>{founder?'In it for the long run.':paid?'Go beyond the headline.':'Get a feel for the market.'}</h3>
     <div className="pricing-amount">{founder?'$999':paid?annual?'$190':'$19':'$0'}<small>{founder?'one-time':paid?(annual?'/ year':'/ month'):'forever'}</small></div>
     <p className="pricing-description">{founder?'Premium access for the operating lifetime of Tradersecho.':paid?annual?'$15.83/month equivalent. Billed $190 yearly; save $38.':'Billed $19 monthly. Cancel renewal anytime.':'A useful daily snapshot. No card required.'}</p>
     <button className={'button full '+(paid?'primary':'')} disabled={Boolean(busy)||(paid&&(premium||!available))} onClick={()=>paid?choose(choice):user?onAccount():onSignup()}>
      {busy===choice?'Opening secure checkout…':selected&&user?'Your current plan':paid?premium?'Premium access included':available?founder?'Become a Founder':'Get Premium':'Payments opening soon':user?'Manage account':'Create free account'}
     </button>
     <ul className="pricing-features">{features.map(([label,free,full])=><li key={label} className={!paid&&free==='Not included'?'excluded':''}><span aria-hidden="true">{!paid&&free==='Not included'?'−':'✓'}</span><div>{label}<strong>{paid?full:free}</strong></div></li>)}</ul>
     <p className="pricing-card-note">{founder?'One payment. No renewal. Same usage limits as Premium; not unlimited X API usage.':paid?'Renews automatically until cancelled. Collected data is shared; requests remain subject to the platform budget.':'Upgrade whenever you want a closer look.'}</p>
    </section>
   })}
  </div>
  {error&&<p className="error" role="alert">{error}</p>}
  <div className="pricing-footnotes"><p>All prices in USD. Applicable taxes will be shown before payment. Founder access lasts while Tradersecho is operated as an active service; it is not a guarantee of perpetual operation.</p><p>Coverage depends on available X data. Paid membership does not guarantee complete coverage, investment returns or instant collection. Email delivery will be announced separately.</p>{!status?.billing_configured&&<p>Plans are available to compare during our private preview. Checkout opens after payment setup and testing.</p>}</div>
 </div>
}
