import React, { useEffect, useRef, useState } from 'react'
const API_BASE = 'http://127.0.0.1:8000'
function number(n){ return Intl.NumberFormat('en-US', {maximumFractionDigits:2}).format(n) }
function pct(n){ return (n>=0?'+':'') + number(n*100) + '%' }
function useAuth(){
  const [token, setToken] = useState(localStorage.getItem('token') || '')
  const save = (t)=>{ localStorage.setItem('token', t); setToken(t) }
  const clear = ()=>{ localStorage.removeItem('token'); setToken('') }
  return { token, save, clear }
}
function FreeList(){
  const [rows, setRows] = useState([])
  useEffect(()=>{ fetch(`${API_BASE}/api/free/daily`).then(r=>r.json()).then(setRows).catch(()=>setRows([])) },[])
  return (<div className="card">
    <div className="row" style={{justifyContent:'space-between'}}>
      <h3 className="section-title">Free (Delayed) Sentiment — Yesterday</h3>
      <span className="muted">Updates daily</span>
    </div>
    <table><thead><tr>
      <th>Ticker</th><th>Interest</th><th>Mentions</th><th>Δ vs Avg</th><th>Sentiment</th>
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
function Login({onAuthed}){
  const [mode, setMode] = useState('login')
  const userRef = useRef(null)
  const passRef = useRef(null)
  async function submit(e){
    e.preventDefault()
    const username = userRef.current.value.trim()
    const password = passRef.current.value.trim()
    if(!username || !password) return
    try {
      if(mode === 'signup'){
        const r = await fetch(`${API_BASE}/api/auth/signup`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({username, password}) })
        const j = await r.json()
        if(j.access_token){ onAuthed(j.access_token) } else { alert(j.detail || 'Signup failed') }
      } else {
        const form = new URLSearchParams(); form.set('username', username); form.set('password', password)
        const r = await fetch(`${API_BASE}/api/auth/login`, { method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body: form })
        const j = await r.json()
        if(j.access_token){ onAuthed(j.access_token) } else { alert(j.detail || 'Login failed') }
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
function ProRealtime({token, onLogout}){
  const [rows, setRows] = useState([])
  useEffect(()=>{
    fetch(`${API_BASE}/api/pro/realtime`, { headers:{Authorization:`Bearer ${token}`} })
      .then(r=>r.json()).then(setRows).catch(()=>{})
    const ws = new WebSocket(`ws://127.0.0.1:8000/ws/realtime?token=${token}`)
    ws.onmessage = (ev)=>{ try{ setRows(JSON.parse(ev.data)) }catch{} }
    return ()=>{ ws.close() }
  }, [token])
  return (<div className="card">
    <div className="row" style={{justifyContent:'space-between'}}>
      <h3 className="section-title">Pro (Realtime) Sentiment</h3>
      <div className="row"><button className="btn" onClick={onLogout}>Logout</button></div>
    </div>
    <table><thead><tr>
      <th>Ticker</th><th>Interest</th><th>Mentions</th><th>Δ vs Avg</th><th>Sentiment</th>
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
  const auth = useAuth()
  return (<>
    <header>
      <div className="brand">Twitter Sentiment</div>
      <div className="row"><a className="btn" href="#pricing">Pricing</a><a className="btn primary" href="#pro">Go Pro</a></div>
    </header>
    <div className="container">
      <div className="hero">
        <div className="card">
          <h2 style={{marginTop:0}}>Spot ticker hype, before the chart.</h2>
          <p className="muted">We track cashtag mentions (like <strong>$TSLA</strong> or <strong>$NVDA</strong>) and compare them to each ticker’s baseline to compute an Interest Score. Add sentiment on top, and you get a real-time crowd signal.</p>
          <div className="row" style={{marginTop:12}}><a className="btn primary" href="#pro">Try Pro (Realtime)</a><a className="btn" href="#free">See free delayed list</a></div>
        </div>
        <div id="free"><FreeList /></div>
      </div>
      <div id="pro" style={{marginTop:24}}>{auth.token ? <ProRealtime token={auth.token} onLogout={auth.clear} /> : <Login onAuthed={auth.save} />}</div>
      <div id="pricing" className="grid cols-2" style={{marginTop:24}}>
        <div className="card"><h3 className="section-title">Free</h3>
          <ul><li>✓ Yesterday’s sentiment (delayed)</li><li>✓ Top tickers ranked by Interest score</li><li>✓ Market-wide snapshot</li></ul>
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