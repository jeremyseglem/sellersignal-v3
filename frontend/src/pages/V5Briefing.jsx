import React, { useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams, Link } from 'react-router-dom'
import SkipTracePanel from '../components/SkipTracePanel.jsx'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { T, api, money, Aperture, useIsMobile } from './V5Shell.jsx'

/* ── Hinge-style briefing: big lead cards, satellite map, dossier ── */

const ARCH_LABEL = {
  divorce:'Divorce filing', probate:'Estate', trust:'Trust · long hold',
  llc:'Entity-held', absentee:'Out-of-state owner', tenure:'Long tenure',
  individual_settled:'Long tenure',
}
function archOf(l){
  if(l.has_divorce_signal) return 'Divorce filing'
  if(l.has_probate_signal) return 'Estate transition'
  if(l.is_absentee||l.is_out_of_state) return 'Out-of-state owner'
  const a=(l.archetype||l.signal_family||'').toLowerCase()
  for(const k in ARCH_LABEL) if(a.includes(k)) return ARCH_LABEL[k]
  return 'Signal'
}

const SIGKIND = {probate:'Estate filing', divorce:'Dissolution filing',
  trust:'Trust event', obituary:'Obituary match', tax_foreclosure:'Tax foreclosure notice'}
function happeningFor(l){
  const hm = l.harvester_matches || []
  const copy = l.copy || {}
  const fresh = copy.happening && !/no selling signals/i.test(copy.happening)
  if (fresh) return copy.happening
  if (hm.length){
    const m = hm[0]
    const kind = SIGKIND[m.signal_type] || 'A public-record signal'
    const verb = m.signal_type==='obituary' ? 'published' : 'filed'
    const when = m.event_date ? ` — ${verb} ${new Date(m.event_date+'T00:00:00')
      .toLocaleDateString('en-US',{month:'short', day:'numeric', year:'numeric'})}` : ''
    return `${kind} verified${when}. The decision window has opened.`
  }
  const fam = (l.signal_family||'') + ' ' + (l.archetype||'')
  const ten = l.tenure_years ? Math.round(l.tenure_years) : null
  if (/absentee|out.?of.?state/i.test(fam))
    return 'Out-of-state owner — carrying costs without the daily use. These homes change hands quietly, and the owner rarely calls a local agent first.'
  if (/llc|investor/i.test(fam))
    return 'Held in an entity — a portfolio decision, not an emotional one. When the disposition window opens, it opens fast.'
  if (/trust/i.test(fam))
    return 'Held in trust with an aging grantor. Succession decisions are being made around this home right now — usually before anyone outside the family hears.'
  return `${ten?ten+' years in':'Deep tenure'} — statistically inside the transition window. Nothing public to chase; you get there first.`
}
function Chip({children, gold}){
  return <span style={{
    fontSize:11.5, fontWeight:600, padding:'5px 11px', borderRadius:999,
    background: gold?'rgba(201,169,97,.14)':'rgba(255,255,255,.06)',
    color: gold?T.gold:T.ink2, border:`1px solid ${gold?'rgba(201,169,97,.3)':T.line}`,
  }}>{children}</span>
}

function LeadCard({l, onOpen, eager}){
  const [hov,setHov]=useState(false)
  const [thumb,setThumb]=useState(null)
  const cardRef=useRef(null)
  useEffect(()=>{
    const el=cardRef.current
    if(!el || !l.pin) return
    let dead=false
    if(eager){
      api.get(`/api/map/streetview/${l.pin}`)
        .then(r=>{ if(!dead && r && r.url) setThumb(r.url) })
        .catch(()=>{})
      return ()=>{ dead=true }
    }
    const io=new IntersectionObserver((ents)=>{
      if(ents.some(e=>e.isIntersecting)){
        io.disconnect()
        api.get(`/api/map/streetview/${l.pin}`)
          .then(r=>{ if(!dead && r && r.url) setThumb(r.url) })
          .catch(()=>{})
      }
    },{rootMargin:'600px'})
    io.observe(el)
    return ()=>{ dead=true; io.disconnect() }
  },[l.pin,eager])
  return (
    <div ref={cardRef} onClick={()=>onOpen(l)}
      onMouseEnter={()=>setHov(true)} onMouseLeave={()=>setHov(false)}
      style={{
        background: hov?T.surface2:T.surface, cursor:'pointer',
        border:`1px solid ${hov?T.line2:T.line}`, borderRadius:18,
        padding:'20px 22px', transition:'all .22s ease',
        transform: hov?'translateY(-1px)':'none',
      }}>
      <div style={{display:'flex', gap:14}}>
        {thumb ? (
          <img src={thumb} alt="" loading="lazy"
            style={{width:96, height:96, objectFit:'cover', borderRadius:12,
              flexShrink:0, border:`1px solid ${T.line}`}}
            onError={e=>{ e.currentTarget.style.display='none' }}/>
        ) : null}
        <div style={{flex:1, minWidth:0}}>
          <div style={{display:'flex', justifyContent:'space-between', alignItems:'flex-start', gap:12}}>
            <div>
              <div style={{fontFamily:T.serif, fontSize:19, fontWeight:600, lineHeight:1.25}}>
                {l.owner_name || 'Owner of record'}
              </div>
              <div style={{fontSize:13, color:T.ink2, marginTop:4}}>{l.address}</div>
            </div>
            <div style={{fontFamily:T.serif, fontSize:18, fontWeight:600, whiteSpace:'nowrap'}}>
              {money(l.value)}
            </div>
          </div>
          <p style={{fontSize:13, lineHeight:1.6, color:T.ink2, margin:'12px 0 0'}}>
            {happeningFor(l)}
          </p>
          <div style={{display:'flex', gap:8, marginTop:14, flexWrap:'wrap'}}>
            <Chip gold>{archOf(l)}</Chip>
            {l.tenure_years ? <Chip>{Math.round(l.tenure_years)}-yr hold</Chip> : null}
            {l.is_out_of_state ? <Chip>Out-of-state owner</Chip>
              : l.is_absentee ? <Chip>Absentee owner</Chip> : null}
            {(l.owner_type==='trust') ? <Chip>Held in trust</Chip>
              : (l.owner_type==='llc'||l.owner_type==='company') ? <Chip>Entity-held</Chip> : null}
            {l.is_new_this_week ? <Chip>New this week</Chip> : null}
          </div>
        </div>
      </div>
    </div>
  )
}

/* ---------- satellite map with tiered dots ---------- */
function BriefMap({zip, leadsByPin, leadTypeByPin, pipelinePins, onOpenLead}){
  const ref=useRef(null), mapRef=useRef(null)
  useEffect(()=>{
    let dead=false
    Promise.all([api.get(`/api/map/${zip}?slim=1`), api.get(`/api/map/${zip}/bounds`),
                 api.get('/api/zip-polygons').catch(()=>null)])
      .then(([m,b,zp])=>{
        if(dead||!ref.current) return
        const style={version:8,sources:{sat:{type:'raster',
          tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
          tileSize:256, attribution:'Imagery © Esri'}},
          layers:[{id:'sat',type:'raster',source:'sat',
                   paint:{'raster-brightness-max':.72,'raster-saturation':-.25}}]}
        const map=new maplibregl.Map({container:ref.current, style,
          bounds:[[b.min_lng,b.min_lat],[b.max_lng,b.max_lat]], fitBoundsOptions:{padding:34},
          attributionControl:{compact:true}})
        map.addControl(new maplibregl.NavigationControl({showCompass:false}), 'top-right')
        mapRef.current=map
        setTimeout(()=>{try{map.resize()}catch(e){}}, 120)
        setTimeout(()=>{try{map.resize()}catch(e){}}, 600)
        map.on('load',()=>{
          const bf=(zp&&zp.features||[]).find(f=>f.properties&&f.properties.zip===zip)
          if(bf){
            map.addSource('zb',{type:'geojson',data:bf})
            map.addLayer({id:'zb-fill',type:'fill',source:'zb',
              paint:{'fill-color':'#E0B458','fill-opacity':0.045}})
            map.addLayer({id:'zb-line',type:'line',source:'zb',
              paint:{'line-color':'#E0B458','line-width':2,'line-opacity':.75}})
          }
          const inPoly = (()=>{
            if(!bf) return null
            const rings = bf.geometry.type==='Polygon' ? [bf.geometry.coordinates]
                        : bf.geometry.type==='MultiPolygon' ? bf.geometry.coordinates : []
            return (lng,lat)=>{
              for(const poly of rings){
                const outer = poly[0]; let inside=false
                for(let i=0,j=outer.length-1;i<outer.length;j=i++){
                  const [xi,yi]=outer[i],[xj,yj]=outer[j]
                  if(((yi>lat)!==(yj>lat)) && (lng < (xj-xi)*(lat-yi)/(yj-yi)+xi)) inside=!inside
                }
                if(inside) return true
              }
              return false
            }
          })()
          const byPin={}
          for(const p of (m.parcels||[])) byPin[p.pin]=p
          const feats=[]
          for(const p of (m.parcels||[])){
            if(inPoly && !inPoly(p.lng, p.lat)) continue
            const isLead = leadTypeByPin && leadTypeByPin[p.pin]
            const isPipe = pipelinePins && pipelinePins.has(p.pin)
            feats.push({type:'Feature',
              properties:{
                pin:p.pin,
                cat: isLead ? 'lead' : (isPipe ? 'pipe' : 'fabric'),
                t: isLead || '',
              },
              geometry:{type:'Point',coordinates:[p.lng,p.lat]}})
          }
          if(leadTypeByPin){
            for(const pin in leadTypeByPin){
              if(!byPin[pin] && leadsByPin[pin] && leadsByPin[pin].lat && leadsByPin[pin].lng){
                if(inPoly && !inPoly(leadsByPin[pin].lng, leadsByPin[pin].lat)) continue
                feats.push({type:'Feature',
                  properties:{pin, cat:'lead', t:leadTypeByPin[pin]},
                  geometry:{type:'Point',coordinates:[leadsByPin[pin].lng, leadsByPin[pin].lat]}})
              }
            }
          }
          map.addSource('px',{type:'geojson',data:{type:'FeatureCollection',features:feats}})
          const typeColor=['match',['get','t'],
            'probate','#E0B458',
            'divorce','#E27D6A',
            'aging_trust','#B08BD9',
            'llc_long_hold','#6FB3A8',
            'absentee','#7FA8E0',
            'long_tenure','#7FBF8A',
            '#E0B458']
          map.addLayer({id:'px-fabric',type:'circle',source:'px',
            filter:['==',['get','cat'],'fabric'],
            paint:{'circle-radius':1.6,'circle-color':'rgba(244,241,236,.16)'}})
          map.addLayer({id:'px-pipe',type:'circle',source:'px',
            filter:['==',['get','cat'],'pipe'],
            paint:{'circle-radius':4,'circle-color':'rgba(138,155,184,.85)'}})
          map.addLayer({id:'px-leads',type:'circle',source:'px',
            filter:['==',['get','cat'],'lead'],
            paint:{
              'circle-radius':['interpolate',['linear'],['zoom'],10,7.5,13,6.5,16,8],
              'circle-color':typeColor,
              'circle-stroke-width':1.5,
              'circle-stroke-color':'rgba(0,0,0,.55)',
            }})
          map.on('click',(e)=>{
            const pad=10
            const feats=map.queryRenderedFeatures(
              [[e.point.x-pad,e.point.y-pad],[e.point.x+pad,e.point.y+pad]],
              {layers:['px-leads','px-pipe','px-fabric']})
            if(!feats.length) return
            const rank={'lead':0,'pipe':1,'fabric':2}
            feats.sort((a,b)=>rank[a.properties.cat]-rank[b.properties.cat])
            const f=feats[0]
            const pn=f.properties.pin
            if(f.properties.cat==='lead' && onOpenLead && leadsByPin[pn]){
              onOpenLead(leadsByPin[pn])
            }
          })
          for(const lyr of ['px-leads','px-pipe']){
            map.on('mouseenter',lyr,()=>{map.getCanvas().style.cursor='pointer'})
            map.on('mouseleave',lyr,()=>{map.getCanvas().style.cursor=''})
          }
        })
      }).catch(()=>{})
    return ()=>{dead=true; mapRef.current&&mapRef.current.remove()}
  },[zip])
  return <div ref={ref} style={{position:'absolute',inset:0}}/>
}

/* ---------- dossier slide-over ---------- */
function Dossier({pin, zip, seed, onClose}){
  const [p,setP]=useState(null),[why,setWhy]=useState(null),[queued,setQueued]=useState(false)
  const [scripts,setScripts]=useState(null)
  const [sTab,setSTab]=useState('phone')
  const [copied,setCopied]=useState(false)
  const [photo,setPhoto]=useState(null)
  const [seq,setSeq]=useState(undefined)
  const [openLetter,setOpenLetter]=useState(null)
  const [mailView,setMailView]=useState(null)
  useEffect(()=>{
    setQueued(false); setPhoto(null)
    api.get(`/api/parcels/${pin}`).then(setP).catch(()=>setP({}))
    api.get(`/api/parcels/${pin}/why`).then(setWhy).catch(()=>setWhy(null))
    api.get(`/api/map/streetview/${pin}`).then(r=>{ if(r&&r.url) setPhoto(r.url) }).catch(()=>{})
    api.get(`/api/parcels/${pin}/scripts`).then(setScripts).catch(()=>{})
    api.get(`/api/letters/by-parcel/${pin}`)
      .then(r=>setSeq((r.sequences&&r.sequences[0])||null))
      .catch(()=>setSeq(null))
  },[pin])
  const l = seed
  const copy = (p&&p.copy) || l.copy || {}
  const hm = (p&&p.harvester_matches) || l.harvester_matches || []
  const cleanWhy = typeof copy.why==='string'
    ? copy.why.replace(/\s*[a-z_]+ \((strict|fuzzy)\):.*$/,'').trim() : null
  const SRC = {kc_superior_court:'King County Superior Court',
               snohomish_superior_court:'Snohomish County Superior Court'}
  const SIG = {probate:'Estate filing', divorce:'Dissolution filing', trust:'Trust event', obituary:'Obituary match', tax_foreclosure:'Tax foreclosure notice'}
  const fmtd = d => d ? new Date(d+'T00:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}) : null
  const sale = p&&p.last_arms_length_price ? p : null
  return (<>
    <div onClick={onClose} style={{position:'fixed',inset:0,background:'rgba(0,0,0,.66)',zIndex:60}}/>
    <div style={{position:'fixed',top:0,right:0,bottom:0,width:'min(540px,94vw)',zIndex:61,
      background:T.bg, borderLeft:`1px solid ${T.line2}`, overflowY:'auto',
      padding:'34px 34px 60px', animation:'ovIn .32s cubic-bezier(.3,.7,.2,1)'}}>
      <style>{`@keyframes ovIn{from{transform:translateX(36px);opacity:0}to{transform:none;opacity:1}}`}</style>
      <div style={{display:'flex',justifyContent:'space-between',marginBottom:26}}>
        <span style={{fontSize:12,letterSpacing:'.14em',color:T.ink3,fontWeight:600}}>DOSSIER</span>
        <button onClick={onClose} style={{background:'none',border:'none',color:T.ink2,cursor:'pointer',fontSize:14}}>Close ✕</button>
      </div>
      {photo && <img src={photo} alt="" style={{width:'100%', height:210, objectFit:'cover',
        borderRadius:16, marginBottom:20, border:`1px solid ${T.line}`}}/>}
      <div style={{fontFamily:T.serif,fontSize:27,fontWeight:600,lineHeight:1.2}}>{l.owner_name}</div>
      <div style={{fontSize:14,color:T.ink2,margin:'8px 0 16px'}}>{l.address}</div>
      <div style={{display:'flex',gap:8,flexWrap:'wrap',marginBottom:28}}>
        <Chip gold>{archOf(l)}</Chip>
        <Chip>{money(l.value)}</Chip>
        {l.tenure_years?<Chip>{Math.round(l.tenure_years)}-yr hold</Chip>:null}
        {l.owner_city?<Chip>Owner in {l.owner_city}{l.owner_state?`, ${l.owner_state}`:''}</Chip>:null}
      </div>

      <Section title="What's happening">
        <p style={{...pStyle,color:T.ink}}>{happeningFor({...l, harvester_matches: hm, copy})}</p>
      </Section>

      {hm.length>0 ? (
        <Section title="The record">
          {hm.slice(0,4).map((m,i)=>(
            <div key={i} style={{background:T.surface, border:`1px solid ${T.line}`,
              borderRadius:14, padding:'14px 16px', marginBottom:10}}>
              <div style={{display:'flex', justifyContent:'space-between', alignItems:'baseline'}}>
                <span style={{fontSize:13.5, fontWeight:600}}>{SIG[m.signal_type]||m.signal_type}</span>
                <span style={{fontSize:12, color:m.match_strength==='strict'?T.gold:T.ink3, fontWeight:600}}>
                  {m.match_strength==='strict'?'Verified match':'Probable match'}
                </span>
              </div>
              <div style={{fontSize:12.5, color:T.ink2, marginTop:6, lineHeight:1.7}}>
                {SRC[m.source_type]||(m.source_type||'').replace(/_/g,' ')}
                {m.document_ref?` \u00b7 Case ${m.document_ref}`:''}
                {m.event_date?` \u00b7 ${fmtd(m.event_date)}`:''}
              </div>
              {(m.party_names||[]).slice(0,2).map((pn,j)=>(
                <div key={j} style={{fontSize:12.5, color:T.ink3, marginTop:4}}>
                  {pn.raw}{pn.role?` \u2014 ${pn.role}`:''}
                </div>
              ))}
            </div>
          ))}
          <p style={{fontSize:11.5, color:T.ink3, margin:'4px 0 0'}}>
            Sourced from public court records, matched to this parcel with
            zero-false-positive identity resolution.
          </p>
        </Section>
      ):null}

      {cleanWhy ? (
        <Section title="Why it matters">
          <p style={pStyle}>{cleanWhy}</p>
        </Section>
      ):null}


      {(!hm.length && why?.transition_window) ? (
        <Section title="Outlook">
          <p style={pStyle}>{why.why_not_selling}</p>
          <div style={{display:'flex', gap:8, flexWrap:'wrap', marginTop:6}}>
            <Chip>{why.transition_window}</Chip>
            {why.confidence?<Chip>{why.confidence} confidence</Chip>:null}
          </div>
        </Section>
      ):null}


      {(p&&p.sales_history&&p.sales_history.length) ? (
        <Section title="Sales history">
          {p.sales_history.slice(0,5).map((sh,i)=>(
            <div key={i} style={{display:'flex', justifyContent:'space-between',
              padding:'7px 2px', borderBottom:`1px solid ${T.line}`, fontSize:13}}>
              <span style={{color:T.ink2}}>{fmtd(sh.sale_date)||'—'}</span>
              <span>{money(sh.sale_price)}</span>
            </div>
          ))}
        </Section>
      ):null}

      <Section title="Reach the owner">
        <SkipTracePanel pin={pin}/>
      </Section>

      {scripts?.call ? (
        <Section title="What to say">
          <div style={{display:'flex', gap:8, marginBottom:12}}>
            {[['phone','Phone'],['door','Door knock'],['letter','Letter']].map(([k,lbl])=>(
              <button key={k} onClick={()=>{setSTab(k); setCopied(false)}} style={{
                fontFamily:T.sans, fontSize:12.5, fontWeight:600, cursor:'pointer',
                padding:'7px 14px', borderRadius:999,
                background: sTab===k?'rgba(224,180,88,.16)':'transparent',
                color: sTab===k?T.gold:T.ink2,
                border:`1px solid ${sTab===k?'rgba(224,180,88,.4)':T.line2}`,
              }}>{lbl}</button>
            ))}
          </div>
          <div style={{background:T.surface, border:`1px solid ${T.line}`, borderRadius:14,
            padding:'16px 18px', fontSize:13.5, lineHeight:1.85, color:T.ink,
            whiteSpace:'pre-line'}}>
            {scripts[{phone:'call',door:'door',letter:'letter'}[sTab]]}
          </div>
          <button onClick={()=>{
            try{ navigator.clipboard.writeText(scripts[{phone:'call',door:'door',letter:'letter'}[sTab]]); setCopied(true) }catch(e){}
          }} style={{marginTop:10, padding:'8px 16px', borderRadius:999, cursor:'pointer',
            background:'none', color: copied?'#7FBF8A':T.ink2,
            border:`1px solid ${T.line2}`, fontFamily:T.sans, fontSize:12}}>
            {copied?'✓ Copied':'Copy script'}</button>
          <p style={{fontSize:11, color:T.ink3, marginTop:10, lineHeight:1.7}}>
            Written from this lead's signal — never referencing the record itself.
            The owner hears service; the record stays your intelligence.
            {' '}<a href="/profile/voice" style={{color:T.gold}}>Make them sound like you →</a>
          </p>
        </Section>
      ):null}

      <Section title="Letter campaign">
        {seq===undefined ? null : seq ? (
          <div style={{background:T.surface, border:`1px solid ${T.line}`, borderRadius:14,
            padding:'16px 18px'}}>
            <div style={{display:'flex', justifyContent:'space-between', alignItems:'baseline'}}>
              <span style={{fontSize:13.5, fontWeight:600}}>
                {seq.status==='completed'?'Completed sequence'
                 : seq.status==='planned'?'The 180-day sequence — ready to begin'
                 : 'Active sequence'}</span>
              <span style={{fontSize:12, color:T.ink3}}>
                {seq.letters?.length||0} letters</span>
            </div>
            <div style={{display:'flex', gap:6, margin:'12px 0'}}>
              {(seq.letters||[]).map((lt,i)=>(
                <span key={i} title={lt.title} style={{width:10, height:10, borderRadius:'50%',
                  background: lt.status==='delivered'?'#7FBF8A'
                           : lt.status==='sent'?'#C9A961'
                           : 'rgba(244,241,236,.18)'}}/>
              ))}
            </div>
            <div style={{fontSize:12.5, color:T.ink2, lineHeight:1.8}}>
              {seq.started_at?`Started ${new Date(seq.started_at).toLocaleDateString('en-US',{month:'short',day:'numeric'})}`:''}
              {seq.next_send_at?` · next piece ${new Date(seq.next_send_at).toLocaleDateString('en-US',{month:'short',day:'numeric'})}`:''}
              {' '}· <a href="/letters" style={{color:T.gold}}>view in Letters</a>
            </div>
            {(seq.letters||[]).some(lt=>lt.body) && (
              <div style={{marginTop:12, borderTop:`1px solid ${T.line}`, paddingTop:10}}>
                <div style={{display:'flex', gap:8, flexWrap:'wrap'}}>
                  {(seq.letters||[]).map((lt,i)=> lt.body ? (
                    <button key={i} onClick={()=>{setOpenLetter(openLetter===i?null:i); setMailView(null)}}
                      style={{fontFamily:T.sans, fontSize:11.5, fontWeight:600, cursor:'pointer',
                        padding:'6px 12px', borderRadius:999,
                        background: openLetter===i?'rgba(224,180,88,.16)':'transparent',
                        color: openLetter===i?T.gold:T.ink2,
                        border:`1px solid ${openLetter===i?'rgba(224,180,88,.4)':T.line2}`}}>
                      Day {lt.day??i+1}{lt.title?` · ${lt.title}`:''}
                    </button>
                  ) : null)}
                </div>
                {openLetter!=null && seq.letters[openLetter]?.body && (
                  <div style={{marginTop:10, background:'rgba(0,0,0,.25)',
                    border:`1px solid ${T.line}`, borderRadius:12, padding:'14px 16px',
                    fontSize:12.5, lineHeight:1.85, color:T.ink2, whiteSpace:'pre-line'}}>
                    {seq.letters[openLetter].body}
                    <div style={{marginTop:12}}>
                      <button onClick={async()=>{
                        if(mailView!=null){ setMailView(null); return }
                        try{
                          const r=await api.post('/api/letters/preview',
                            {pin, letter_index: seq.letters[openLetter].letter_index||openLetter+1})
                          setMailView(r.html||null)
                        }catch(e){ setMailView(null) }
                      }} style={{background:'none', border:`1px solid ${T.line2}`,
                        color:T.gold, borderRadius:999, padding:'7px 14px', cursor:'pointer',
                        fontFamily:T.sans, fontSize:11.5, fontWeight:600}}>
                        {mailView!=null?'Hide the letterhead':'View as it mails →'}</button>
                    </div>
                    {mailView!=null && (
                      <iframe title="letter" srcDoc={mailView} style={{marginTop:10,
                        width:'100%', height:420, border:`1px solid ${T.line2}`,
                        borderRadius:10, background:'#fff'}}/>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <p style={{...pStyle, fontSize:12.5}}>
            No letter sequence yet. Begin outreach and the composer drafts a
            three-piece campaign in your voice — $1.38 per piece, tracked in the
            Letters tab.
          </p>
        )}
      </Section>

      {copy.action ? (
        <Section title="Your move">
          <p style={{...pStyle, fontStyle:'italic', color:T.ink}}>{copy.action}</p>
        </Section>
      ):null}

      <button onClick={async()=>{
        setQueued(true)
        try{ await api.post('/api/demo/queue', {...l, zip}) }catch(e){}
        try{
          const r = await api.get(`/api/letters/by-parcel/${pin}`)
          setSeq((r.sequences&&r.sequences[0])||null)
        }catch(e){}
      }} disabled={queued} style={{
        width:'100%', padding:'15px 0', borderRadius:999, border:'none',
        cursor:queued?'default':'pointer',
        background: queued?'rgba(127,191,138,.16)':T.ink,
        color: queued?'#7FBF8A':'#0B0A09',
        fontFamily:T.sans, fontSize:14, fontWeight:600, marginTop:8,
        borderTop: queued?'1px solid rgba(127,191,138,.4)':'none',
      }}>{queued?'✓ Queued — see My leads':'Begin outreach'}</button>
    </div>
  </>)
}
const pStyle={fontSize:14, lineHeight:1.75, color:T.ink2, margin:'0 0 10px'}
function Section({title,children}){
  return <div style={{marginBottom:26}}>
    <div style={{fontSize:11.5, letterSpacing:'.12em', fontWeight:700, color:T.ink3,
      textTransform:'uppercase', marginBottom:10}}>{title}</div>
    {children}
  </div>
}

/* ---------- page ---------- */
export default function V5Briefing(){
  const {zip}=useParams()
  const [sp] = useSearchParams()
  const [b,setB]=useState(null)
  const [open,setOpen]=useState(null)
  const [showAllBn,setShowAllBn]=useState(false)
  const [demand,setDemand]=useState(null)
  const isM = useIsMobile()
  const [mView,setMView]=useState('leads')
  const [tab,setTab]=useState('all')
  const [openBrief,setOpenBrief]=useState(null)
  const [responded,setResponded]=useState({})
  const [q,setQ]=useState('')
  useEffect(()=>{ api.get(`/api/briefings/${zip}`).then(setB) },[zip])
  useEffect(()=>{ api.get(`/api/marketplace/demand/${zip}`).then(setDemand).catch(()=>{}) },[zip])
  useEffect(()=>{
    const dp = sp.get('pin')
    if(dp && b && !open){
      const l = leadsByPin[dp]
      if(l) setOpen(l)
    }
  },[b])
  if(!b) return null
  if(b.compiling || (b.detail && !b.playbook)) return (
    <main style={{maxWidth:760, margin:'0 auto', padding:'80px 28px', textAlign:'center'}}>
      <style>{`@keyframes ovSpin{to{transform:rotate(360deg)}}`}</style>
      <div style={{width:44, height:44, margin:'0 auto 26px', borderRadius:'50%',
        border:'2px solid rgba(201,169,97,.25)', borderTopColor:'#C9A961',
        animation:'ovSpin 1.1s linear infinite'}}/>
      <h1 style={{fontFamily:T.serif, fontSize:30, fontWeight:600, margin:'0 0 12px'}}>
        {zip} is compiling.</h1>
      <p style={{fontSize:14.5, color:T.ink2, lineHeight:1.9, maxWidth:520, margin:'0 auto 26px'}}>
        Court monitors are on. The ownership graph is building
        {b.stats?.total_parcels?` across ${Number(b.stats.total_parcels).toLocaleString()} homes`:''}.
        Your first briefing lands Sunday — from then on, every signal in {zip} reaches
        you before it reaches anyone.
      </p>
      <Link to="/territories" style={{color:T.gold, fontSize:13.5}}>← Back to your territories</Link>
    </main>
  )
  const pb=b.playbook||{}
  const buckets = pb.contact_now || {}
  const totals = pb.contact_now_totals || {}
  const TYPE = {probate:'Estate', divorce:'Divorce', aging_trust:'Trust',
                llc_long_hold:'LLC hold', absentee:'Absentee', long_tenure:'Long tenure'}
  const allCn = (pb.call_now||[])
  const cnRaw = tab==='all' ? allCn : (buckets[tab]||[])
  const cn = q.trim() ? cnRaw.filter(l=>{
    const t=q.trim().toLowerCase()
    return (l.owner_name||'').toLowerCase().includes(t)
        || (l.address||'').toLowerCase().includes(t)
        || String(l.pin||'').includes(t)
  }) : cnRaw
  const bn = (pb.build_now||[])
  const st = b.stats || {}
  const leadsByPin = {}, leadTypeByPin = {}
  for(const [k,list] of Object.entries(buckets)){
    for(const l of (list||[])){ leadsByPin[l.pin]=l; leadTypeByPin[l.pin]=k }
  }
  for(const l of allCn){ leadsByPin[l.pin]=l; if(!leadTypeByPin[l.pin]) leadTypeByPin[l.pin]=(l.has_divorce_signal?'divorce':l.has_probate_signal?'probate':'long_tenure') }
  const pipelinePins = new Set((pb.build_now||[]).map(l=>l.pin))
  for(const l of (pb.build_now||[])) leadsByPin[l.pin]=l
  return (
    <div style={{display:'flex', flexDirection:isM?'column':'row',
      height:isM?'auto':'calc(100vh - 62px)', minHeight:isM?'calc(100vh - 54px)':'auto'}}>
      {isM && (
        <div style={{display:'flex', gap:8, padding:'12px 16px 2px'}}>
          {['leads','map'].map(v=>(
            <button key={v} onClick={()=>setMView(v)} style={{
              flex:1, padding:'10px 0', borderRadius:999, cursor:'pointer',
              fontFamily:T.sans, fontSize:13, fontWeight:600,
              background: mView===v?'rgba(224,180,88,.16)':'transparent',
              color: mView===v?T.gold:T.ink2,
              border:`1px solid ${mView===v?'rgba(224,180,88,.4)':T.line2}`,
            }}>{v==='leads'?'Leads':'Map'}</button>
          ))}
        </div>
      )}
      {/* leads column */}
      <div style={{flex: isM?'1 1 auto':'0 0 min(460px,46vw)',
        display: isM&&mView!=='leads' ? 'none':'block',
        overflowY: isM?'visible':'auto', padding: isM?'22px 16px 70px':'30px 26px 70px',
        borderRight: isM?'none':`1px solid ${T.line}`}}>
        <Link to="/territories" style={{fontSize:13, color:T.ink3, textDecoration:'none'}}>← All territories</Link>
        <h1 style={{fontFamily:T.serif, fontSize:32, fontWeight:600, margin:'14px 0 6px'}}>
          {b.zip} <span style={{color:T.ink3, fontWeight:400, fontSize:20}}>· week of {b.week_of}</span>
        </h1>
        <p style={{fontSize:14, color:T.ink2, margin:'0 0 18px'}}>
          {allCn.length} to contact now · {(st.build_now_total||0).toLocaleString()} in pipeline
          · {(st.total_parcels||0).toLocaleString()} homes watched
        </p>
        <div style={{display:'flex', gap:8, flexWrap:'wrap', marginBottom:24}}>
          <TabChip active={tab==='all'} onClick={()=>setTab('all')}>This week · {allCn.length}</TabChip>
          {Object.keys(TYPE).map(k=>
            <TabChip key={k} active={tab===k} onClick={()=>setTab(k)}>
              {TYPE[k]} · {totals[k]||0}
            </TabChip>)}
        </div>

        {demand?.briefs?.length ? (
          <div style={{background:'rgba(201,169,97,.07)', border:'1px solid rgba(201,169,97,.28)',
            borderRadius:18, padding:'18px 20px', marginBottom:26}}>
            <div style={{display:'flex', alignItems:'baseline', gap:10, marginBottom:10}}>
              <span style={{fontFamily:T.serif, fontSize:19, fontWeight:600, color:T.gold}}>
                {demand.briefs.length} buyer{demand.briefs.length>1?'s':''} waiting
              </span>
              <span style={{fontSize:12, color:T.ink3}}>verified · in this ZIP</span>
            </div>
            {demand.briefs.slice(0,4).map((br,i)=>{
              const c=br.criteria||{}
              const isOpen = openBrief===i
              const ff=c.feature_filters||{}
              const musts=Object.entries(ff).filter(([k,v])=>v===true).map(([k])=>k.replace(/_/g,' '))
              const band = !!(c.price_min||c.price_max)
              const fits = allCn.filter(l=>{
                const v=l.value||0
                if(band && !v) return false
                if(c.price_min&&v<c.price_min) return false
                if(c.price_max&&v>c.price_max) return false
                return true
              })
              const matches = fits
              return <div key={i} style={{borderTop: i? `1px solid rgba(201,169,97,.16)`:'none',
                  padding: i? '10px 0 2px':'0 0 2px'}}>
                <div onClick={()=>setOpenBrief(isOpen?null:i)}
                  style={{fontSize:13, color:T.ink2, lineHeight:1.9, cursor:'pointer',
                    display:'flex', justifyContent:'space-between', alignItems:'center'}}>
                  <span>
                    {money(c.price_min)}–{money(c.price_max)} · {c.beds_min||'—'}+ beds
                    · {br.posted_by||'buyer agent'}
                  </span>
                  <span style={{color:T.gold, fontSize:12}}>{isOpen?'Hide':'Details'} ▾</span>
                </div>
                {isOpen && <div style={{padding:'8px 0 12px'}}>
                  <div style={{fontSize:12.5, color:T.ink2, lineHeight:1.9}}>
                    {c.sqft_min?`${c.sqft_min.toLocaleString()}+ sqft · `:''}
                    {ff.view_any?.length?`Views: ${ff.view_any.join(', ').replace(/_/g,' ')} · `:''}
                    {musts.length?`Must have: ${musts.join(', ')}`:''}
                    {(!c.sqft_min&&!ff.view_any?.length&&!musts.length)?'No additional requirements.':''}
                  </div>
                  <div style={{fontSize:11.5, fontWeight:700, letterSpacing:'.1em',
                    color:T.ink3, textTransform:'uppercase', margin:'10px 0 8px'}}>
                    Your contact-now leads that fit{br.matched_total?` · ${br.matched_total} homes matched fabric-wide`:''}
                  </div>
                  {matches.length ? <div style={{maxHeight:230, overflowY:'auto'}}>{matches.map(l=>(
                    <div key={l.pin} onClick={()=>setOpen(l)}
                      style={{fontSize:13, color:T.ink, cursor:'pointer', padding:'5px 0',
                        display:'flex', justifyContent:'space-between'}}>
                      <span style={{textDecoration:'underline', textDecorationColor:'rgba(255,255,255,.25)'}}>
                        {l.owner_name} · {l.address}</span>
                      <span style={{color:T.ink2}}>{money(l.value)}</span>
                    </div>
                  ))}</div> : <div style={{fontSize:13, color:T.ink3}}>
                    No current contact-now leads fit this band — the fabric keeps watching.</div>}
                  {(()=>{
                    const fw = br.matched_total||fits.length
                    const rest = Math.max(0, fw - fits.length)
                    return rest>0 ? <div style={{fontSize:12, color:T.ink3, marginTop:8, lineHeight:1.7}}>
                      The other {rest} matched home{rest>1?'s':''} sit in the watched fabric —
                      no active signal yet. The moment one develops a reason to sell,
                      it appears here.
                    </div> : null
                  })()}
                  {br.responded || responded[br.need_id] ? (
                    <div style={{marginTop:12, fontSize:13, fontWeight:600, color:'#7FBF8A'}}>
                      ✓ Introduction signaled — the buyer's agent now sees you have a fit.
                    </div>
                  ) : (
                    <button onClick={async(e)=>{
                      e.stopPropagation()
                      try{
                        await api.post(`/api/marketplace/demand/${zip}/${br.need_id}/respond`,
                          {pin: matches[0]?.pin})
                        setResponded(r=>({...r,[br.need_id]:true}))
                      }catch(err){}
                    }} style={{marginTop:12, padding:'10px 18px', borderRadius:999,
                      border:'none', cursor:'pointer', background:T.gold, color:'#151311',
                      fontFamily:T.sans, fontSize:12.5, fontWeight:700}}>
                      Signal a fit — make the introduction
                    </button>
                  )}
                </div>}
              </div>
            })}
          </div>
        ):null}
        <input value={q} onChange={e=>setQ(e.target.value)}
          placeholder="Search by owner, address, or PIN"
          style={{width:'100%', boxSizing:'border-box', margin:'0 0 18px',
            background:T.surface, border:`1px solid ${T.line2}`, borderRadius:12,
            color:T.ink, padding:'12px 14px', fontFamily:T.sans, fontSize:13.5, outline:'none'}}/>
        <SectionHead n={cn.length}>{tab==='all'?'Contact now':`Top ${TYPE[tab]} leads`}</SectionHead>
        <div style={{display:'flex', flexDirection:'column', gap:12, marginBottom:34}}>
          {cn.map((l,i)=><LeadCard key={l.pin} l={l} eager={i<8} onOpen={x=>setOpen(x)}/>)}
        </div>

        {bn.length>0 && <>
          <SectionHead n={bn.length}>Building</SectionHead>
          <div style={{display:'flex', flexDirection:'column', gap:10}}>
            {bn.slice(0,showAllBn?bn.length:14).map(l=><LeadCard key={l.pin} l={l} onOpen={x=>setOpen(x)}/>)}
          </div>
          {bn.length>14 && !showAllBn &&
            <button onClick={()=>setShowAllBn(true)} style={{marginTop:14, background:'none',
              border:`1px solid ${T.line2}`, borderRadius:999, color:T.ink2, padding:'10px 18px',
              cursor:'pointer', fontFamily:T.sans, fontSize:13}}>
              Show all {bn.length} building leads</button>}
        </>}
      </div>

      {/* map */}
      <div style={{flex:1, position:'relative', background:'#0a0a0a',
        display: isM&&mView!=='map' ? 'none':'block',
        minHeight: isM?'58vh':'auto'}}>
        <BriefMap key={isM?mView:'d'} zip={zip}
          leadsByPin={leadsByPin}
          leadTypeByPin={leadTypeByPin}
          pipelinePins={pipelinePins}
          onOpenLead={l=>setOpen(l)}/>
        <div style={{position:'absolute', left:18, bottom:18,
          background:'rgba(11,10,9,.85)', backdropFilter:'blur(8px)', padding:'12px 16px',
          borderRadius:12, border:`1px solid ${T.line}`, fontSize:12, color:T.ink2,
          display:'flex', flexDirection:'column', gap:6}}>
          <div style={{display:'flex', gap:13, flexWrap:'wrap'}}>
            <span><span style={dot('#E0B458')}/>Estate</span>
            <span><span style={dot('#E27D6A')}/>Divorce</span>
            <span><span style={dot('#B08BD9')}/>Trust</span>
            <span><span style={dot('#6FB3A8')}/>LLC</span>
            <span><span style={dot('#7FA8E0')}/>Absentee</span>
            <span><span style={dot('#7FBF8A')}/>Tenure</span>
          </div>
          <div style={{fontSize:11, color:T.ink3}}>
            Large dots: contact now · medium: pipeline · faint: watched fabric
          </div>
        </div>
      </div>

      {open && <Dossier pin={open.pin} zip={zip} seed={open} onClose={()=>setOpen(null)}/>}
    </div>
  )
}
const dot=c=>({display:'inline-block',width:9,height:9,borderRadius:99,background:c,marginRight:7})
function TabChip({active,onClick,children}){
  return <button onClick={onClick} style={{
    fontFamily:T.sans, fontSize:12.5, fontWeight:600, cursor:'pointer',
    padding:'7px 13px', borderRadius:999,
    background: active?'rgba(224,180,88,.16)':'transparent',
    color: active?T.gold:T.ink2,
    border:`1px solid ${active?'rgba(224,180,88,.4)':T.line2}`,
  }}>{children}</button>
}
function SectionHead({children,n}){
  return <div style={{display:'flex', alignItems:'baseline', gap:10, marginBottom:14}}>
    <span style={{fontSize:12, letterSpacing:'.12em', fontWeight:700, color:T.ink3,
      textTransform:'uppercase'}}>{children}</span>
    <span style={{fontSize:12, color:T.gold, fontWeight:700}}>{n}</span>
  </div>
}
