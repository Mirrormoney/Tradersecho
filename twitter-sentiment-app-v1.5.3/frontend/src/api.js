const inflight = new Map()
export async function api(path,method='GET',body){
 const key=method+path
 if(method==='GET'&&inflight.has(key))return inflight.get(key)
 const task=(async()=>{
  const controller=new AbortController()
  const timer=setTimeout(()=>controller.abort(),method==='GET'?25000:190000)
  try{
   const r=await fetch('/api'+path,{method,credentials:'include',signal:controller.signal,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined})
   let j;try{j=await r.json()}catch{throw Error('The server is temporarily unavailable. Please try again.')}
   if(!r.ok)throw Error(typeof j.detail==='string'?j.detail:r.status===401?'Please sign in again.':'The request could not be completed. Please try again.')
   return j
  }catch(e){if(e.name==='AbortError')throw Error(method==='GET'?'The server took too long to respond. Please retry.':'The request is taking longer than expected. Refresh its status before trying again.');throw e}
  finally{clearTimeout(timer)}
 })()
 if(method==='GET')inflight.set(key,task)
 try{return await task}finally{if(inflight.get(key)===task)inflight.delete(key)}
}
