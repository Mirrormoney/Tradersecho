export function rankSignals(stocks=[]){
 const rows=stocks.map(s=>{const values=s.axes.map(a=>a.score).filter(v=>typeof v==='number'&&Number.isFinite(v));return {...s,available:values.length,total:values.reduce((a,b)=>a+b,0),activity:s.axes[3]?.score??null}})
 const byTotal=[...rows].sort((a,b)=>b.available-a.available||b.total-a.total||a.ticker.localeCompare(b.ticker))
 const byActivity=[...rows].filter(s=>s.activity!=null).sort((a,b)=>b.activity-a.activity||a.ticker.localeCompare(b.ticker))
 return {rows:byTotal,byTotal:byTotal.filter(s=>s.available>0),byActivity}
}
