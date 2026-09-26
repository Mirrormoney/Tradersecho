import {useEffect,useState} from 'react'
export const launchAt=Date.parse('2026-10-01T00:00:00+02:00')
export function useFeatureLaunch(){const [live,setLive]=useState(Date.now()>=launchAt);useEffect(()=>{if(live)return;const id=setInterval(()=>setLive(Date.now()>=launchAt),30000);return()=>clearInterval(id)},[live]);return live}
export const isPro=user=>Boolean(user?.pro_access)
