import {useEffect,useRef,useState} from 'react'

export const pagePaths={home:'/',market:'/marketpulse',briefing:'/daily-briefing',watchlist:'/watchlist',voices:'/tracked-voices',data:'/data-sources',community:'/trading-room',account:'/account',admin:'/admin'}
export const modalPaths={plans:'/plans',method:'/how-it-works',contact:'/contact',privacy:'/privacy',terms:'/terms',auth:'/login',forgot:'/forgot-password',owner:'/owner-setup',import:'/admin/import'}
export function readRoute(path=location.pathname){
 const clean=path.replace(/\/+$/,'')||'/'
 const page=Object.keys(pagePaths).find(k=>pagePaths[k]===clean)
 const modal=Object.keys(modalPaths).find(k=>modalPaths[k]===clean)||''
 return {page:page||(clean.startsWith('/admin/')?'admin':'home'),modal}
}
export function useAppRoute(){
 const [route,update]=useState(()=>readRoute()),current=useRef(route)
 function change(next){
  current.current=next;update(next)
  const path=modalPaths[next.modal]||pagePaths[next.page]||'/'
  const query=new URLSearchParams(location.search);query.delete('view');query.delete('ticker');
  if(location.pathname!==path)history.pushState({page:next.page},'',path+(query.size?'?'+query.toString():'')+location.hash)
 }
 useEffect(()=>{const back=()=>{const next=readRoute();if(next.modal&&history.state?.page)next.page=history.state.page;current.current=next;update(next)};window.addEventListener('popstate',back);return()=>window.removeEventListener('popstate',back)},[])
 return {...route,setPage:page=>change({page,modal:''}),setModal:modal=>change({...current.current,modal})}
}
