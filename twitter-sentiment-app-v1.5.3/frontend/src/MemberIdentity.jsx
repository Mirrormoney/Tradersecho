import React from 'react'
import {displayInitials} from './identity.js'

export function PremiumBadge({plan}){
 return plan==='premium'?<span className="premium-badge" title="Premium membership, not identity verification">Premium</span>:null
}
export function MemberIdentity({user}){
 return <div className="member-identity"><span className="avatar" aria-hidden="true">{displayInitials(user.display_name)}</span><strong>{user.display_name}</strong><PremiumBadge plan={user.plan}/></div>
}
