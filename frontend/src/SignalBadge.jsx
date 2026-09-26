import React from 'react'
export function SignalBadge({candidate}){
 const label={bullish:'Bullish',bearish:'Bearish',watch:'Neutral'}[candidate]
 if(!label)return null
 return <span className={'lab-direction-stamp lab-direction-'+label.toLowerCase()} title="Last saved setup classification; neutral means no confirmed directional setup.">{label}</span>
}
