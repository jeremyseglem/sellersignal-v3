import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { T, api, money } from './V5Shell.jsx'

/* Your ground as hero cards; the wider map as one quiet section. */

function HeroCard({z}){
  const [hov,setHov]=useState(false)
  return (
    <Link to={`/zip/${z.zip_code}`}
      onMouseEnter={()=>setHov(true)} onMouseLeave={()=>setHov(false)}
      style={{
        display:'block', textDecoration:'none', color:T.ink,
        background: hov?T.surface2:T.surface,
        border:`1px solid ${hov?T.line2:T.line}`,
        borderRadius:20, padding:'26px 26px 22px',
        transition:'all .25s ease',
        transform: hov?'translateY(-2px)':'none',
      }}>
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'baseline'}}>
        <div style={{fontFamily:T.serif, fontSize:26, fontWeight:600}}>{z.city}</div>
        <span style={{fontSize:12, color:T.ink3}}>{z.zip_code}</span>
      </div>
      <div style={{margin:'20px 0 22px', display:'flex', gap:26}}>
        <div>
          <div style={{fontFamily:T.serif, fontSize:34, fontWeight:600, color:T.gold, lineHeight:1}}>
            {z.current_call_now_count ?? 0}
          </div>
          <div style={{fontSize:11.5, color:T.ink2, marginTop:6}}>to contact this week</div>
        </div>
        <div>
          <div style={{fontFamily:T.serif, fontSize:34, fontWeight:600, lineHeight:1}}>
            {(z.parcel_count||0).toLocaleString()}
          </div>
          <div style={{fontSize:11.5, color:T.ink2, marginTop:6}}>homes tracked</div>
        </div>
      </div>
      <div style={{
        fontSize:13, fontWeight:600, color: hov?T.ink:T.ink2,
        display:'flex', alignItems:'center', gap:8, transition:'color .25s',
      }}>
        Open this week's briefing <span style={{fontSize:16}}>→</span>
      </div>
    </Link>
  )
}

function MarketChip({name, n, active, onClick}){
  return (
    <div onClick={onClick} style={{
      flex:'0 0 auto', padding:'10px 16px', borderRadius:14, cursor:'pointer',
      background: active?'rgba(201,169,97,.1)':T.surface,
      border:`1px solid ${active?'rgba(201,169,97,.45)':T.line}`,
      fontSize:13, color:T.ink2, display:'flex', gap:8, alignItems:'center',
      transition:'all .18s ease',
    }}>
      <span style={{color:T.ink, fontWeight:600}}>{name}</span>
      <span style={{color:T.ink3}}>{n} {n===1?'territory':'territories'}</span>
      <span style={{fontSize:10, color:T.gold, border:'1px solid rgba(201,169,97,.4)',
        borderRadius:999, padding:'2px 8px'}}>Open</span>
      <span style={{fontSize:11, color: active?T.gold:T.ink3}}>{active?'▴':'▾'}</span>
    </div>
  )
}

const MARKET_LABEL = {
  WA_KING:'Seattle Eastside', WA_SNOHOMISH:'Edmonds & Snohomish',
  MA_NANTUCKET:'Nantucket', MA_DUKES:"Martha's Vineyard",
  MA_MIDDLESEX:'Greater Boston', MA_ESSEX:'Boston North Shore',
  MA_NORFOLK:'Brookline & Wellesley', MA_PLYMOUTH:'Boston South Shore',
  FL_PALM_BEACH:'Palm Beach', FL_COLLIER:'Naples', FL_INDIAN_RIVER:'Vero Beach',
  CT_FAIRFIELD:'Greenwich & Gold Coast', CT_LITCHFIELD:'Litchfield Hills',
  AZ_MARICOPA:'Scottsdale', TN_DAVIDSON:'Nashville', TX_TRAVIS:'Austin',
  TX_DALLAS:'Dallas', TX_COLLIN:'Plano & Frisco',
  CO_BOULDER:'Boulder', CO_DENVER:'Denver', CO_ARAPAHOE:'Cherry Hills', CO_PITKIN:'Aspen',
  MT_FLATHEAD:'Whitefish', MT_GALLATIN:'Bozeman', MT_MISSOULA:'Missoula', MT_PARK:'Livingston',
  MT_CARBON:'Red Lodge', MT_LAKE:'Flathead Lake', MT_RAVALLI:'Bitterroot Valley',
  MN_HENNEPIN:'Minneapolis', WI_MILWAUKEE:'Milwaukee',
  NC_BUNCOMBE:'Asheville', NC_WAKE:'Raleigh', CA_SANTACLARA:'Silicon Valley',
}

export default function V5Territories(){
  const [rows,setRows]=useState(null)
  const [claiming,setClaiming]=useState(null)   // zip being confirmed
  const [claimed,setClaimed]=useState(null)     // zip just claimed (celebration)
  const [claimError,setClaimError]=useState(null) // checkout error message
  const [busy,setBusy]=useState(false)
  const [mkt,setMkt]=useState(null)        // expanded market key
  const load=()=>api.get('/api/agent/territory-status').then(d=>setRows(d.zips||[]))
  useEffect(()=>{ load() },[])
  const mine = useMemo(()=>(rows||[]).filter(r=>r.status==='mine'),[rows])
  const open = useMemo(()=>(rows||[]).filter(r=>r.status==='available'),[rows])
  const markets = useMemo(()=>{
    const m=new Map()
    for(const r of (rows||[])){
      if(r.status==='mine') continue
      // everything not mine is open ground — count it honestly
      const k=r.market_key
      m.set(k,(m.get(k)||0)+1)
    }
    return [...m.entries()]
  },[rows])
  if(rows===null) return null

  const isM = typeof window!=='undefined' && window.innerWidth<760
  return (
    <main style={{maxWidth:1240, margin:'0 auto', padding: isM?'26px 16px 70px':'42px 28px 90px'}}>
      <div style={{marginBottom:34}}>
        <h1 style={{fontFamily:T.serif, fontSize:40, fontWeight:600, margin:0}}>Your territory</h1>
        <p style={{color:T.ink2, fontSize:15, margin:'10px 0 0', maxWidth:560, lineHeight:1.6}}>
          Every home, every signal, one agent — you. Open a briefing to see who's
          likely to sell this week.
        </p>
      </div>

      <div style={{display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(290px,1fr))',
        gap:20, marginBottom:64}}>
        {mine.map(z=><HeroCard key={z.zip_code} z={z}/>)}
      </div>

      {open.length>0 && (<>
        <div style={{display:'flex', alignItems:'center', gap:14, margin:'46px 0 18px'}}>
          <h2 style={{fontFamily:T.serif, fontSize:24, fontWeight:600, margin:0}}>Open ground</h2>
          <span style={{fontSize:13, color:T.ink3}}>{open.length} open · claim one and it's yours alone — forever</span>
        </div>
        <div style={{display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(250px,1fr))', gap:14, marginBottom:8}}>
          {open.slice(0,6).map(r=>(
            <div key={r.zip_code} style={{background:T.surface, border:`1px solid ${T.line}`,
              borderRadius:18, padding:'20px 22px'}}>
              <div style={{display:'flex', justifyContent:'space-between', alignItems:'baseline'}}>
                <span style={{fontFamily:T.serif, fontSize:21, fontWeight:600}}>{r.zip_code}</span>
                <span style={{fontSize:12, color:T.ink3}}>{r.city||''}</span>
              </div>
              <div style={{fontSize:12.5, color:T.ink2, margin:'8px 0 16px'}}>
                {MARKET_LABEL[r.market_key]||r.market_key}
                {r.parcel_count?` · ${Number(r.parcel_count).toLocaleString()} homes`:''}
              </div>
              <button onClick={()=>setClaiming(r)} style={{width:'100%', padding:'11px 0',
                borderRadius:999, border:'1px solid rgba(201,169,97,.45)', cursor:'pointer',
                background:'none', color:T.gold, fontFamily:T.sans, fontSize:13, fontWeight:700}}>
                Claim {r.zip_code} — $299/mo</button>
              <Link to={`/zip/${r.zip_code}`} style={{display:'block', textAlign:'center',
                marginTop:10, fontSize:12, color:T.ink3, textDecoration:'none'}}>
                Walk the ground first →</Link>
            </div>
          ))}
        </div>
      </>)}

      <div style={{display:'flex', alignItems:'baseline', justifyContent:'space-between', marginBottom:18}}>
        <h2 style={{fontFamily:T.serif, fontSize:24, fontWeight:600, margin:0}}>Across the map</h2>
        <span style={{fontSize:13, color:T.gold}}>All open · one agent per ZIP · claimed ground never resells</span>
      </div>
      <div style={{display:'flex', gap:12, flexWrap:'wrap'}}>
        {markets.map(([k,n])=><MarketChip key={k} name={MARKET_LABEL[k]||k} n={n}
          active={mkt===k} onClick={()=>setMkt(mkt===k?null:k)}/>)}
      </div>
      {mkt && (
        <div style={{display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(250px,1fr))',
          gap:14, marginTop:18}}>
          {(rows||[]).filter(r=>r.market_key===mkt).map(r=>(
            <div key={r.zip_code} style={{background:T.surface, border:`1px solid ${T.line}`,
              borderRadius:18, padding:'20px 22px'}}>
              <div style={{display:'flex', justifyContent:'space-between', alignItems:'baseline'}}>
                <span style={{fontFamily:T.serif, fontSize:21, fontWeight:600}}>{r.zip_code}</span>
                <span style={{fontSize:12, color:T.ink3}}>{r.city||''}</span>
              </div>
              <div style={{fontSize:12.5, color:T.ink2, margin:'8px 0 16px'}}>
                {r.parcel_count?`${Number(r.parcel_count).toLocaleString()} homes`:''}
                {r.current_call_now_count?` · ${r.current_call_now_count} to contact now`:''}
              </div>
              {r.status==='mine' ? (
                <Link to={`/zip/${r.zip_code}`} style={{display:'block', textAlign:'center',
                  padding:'11px 0', borderRadius:999, textDecoration:'none',
                  background:T.ink, color:'#0B0A09', fontFamily:T.sans,
                  fontSize:13, fontWeight:700}}>Open the briefing →</Link>
              ) : (<>
                <button onClick={()=>setClaiming(r)} style={{width:'100%', padding:'11px 0',
                  borderRadius:999, border:'1px solid rgba(201,169,97,.45)', cursor:'pointer',
                  background:'none', color:T.gold, fontFamily:T.sans, fontSize:13, fontWeight:700}}>
                  Claim {r.zip_code} — $299/mo</button>
                <Link to={`/zip/${r.zip_code}`} style={{display:'block', textAlign:'center',
                  marginTop:10, fontSize:12, color:T.ink3, textDecoration:'none'}}>
                  Walk the ground first →</Link>
              </>)}
            </div>
          ))}
        </div>
      )}
      {claiming && (
        <div onClick={()=>!busy&&setClaiming(null)} style={{position:'fixed', inset:0, zIndex:80,
          background:'rgba(0,0,0,.72)', display:'flex', alignItems:'center', justifyContent:'center'}}>
          <div onClick={e=>e.stopPropagation()} style={{width:'min(460px,92vw)',
            background:T.bg, border:`1px solid ${T.line2}`, borderRadius:24, padding:'34px 34px 30px'}}>
            <div style={{fontFamily:T.serif, fontSize:26, fontWeight:600, marginBottom:6}}>
              Claim {claiming.zip_code}</div>
            <p style={{fontSize:13.5, color:T.ink2, lineHeight:1.85, margin:'0 0 22px'}}>
              {MARKET_LABEL[claiming.market_key]||claiming.market_key}
              {claiming.parcel_count?` · ${Number(claiming.parcel_count).toLocaleString()} homes`:''}.
              One agent per ZIP — once it's yours, no other agent can ever buy in.
              Every signal, every briefing, every buyer introduction in {claiming.zip_code} routes to you.
            </p>
            <div style={{display:'flex', justifyContent:'space-between', padding:'14px 0',
              borderTop:`1px solid ${T.line}`, borderBottom:`1px solid ${T.line}`,
              fontSize:14, marginBottom:22}}>
              <span style={{color:T.ink2}}>Founding Agent rate</span>
              <span style={{fontWeight:700}}>$299/mo</span>
            </div>
            {claimError && (
              <p style={{fontSize:12.5, color:'#C97B61', lineHeight:1.6, margin:'0 0 14px'}}>
                {claimError}</p>
            )}
            <button disabled={busy} onClick={async()=>{
              setBusy(true); setClaimError(null)
              try{
                // Real purchase: Stripe Checkout session from the billing
                // API, then hand the browser to Stripe. On success Stripe
                // returns the agent to /zip/{zip}?welcome=1 (the webhook
                // has assigned the territory by then).
                const {checkout_url} = await api.post(`/api/billing/create-checkout`, {zip_code: claiming.zip_code})
                if(!checkout_url) throw new Error('No checkout URL returned — try again.')
                window.location.href = checkout_url
                return
              }catch(e){
                setClaimError(e?.message || 'Could not start checkout. Try again?')
              }
              setBusy(false)
            }} style={{width:'100%', padding:'14px 0', borderRadius:999, border:'none',
              cursor:'pointer', background:T.gold, color:'#151311', fontFamily:T.sans,
              fontSize:14, fontWeight:700}}>
              {busy?'Opening secure checkout…':'Claim it — $299/mo'}</button>
            <p style={{fontSize:11, color:T.ink3, textAlign:'center', margin:'12px 0 0'}}>
              Secure checkout via Stripe. Cancel anytime from your profile.</p>
          </div>
        </div>
      )}
      {claimed && (
        <div onClick={()=>setClaimed(null)} style={{position:'fixed', inset:0, zIndex:80,
          background:'rgba(0,0,0,.72)', display:'flex', alignItems:'center', justifyContent:'center'}}>
          <div onClick={e=>e.stopPropagation()} style={{width:'min(460px,92vw)', textAlign:'center',
            background:T.bg, border:'1px solid rgba(201,169,97,.4)', borderRadius:24, padding:'40px 34px'}}>
            <div style={{fontSize:40, marginBottom:10}}>🥂</div>
            <div style={{fontFamily:T.serif, fontSize:26, fontWeight:600, marginBottom:10}}>
              {claimed} is yours. Alone. Forever.</div>
            <p style={{fontSize:13.5, color:T.ink2, lineHeight:1.85, margin:'0 0 24px'}}>
              The fabric is waking up on your territory — court monitors, ownership graph,
              signal harvest. Your first briefing compiles this Sunday.</p>
            <button onClick={()=>setClaimed(null)} style={{padding:'12px 28px', borderRadius:999,
              border:'none', cursor:'pointer', background:T.ink, color:'#0B0A09',
              fontFamily:T.sans, fontSize:13.5, fontWeight:700}}>Walk the ground</button>
          </div>
        </div>
      )}
    </main>
  )
}
