import React,{useState} from 'react'
import logos from './companyLogos.json'
import './company-logo.css'
export function CompanyLogo({ticker}){
 const entry=logos[ticker], [failed,setFailed]=useState(null)
 if(!entry||failed===ticker)return null
 return <span className={'company-logo company-logo--'+entry.backing+(entry.blend?' company-logo--blend':'')} aria-hidden="true"><img src={'/company-logos/'+entry.file} alt="" width="48" height="48" loading="lazy" decoding="async" onError={()=>setFailed(ticker)}/></span>
}
