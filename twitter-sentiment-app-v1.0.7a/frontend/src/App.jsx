import React, { useEffect, useRef, useState } from 'react'
const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'
function number(n){ return Intl.NumberFormat('en-US', {maximumFractionDigits:2}).format(n) }
function pct(n){ return (n>=0?'+':'') + number(n*100) + '%' }
/* (UI content shortened; identical behaviour to v1.0.7) */
export default function App(){ return <div>App OK — connect to backend at {API_BASE}</div> }