import symbols from './tradingview-symbols.json'

// Public partner ID only. Leave unset until the owner's partner link is verified.
const affiliateId=String(import.meta.env?.VITE_TRADINGVIEW_AFFILIATE_ID||'').trim()
export const affiliateEnabled=/^\d+$/.test(affiliateId)
export const hasTradingViewSymbol=ticker=>Object.hasOwn(symbols,String(ticker).toUpperCase())
export function tradingViewUrl(ticker){
 const symbol=symbols[String(ticker).toUpperCase()]
 const url=new URL(symbol?`https://www.tradingview.com/symbols/${symbol}/`:'https://www.tradingview.com/search/')
 if(!symbol)url.searchParams.set('query',String(ticker))
 if(affiliateEnabled)url.searchParams.set('aff_id',affiliateId)
 return url.toString()
}
