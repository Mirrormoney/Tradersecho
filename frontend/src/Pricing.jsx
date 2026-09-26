import React,{useState} from 'react'
import {api} from './api.js'
import './pricing.css'
import {ApiAddon} from './ApiAddon.jsx'

const featureOrder=value=>value==='Not included'?2:/preview/i.test(value)?1:0
const features=[
 ['Signal Lab','Preview only','Top-three tiles only','Full screening & indicator history'],
 ['AI Insights','Topic introductions','Topic previews','Full timelines & beneficiaries'],
 ['Stock rankings','Top 5','Top 20 per timeframe'],
 ['Day, week & month views','Included','Included'],
 ['Saved stocks','5 stocks','25 stocks','50 stocks'],
 ['Shared tracked voices','Included','Included'],
 ['Personal tracked voices','Up to 3 accounts','Up to 3 accounts','Up to 5 accounts'],
 ['AI Supply Chain','Sector preview only','Full heatmap & sector rankings'],
 ['Trending Research','Preview only','Full broker research summaries'],
 ['Scheduled research emails','Not included','Four opt-in editions'],
 ['Trading room','Included','Included'],
 ['Ticker refresh requests','Not included','Up to 3 per day','Up to 5 per day'],
]
export function Pricing({user,status,onSignup,onAccount}){
 const [annual,setAnnual]=useState(false),[busy,setBusy]=useState(''),[error,setError]=useState(''),[checks,setChecks]=useState([])
 const premium=(['premium','pro'].includes(user?.plan)&&!user?.trial_active)||['admin','owner'].includes(user?.role)
 async function choose(tier){
  if(!user||user.demo){onSignup();return}
  setBusy(tier);setError('')
  try{const result=await api('/billing/checkout','POST',{tier});location.assign(result.url)}catch(e){setError(e.message)}finally{setBusy('')}
 }
 if(status?.free_launch)return <div className="pricing-content"><span className="eyebrow">FREE EARLY ACCESS</span><h2>Explore the full conversation.</h2><p>No payment or card required during our free launch.</p><ul><li>Full stock attention rankings across the tracked universe</li><li>Daily, weekly and growing monthly history</li><li>Five saved stocks and shared curated voices</li><li>Daily web briefing</li></ul><p className="muted">Personal voices and the trading room are planned membership extras. Email newsletters are not yet included. We’ll announce any future paid plans separately; no automatic charges.</p><button className="button primary" onClick={user?onAccount:onSignup}>{user?'My account':'Create a free account'}</button></div>
 return <div className="pricing-content">
  {status?.billing_sandbox&&<div className="payment-sandbox-banner"><strong>Test checkout only.</strong> Use Stripe test card 4242 4242 4242 4242, any future expiry and any three-digit CVC. Do not enter a real card. Test purchases affect only this sandbox account.</div>}<p className="pricing-intro">Start with 7 days of Premium, free. No card. No automatic charges.</p>
  {!premium&&!user?.trial_active&&!user?.trial_started_at&&<div className="trial-notice"><div><strong>Try the full picture before choosing.</strong><p>Create your account and verify your email to start a one-time seven-day trial. Normal Premium limits apply. You return to Free automatically.</p></div><button className="button primary" onClick={user?onAccount:onSignup}>{user?'Start from My account':'Create account & try Premium'}</button></div>}<div className="pricing-switch" role="group" aria-label="Premium billing interval">
   <button aria-pressed={!annual} onClick={()=>setAnnual(false)}>Monthly</button>
   <button aria-pressed={annual} onClick={()=>setAnnual(true)}>Yearly <span>Save with annual billing</span></button>
  </div>
  <div className="pricing-grid">
   {['free','premium','pro','founder'].map(tier=>{
    const paid=tier!=='free',founder=tier==='founder',pro=tier==='pro',full=founder||pro
    const current=user?.billing_tier==='founder'?'founder':user?.pro_access?'pro':premium?'premium':'free'
    const selected=tier===current
    const visibleFeatures=paid?features:[...features].sort((a,b)=>featureOrder(a[1])-featureOrder(b[1]))
    const choice=founder?'founder':(pro?'pro_':'')+(annual?'yearly':'monthly')
    const available=Boolean(status?.billing_options?.[choice])
    return <section key={tier} className={'pricing-card '+tier} aria-label={tier+' plan'}>
     <div className="pricing-card-top"><span className="eyebrow">{tier}</span>{pro&&<span className="pricing-recommended">Full research toolkit</span>}</div>
     <h3>{founder?'In it for the long run.':pro?'Connect the full picture.':paid?'Go beyond the headline.':'Get a feel for the market.'}</h3>
     <div className="pricing-amount">{founder?'$499':pro?annual?'$190':'$19':paid?annual?'$99':'$9':'$0'}<small>{founder?'one-time':paid?(annual?'/ year':'/ month'):'forever'}</small></div>
     <p className="pricing-description">{founder?'Full Pro access for the operating lifetime of Tradersecho.':pro?annual?'Billed $190 yearly. Two months free; save $38.':'Billed $19 monthly. Cancel renewal anytime.':paid?annual?'$8.25/month equivalent. Billed $99 yearly; save $9.':'Billed $9 monthly. Cancel renewal anytime.':'A useful daily snapshot. No card required.'}</p>
     <button className={'button full '+(paid?'primary':'')} disabled={Boolean(busy)||(paid&&!available)} onClick={()=>paid?(premium?onAccount():choose(choice)):user?onAccount():onSignup()}>
      {busy===choice?'Opening secure checkout…':selected&&user?'Your current plan':paid?premium?'Manage membership':available?founder?'Become a Founder':pro?'Get Pro':'Get Premium':'Payments opening soon':user?'Manage account':'Create free account'}
     </button>
     <ul className="pricing-features">{visibleFeatures.map(([label,free,full,founderValue])=><li key={label} className={!paid&&free==='Not included'?'excluded':''}><span aria-hidden="true">{!paid&&free==='Not included'?'−':'✓'}</span><div>{label}<strong>{(founder||pro)?(founderValue||full):paid?full:free}</strong></div></li>)}</ul>
     <p className="pricing-card-note">{founder?'One payment. No renewal. Same feature access and allowances as Pro; shared collection budgets still apply.':paid?'Renews automatically until cancelled. Collected data is shared; requests remain subject to the platform budget.':'Upgrade whenever you want a closer look.'}</p>
    </section>
   })}
  </div>
  <p className="muted">Have a promotional code? Enter it in secure Stripe checkout for monthly or annual Premium or Pro. Invite friends from My account to earn Premium rewards.</p>
  {user?.role==='owner'&&<details className="panel"><summary>Owner billing verification</summary><p>Prepare the two Pro prices and open unpaid checkout previews. This does not buy a subscription.</p><button className="button" disabled={Boolean(busy)} onClick={async()=>{setBusy('verify');setError('');try{const d=await api('/admin/billing/prepare-pro','POST');setChecks(d.checkouts)}catch(e){setError(e.message)}finally{setBusy('')}}}>Prepare & verify Pro checkout</button>{checks.map(c=><p key={c.tier}><a href={c.url} target="_blank" rel="noreferrer">Open {c.tier==='pro_monthly'?'$19 monthly':'$190 annual'} checkout ↗</a></p>)}</details>}
  <ApiAddon user={user}/>
  {error&&<p className="error" role="alert">{error}</p>}
  <div className="pricing-footnotes"><p>All prices in USD. Applicable taxes will be shown before payment. Founder access lasts while Tradersecho is operated as an active service; it is not a guarantee of perpetual operation.</p><p>Coverage depends on available X data. Paid membership does not guarantee complete coverage, investment returns or instant collection. Choose morning, closing, weekly and monthly research emails in My account.</p>{!status?.billing_configured&&<p>Plans are available to compare during our private preview. Checkout opens after payment setup and testing.</p>}</div>
 </div>
}
