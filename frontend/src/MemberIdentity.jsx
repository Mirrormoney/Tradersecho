import React from 'react'
import {displayInitials} from './identity.js'

export function PremiumBadge({plan,tier}){
 return ['premium','pro'].includes(plan)?<span className={'premium-badge '+(tier==='founder'?'founder-badge':'')} title={tier==='founder'?'Founder membership — Premium access while Tradersecho operates':'Premium membership, not identity verification'}>{tier==='founder'?'◆ Founder':tier==='trial'?'Premium trial':plan==='pro'||tier==='pro'?'Pro':'Premium'}</span>:null
}
export function MemberIdentity({user}){
 return <div className="member-identity"><span className="avatar" aria-hidden="true">{displayInitials(user.display_name)}</span><strong>{user.display_name}</strong><PremiumBadge plan={user.plan} tier={user.billing_tier}/></div>
}
