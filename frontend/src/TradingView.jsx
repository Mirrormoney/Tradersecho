import React from 'react'
import {tradingViewUrl, affiliateEnabled, hasTradingViewSymbol} from './tradingview.js'
import './tradingview.css'

export function TradingViewLink({ticker,name,detail=false}) {
 const matched=hasTradingViewSymbol(ticker)
 const label=matched?`Open ${name||ticker} chart on TradingView`:`Find ${name||ticker} on TradingView`
 return <a className={detail?'button primary tradingview-detail-link':'tradingview-link'} href={tradingViewUrl(ticker)} target="_blank" rel={affiliateEnabled?'sponsored nofollow noopener noreferrer':'noopener noreferrer'} aria-label={label+' (opens in a new tab)'} title={label} onClick={e=>e.stopPropagation()}>
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M3 3v18h18M6 15l4-5 4 3 6-8M16 5h4v4"/></svg>
  <span className={detail?'':'tradingview-link-text'}>{detail?label:matched?'Chart':'Find chart'}</span><span aria-hidden="true">↗</span>
 </a>
}
export function TradingViewDisclosure(){return affiliateEnabled?<p className="tradingview-disclosure">We may earn a commission if you subscribe through our TradingView links.</p>:null}
export function TradingViewDetail({ticker,name}){return <section className="tradingview-detail"><TradingViewLink ticker={ticker} name={name} detail/><p>Explore price action, indicators and technical charts.</p><TradingViewDisclosure/></section>}
