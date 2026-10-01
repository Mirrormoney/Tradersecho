import React,{useEffect,useState} from 'react'
import {api} from './api.js'
import {SignalAnnouncement,SignalTeaser} from './SignalLab.jsx'
import {InsightsAnnouncement} from './InsightsAnnouncement.jsx'
import {SignalOverview} from './SignalOverview.jsx'
import {InsightsAdmin} from './InsightsAdmin.jsx'
import {useFeatureLaunch,isPro} from './featureAccess.js'
import './pro-features.css'
export function ProLock({title='Full analysis'}){return <div className="pro-lock"><div className="pro-lock-sample" aria-hidden="true"><i/><i/><i/></div><div className="pro-lock-message"><strong>{title}</strong><p>Unlock full Signal Lab screening and AI Insights with Pro.</p><a className="button primary" href="/plans">Upgrade to Pro ↗</a></div></div>}
export function ProFeaturePage({kind,user}){
 const live=useFeatureLaunch(),[topics,setTopics]=useState([])
 useEffect(()=>{if(kind==='insights')api('/insights').then(setTopics).catch(()=>{})},[kind])
 if(!live)return <>{kind==='signal'?<SignalAnnouncement/>:<InsightsAnnouncement/>}{!isPro(user)&&<ProLock title="Full access opens October 1"/>}</>
 if(isPro(user))return kind==='signal'?<SignalOverview member/>:<InsightsAdmin member/>
 return <section>{kind==='signal'?<><h1>Signal Lab</h1><div className="signal-preview-layout"><SignalTeaser/><aside className="signal-preview-indicators" aria-label="Five indicators available with Pro"><h2>Five perspectives.</h2>{["Price strength","Volume","Options pressure","X activity","Catalyst strength"].map(name=><div className="panel signal-preview-indicator" key={name}><span className="sr-only">{name} · Pro access required</span><div className="signal-preview-blur" aria-hidden="true"><strong>{name}</strong><i/><i/></div></div>)}</aside></div></>:<><h1>AI Insights</h1><p>Understand the technologies shaping the AI economy.</p><div className="data-grid">{topics.map(t=><article className="panel" key={t.slug}><h2>{t.title}</h2><p>{t.intro}</p></article>)}</div></>}<ProLock title={kind==='signal'?'Screen individual stocks with Pro':'Explore timelines and potential beneficiaries with Pro'}/></section>
}
