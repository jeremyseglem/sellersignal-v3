import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { T, api, money } from './V5Shell.jsx'

/* Overture V5 — Buyer network. Registry of client searches, compose flow,
   and the match report. The demand side is free; searches are blind:
   territory agents see criteria, never the client. */

const VIEW_LABEL = {lake_washington:'Lake Washington', lake_sammamish:'Lake Sammamish',
  puget_sound:'Puget Sound', mount_rainier:'Mount Rainier', olympic_mountains:'Olympics',
  cascade_mountains:'Cascades', seattle_skyline:'Seattle skyline', bellevue_skyline:'Bellevue skyline',
  territorial:'Territorial', golf_course:'Golf course'}
const FEATURE_LABEL = {waterfront:'Waterfront', pool:'Pool', elevator:'Elevator',
  guest_house:'Guest house', view_protected:'Protected view', gated:'Gated',
  smart_home:'Smart home', wine_cellar:'Wine cellar', sport_court:'Sport court', dock:'Dock'}
const viewQ = v => VIEW_LABEL[v] || (v||'').replace(/_/g,' ')

function Pill({children, gold}){
  return <span style={{fontSize:11.5, fontWeight:600, padding:'4px 11px', borderRadius:999,
    background: gold?'rgba(201,169,97,.13)':'rgba(255,255,255,.05)',
    color: gold?T.gold:T.ink2,
    border:`1px solid ${gold?'rgba(201,169,97,.4)':T.line2}`}}>{children}</span>
}

function NeedCard({c, onReport, onDelete}){
  const cr = c.criteria || c
  const ff = cr.feature_filters || c.feature_filters || {}
  const views = ff.view_any || []
  const musts = Object.entries(ff).filter(([k,v])=>v===true).map(([k])=>FEATURE_LABEL[k]||k.replace(/_/g,' '))
  return (
    <div style={{background:T.surface, border:`1px solid ${T.line}`, borderRadius:20,
      padding:'24px 26px 20px'}}>
      {(c.responses&&c.responses.length>0) &&
        <div style={{marginBottom:12, padding:'9px 14px', borderRadius:12,
          background:'rgba(127,191,138,.1)', border:'1px solid rgba(127,191,138,.35)',
          fontSize:12.5, fontWeight:600, color:'#7FBF8A'}}>
          ✦ {c.responses.length} territory agent{c.responses.length>1?'s have':' has'} a fit for this client
        </div>}
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'baseline'}}>
        <div style={{fontFamily:T.serif, fontSize:19, fontWeight:600}}>{c.client_ref||'Client search'}</div>
        <span style={{fontSize:11.5, letterSpacing:'.12em', textTransform:'uppercase',
          color: c.status==='open'?'#7FBF8A':T.ink3, fontWeight:700}}>{c.status||'open'}</span>
      </div>
      <div style={{fontSize:13.5, color:T.ink2, margin:'10px 0 14px', lineHeight:1.8}}>
        {(c.zips||[]).join(' · ')} &nbsp;·&nbsp; {money(c.price_min)}–{money(c.price_max)}
        {c.beds_min?` · ${c.beds_min}+ beds`:''}
        {c.sqft_min?` · ${Number(c.sqft_min).toLocaleString()}+ sqft`:''}
      </div>
      <div style={{display:'flex', gap:7, flexWrap:'wrap', marginBottom:16}}>
        {views.map(v=><Pill key={v} gold>{viewQ(v)} view</Pill>)}
        {musts.map(m=><Pill key={m}>{m}</Pill>)}
      </div>
      {c.last_matched!=null && (
        <div style={{fontSize:13, color:T.gold, fontWeight:600, marginBottom:14}}>
          {c.last_matched} home{c.last_matched===1?'':'s'} match — none of them on the market.
        </div>
      )}
      <div style={{display:'flex', gap:10}}>
        <button onClick={onReport} style={{padding:'9px 18px', borderRadius:999, cursor:'pointer',
          background:T.ink, color:'#0B0A09', border:'none', fontFamily:T.sans,
          fontSize:12.5, fontWeight:700}}>Report</button>
        <button onClick={onDelete} style={{padding:'9px 18px', borderRadius:999, cursor:'pointer',
          background:'none', color:T.ink3, border:`1px solid ${T.line2}`, fontFamily:T.sans,
          fontSize:12.5}}>Retire</button>
      </div>
    </div>
  )
}

function Report({need, onBack}){
  const per = need.report_per_zip || {}
  return (
    <div>
      <button onClick={onBack} style={{background:'none', border:'none', color:T.ink3,
        cursor:'pointer', fontFamily:T.sans, fontSize:13, padding:0, marginBottom:22}}>← All searches</button>
      <div style={{fontFamily:T.serif, fontSize:28, fontWeight:600}}>{need.client_ref||'Client search'}</div>
      <div style={{fontSize:14, color:T.ink2, margin:'8px 0 24px'}}>
        {(need.zips||[]).join(' · ')} · {money(need.price_min)}–{money(need.price_max)}
        {need.beds_min?` · ${need.beds_min}+ beds`:''}
      </div>
      <div style={{background:'rgba(201,169,97,.07)', border:'1px solid rgba(201,169,97,.28)',
        borderRadius:18, padding:'22px 24px', marginBottom:8}}>
        <div style={{fontFamily:T.serif, fontSize:34, fontWeight:600, color:T.gold}}>
          {need.last_matched!=null?need.last_matched:'—'}
        </div>
        <div style={{fontSize:13.5, color:T.ink2, marginTop:4}}>
          homes match this search — none of them on the market.
        </div>
      </div>
      {Object.keys(per).length>0 && (
        <div style={{margin:'16px 0 6px'}}>
          {Object.entries(per).map(([z,d])=>(
            <div key={z} style={{display:'flex', justifyContent:'space-between',
              padding:'10px 4px', borderBottom:`1px solid ${T.line}`, fontSize:13.5}}>
              <span style={{color:T.ink2}}>{z}</span>
              <span>{d.matched} matched{d.signals?` · ${d.signals} with active signals`:''}</span>
            </div>
          ))}
        </div>
      )}
      {(need.responses&&need.responses.length>0) &&
        <div style={{margin:'18px 0', padding:'16px 20px', borderRadius:14,
          background:'rgba(127,191,138,.1)', border:'1px solid rgba(127,191,138,.35)'}}>
          <div style={{fontSize:14, fontWeight:700, color:'#7FBF8A'}}>
            ✦ An introduction is waiting
          </div>
          <p style={{fontSize:13, color:T.ink2, margin:'8px 0 0', lineHeight:1.7}}>
            {need.responses.length} territory agent{need.responses.length>1?'s':''} signaled
            a fit for this search. They'll reach out through the network — the home stays
            private until both of you choose.
          </p>
        </div>}
      <p style={{fontSize:13, color:T.ink2, lineHeight:1.8, margin:'20px 4px'}}>
        The agents who represent these territories can now see this search.
        Your client stays invisible; the homes stay private. When a fit develops
        a reason to sell, the introduction comes to you.
      </p>
    </div>
  )
}

function Compose({onDone, onCancel}){
  const [f,setF]=useState({client_ref:'', zips:'', price_min:'', price_max:'',
    beds_min:'', sqft_min:''})
  const [busy,setBusy]=useState(false)
  const num = v => {
    if (v == null || v === '') return null
    const n = Number(String(v).replace(/[^0-9.]/g,''))
    return Number.isFinite(n) ? n : null
  }
  const inp = {width:'100%', background:T.surface, border:`1px solid ${T.line2}`,
    borderRadius:12, color:T.ink, padding:'12px 14px', fontFamily:T.sans,
    fontSize:14, outline:'none', boxSizing:'border-box'}
  const lab = {fontSize:11.5, letterSpacing:'.1em', textTransform:'uppercase',
    color:T.ink3, fontWeight:700, display:'block', margin:'0 0 7px'}
  async function submit(){
    setBusy(true)
    try{
      const body = {
        client_ref: f.client_ref || null,
        zips: f.zips.split(/[,\s]+/).map(z=>z.trim()).filter(Boolean),
        price_min: num(f.price_min), price_max: num(f.price_max),
        beds_min: num(f.beds_min), sqft_min: num(f.sqft_min),
      }
      const r = await api.post('/overture-api/marketplace/needs', body)
      const id = r?.need?.id
      if(id){ try{ await api.post(`/overture-api/marketplace/needs/${id}/match`, {}) }catch(e){} }
      onDone()
    }catch(e){ setBusy(false) }
  }
  return (
    <div style={{maxWidth:560}}>
      <button onClick={onCancel} style={{background:'none', border:'none', color:T.ink3,
        cursor:'pointer', fontFamily:T.sans, fontSize:13, padding:0, marginBottom:22}}>← Cancel</button>
      <div style={{fontFamily:T.serif, fontSize:28, fontWeight:600, marginBottom:6}}>New client search</div>
      <p style={{fontSize:13.5, color:T.ink2, lineHeight:1.8, margin:'0 0 26px'}}>
        Blind to everyone: territory agents see the criteria, never the client.
        We search every home in the territory — not just listings.
      </p>
      <div style={{display:'grid', gap:18}}>
        <div><label style={lab}>Client reference (private to you)</label>
          <input style={inp} value={f.client_ref} placeholder="The Kaplans — relocating from SF"
            onChange={e=>setF({...f, client_ref:e.target.value})}/></div>
        <div><label style={lab}>ZIP codes</label>
          <input style={inp} value={f.zips} placeholder="98004, 98039"
            onChange={e=>setF({...f, zips:e.target.value})}/></div>
        <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:14}}>
          <div><label style={lab}>Price min</label>
            <input style={inp} value={f.price_min} placeholder="3,000,000"
              onChange={e=>setF({...f, price_min:e.target.value})}/></div>
          <div><label style={lab}>Price max</label>
            <input style={inp} value={f.price_max} placeholder="8,000,000"
              onChange={e=>setF({...f, price_max:e.target.value})}/></div>
        </div>
        <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:14}}>
          <div><label style={lab}>Beds min</label>
            <input style={inp} value={f.beds_min} placeholder="4"
              onChange={e=>setF({...f, beds_min:e.target.value})}/></div>
          <div><label style={lab}>Sqft min</label>
            <input style={inp} value={f.sqft_min} placeholder="4,000"
              onChange={e=>setF({...f, sqft_min:e.target.value})}/></div>
        </div>
        <button onClick={submit} disabled={busy} style={{padding:'14px 0', borderRadius:999,
          border:'none', cursor:'pointer', background:T.gold, color:'#151311',
          fontFamily:T.sans, fontSize:14, fontWeight:700}}>
          {busy?'Matching against the territory…':'Post the search'}</button>
      </div>
    </div>
  )
}

export default function V5Network(){
  const [needs,setNeeds]=useState(null)
  const [view,setView]=useState('list')   // list | compose | report
  const [sel,setSel]=useState(null)
  const load=()=>api.get('/api/marketplace/needs').then(d=>setNeeds(d.needs||[])).catch(()=>setNeeds([]))
  useEffect(()=>{ load() },[])
  const isM = typeof window!=='undefined' && window.innerWidth<760
  return (
    <main style={{maxWidth:1120, margin:'0 auto', padding: isM?'26px 16px 70px':'42px 28px 90px'}}>
      {view==='compose' ? <Compose onDone={()=>{setView('list'); load()}} onCancel={()=>setView('list')}/>
      : view==='report' && sel ? <Report need={sel} onBack={()=>{setView('list'); load()}}/>
      : (<>
        <div style={{display:'flex', justifyContent:'space-between', alignItems:'baseline',
          flexWrap:'wrap', gap:14, marginBottom:10}}>
          <h1 style={{fontFamily:T.serif, fontSize:'clamp(28px,3.4vw,40px)', fontWeight:600, margin:0}}>
            Buyer network</h1>
          <button onClick={()=>setView('compose')} style={{padding:'11px 22px', borderRadius:999,
            border:'none', cursor:'pointer', background:T.gold, color:'#151311',
            fontFamily:T.sans, fontSize:13, fontWeight:700}}>New search</button>
        </div>
        <p style={{fontSize:14, color:T.ink2, lineHeight:1.8, margin:'0 0 30px', maxWidth:640}}>
          Your clients' searches, run against every home in the territory — not just
          listings. Free for buyer's agents, forever.
          {' '}<Link to="/network/classic" style={{color:T.ink3}}>classic view</Link>
        </p>
        {needs===null ? null : needs.length===0 ? (
          <div style={{background:T.surface, border:`1px solid ${T.line}`, borderRadius:20,
            padding:'40px 34px', maxWidth:560}}>
            <div style={{fontFamily:T.serif, fontSize:21, fontWeight:600, marginBottom:10}}>
              No client searches yet.</div>
            <p style={{fontSize:13.5, color:T.ink2, lineHeight:1.8, margin:0}}>
              Post what your client wants and we'll tell you how many homes match —
              including every one that isn't for sale.</p>
          </div>
        ) : (
          <div style={{display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(320px,1fr))', gap:18}}>
            {needs.map(c=>(
              <NeedCard key={c.id} c={c}
                onReport={()=>{setSel(c); setView('report')}}
                onDelete={async()=>{ try{ await api.del(`/api/marketplace/needs/${c.id}`) }catch(e){}; load() }}/>
            ))}
          </div>
        )}
      </>)}
    </main>
  )
}
