import React from 'react'
import {cashtagParts} from './chat-cashtags.js'

export function ChatCashtags({text,catalog,onTicker}) {
 return cashtagParts(text,catalog).map((part,index)=>part.ticker&&onTicker?
  <button type="button" className="chat-cashtag" key={index} aria-label={`Open ${part.ticker} stock details`} onClick={()=>onTicker(part.ticker)}>{part.text}</button>:
  <React.Fragment key={index}>{part.text}</React.Fragment>)
}
