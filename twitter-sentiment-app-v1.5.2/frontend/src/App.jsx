import React, { useEffect, useRef, useState } from 'react'
const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'
function number(n){ return Intl.NumberFormat('en-US', {maximumFractionDigits:2}).format(n) }
function pct(n){ return (n>=0?'+':'') + number(n*100) + '%' }
function useAuth(){
  const [token, setToken] = useState(localStorage.getItem('token') || '')
  const save = (t)=>{ localStorage.setItem('token', t); setToken(t) }
  const clear = ()=>{ localStorage.removeItem('token'); setToken('') }
  return { token, save, clear }
}
function useMe(token){
  const [me, setMe] = useState(null)
  useEffect(()=>{
    if(!token){ setMe(null); return }
    fetch(`${API_BASE}/api/me`, { headers:{Authorization:`Bearer ${token}`} })
      .then(r=>r.ok?r.json():null).then(setMe).catch(()=>setMe(null))
  }, [token])
  return me
}
function FreeList(){
  const [rows, setRows] = useState([])
  const [tickers, setTickers] = useState('')
  const [limit, setLimit] = useState(10)
  const [sort, setSort] = useState('interest_score')
  async function load(){
    const params = new URLSearchParams()
    if(tickers.trim()) params.set('tickers', tickers.trim())
    params.set('limit', limit); params.set('sort', sort)
    const r = await fetch(`${API_BASE}/api/free/daily?${params.toString()}`)
    const j = await r.json(); setRows(j)
  }
  useEffect(()=>{ load() },[])
  return (<div className="card">
    <div className="row" style={{justifyContent:'space-between'}}>
      <h3 className="section-title">Free (Delayed) Sentiment — Yesterday</h3>
      <span className="muted">From DB rollups</span>
    </div>
    <div className="row" style={{gap:8, marginBottom:10}}>
      <input placeholder="Tickers (e.g. AAPL,TSLA)" value={tickers} onChange={e=>setTickers(e.target.value)} />
      <input type="number" min="1" max="100" value={limit} onChange={e=>setLimit(e.target.value)} style={{width:90}}/>
      <select value={sort} onChange={e=>setSort(e.target.value)}>
        <option value="interest_score">Sort: Interest</option>
        <option value="mentions">Sort: Mentions</option>
        <option value="zscore">Sort: Z</option>
      </select>
      <button className="btn" onClick={load}>Apply</button>
    </div>
    <table><thead><tr>
      <th>Date</th><th>Ticker</th><th>Mentions</th><th>Interest</th><th>Z</th><th>Pos/Neg/Neu</th>
    </tr></thead><tbody>
      {rows.map(r=>(
        <tr key={r.ticker+String(r.date)}>
          <td>{r.date}</td>
          <td><span className="pill">${r.ticker}</span></td>
          <td>{r.mentions}</td>
          <td>{number(r.interest_score)}</td>
          <td>{number(r.zscore)}</td>
          <td>{r.pos}/{r.neg}/{r.neu}</td>
        </tr>
      ))}
    </tbody></table>
  </div>)
}
function Login({onAuthed}){
  const [mode, setMode] = useState('login')
  const userRef = useRef(null); const passRef = useRef(null)
  async function submit(e){
    e.preventDefault()
    const username = userRef.current.value.trim(), password = passRef.current.value.trim()
    if(!username || !password) return
    try {
      if(mode === 'signup'){
        const r = await fetch(`${API_BASE}/api/auth/signup`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({username, password}) })
        const j = await r.json(); if(j.access_token){ onAuthed(j.access_token) } else { alert(j.detail || 'Signup failed') }
      } else {
        const form = new URLSearchParams(); form.set('username', username); form.set('password', password)
        const r = await fetch(`${API_BASE}/api/auth/login`, { method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body: form })
        const j = await r.json(); if(j.access_token){ onAuthed(j.access_token) } else { alert(j.detail || 'Login failed') }
      }
    } catch{ alert('Network error') }
  }
  return (<div className="card">
    <h3 className="section-title">{mode==='signup' ? 'Create account' : 'Log in for Pro (Realtime)'}</h3>
    <form onSubmit={submit}>
      <div className="field"><label>Username</label><input ref={userRef} placeholder="you@example.com" /></div>
      <div className="field"><label>Password</label><input ref={passRef} type="password" placeholder="••••••••" /></div>
      <div className="row"><button className="btn primary" type="submit">{mode==='signup'?'Sign up':'Log in'}</button>
      <button className="btn" type="button" onClick={()=>setMode(mode==='signup'?'login':'signup')}>{mode==='signup'?'Have an account? Log in':'No account? Sign up'}</button></div>
    </form>
  </div>)
}
function Upgrade({token}){
  async function go(){
    const r = await fetch(`${API_BASE}/api/billing/create-checkout-session`, { method:'POST', headers:{ Authorization:`Bearer ${token}` } })
    const j = await r.json()
    if(j.url){ window.location.href = j.url } else { alert(j.detail || 'Failed to start checkout') }
  }
  return (<div className="card">
    <h3 className="section-title">Upgrade to Pro</h3>
    <p className="muted">Unlock realtime updates and full ticker coverage.</p>
    <button className="btn primary" onClick={go}>Start Stripe Checkout</button>
  </div>)
}
function ProRealtime({token}){
  const [rows, setRows] = useState([])
  useEffect(()=>{
    fetch(`${API_BASE}/api/pro/snapshot?window=5m`, { headers:{Authorization:`Bearer ${token}`} })
      .then(async r=>{ if(r.status===403) throw new Error('notpro'); return r.json() })
      .then(setRows).catch(()=>{})
    const ws = new WebSocket(`${API_BASE.replace('http','ws')}/ws/realtime?token=${token}`)
    ws.onmessage = (ev)=>{ try{ setRows(JSON.parse(ev.data)) }catch{} }
    return ()=>{ ws.close() }
  }, [token])
  return (<div className="card">
    <div className="row" style={{justifyContent:'space-between'}}>
      <h3 className="section-title">Pro (Realtime) Sentiment</h3>
    </div>
    <table><thead><tr>
      <th>Ticker</th><th>Interest</th><th>Mentions (5m)</th><th>Δ vs Avg</th><th>Sentiment</th>
    </tr></thead><tbody>
      {rows.map(r=>{
        const pos = r.sentiment >= 0
        return (<tr key={r.ticker}>
          <td><span className="pill">${r.ticker}</span></td>
          <td>{number(r.interest_score)}</td>
          <td>{r.mentions}</td>
          <td>{pct(r.change_vs_avg)}</td>
          <td><span className={`badge ${pos?'pos':'neg'}`}>{number(r.sentiment)}</span></td>
        </tr>)
      })}
    </tbody></table>
  </div>)
}
export default function App(){
  const [themeCss] = useState(`
    :root { --bg:#0b0d12; --card:#141821; --text:#e5e7eb; --muted:#9ca3af; }
    * { box-sizing: border-box; } body { margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto; background:var(--bg); color:var(--text); }
    header { display:flex; align-items:center; justify-content:space-between; padding:16px 24px; border-bottom:1px solid #1f2937; position:sticky; top:0; background:rgba(11,13,18,0.8); backdrop-filter:saturate(180%) blur(8px); }
    .brand { font-weight:700; letter-spacing:.3px; }
    .container { max-width:1100px; margin:0 auto; padding:24px; }
    .hero { display:grid; grid-template-columns: 1.2fr 0.8fr; gap:24px; align-items:center; margin-top:12px; }
    .card { background:var(--card); border:1px solid #1f2937; border-radius:16px; padding:20px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); }
    .muted { color:var(--muted); }
    .btn { padding:10px 14px; border-radius:12px; border:1px solid #334155; background:#0b1220; color:var(--text); cursor:pointer; }
    .btn.primary { background: linear-gradient(135deg, #2563eb, #0891b2); border-color:#1d4ed8; }
    .grid { display:grid; gap:16px; } .grid.cols-2 { grid-template-columns: 1fr 1fr; }
    table { width:100%; border-collapse: collapse; } th, td { text-align:left; padding:10px 8px; border-bottom:1px solid #1f2937; } th { color:#93c5fd; font-weight:600; }
    .badge { padding:4px 8px; border-radius:999px; font-size:12px; border:1px solid #334155; } .badge.pos { color:#86efac; } .badge.neg { color:#fca5a5; }
    .section-title { font-size:18px; margin:0 0 8px 0; } .field { display:flex; flex-direction:column; gap:6px; margin-bottom:10px; }
    input, select { padding:10px 12px; border-radius:10px; border:1px solid #334155; background:#0b1220; color:var(--text); }
    .row { display:flex; gap:10px; align-items:center; } .pill { font-weight:600; color:#93c5fd; }
    .footer { color:var(--muted); font-size:12px; margin-top:36px; text-align:center; }
  `)
  const auth = (function useAuth(){
    const [token, setToken] = useState(localStorage.getItem('token') || '')
    const save = (t)=>{ localStorage.setItem('token', t); setToken(t) }
    const clear = ()=>{ localStorage.removeItem('token'); setToken('') }
    return { token, save, clear }
  })()
  const me = useMe(auth.token)
  const authed = !!auth.token
  return (<>
    <style>{themeCss}</style>
    <header>
      <div className="brand">Twitter Sentiment</div>
      <div className="row"><a className="btn" href="#pricing">Pricing</a><a className="btn primary" href="#pro">Go Pro</a></div>
    </header>
    <div className="container">
      <div className="hero">
        <div className="card">
          <h2 style={{marginTop:0}}>Spot ticker hype, before the chart.</h2>
          <p className="muted">We track cashtag mentions and compare them to each ticker’s baseline to compute an Interest Score. Add sentiment on top, and you get a real-time crowd signal.</p>
          <div className="row" style={{marginTop:12}}><a className="btn primary" href="#pro">Try Pro (Realtime)</a><a className="btn" href="#free">See free delayed list</a></div>
        </div>
        <div id="free"><FreeList /></div>
      </div>
      <div id="pro" style={{marginTop:24}}>
        {!authed ? <Login onAuthed={auth.save} /> : (me && me.pro ? <ProRealtime token={auth.token} /> : <Upgrade token={auth.token} />)}
      </div>
      <div id="pricing" className="grid cols-2" style={{marginTop:24}}>
        <div className="card"><h3 className="section-title">Free</h3>
          <ul><li>✓ Yesterday’s sentiment (delayed, from DB)</li><li>✓ Top tickers ranked by Interest score</li><li>✓ Market-wide snapshot</li></ul>
          <div className="row" style={{marginTop:8}}><span className="muted">€0 / month</span></div>
        </div>
        <div className="card"><h3 className="section-title">Pro</h3>
          <ul><li>✓ Realtime updates (WebSocket)</li><li>✓ Full ticker universe</li><li>✓ API access</li></ul>
          <div className="row" style={{marginTop:8, justifyContent:'space-between'}}><span className="muted">from €29 / month</span><a className="btn primary" href="#pro">Get started</a></div>
        </div>
      </div>
      <div className="footer">Demo data shown. Plug in your collector to go live.</div>
    </div>
  </>)
}
