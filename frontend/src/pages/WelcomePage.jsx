import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

/* Overture — the front door after the ident. One world: same dark, same serif,
   same gold as the product. Two doors, live receipts, no invented numbers. */

const T = {
  bg:'#0B0A09', surface:'#141210', line:'rgba(255,255,255,.07)', line2:'rgba(255,255,255,.13)',
  ink:'#F4F1EC', ink2:'rgba(244,241,236,.62)', ink3:'rgba(244,241,236,.38)',
  gold:'#C9A961',
  serif:"'Playfair Display', Georgia, serif",
  sans:"'Inter', -apple-system, sans-serif",
}

function Mark({size=54}){
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none">
      {[26,20,14,8].map((r,i)=>(
        <path key={r}
          d={`M ${32-r} 32 A ${r} ${r} 0 1 1 ${32+r} 32`}
          stroke={i===3?T.gold:'rgba(244,241,236,.55)'}
          strokeWidth={i===3?2.2:1.4} strokeLinecap="round"/>
      ))}
    </svg>
  )
}

export default function WelcomePage(){
  const [cov,setCov]=useState(null)
  useEffect(()=>{
    fetch('/api/coverage',{headers:{Authorization:'Bearer demo'}})
      .then(r=>r.json()).then(setCov).catch(()=>{})
  },[])
  const rows = cov?.coverage || []
  const homes = rows.reduce((a,r)=>a+(r.parcel_count||0),0)
  const states = new Set(rows.map(r=>r.state).filter(Boolean)).size
  const isM = typeof window!=='undefined' && window.innerWidth<760

  const card = {
    background:T.surface, border:`1px solid ${T.line}`, borderRadius:24,
    padding: isM?'30px 26px':'40px 38px', display:'flex', flexDirection:'column',
  }
  const kicker = {fontSize:11.5, letterSpacing:'.16em', textTransform:'uppercase',
    color:T.gold, fontWeight:700, marginBottom:14}
  const cta = {marginTop:'auto', alignSelf:'flex-start', padding:'13px 26px',
    borderRadius:999, textDecoration:'none', fontFamily:T.sans, fontSize:14, fontWeight:700}

  return (
    <div style={{minHeight:'100vh', background:T.bg, color:T.ink, fontFamily:T.sans}}>
      <div style={{maxWidth:1060, margin:'0 auto', padding: isM?'54px 22px 60px':'90px 28px 80px'}}>

        <div style={{display:'flex', alignItems:'center', gap:16, marginBottom:isM?40:60}}>
          <Mark size={isM?44:54}/>
          <span style={{fontFamily:T.serif, fontSize:isM?22:26, fontWeight:600,
            letterSpacing:'.02em'}}>Overture</span>
        </div>

        <h1 style={{fontFamily:T.serif, fontWeight:600, lineHeight:1.18,
          fontSize:isM?'clamp(30px,8vw,40px)':'clamp(38px,4.6vw,58px)', margin:'0 0 22px', maxWidth:820}}>
          Every home has an owner.<br/>
          Every owner has a moment.<br/>
          <span style={{color:T.gold}}>We make the match.</span>
        </h1>
        <p style={{fontSize:isM?15:16.5, color:T.ink2, lineHeight:1.9, maxWidth:640,
          margin:'0 0 52px'}}>
          Overture watches the public record across entire territories — estates,
          dissolutions, trusts, tenure — and matches what it learns with verified
          buyers, before anything reaches a listing. The market before the market.
        </p>

        <div style={{display:'grid', gridTemplateColumns:isM?'1fr':'1fr 1fr', gap:18,
          marginBottom:56}}>
          <div style={card}>
            <div style={kicker}>For listing agents</div>
            <div style={{fontFamily:T.serif, fontSize:isM?24:28, fontWeight:600, marginBottom:12}}>
              Find sellers</div>
            <p style={{fontSize:14, color:T.ink2, lineHeight:1.85, margin:'0 0 28px'}}>
              Claim a ZIP and it's yours alone — forever. Every filing, every signal,
              every buyer introduction in your territory routes to one agent: you.
            </p>
            <Link to="/territories" style={{...cta, background:T.gold, color:'#151311'}}>
              Claim your ground</Link>
          </div>
          <div style={card}>
            <div style={kicker}>For buyer's agents · free</div>
            <div style={{fontFamily:T.serif, fontSize:isM?24:28, fontWeight:600, marginBottom:12}}>
              Find homes</div>
            <p style={{fontSize:14, color:T.ink2, lineHeight:1.85, margin:'0 0 28px'}}>
              Post what your client wants. We search every home in the territory —
              not just listings — and tell you when a fit develops a reason to sell.
            </p>
            <Link to="/network" style={{...cta, background:'none', color:T.ink,
              border:`1px solid ${T.line2}`}}>Post a search</Link>
          </div>
        </div>

        <div style={{display:'flex', gap:isM?18:44, flexWrap:'wrap', alignItems:'baseline',
          borderTop:`1px solid ${T.line}`, paddingTop:30}}>
          {[
            [homes? homes.toLocaleString() : '—', 'homes watched'],
            [rows.length? rows.length : '—', 'territories mapped'],
            [states || '—', 'states'],
            ['1', 'agent per ZIP — forever'],
          ].map(([v,l])=>(
            <div key={l}>
              <span style={{fontFamily:T.serif, fontSize:isM?20:24, fontWeight:600,
                color:T.ink}}>{v}</span>
              <span style={{fontSize:12.5, color:T.ink3, marginLeft:8}}>{l}</span>
            </div>
          ))}
        </div>

        <div style={{marginTop:70, fontSize:12, color:T.ink3}}>
          Overture · The market before the market
        </div>
      </div>
    </div>
  )
}
