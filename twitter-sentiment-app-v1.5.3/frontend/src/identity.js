export function displayInitials(name){
 const words=(name||'').trim().split(/[\s._-]+/).filter(Boolean)
 if(!words.length)return 'TE'
 return (words.length>1?words[0][0]+words[words.length-1][0]:words[0].slice(0,2)).toUpperCase()
}
