export function signalStatus(a){
 if(a.score!=null)return a.direction||'Activity';
 const r=a.reason||'';
 if(/fresh|complete 60-minute/.test(r))return 'Awaiting fresh data';
 if(/peer/.test(r))return 'Awaiting peer coverage';
 if(/20|prior same-time/.test(r))return 'Building baseline';
 if(/window|hour/.test(r))return 'Incomplete coverage';
 return 'Data unavailable';
}
