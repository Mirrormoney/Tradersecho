import {captureCampaign,campaignForSignup} from './campaignAttribution.js'
captureCampaign()
const inflight = new Map()
const pause = ms => new Promise(resolve => setTimeout(resolve,ms))
export async function api(path,method='GET',body){
 if(path==='/auth/signup'&&method==='POST')body={...body,campaign_attribution:campaignForSignup()}
 const key=method+path
 if(method==='GET'&&inflight.has(key))return inflight.get(key)
 const task=(async()=>{
  const retryable=method==='GET'||(method==='POST'&&path==='/auth/login')
  for(let attempt=0;attempt<2;attempt++){
   const controller=new AbortController()
   const timer=setTimeout(()=>controller.abort(),method==='GET'||path==='/auth/login'?25000:190000)
   try{
    const r=await fetch('/api'+path,{method,credentials:'include',signal:controller.signal,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined})
    if(retryable&&attempt===0&&[502,503,504].includes(r.status)){await pause(700);continue}
    let j;try{j=await r.json()}catch{throw Error('The server is temporarily unavailable. Please try again.')}
    if(!r.ok)throw Error(typeof j.detail==='string'?j.detail:r.status===401?'Please sign in again.':'The request could not be completed. Please try again.')
    return j
   }catch(e){
    const interrupted=e instanceof TypeError||e.name==='AbortError'
    if(interrupted&&retryable&&attempt===0){await pause(700);continue}
    if(e.name==='AbortError')throw Error(retryable?'The server took too long to respond. Please retry.':'The request is taking longer than expected. Refresh its status before trying again.')
    if(e instanceof TypeError)throw Error('Connection interrupted. Please check your internet connection and try again.')
    throw e
   }finally{clearTimeout(timer)}
  }
 })()
 if(method==='GET')inflight.set(key,task)
 try{return await task}finally{if(inflight.get(key)===task)inflight.delete(key)}
}
