import{o as l}from"./deep-equal-Dwhz1A9B.js";class n{static get componentName(){return Object.prototype.hasOwnProperty.call(this,"extensionName")?this.extensionName:""}constructor(s){s&&(this.opts=s)}equals(s){return this===s?!0:this.constructor===s.constructor&&l(this.opts,s.opts,1)}getShaders(s){return null}getSubLayerProps(s){const{defaultProps:i}=s.constructor,e={updateTriggers:{}};for(const t in i)if(t in this.props){const c=i[t],o=this.props[t];e[t]=o,c&&c.type==="accessor"&&(e.updateTriggers[t]=this.props.updateTriggers[t],typeof o=="function"&&(e[t]=this.getSubLayerAccessor(o)))}return e}initializeState(s,i){}updateState(s,i){}onNeedsRedraw(s){}getNeedsPickingBuffer(s){return!1}draw(s,i){}finalizeState(s,i){}}n.defaultProps={};n.extensionName="LayerExtension";const u={clipBounds:[0,0,1,1],clipByInstance:void 0},r=`
layout(std140) uniform clipUniforms {
  vec4 bounds;
} clip;

bool clip_isInBounds(vec2 position) {
  return position.x >= clip.bounds[0] && position.y >= clip.bounds[1] && position.x < clip.bounds[2] && position.y < clip.bounds[3];
}
`,d={name:"clip",vs:r,uniformTypes:{bounds:"vec4<f32>"}},f={"vs:#decl":`
out float clip_isVisible;
`,"vs:DECKGL_FILTER_GL_POSITION":`
  clip_isVisible = float(clip_isInBounds(geometry.worldPosition.xy));
`,"fs:#decl":`
in float clip_isVisible;
`,"fs:DECKGL_FILTER_COLOR":`
  if (clip_isVisible < 0.5) discard;
`},m={name:"clip",fs:r,uniformTypes:{bounds:"vec4<f32>"}},h={"vs:#decl":`
out vec2 clip_commonPosition;
`,"vs:DECKGL_FILTER_GL_POSITION":`
  clip_commonPosition = geometry.position.xy;
`,"fs:#decl":`
in vec2 clip_commonPosition;
`,"fs:DECKGL_FILTER_COLOR":`
  if (!clip_isInBounds(clip_commonPosition)) discard;
`};class p extends n{getShaders(){let s="instancePositions"in this.getAttributeManager().attributes;return this.props.clipByInstance!==void 0&&(s=!!this.props.clipByInstance),this.state.clipByInstance=s,s?{modules:[d],inject:f}:{modules:[m],inject:h}}draw(){const{clipBounds:s}=this.props,i={};if(this.state.clipByInstance)i.bounds=s;else{const e=this.projectPosition([s[0],s[1],0]),t=this.projectPosition([s[2],s[3],0]);i.bounds=[Math.min(e[0],t[0]),Math.min(e[1],t[1]),Math.max(e[0],t[0]),Math.max(e[1],t[1])]}this.setShaderModuleProps({clip:i})}}p.defaultProps=u;p.extensionName="ClipExtension";export{p as C,n as L};
//# sourceMappingURL=clip-extension-DJx3AiGE.js.map
