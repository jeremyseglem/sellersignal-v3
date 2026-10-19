import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

/* The v13 Overture ident: two halves connect, internals interlay,
   the Aperture resolves, the name settles. */

const D2R = Math.PI/180
const P = (r,deg)=>[500+r*Math.cos(deg*D2R), 500+r*Math.sin(deg*D2R)]
const arc = (r,a0,a1)=>{
  const [x0,y0]=P(r,a0), [x1,y1]=P(r,a1)
  const large = (a1-a0)>180?1:0
  return `M ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1}`
}
const SEG_A = [[0,60],[120,180],[240,300]]
const SEG_B = [[60,120],[180,240],[300,360]]

function HalfSegs({side}){
  const out=[]
  ;[[330,SEG_A,0],[210,SEG_B,120]].forEach(([r,segs,rot],ri)=>{
    segs.forEach(([s0,s1],i)=>{
      const a0=s0-1.2, a1=s1+1.2
      const mid=(a0+a1)/2-90+rot
      const c=Math.cos(mid*D2R)
      if((side<0&&c<0)||(side>0&&c>=0)){
        out.push(<path key={ri+'-'+i} d={arc(r,a0-90+rot,a1+rot-90)}
          stroke="#F4F1EC" strokeWidth={ri===0?46:30} fill="none" strokeLinecap="butt"/>)
      }
    })
  })
  return out
}

const chrome = {
  position:'fixed',zIndex:8,fontSize:11,letterSpacing:'.28em',textTransform:'uppercase',
  color:'#F4F1EC',transition:'opacity 1.1s ease .8s',textDecoration:'none',
}

export default function HomeOverture(){
  const [st, setSt] = useState({s1:false,s3:false,s5:false,swap:false})
  useEffect(()=>{
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches
    if(reduced){ setSt({s1:true,s3:true,s5:true,swap:true}); return }
    const ts=[
      setTimeout(()=>setSt(s=>({...s,s1:true})), 100),
      setTimeout(()=>setSt(s=>({...s,swap:true})), 1170),
      setTimeout(()=>setSt(s=>({...s,s3:true})), 1320),
      setTimeout(()=>setSt(s=>({...s,s5:true})), 3050),
    ]
    return ()=>ts.forEach(clearTimeout)
  },[])

  const halfStyle = side => ({
    transformOrigin:'500px 500px', transformBox:'view-box',
    transition:'transform 1.05s cubic-bezier(.52,0,.16,1), opacity .22s ease',
    opacity: st.swap?0 : (st.s1?1:0),
    transform: st.s1 ? 'translateX(0)' : `translateX(${side<0?'-42%':'42%'})`,
  })
  const ringStyle = (rot, scale) => ({
    transformOrigin:'500px 500px', transformBox:'view-box',
    transition:'transform 1.55s cubic-bezier(.6,.01,.1,1)',
    transform: st.s3 ? `rotate(${rot}deg) scale(${scale})` : 'none',
  })

  return (
    <div style={{position:'fixed',inset:0,background:'#0B0A09',overflow:'hidden',zIndex:50}}>
      <div style={{position:'fixed',inset:0,zIndex:5,pointerEvents:'none',
        background:'radial-gradient(ellipse 130% 100% at 50% 46%, transparent 60%, rgba(0,0,0,.5) 100%)'}}/>

      <span style={{...chrome, top:26,left:30, opacity:st.s5?.7:0}}>Overture</span>
      <Link to="/welcome" style={{...chrome, top:26,right:30, opacity:st.s5?.7:0}}>Sign in</Link>

      <div style={{position:'fixed',inset:0,display:'flex',alignItems:'center',justifyContent:'center'}}>
        <div style={{
          width:'min(62vmin,580px)', aspectRatio:'1/1',
          transition:'transform 1.05s cubic-bezier(.45,.02,.13,1)',
          transform: st.s5 ? 'translateY(-15.5vmin) scale(.26)' : 'none',
        }}>
          <svg viewBox="0 0 1000 1000" style={{width:'100%',height:'100%',overflow:'visible'}}>
            {!(st.swap) && <>
              <g style={halfStyle(-1)}>
                <path d={arc(396,92,268)} stroke="#F4F1EC" strokeWidth="46" fill="none" strokeLinecap="butt"/>
                <HalfSegs side={-1}/>
              </g>
              <g style={halfStyle(1)}>
                <path d={arc(396,-88,88)} stroke="#F4F1EC" strokeWidth="46" fill="none" strokeLinecap="butt"/>
                <HalfSegs side={1}/>
              </g>
            </>}
            {st.swap && <>
              <circle cx="500" cy="500" r="396" stroke="#F4F1EC" strokeWidth="46" fill="none"/>
              <g style={ringStyle(60,.8182)}>
                {SEG_A.map(([a0,a1],i)=>
                  <path key={i} d={arc(330,a0-1.2-90,a1+1.2-90)} stroke="#F4F1EC" strokeWidth="46" fill="none" strokeLinecap="butt"/>)}
              </g>
              <g style={{...ringStyle(-60,1.2857),
                  opacity: st.s3?0:1,
                  transition:'transform 1.55s cubic-bezier(.6,.01,.1,1), opacity .32s ease 1.1s'}}>
                {SEG_B.map(([a0,a1],i)=>
                  <path key={i} d={arc(210,a0-1.2-90+120,a1+1.2-90+120)} stroke="#F4F1EC" strokeWidth="30" fill="none" strokeLinecap="butt"/>)}
              </g>
            </>}
          </svg>
        </div>
      </div>

      <div style={{
        position:'fixed',inset:0,zIndex:6,pointerEvents:'none',
        display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',
        paddingTop:'17vmin',textAlign:'center',
        opacity:st.s5?1:0, transform:st.s5?'none':'translateY(12px)',
        transition:'opacity 1s ease .3s, transform 1s cubic-bezier(.2,.6,.2,1) .3s',
      }}>
        <h1 style={{fontFamily:"'Playfair Display', serif",fontWeight:600,fontSize:'clamp(38px,6.4vmin,72px)',
          letterSpacing:'.18em',textIndent:'.3em',color:'#F4F1EC'}}>OVERTURE</h1>
        <div style={{width:'10vmin',height:2,background:'#F4F1EC',opacity:.6,margin:'2.8vmin auto 2.3vmin'}}/>
        <p style={{fontFamily:"Inter, monospace",fontSize:'clamp(10px,1.35vmin,13px)',
          letterSpacing:'.18em',textTransform:'uppercase',color:'#F4F1EC',opacity:.8,lineHeight:2,maxWidth:'86vw'}}>
          The market before the market
        </p>
      </div>

      <Link to="/welcome" style={{
        position:'fixed',left:'50%',bottom:'5.4vh',transform:'translateX(-50%)',zIndex:8,
        fontSize:11,letterSpacing:'.4em',textTransform:'uppercase',color:'#F4F1EC',
        fontFamily:"Inter, monospace",textDecoration:'none',
        paddingBottom:9,borderBottom:'2px solid rgba(255,255,255,.25)',
        opacity:st.s5?.8:0, transition:'opacity 1.1s ease .5s',
      }}>Enter</Link>
    </div>
  )
}
