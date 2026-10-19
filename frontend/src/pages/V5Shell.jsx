import React, { useEffect, useState } from 'react'
import { Outlet, NavLink, Link } from 'react-router-dom'
import { useAuth } from '../lib/AuthContext.jsx'

export function useIsMobile(){
  const [m,setM]=useState(typeof window!=='undefined' && window.innerWidth<760)
  useEffect(()=>{
    const f=()=>setM(window.innerWidth<760)
    window.addEventListener('resize',f); return ()=>window.removeEventListener('resize',f)
  },[])
  return m
}

/* ── Overture V5 shell: Zillow-meets-Hinge on dark ─────────────────
   Top nav (not sidebar). Aperture mark. Sans UI, serif display.
   Card language: rounded-16, elevated surfaces, generous space. */

export const T = {
  bg:      '#0B0A09',
  surface: '#151311',
  surface2:'#1D1A17',
  line:    'rgba(255,255,255,.08)',
  line2:   'rgba(255,255,255,.16)',
  ink:     '#F4F1EC',
  ink2:    'rgba(244,241,236,.62)',
  ink3:    'rgba(244,241,236,.38)',
  gold:    '#C9A961',
  sans:    "'Inter', -apple-system, system-ui, sans-serif",
  serif:   "'Playfair Display', Georgia, serif",
}

export function Aperture({size=34, stroke='#F4F1EC'}){
  return (
    <svg viewBox="0 0 1000 1000" width={size} height={size} aria-hidden="true">
      <circle cx="500" cy="500" r="388" stroke={stroke} strokeWidth="56" fill="none"/>
      <path d="M 743.4 435.8 A 252 252 0 0 1 565.2 743.4" stroke={stroke} strokeWidth="42" fill="none"/>
      <path d="M 321.8 678.2 A 252 252 0 0 1 256.6 435.8" stroke={stroke} strokeWidth="42" fill="none"/>
      <path d="M 391.5 285.7 A 252 252 0 0 1 630.3 296.1" stroke={stroke} strokeWidth="42" fill="none"/>
    </svg>
  )
}

// Real auth: every V5 call carries the Supabase session JWT. The demo
// build used a hardcoded 'Bearer demo'; the production backend rejects
// that, so the token comes from the live session on every request.
// (Demo builds still work: with __OVERTURE_DEMO__ set there is no
// session and the demo server ignores the Authorization header.)
import { getAccessToken } from '../lib/supabase.js'
async function _hdrs(json){
  const h = {}
  if (json) h['Content-Type'] = 'application/json'
  try {
    const t = (typeof window!=='undefined' && window.__OVERTURE_DEMO__) ? 'demo' : await getAccessToken()
    if (t) h['Authorization'] = `Bearer ${t}`
  } catch (e) { /* unauthenticated — AuthGate handles redirect */ }
  return h
}
async function _check(r){
  if(!r.ok){
    let detail = r.status
    try { const j = await r.json(); detail = j?.detail?.message || j?.detail || r.status } catch(e){}
    const err = new Error(typeof detail==='string'?detail:JSON.stringify(detail)); err.status=r.status; throw err
  }
  return r.json()
}
export const api = {
  async get(p){ return _check(await fetch(p,{headers: await _hdrs(false)})) },
  async post(p,b){ return _check(await fetch(p,{method:'POST',headers: await _hdrs(true),body:JSON.stringify(b||{})})) },
  async del(p){ return _check(await fetch(p,{method:'DELETE',headers: await _hdrs(false)})) },
}
export const money = v => (!v)?'—':(v>=1e6?`$${(v/1e6).toFixed(v<10e6?1:0)}M`:`$${Math.round(v/1e3)}K`)

const tab = ({isActive}) => ({
  fontFamily:T.sans, fontSize: (typeof window!=='undefined'&&window.innerWidth<760)?13.5:14, whiteSpace:'nowrap', fontWeight:isActive?600:450,
  color:isActive?T.ink:T.ink2, textDecoration:'none',
  padding:'8px 14px', borderRadius:999,
  background:isActive?'rgba(255,255,255,.07)':'transparent',
  transition:'all .2s',
})

export default function V5Shell(){
  const isM = useIsMobile()
  const { profile } = useAuth()
  const agentName = profile?.full_name || profile?.email || 'Agent'
  const initials = (profile?.full_name || 'A').split(/\s+/).map(w=>w[0]).join('').slice(0,2).toUpperCase()
  return (
    <div style={{minHeight:'100vh', background:T.bg, color:T.ink, fontFamily:T.sans}}>
      <header style={{
        position:'sticky', top:0, zIndex:30,
        background:'rgba(11,10,9,.86)', backdropFilter:'blur(14px)',
        borderBottom:`1px solid ${T.line}`,
      }}>
        <div style={{maxWidth:1240, margin:'0 auto', padding: isM?'0 14px':'0 28px',
          height: isM?54:62, display:'flex', alignItems:'center', gap: isM?12:26}}>
          <Link to="/welcome" style={{display:'flex', alignItems:'center', gap:12, textDecoration:'none', color:T.ink}}>
            <Aperture size={30}/>
            {!isM && <span style={{fontFamily:T.serif, fontWeight:600, fontSize:19, letterSpacing:'.06em'}}>Overture</span>}
          </Link>
          <nav style={{display:'flex', gap:6, marginLeft: isM?0:10, overflowX:'auto',
            WebkitOverflowScrolling:'touch'}}>
            <NavLink to="/territories" style={tab}>My territory</NavLink>
            <NavLink to="/network"     style={tab}>Buyer network</NavLink>
            <NavLink to="/my-leads"    style={tab}>My leads</NavLink>
            <NavLink to="/letters"     style={tab}>Letters</NavLink>
            <NavLink to="/profile"     style={tab}>Profile</NavLink>
          </nav>
          <div style={{marginLeft:'auto', display:'flex', alignItems:'center', gap:14}}>
            {!isM && <span style={{fontSize:13, color:T.ink3}}>{agentName}</span>}
            <Link to="/profile" title="Profile & voice" style={{textDecoration:'none', color:T.ink}}>
              <div style={{width:32, height:32, borderRadius:999, background:T.surface2,
                border:`1px solid ${T.line2}`, display:'flex', alignItems:'center',
                justifyContent:'center', fontSize:12, fontWeight:600, cursor:'pointer'}}>{initials}</div>
            </Link>
          </div>
        </div>
      </header>
      <Outlet/>
    </div>
  )
}
