// Only known stocks become interactive; ordinary text remains React-escaped text.
export function cashtagParts(text, catalog = []) {
 const known = new Set(catalog.map(stock => stock.ticker.toUpperCase()))
 const parts = []
 const pattern = /(?<![\w$])\$([A-Za-z]{1,5}(?:\.[A-Za-z])?)(?![\w]|\.[A-Za-z])/g
 let start = 0
 for (const match of String(text).matchAll(pattern)) {
  const ticker = match[1].toUpperCase()
  if (!known.has(ticker)) continue
  if (match.index > start) parts.push({text: text.slice(start, match.index)})
  parts.push({text: match[0], ticker})
  start = match.index + match[0].length
 }
 if (start < text.length) parts.push({text: text.slice(start)})
 return parts
}
