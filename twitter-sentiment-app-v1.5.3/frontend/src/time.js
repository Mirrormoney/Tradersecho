// Presentation only: storage, billing and collection windows keep their original instants.
function parts(date, zone) {
  return Object.fromEntries(new Intl.DateTimeFormat('en-US', {timeZone:zone,year:'numeric',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',hour12:false,timeZoneName:'short'}).formatToParts(date).map(p=>[p.type,p.value]))
}
export function dualTime(value, {date=true}={}) {
  if(value===null||value===undefined||value==='') return '—'
  const instant=value instanceof Date?value:new Date(typeof value==='number'?value*1000:value)
  if(Number.isNaN(instant.getTime())) return '—'
  const ny=parts(instant,'America/New_York'),berlin=parts(instant,'Europe/Berlin')
  const stamp=p=>`${p.month} ${p.day}`
  const sameDay=ny.year===berlin.year&&ny.month===berlin.month&&ny.day===berlin.day
  const h=Number(ny.hour)%24,bh=Number(berlin.hour)%24
  const minute=p=>p.minute==='00'?'':':'+p.minute
  const east=`${h%12||12}${minute(ny)}${h<12?'am':'pm'} ${ny.timeZoneName}`
  // Some browser ICU versions render Berlin as GMT+1 / GMT+2.
  const zone=berlin.timeZoneName==='GMT+2'?'CEST':berlin.timeZoneName==='GMT+1'?'CET':berlin.timeZoneName
  const central=`${bh}${minute(berlin)} ${zone}`
  if(!sameDay) return `${stamp(ny)} ${east} / ${stamp(berlin)} ${central}`
  return `${date?stamp(ny)+' · ':''}${east} / ${central}`
}

// A recurring New York clock time, displayed with today's seasonal offsets.
export function dualScheduledTime(hour,minute=0,now=new Date()) {
  const day=parts(now,'America/New_York')
  const probe=new Date(`${day.month} ${day.day}, ${day.year} 12:00:00 GMT`)
  const offset=12-Number(parts(probe,'America/New_York').hour)
  probe.setUTCHours(hour+offset,minute,0,0)
  return dualTime(probe,{date:false})
}
