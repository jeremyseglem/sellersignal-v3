import{n as ue,j as he,aK as I,aL as pe,u as j,M as H,p as _,o as Y,d as M,m as me,aM as ge,aN as V,q as $,x as ve,ak as k}from"./deep-equal-Dwhz1A9B.js";import{L as y}from"./clip-extension-DJx3AiGE.js";import{C as Xt}from"./clip-extension-DJx3AiGE.js";import{M as _e,a as W,m as z}from"./shader-Cz896RLg.js";import{L as R,P as ye}from"./pick-layers-pass-DvgClpsw.js";import"./array-utils-flat-Bshre25B.js";const xe=new H().lookAt({eye:[0,0,1]});function Pe({width:a,height:e,near:t,far:i,padding:s}){let o=-a/2,r=a/2,n=-e/2,l=e/2;if(s){const{left:c=0,right:f=0,top:d=0,bottom:u=0}=s,h=j((c+a-f)/2,0,a)-a/2,p=j((d+e-u)/2,0,e)-e/2;o-=h,r-=h,n+=p,l+=p}return new H().ortho({left:o,right:r,bottom:n,top:l,near:t,far:i})}class K extends ue{constructor(e){const{width:t,height:i,near:s=.1,far:o=1e3,zoom:r=0,target:n=[0,0,0],padding:l=null,flipY:c=!0}=e,f=e.zoomX??(Array.isArray(r)?r[0]:r),d=e.zoomY??(Array.isArray(r)?r[1]:r),u=Math.min(f,d),h=Math.pow(2,u);let p;if(f!==d){const P=Math.pow(2,f),v=Math.pow(2,d);p={unitsPerMeter:[P/h,v/h,1],metersPerUnit:[h/P,h/v,1]}}super({...e,longitude:void 0,position:n,viewMatrix:xe.clone().scale([h,h*(c?-1:1),h]),projectionMatrix:Pe({width:t||1,height:i||1,padding:l,near:s,far:o}),zoom:u,distanceScales:p}),this.target=n,this.zoomX=f,this.zoomY=d,this.flipY=c}projectFlat([e,t]){const{unitsPerMeter:i}=this.distanceScales;return[e*i[0],t*i[1]]}unprojectFlat([e,t]){const{metersPerUnit:i}=this.distanceScales;return[e*i[0],t*i[1]]}panByPosition(e,t,i){const s=he(t,this.pixelUnprojectionMatrix),o=this.projectFlat(e),r=I([],o,pe([],s)),n=I([],this.center,r);return{target:this.unprojectFlat(n)}}}K.displayName="OrthographicViewport";const Z=`layout(std140) uniform brushingUniforms {
  bool enabled;
  highp int target;
  vec2 mousePos;
  float radius;
} brushing;
`,Me=`
  in vec2 brushingTargets;

  out float brushing_isVisible;

  bool brushing_isPointInRange(vec2 position) {
    if (!brushing.enabled) {
      return true;
    }
    vec2 source_commonspace = project_position(position);
    vec2 target_commonspace = project_position(brushing.mousePos);
    float distance = length((target_commonspace - source_commonspace) / project.commonUnitsPerMeter.xy);

    return distance <= brushing.radius;
  }

  bool brushing_arePointsInRange(vec2 sourcePos, vec2 targetPos) {
    return brushing_isPointInRange(sourcePos) || brushing_isPointInRange(targetPos);
  }

  void brushing_setVisible(bool visible) {
    brushing_isVisible = float(visible);
  }
`,be=`
${Z}
${Me}
`,Te=`
  in float brushing_isVisible;
`,Fe=`
${Z}
${Te}
`,Ce={source:0,target:1,custom:2,source_target:3},ke={"vs:DECKGL_FILTER_GL_POSITION":`
    vec2 brushingTarget;
    vec2 brushingSource;
    if (brushing.target == 3) {
      brushingTarget = geometry.worldPositionAlt.xy;
      brushingSource = geometry.worldPosition.xy;
    } else if (brushing.target == 0) {
      brushingTarget = geometry.worldPosition.xy;
    } else if (brushing.target == 1) {
      brushingTarget = geometry.worldPositionAlt.xy;
    } else {
      brushingTarget = brushingTargets;
    }
    bool visible;
    if (brushing.target == 3) {
      visible = brushing_arePointsInRange(brushingSource, brushingTarget);
    } else {
      visible = brushing_isPointInRange(brushingTarget);
    }
    brushing_setVisible(visible);
  `,"fs:DECKGL_FILTER_COLOR":`
    if (brushing.enabled && brushing_isVisible < 0.5) {
      discard;
    }
  `},Le={name:"brushing",dependencies:[_],vs:be,fs:Fe,inject:ke,getUniforms:a=>{if(!a||!("viewport"in a))return{};const{brushingEnabled:e=!0,brushingRadius:t=1e4,brushingTarget:i="source",mousePosition:s,viewport:o}=a;return{enabled:!!(e&&s&&o.containsPixel(s)),radius:t,target:Ce[i]||0,mousePos:s?o.unproject([s.x-o.x,s.y-o.y]):[0,0]}},uniformTypes:{enabled:"i32",target:"i32",mousePos:"vec2<f32>",radius:"f32"}},Ee={getBrushingTarget:{type:"accessor",value:[0,0]},brushingTarget:"source",brushingEnabled:!0,brushingRadius:1e4};class X extends y{getShaders(){return{modules:[Le]}}initializeState(e,t){const i=this.getAttributeManager();i&&i.add({brushingTargets:{size:2,stepMode:"dynamic",accessor:"getBrushingTarget"}});const s=()=>{var o;(o=this.getCurrentLayer())==null||o.setNeedsRedraw()};this.state.onMouseMove=s,e.deck&&e.deck.eventManager.on({pointermove:s,pointerleave:s})}finalizeState(e,t){if(e.deck){const i=this.state.onMouseMove;e.deck.eventManager.off({pointermove:i,pointerleave:i})}}draw(e,t){const{viewport:i,mousePosition:s}=e.context,{brushingEnabled:o,brushingRadius:r,brushingTarget:n}=this.props,l={viewport:i,mousePosition:s,brushingEnabled:o,brushingRadius:r,brushingTarget:n};this.setShaderModuleProps({brushing:l})}}X.defaultProps=Ee;X.extensionName="BrushingExtension";const q=`layout(std140) uniform dataFilterUniforms {
  bool useSoftMargin;
  bool enabled;
  bool transformSize;
  bool transformColor;
  vec4 min;
  vec4 softMin;
  vec4 softMax;
  vec4 max;
  vec4 min64High;
  vec4 max64High;
  highp uvec4 categoryBitMask;
} dataFilter;
`,Ae=`
#ifdef DATAFILTER_TYPE
  in DATAFILTER_TYPE filterValues;
#ifdef DATAFILTER_DOUBLE
  in DATAFILTER_TYPE filterValues64Low;
#endif
#endif

#ifdef DATACATEGORY_TYPE
  in DATACATEGORY_TYPE filterCategoryValues;
#endif

out float dataFilter_value;

#ifdef DATAFILTER_TYPE
  float dataFilter_getMin(float _) {
    return dataFilter.min.x;
  }
  vec2 dataFilter_getMin(vec2 _) {
    return dataFilter.min.xy;
  }
  vec3 dataFilter_getMin(vec3 _) {
    return dataFilter.min.xyz;
  }
  vec4 dataFilter_getMin(vec4 _) {
    return dataFilter.min;
  }

  float dataFilter_getSoftMin(float _) {
    return dataFilter.softMin.x;
  }
  vec2 dataFilter_getSoftMin(vec2 _) {
    return dataFilter.softMin.xy;
  }
  vec3 dataFilter_getSoftMin(vec3 _) {
    return dataFilter.softMin.xyz;
  }
  vec4 dataFilter_getSoftMin(vec4 _) {
    return dataFilter.softMin;
  }

  float dataFilter_getSoftMax(float _) {
    return dataFilter.softMax.x;
  }
  vec2 dataFilter_getSoftMax(vec2 _) {
    return dataFilter.softMax.xy;
  }
  vec3 dataFilter_getSoftMax(vec3 _) {
    return dataFilter.softMax.xyz;
  }
  vec4 dataFilter_getSoftMax(vec4 _) {
    return dataFilter.softMax;
  }

  float dataFilter_getMax(float _) {
    return dataFilter.max.x;
  }
  vec2 dataFilter_getMax(vec2 _) {
    return dataFilter.max.xy;
  }
  vec3 dataFilter_getMax(vec3 _) {
    return dataFilter.max.xyz;
  }
  vec4 dataFilter_getMax(vec4 _) {
    return dataFilter.max;
  }

  float dataFilter_getMin64High(float _) {
    return dataFilter.min64High.x;
  }
  vec2 dataFilter_getMin64High(vec2 _) {
    return dataFilter.min64High.xy;
  }
  vec3 dataFilter_getMin64High(vec3 _) {
    return dataFilter.min64High.xyz;
  }
  vec4 dataFilter_getMin64High(vec4 _) {
    return dataFilter.min64High;
  }

  float dataFilter_getMax64High(float _) {
    return dataFilter.max64High.x;
  }
  vec2 dataFilter_getMax64High(vec2 _) {
    return dataFilter.max64High.xy;
  }
  vec3 dataFilter_getMax64High(vec3 _) {
    return dataFilter.max64High.xyz;
  }
  vec4 dataFilter_getMax64High(vec4 _) {
    return dataFilter.max64High;
  }
#endif

float dataFilter_reduceValue(float value) {
  return value;
}
float dataFilter_reduceValue(vec2 value) {
  return min(value.x, value.y);
}
float dataFilter_reduceValue(vec3 value) {
  return min(min(value.x, value.y), value.z);
}
float dataFilter_reduceValue(vec4 value) {
  return min(min(value.x, value.y), min(value.z, value.w));
}

#ifdef DATAFILTER_TYPE
  void dataFilter_setValue(DATAFILTER_TYPE valueFromMin, DATAFILTER_TYPE valueFromMax) {
    DATAFILTER_TYPE dataFilter_min = dataFilter_getMin(valueFromMin);
    DATAFILTER_TYPE dataFilter_softMin = dataFilter_getSoftMin(valueFromMin);
    DATAFILTER_TYPE dataFilter_softMax = dataFilter_getSoftMax(valueFromMin);
    DATAFILTER_TYPE dataFilter_max = dataFilter_getMax(valueFromMin);
    if (dataFilter.useSoftMargin) {
      // smoothstep results are undefined if edge0 ≥ edge1
      // Fallback to ignore filterSoftRange if it is truncated by filterRange
      DATAFILTER_TYPE leftInRange = mix(
        smoothstep(dataFilter_min, dataFilter_softMin, valueFromMin),
        step(dataFilter_min, valueFromMin),
        step(dataFilter_softMin, dataFilter_min)
      );
      DATAFILTER_TYPE rightInRange = mix(
        1.0 - smoothstep(dataFilter_softMax, dataFilter_max, valueFromMax),
        step(valueFromMax, dataFilter_max),
        step(dataFilter_max, dataFilter_softMax)
      );
      dataFilter_value = dataFilter_reduceValue(leftInRange * rightInRange);
    } else {
      dataFilter_value = dataFilter_reduceValue(
        step(dataFilter_min, valueFromMin) * step(valueFromMax, dataFilter_max)
      );
    }
  }
#endif

#ifdef DATACATEGORY_TYPE
  void dataFilter_setCategoryValue(DATACATEGORY_TYPE category) {
    #if DATACATEGORY_CHANNELS == 1 // One 128-bit mask
    uint dataFilter_masks = dataFilter.categoryBitMask[category / 32u];
    #elif DATACATEGORY_CHANNELS == 2 // Two 64-bit masks
    uvec2 dataFilter_masks = uvec2(
      dataFilter.categoryBitMask[category.x / 32u],
      dataFilter.categoryBitMask[category.y / 32u + 2u]
    );
    #elif DATACATEGORY_CHANNELS == 3 // Three 32-bit masks
    uvec3 dataFilter_masks = dataFilter.categoryBitMask.xyz;
    #else // Four 32-bit masks
    uvec4 dataFilter_masks = dataFilter.categoryBitMask;
    #endif

    // Shift mask and extract relevant bits
    DATACATEGORY_TYPE dataFilter_bits = DATACATEGORY_TYPE(dataFilter_masks) >> (category & 31u);
    dataFilter_bits &= 1u;

    #if DATACATEGORY_CHANNELS == 1
    if (dataFilter_bits == 0u) dataFilter_value = 0.0;
    #else
    if (any(equal(dataFilter_bits, DATACATEGORY_TYPE(0u)))) dataFilter_value = 0.0;
    #endif
  }
#endif
`,J=`
${q}
${Ae}
`,Re=`
in float dataFilter_value;
`,Q=`
${q}
${Re}
`;function ee(a){if(!a||!("extensions"in a))return{};const{filterRange:e=[-1,1],filterEnabled:t=!0,filterTransformSize:i=!0,filterTransformColor:s=!0,categoryBitMask:o}=a,r=a.filterSoftRange||e,n=l=>Array.isArray(l)?[l[0]||0,l[1]||0,l[2]||0,l[3]||0]:[l,0,0,0];return{...Number.isFinite(e[0])?{min:n(e[0]),softMin:n(r[0]),softMax:n(r[1]),max:n(e[1])}:{min:n(e.map(l=>l[0])),softMin:n(r.map(l=>l[0])),softMax:n(r.map(l=>l[1])),max:n(e.map(l=>l[1]))},enabled:t,useSoftMargin:!!a.filterSoftRange,transformSize:t&&i,transformColor:t&&s,...o&&{categoryBitMask:o}}}function we(a){if(!a||!("extensions"in a))return{};const e=ee(a),t=e.min.map(Math.fround);e.min=e.min.map((s,o)=>s-t[o]),e.softMin=e.softMin.map((s,o)=>s-t[o]),e.min64High=t;const i=e.max.map(Math.fround);return e.max=e.max.map((s,o)=>s-i[o]),e.softMax=e.softMax.map((s,o)=>s-i[o]),e.max64High=i,e}const te={"vs:#main-start":`
    dataFilter_value = 1.0;
    if (dataFilter.enabled) {
      #ifdef DATAFILTER_TYPE
        #ifdef DATAFILTER_DOUBLE
          dataFilter_setValue(
            filterValues - dataFilter_getMin64High(filterValues) + filterValues64Low,
            filterValues - dataFilter_getMax64High(filterValues) + filterValues64Low
          );
        #else
          dataFilter_setValue(filterValues, filterValues);
        #endif
      #endif

      #ifdef DATACATEGORY_TYPE
        dataFilter_setCategoryValue(filterCategoryValues);
      #endif
    }
  `,"vs:#main-end":`
    if (dataFilter_value == 0.0) {
      gl_Position = vec4(0.);
    }
  `,"vs:DECKGL_FILTER_SIZE":`
    if (dataFilter.transformSize) {
      size = size * dataFilter_value;
    }
  `,"fs:DECKGL_FILTER_COLOR":`
    if (dataFilter_value == 0.0) discard;
    if (dataFilter.transformColor) {
      color.a *= dataFilter_value;
    }
  `};function ie(a){return{useSoftMargin:"i32",enabled:"i32",transformSize:"i32",transformColor:"i32",min:"vec4<f32>",softMin:"vec4<f32>",softMax:"vec4<f32>",max:"vec4<f32>",min64High:"vec4<f32>",max64High:"vec4<f32>",categoryBitMask:"vec4<u32>"}}const Se={name:"dataFilter",vs:J,fs:Q,inject:te,getUniforms:ee,uniformTypesFromOptions:ie},Be={name:"dataFilter",vs:J,fs:Q,inject:te,getUniforms:we,uniformTypesFromOptions:ie},Oe=`#version 300 es
#define SHADER_NAME data-filter-vertex-shader

#ifdef FLOAT_TARGET
  in float filterIndices;
  in float filterPrevIndices;
#else
  in vec2 filterIndices;
  in vec2 filterPrevIndices;
#endif

out vec4 vColor;
const float component = 1.0 / 255.0;

void main() {
  #ifdef FLOAT_TARGET
    dataFilter_value *= float(filterIndices != filterPrevIndices);
    gl_Position = vec4(0.0, 0.0, 0.0, 1.0);
    vColor = vec4(0.0, 0.0, 0.0, 1.0);
  #else
    // Float texture is not supported: pack result into 4 channels x 256 px x 64px
    dataFilter_value *= float(filterIndices.x != filterPrevIndices.x);
    float col = filterIndices.x;
    float row = filterIndices.y * 4.0;
    float channel = floor(row);
    row = fract(row);
    vColor = component * vec4(bvec4(channel == 0.0, channel == 1.0, channel == 2.0, channel == 3.0));
    gl_Position = vec4(col * 2.0 - 1.0, row * 2.0 - 1.0, 0.0, 1.0);
  #endif
  gl_PointSize = 1.0;
}
`,De=`#version 300 es
#define SHADER_NAME data-filter-fragment-shader
precision highp float;

in vec4 vColor;

out vec4 fragColor;

void main() {
  if (dataFilter_value < 0.5) {
    discard;
  }
  fragColor = vColor;
}
`,Ie=["float32-renderable-webgl","texture-blend-float-webgl"];function je(a){return Ie.every(e=>a.features.has(e))}function Ve(a,e){return e?a.createFramebuffer({width:1,height:1,colorAttachments:[a.createTexture({format:"rgba32float",dimension:"2d",width:1,height:1})]}):a.createFramebuffer({width:256,height:64,colorAttachments:[a.createTexture({format:"rgba8unorm",dimension:"2d",width:256,height:64})]})}function ze(a,e,t,i){return t.defines.NON_INSTANCED_MODEL=1,i&&(t.defines.FLOAT_TARGET=1),new _e(a,{id:"data-filter-aggregation-model",vertexCount:1,isInstanced:!1,topology:"point-list",disableWarnings:!0,vs:Oe,fs:De,bufferLayout:e,...t})}const Ne={blend:!0,blendColorSrcFactor:"one",blendColorDstFactor:"one",blendAlphaSrcFactor:"one",blendAlphaDstFactor:"one",blendColorOperation:"add",blendAlphaOperation:"add",depthCompare:"never"},Ue={getFilterValue:{type:"accessor",value:0},getFilterCategory:{type:"accessor",value:0},onFilteredItemsChange:{type:"function",value:null,optional:!0},filterEnabled:!0,filterRange:[-1,1],filterSoftRange:null,filterCategories:[0],filterTransformSize:!0,filterTransformColor:!0},Ge={categorySize:0,filterSize:1,fp64:!1,countItems:!1},He={1:"uint",2:"uvec2",3:"uvec3",4:"uvec4"},Ye={1:"float",2:"vec2",3:"vec3",4:"vec4"};class se extends y{constructor(e={}){super({...Ge,...e})}getShaders(e){const{categorySize:t,filterSize:i,fp64:s}=e.opts,o={};t&&(o.DATACATEGORY_TYPE=He[t],o.DATACATEGORY_CHANNELS=t),i&&(o.DATAFILTER_TYPE=Ye[i],o.DATAFILTER_DOUBLE=!!s);const r=s?Be:Se;return r.uniformTypes=r.uniformTypesFromOptions(e.opts),{modules:[r],defines:o}}initializeState(e,t){const i=this.getAttributeManager(),{categorySize:s,filterSize:o,fp64:r}=t.opts;i&&(o&&i.add({filterValues:{size:o,type:r?"float64":"float32",stepMode:"dynamic",accessor:"getFilterValue"}}),s&&i.add({filterCategoryValues:{size:s,stepMode:"dynamic",accessor:"getFilterCategory",type:"uint32",transform:s===1?l=>t._getCategoryKey.call(this,l,0):l=>l.map((c,f)=>t._getCategoryKey.call(this,c,f))}}));const{device:n}=this.context;if(i&&t.opts.countItems){const l=je(n);i.add({filterVertexIndices:{size:l?1:2,vertexOffset:1,type:"unorm8",accessor:(d,{index:u})=>{const h=d&&d.__source?d.__source.index:u;return l?(h+1)%255:[(h+1)%255,Math.floor(h/255)%255]},shaderAttributes:{filterPrevIndices:{vertexOffset:0},filterIndices:{vertexOffset:1}}}});const c=Ve(n,l),f=ze(n,i.getBufferLayouts({isInstanced:!1}),t.getShaders.call(this,t),l);this.setState({filterFBO:c,filterModel:f})}}updateState({props:e,oldProps:t,changeFlags:i},s){var n,l;const o=this.getAttributeManager(),{categorySize:r}=s.opts;if(this.state.filterModel){const c=((n=o.attributes.filterValues)==null?void 0:n.needsUpdate())||((l=o.attributes.filterCategoryValues)==null?void 0:l.needsUpdate())||e.filterEnabled!==t.filterEnabled||e.filterRange!==t.filterRange||e.filterSoftRange!==t.filterSoftRange||e.filterCategories!==t.filterCategories;c&&this.setState({filterNeedsUpdate:c})}o!=null&&o.attributes.filterCategoryValues&&((o.attributes.filterCategoryValues.needsUpdate()||!Y(e.filterCategories,t.filterCategories,2))&&this.setState({categoryBitMask:null}),i.dataChanged&&(this.setState({categoryMap:Array(r).fill(0).map(()=>({}))}),o.attributes.filterCategoryValues.setNeedsUpdate("categoryMap")))}draw(e,t){const i=this.state.filterFBO,s=this.state.filterModel,o=this.state.filterNeedsUpdate;this.state.categoryBitMask||t._updateCategoryBitMask.call(this,e,t);const{onFilteredItemsChange:r,extensions:n,filterEnabled:l,filterRange:c,filterSoftRange:f,filterTransformSize:d,filterTransformColor:u,filterCategories:h}=this.props,p={extensions:n,filterEnabled:l,filterRange:c,filterSoftRange:f,filterTransformSize:d,filterTransformColor:u,filterCategories:h};if(this.state.categoryBitMask&&(p.categoryBitMask=this.state.categoryBitMask),this.setShaderModuleProps({dataFilter:p}),o&&r&&s){const P=this.getAttributeManager(),{attributes:{filterValues:v,filterCategoryValues:g,filterVertexIndices:x}}=P;s.setVertexCount(this.getNumInstances());const T={...v==null?void 0:v.getValue(),...g==null?void 0:g.getValue(),...x==null?void 0:x.getValue()};s.setAttributes(T),s.shaderInputs.setProps({dataFilter:p});const F=[0,0,i.width,i.height],b=s.device.beginRenderPass({id:"data-filter-aggregation",framebuffer:i,parameters:{viewport:F},clearColor:[0,0,0,0]});s.setParameters(Ne),s.draw(b),b.end();const O=s.device.readPixelsToArrayWebGL(i);let D=0;for(let C=0;C<O.length;C++)D+=O[C];r({id:this.id,count:D}),this.state.filterNeedsUpdate=!1}}finalizeState(){const e=this.state.filterFBO,t=this.state.filterModel;e==null||e.destroy(),t==null||t.destroy()}_updateCategoryBitMask(e,t){const{categorySize:i}=t.opts;if(!i)return;const{filterCategories:s}=this.props,o=new Uint32Array([0,0,0,0]),r=i===1?[s]:s,n=i===1?128:i===2?64:32;for(let l=0;l<r.length;l++){const c=r[l];for(const f of c){const d=t._getCategoryKey.call(this,f,l);if(d<n){const u=l*(n/32)+Math.floor(d/32);o[u]+=Math.pow(2,d%32)}else M.warn(`Exceeded maximum number of categories (${n})`)()}}this.state.categoryBitMask=o}_getCategoryKey(e,t){const i=this.state.categoryMap[t];return e in i||(i[e]=Object.keys(i).length),i[e]}}se.defaultProps=Ue;se.extensionName="DataFilterExtension";const $e=`const vec2 WORLD_SCALE_FP64 = vec2(81.4873275756836, 0.0000032873668232014097);
layout(std140) uniform project64Uniforms {
vec2 scale;
mat4 viewProjectionMatrix;
mat4 viewProjectionMatrix64Low;
} project64;
void mercatorProject_fp64(vec4 lnglat_fp64, out vec2 out_val[2]) {
#if defined(NVIDIA_FP64_WORKAROUND)
out_val[0] = sum_fp64(radians_fp64(lnglat_fp64.xy), PI_FP64 * ONE);
#else
out_val[0] = sum_fp64(radians_fp64(lnglat_fp64.xy), PI_FP64);
#endif
out_val[1] = sum_fp64(PI_FP64,
log_fp64(tan_fp64(sum_fp64(PI_4_FP64, radians_fp64(lnglat_fp64.zw) / 2.0))));
return;
}
void project_position_fp64(vec4 position_fp64, out vec2 out_val[2]) {
vec2 pos_fp64[2];
mercatorProject_fp64(position_fp64, pos_fp64);
out_val[0] = mul_fp64(pos_fp64[0], WORLD_SCALE_FP64);
out_val[1] = mul_fp64(pos_fp64[1], WORLD_SCALE_FP64);
return;
}
void project_position_fp64(vec2 position, vec2 position64xyLow, out vec2 out_val[2]) {
vec4 position64xy = vec4(
position.x, position64xyLow.x,
position.y, position64xyLow.y);
project_position_fp64(position64xy, out_val);
}
vec4 project_common_position_to_clipspace_fp64(vec2 vertex_pos_modelspace[4]) {
vec2 vertex_pos_clipspace[4];
vec2 viewProjectionMatrixFP64[16];
for (int i = 0; i < 4; i++) {
for (int j = 0; j < 4; j++) {
viewProjectionMatrixFP64[4 * i + j] = vec2(
project64.viewProjectionMatrix[j][i],
project64.viewProjectionMatrix64Low[j][i]
);
}
}
mat4_vec4_mul_fp64(viewProjectionMatrixFP64, vertex_pos_modelspace,
vertex_pos_clipspace);
return vec4(
vertex_pos_clipspace[0].x,
vertex_pos_clipspace[1].x,
vertex_pos_clipspace[2].x,
vertex_pos_clipspace[3].x
);
}
vec4 project_position_to_clipspace(
vec3 position, vec3 position64xyLow, vec3 offset, out vec4 commonPosition
) {
vec2 offset64[4];
vec4_fp64(vec4(offset, 0.0), offset64);
float z = project_size(position.z);
vec2 projectedPosition64xy[2];
project_position_fp64(position.xy, position64xyLow.xy, projectedPosition64xy);
vec2 commonPosition64[4];
commonPosition64[0] = sum_fp64(offset64[0], projectedPosition64xy[0]);
commonPosition64[1] = sum_fp64(offset64[1], projectedPosition64xy[1]);
commonPosition64[2] = sum_fp64(offset64[2], vec2(z, 0.0));
commonPosition64[3] = vec2(1.0, 0.0);
commonPosition = vec4(projectedPosition64xy[0].x, projectedPosition64xy[1].x, z, 1.0);
return project_common_position_to_clipspace_fp64(commonPosition64);
}
vec4 project_position_to_clipspace(
vec3 position, vec3 position64xyLow, vec3 offset
) {
vec4 commonPosition;
return project_position_to_clipspace(
position, position64xyLow, offset, commonPosition
);
}
`,{fp64ify:We,fp64ifyMatrix4:Ke}=W,Ze={name:"project64",dependencies:[_,W],vs:$e,getUniforms:qe,uniformTypes:{scale:"vec2<f32>",viewProjectionMatrix:"mat4x4<f32>",viewProjectionMatrix64Low:"mat4x4<f32>"}},Xe=me(Je);function qe(a){if(a&&"viewport"in a){const{viewProjectionMatrix:e,scale:t}=a.viewport;return Xe({viewProjectionMatrix:e,scale:t})}return{}}function Je({viewProjectionMatrix:a,scale:e}){const t=Ke(a),i=new Float32Array(16),s=new Float32Array(16);for(let o=0;o<4;o++)for(let r=0;r<4;r++){const n=4*o+r,l=4*r+o;i[l]=t[2*n],s[l]=t[2*n+1]}return{scale:We(e),viewProjectionMatrix:[...i],viewProjectionMatrix64Low:[...s]}}class Qe extends y{getShaders(){const{coordinateSystem:e}=this.props;if(e!=="lnglat"&&e!=="default")throw new Error("fp64: coordinateSystem must be LNGLAT");return{modules:[Ze]}}draw(e,t){const{viewport:i}=e.context;this.setShaderModuleProps({project64:{viewport:i}})}}Qe.extensionName="Fp64Extension";const et={inject:{"vs:#decl":`
in vec2 instanceDashArrays;
#ifdef HIGH_PRECISION_DASH
in float instanceDashOffsets;
#endif
out vec2 vDashArray;
out float vDashOffset;
`,"vs:#main-end":`
vDashArray = instanceDashArrays;
#ifdef HIGH_PRECISION_DASH
vDashOffset = instanceDashOffsets / width.x;
#else
vDashOffset = 0.0;
#endif
`,"fs:#decl":`
layout(std140) uniform pathStyleUniforms {
float dashAlignMode;
bool dashGapPickable;
} pathStyle;
in vec2 vDashArray;
in float vDashOffset;
`,"fs:#main-start":`
float solidLength = vDashArray.x;
float gapLength = vDashArray.y;
float unitLength = solidLength + gapLength;
float offset;
if (unitLength > 0.0) {
if (pathStyle.dashAlignMode == 0.0) {
offset = vDashOffset;
} else {
unitLength = vPathLength / round(vPathLength / unitLength);
offset = solidLength / 2.0;
}
float unitOffset = mod(vPathPosition.y + offset, unitLength);
if (gapLength > 0.0 && unitOffset > solidLength) {
if (path.capType <= 0.5) {
if (!(pathStyle.dashGapPickable && bool(picking.isActive))) {
discard;
}
} else {
float distToEnd = length(vec2(
min(unitOffset - solidLength, unitLength - unitOffset),
vPathPosition.x
));
if (distToEnd > 1.0) {
if (!(pathStyle.dashGapPickable && bool(picking.isActive))) {
discard;
}
}
}
}
}
`}},tt={inject:{"vs:#decl":`
in vec2 instanceDashArrays;
out vec2 vDashArray;
`,"vs:#main-end":`
vDashArray = instanceDashArrays;
`,"fs:#decl":`
layout(std140) uniform pathStyleUniforms {
bool dashGapPickable;
} pathStyle;
in vec2 vDashArray;
#define PI 3.141592653589793
`,"fs:#main-start":`
bool inDashGap = false;
float dashUnitLength = vDashArray.x + vDashArray.y;
if (dashUnitLength > 0.0 && scatterplot.stroked > 0.5) {
float _distToCenter = length(unitPosition) * outerRadiusPixels;
float innerRadius = innerUnitRadius * outerRadiusPixels;
if (_distToCenter >= innerRadius) {
float strokeWidth = (1.0 - innerUnitRadius) * outerRadiusPixels;
float midStrokeRadius = (innerUnitRadius + 1.0) * 0.5 * outerRadiusPixels;
float angle = atan(unitPosition.y, unitPosition.x) + PI;
float circumference = 2.0 * PI * midStrokeRadius;
float posAlongStroke = (angle / (2.0 * PI)) * circumference / strokeWidth;
float unitOffset = mod(posAlongStroke, dashUnitLength);
if (unitOffset > vDashArray.x) {
if (scatterplot.filled > 0.5) {
inDashGap = true;
} else {
if (!(pathStyle.dashGapPickable && bool(picking.isActive))) {
discard;
}
}
}
}
}
`,"fs:#main-end":`
if (inDashGap) {
float alphaFactor = fragColor.a / max(vLineColor.a, 0.001);
fragColor = vec4(vFillColor.rgb, vFillColor.a * alphaFactor);
fragColor = picking_filterPickingColor(fragColor);
fragColor = picking_filterHighlightColor(fragColor);
}
`}},it={inject:{"vs:#decl":`
in vec2 instanceDashArrays;
out vec2 vDashArray;
`,"vs:#main-end":`
vDashArray = instanceDashArrays;
`,"fs:#decl":`
layout(std140) uniform pathStyleUniforms {
bool dashGapPickable;
} pathStyle;
in vec2 vDashArray;
#define PI 3.141592653589793
float getPerimeterPosition(vec2 fragUV, vec2 dims, vec4 radii, float lineWidth) {
float width = dims.x;
float height = dims.y;
float maxRadius = min(width, height) * 0.5;
float rBL = min(radii.w, maxRadius);
float rTL = min(radii.z, maxRadius);
float rTR = min(radii.x, maxRadius);
float rBR = min(radii.y, maxRadius);
vec2 p = fragUV * dims;
float leftLen = height - rBL - rTL;
float topLen = width - rTL - rTR;
float rightLen = height - rTR - rBR;
float bottomLen = width - rBR - rBL;
float arcBL = PI * 0.5 * rBL;
float arcTL = PI * 0.5 * rTL;
float arcTR = PI * 0.5 * rTR;
float arcBR = PI * 0.5 * rBR;
float pos = 0.0;
float distLeft = p.x;
float distRight = width - p.x;
float distBottom = p.y;
float distTop = height - p.y;
float minDist = min(min(distLeft, distRight), min(distBottom, distTop));
if (p.x < rBL && p.y < rBL) {
vec2 c = vec2(rBL, rBL);
vec2 d = p - c;
float angle = atan(-d.x, -d.y);
pos = angle / (PI * 0.5) * arcBL;
} else if (p.x < rTL && p.y > height - rTL) {
vec2 c = vec2(rTL, height - rTL);
vec2 d = p - c;
float angle = atan(d.y, -d.x);
pos = arcBL + leftLen + angle / (PI * 0.5) * arcTL;
} else if (p.x > width - rTR && p.y > height - rTR) {
vec2 c = vec2(width - rTR, height - rTR);
vec2 d = p - c;
float angle = atan(d.x, d.y);
pos = arcBL + leftLen + arcTL + topLen + angle / (PI * 0.5) * arcTR;
} else if (p.x > width - rBR && p.y < rBR) {
vec2 c = vec2(width - rBR, rBR);
vec2 d = p - c;
float angle = atan(-d.y, d.x);
pos = arcBL + leftLen + arcTL + topLen + arcTR + rightLen + angle / (PI * 0.5) * arcBR;
} else if (minDist == distLeft) {
pos = arcBL + clamp(p.y - rBL, 0.0, leftLen);
} else if (minDist == distTop) {
pos = arcBL + leftLen + arcTL + clamp(p.x - rTL, 0.0, topLen);
} else if (minDist == distRight) {
pos = arcBL + leftLen + arcTL + topLen + arcTR + clamp(height - rTR - p.y, 0.0, rightLen);
} else {
pos = arcBL + leftLen + arcTL + topLen + arcTR + rightLen + arcBR + clamp(width - rBR - p.x, 0.0, bottomLen);
}
return pos / lineWidth;
}
float getRectPerimeterPosition(vec2 fragUV, vec2 dims, float lineWidth) {
float width = dims.x;
float height = dims.y;
float distLeft = fragUV.x * width;
float distRight = (1.0 - fragUV.x) * width;
float distBottom = fragUV.y * height;
float distTop = (1.0 - fragUV.y) * height;
float minDist = min(min(distLeft, distRight), min(distBottom, distTop));
float pos = 0.0;
if (minDist == distLeft) {
pos = fragUV.y * height;
} else if (minDist == distTop) {
pos = height + fragUV.x * width;
} else if (minDist == distRight) {
pos = height + width + (1.0 - fragUV.y) * height;
} else {
pos = 2.0 * height + width + (1.0 - fragUV.x) * width;
}
return pos / lineWidth;
}
`,"fs:#main-start":`
bool inDashGap = false;
float dashUnitLength = vDashArray.x + vDashArray.y;
if (dashUnitLength > 0.0 && textBackground.stroked) {
float distToEdge;
bool hasRoundedCorners = textBackground.borderRadius != vec4(0.0);
if (hasRoundedCorners) {
distToEdge = round_rect(uv, dimensions, textBackground.borderRadius);
} else {
distToEdge = rect(uv, dimensions);
}
if (distToEdge <= vLineWidth && distToEdge >= 0.0) {
float posAlongStroke;
if (hasRoundedCorners) {
posAlongStroke = getPerimeterPosition(uv, dimensions, textBackground.borderRadius, vLineWidth);
} else {
posAlongStroke = getRectPerimeterPosition(uv, dimensions, vLineWidth);
}
float unitOffset = mod(posAlongStroke, dashUnitLength);
if (unitOffset > vDashArray.x) {
if (vFillColor.a > 0.0) {
inDashGap = true;
} else {
if (!(pathStyle.dashGapPickable && bool(picking.isActive))) {
discard;
}
}
}
}
}
`,"fs:#main-end":`
if (inDashGap) {
float alphaFactor = fragColor.a / max(vLineColor.a, 0.001);
fragColor = vec4(vFillColor.rgb, vFillColor.a * alphaFactor);
fragColor = picking_filterPickingColor(fragColor);
fragColor = picking_filterHighlightColor(fragColor);
}
`}},st={inject:{"vs:#decl":`
in float instanceOffsets;
`,"vs:DECKGL_FILTER_SIZE":`
float offsetWidth = abs(instanceOffsets * 2.0) + 1.0;
size *= offsetWidth;
`,"vs:#main-end":`
float offsetWidth = abs(instanceOffsets * 2.0) + 1.0;
float offsetDir = sign(instanceOffsets);
vPathPosition.x = (vPathPosition.x + offsetDir) * offsetWidth - offsetDir;
vPathPosition.y *= offsetWidth;
vPathLength *= offsetWidth;
`,"fs:#main-start":`
float isInside;
isInside = step(-1.0, vPathPosition.x) * step(vPathPosition.x, 1.0);
if (isInside == 0.0) {
discard;
}
`}},rt={getDashArray:{type:"accessor",value:[0,0]},getOffset:{type:"accessor",value:0},dashJustified:!1,dashGapPickable:!1};class re extends y{constructor({dash:e=!1,offset:t=!1,highPrecisionDash:i=!1}={}){super({dash:e||i,offset:t,highPrecisionDash:i})}getLayerType(e){if("pathTesselator"in e.state)return"path";const t=e.constructor.layerName;return t==="ScatterplotLayer"?"scatterplot":t==="TextBackgroundLayer"?"textBackground":null}isEnabled(e){return this.getLayerType(e)!==null}getShaders(e){const t=e.getLayerType(this);if(!t)return null;if(t==="scatterplot"||t==="textBackground")return e.opts.dash?{modules:[{name:"pathStyle",inject:t==="scatterplot"?tt.inject:it.inject,uniformTypes:{dashGapPickable:"i32"}}]}:null;let i={};const s={};e.opts.dash&&(i=z(i,et),e.opts.highPrecisionDash&&(s.HIGH_PRECISION_DASH=!0)),e.opts.offset&&(i=z(i,st));const{inject:o}=i;return{modules:[{name:"pathStyle",inject:o,uniformTypes:{dashAlignMode:"f32",dashGapPickable:"i32"}}],defines:s}}initializeState(e,t){const i=this.getAttributeManager(),s=t.getLayerType(this);!i||!s||(t.opts.dash&&i.addInstanced({instanceDashArrays:{size:2,accessor:"getDashArray"},...s==="path"&&t.opts.highPrecisionDash?{instanceDashOffsets:{size:1,accessor:"getPath",transform:t.getDashOffsets.bind(this)}}:{}}),s==="path"&&t.opts.offset&&i.addInstanced({instanceOffsets:{size:1,accessor:"getOffset"}}))}updateState(e,t){if(t.isEnabled(this)&&t.opts.dash){const i=t.getLayerType(this);if(i==="scatterplot"||i==="textBackground"){const s={dashGapPickable:!!this.props.dashGapPickable};this.setShaderModuleProps({pathStyle:s})}else{const s={dashAlignMode:this.props.dashJustified?1:0,dashGapPickable:!!this.props.dashGapPickable};this.setShaderModuleProps({pathStyle:s})}}}getDashOffsets(e){const t=[0],i=this.props.positionFormat==="XY"?2:3,s=Array.isArray(e[0]),o=s?e.length:e.length/i;let r,n;for(let l=0;l<o-1;l++)r=s?e[l]:e.slice(l*i,l*i+i),r=this.projectPosition(r),l>0&&(t[l]=t[l-1]+ge(n,r)),n=r;return t[o-1]=0,t}}re.defaultProps=rt;re.extensionName="PathStyleExtension";const oe=`layout(std140) uniform fillUniforms {
  vec2 patternTextureSize;
  bool patternEnabled;
  bool patternMask;
  vec2 uvCoordinateOrigin;
  vec2 uvCoordinateOrigin64Low;
} fill;
`,ot=`
in vec4 fillPatternFrames;
in float fillPatternScales;
in vec2 fillPatternOffsets;

out vec2 fill_uv;
out vec4 fill_patternBounds;
out vec4 fill_patternPlacement;
`,at=`
${oe}
${ot}
`,nt=`
uniform sampler2D fill_patternTexture;

in vec4 fill_patternBounds;
in vec4 fill_patternPlacement;
in vec2 fill_uv;

const float FILL_UV_SCALE = 512.0 / 40000000.0;
`,lt=`
${oe}
${nt}
`,ct={"vs:DECKGL_FILTER_GL_POSITION":`
    fill_uv = geometry.position.xy;
  `,"vs:DECKGL_FILTER_COLOR":`
    if (fill.patternEnabled) {
      fill_patternBounds = fillPatternFrames / vec4(fill.patternTextureSize, fill.patternTextureSize);
      fill_patternPlacement.xy = fillPatternOffsets;
      fill_patternPlacement.zw = fillPatternScales * fillPatternFrames.zw;
    }
  `,"fs:DECKGL_FILTER_COLOR":`
    if (fill.patternEnabled) {
      vec2 scale = FILL_UV_SCALE * fill_patternPlacement.zw;
      vec2 patternUV = mod(mod(fill.uvCoordinateOrigin, scale) + fill.uvCoordinateOrigin64Low + fill_uv, scale) / scale;
      patternUV = mod(fill_patternPlacement.xy + patternUV, 1.0);

      vec2 texCoords = fill_patternBounds.xy + fill_patternBounds.zw * patternUV;

      vec4 patternColor = texture(fill_patternTexture, texCoords);
      color.a *= patternColor.a;
      if (!fill.patternMask) {
        color.rgb = patternColor.rgb;
      }
    }
  `};function dt(a){if(!a)return{};const e={};if("fillPatternTexture"in a){const{fillPatternTexture:t}=a;e.fill_patternTexture=t,e.patternTextureSize=[t.width,t.height]}if("project"in a){const{fillPatternMask:t=!0,fillPatternEnabled:i=!0}=a,s=_.getUniforms(a.project),{commonOrigin:o}=s,r=[V(o[0]),V(o[1])];e.uvCoordinateOrigin=o.slice(0,2),e.uvCoordinateOrigin64Low=r,e.patternMask=t,e.patternEnabled=i}return e}const ft={name:"fill",vs:at,fs:lt,inject:ct,dependencies:[_],getUniforms:dt,uniformTypes:{patternTextureSize:"vec2<f32>",patternEnabled:"i32",patternMask:"i32",uvCoordinateOrigin:"vec2<f32>",uvCoordinateOrigin64Low:"vec2<f32>"}},ut={fillPatternEnabled:!0,fillPatternAtlas:{type:"image",value:null,async:!0,parameters:{lodMaxClamp:0}},fillPatternMapping:{type:"object",value:{},async:!0},fillPatternMask:!0,getFillPattern:{type:"accessor",value:a=>a.pattern},getFillPatternScale:{type:"accessor",value:1},getFillPatternOffset:{type:"accessor",value:[0,0]}};class ae extends y{constructor({pattern:e=!1}={}){super({pattern:e})}isEnabled(e){return e.getAttributeManager()!==null&&!("pathTesselator"in e.state)}getShaders(e){return e.isEnabled(this)?{modules:[e.opts.pattern&&ft].filter(Boolean)}:null}initializeState(e,t){if(!t.isEnabled(this))return;const i=this.getAttributeManager();t.opts.pattern&&i.add({fillPatternFrames:{size:4,stepMode:"dynamic",accessor:"getFillPattern",transform:t.getPatternFrame.bind(this)},fillPatternScales:{size:1,stepMode:"dynamic",accessor:"getFillPatternScale",defaultValue:1},fillPatternOffsets:{size:2,stepMode:"dynamic",accessor:"getFillPatternOffset"}}),this.setState({emptyTexture:this.context.device.createTexture({data:new Uint8Array(4),width:1,height:1})})}updateState({props:e,oldProps:t},i){i.isEnabled(this)&&e.fillPatternMapping&&e.fillPatternMapping!==t.fillPatternMapping&&this.getAttributeManager().invalidate("getFillPattern")}draw(e,t){if(!t.isEnabled(this))return;const{fillPatternAtlas:i,fillPatternEnabled:s,fillPatternMask:o}=this.props,r={project:e.shaderModuleProps.project,fillPatternEnabled:s,fillPatternMask:o,fillPatternTexture:i||this.state.emptyTexture};this.setShaderModuleProps({fill:r})}finalizeState(){const e=this.state.emptyTexture;e==null||e.delete()}getPatternFrame(e){const{fillPatternMapping:t}=this.getCurrentLayer().props,i=t&&t[e];return i?[i.x,i.y,i.width,i.height]:[0,0,0,0]}}ae.defaultProps=ut;ae.extensionName="FillStyleExtension";const ht=`
in float collisionPriorities;

uniform sampler2D collision_texture;

layout(std140) uniform collisionUniforms {
  bool sort;
  bool enabled;
} collision;

vec2 collision_getCoords(vec4 position) {
  vec4 collision_clipspace = project_common_position_to_clipspace(position);
  return (1.0 + collision_clipspace.xy / collision_clipspace.w) / 2.0;
}

float collision_match(vec2 tex, vec3 pickingColor) {
  vec4 collision_pickingColor = texture(collision_texture, tex);
  float delta = dot(abs(collision_pickingColor.rgb - pickingColor), vec3(1.0));
  float e = 0.001;
  return step(delta, e);
}

float collision_isVisible(vec2 texCoords, vec3 pickingColor) {
  if (!collision.enabled) {
    return 1.0;
  }

  // Visibility test, sample area of 5x5 pixels in order to fade in/out.
  // Due to the locality, the lookups will be cached
  // This reduces the flicker present when objects are shown/hidden
  const int N = 2;
  float accumulator = 0.0;
  vec2 step = vec2(1.0 / project.viewportSize);

  const float floatN = float(N);
  vec2 delta = -floatN * step;
  for(int i = -N; i <= N; i++) {
    delta.x = -step.x * floatN;
    for(int j = -N; j <= N; j++) {
      accumulator += collision_match(texCoords + delta, pickingColor);
      delta.x += step.x;
    }
    delta.y += step.y;
  }

  float W = 2.0 * floatN + 1.0;
  return pow(accumulator / (W * W), 2.2);
}
`,pt={"vs:#decl":`
  float collision_fade = 1.0;
`,"vs:DECKGL_FILTER_GL_POSITION":`
  if (collision.sort) {
    float collisionPriority = collisionPriorities;
    position.z = -0.001 * collisionPriority * position.w; // Support range -1000 -> 1000
  }

  if (collision.enabled) {
    vec4 collision_common_position = project_position(vec4(geometry.worldPosition, 1.0));
    vec2 collision_texCoords = collision_getCoords(collision_common_position);
    collision_fade = collision_isVisible(collision_texCoords, geometry.pickingColor / 255.0);
    if (collision_fade < 0.0001) {
      // Position outside clip space bounds to discard
      position = vec4(0.0, 0.0, 2.0, 1.0);
    }
  }
  `,"vs:DECKGL_FILTER_COLOR":`
  color.a *= collision_fade;
  `},mt=a=>{if(!a||!("dummyCollisionMap"in a))return{};const{enabled:e,collisionFBO:t,drawToCollisionMap:i,dummyCollisionMap:s}=a;return{enabled:e&&!i,sort:!!i,collision_texture:!i&&t?t.colorAttachments[0]:s}},gt={name:"collision",dependencies:[_],vs:ht,inject:pt,getUniforms:mt,uniformTypes:{sort:"i32",enabled:"i32"}};class vt extends R{renderCollisionMap(e,t){const s=[0,0,0,0],o=[1,1,e.width-2*1,e.height-2*1];this.render({...t,clearColor:s,scissorRect:o,target:e,pass:"collision"})}getLayerParameters(e,t,i){return{...e.props.parameters,blend:!1,depthWriteEnabled:!0,depthCompare:"less-equal"}}getShaderModuleProps(){return{collision:{drawToCollisionMap:!0},picking:{isActive:1,isAttribute:!1},lighting:{enabled:!1}}}}const L=2;class _t{constructor(){this.id="collision-filter-effect",this.props=null,this.useInPicking=!0,this.order=1,this.channels={},this.collisionFBOs={}}setup(e){this.context=e;const{device:t}=e;this.dummyCollisionMap=t.createTexture({width:1,height:1}),this.collisionFilterPass=new vt(t,{id:"default-collision-filter"})}preRender({effects:e,layers:t,layerFilter:i,viewports:s,onViewportActive:o,views:r,isPicking:n,preRenderStats:l={}}){var v;const{device:c}=this.context;if(n)return;const f=t.filter(({props:{visible:g,collisionEnabled:x}})=>g&&x);if(f.length===0){this.channels={};return}const d=e==null?void 0:e.filter(g=>g.useInPicking&&l[g.id]),u=(v=l["mask-effect"])==null?void 0:v.didRender,h=this._groupByCollisionGroup(c,f),p=s[0],P=!this.lastViewport||!this.lastViewport.equals(p)||u;for(const g in h){const x=this.collisionFBOs[g],T=h[g],[F,b]=c.canvasContext.getPixelSize();x.resize({width:F/L,height:b/L}),this._render(T,{effects:d,layerFilter:i,onViewportActive:o,views:r,viewport:p,viewportChanged:P})}}_render(e,{effects:t,layerFilter:i,onViewportActive:s,views:o,viewport:r,viewportChanged:n}){const{collisionGroup:l}=e,c=this.channels[l];if(!c)return;const f=n||e===c||!Y(c.layers,e.layers,1)||e.layerBounds.some((d,u)=>!$(d,c.layerBounds[u]))||e.allLayersLoaded!==c.allLayersLoaded||e.layers.some(d=>d.props.transitions);if(this.channels[l]=e,f){this.lastViewport=r;const d=this.collisionFBOs[l];this.collisionFilterPass.renderCollisionMap(d,{pass:"collision-filter",isPicking:!0,layers:e.layers,effects:t,layerFilter:i,viewports:r?[r]:[],onViewportActive:s,views:o,shaderModuleProps:{collision:{enabled:!0,dummyCollisionMap:this.dummyCollisionMap},project:{devicePixelRatio:d.device.canvasContext.getDevicePixelRatio()/L}}})}}_groupByCollisionGroup(e,t){const i={};for(const s of t){const o=s.props.collisionGroup;let r=i[o];r||(r={collisionGroup:o,layers:[],layerBounds:[],allLayersLoaded:!0},i[o]=r),r.layers.push(s),r.layerBounds.push(s.getBounds()),s.isLoaded||(r.allLayersLoaded=!1)}for(const s of Object.keys(i))this.collisionFBOs[s]||this.createFBO(e,s),this.channels[s]||(this.channels[s]=i[s]);for(const s of Object.keys(this.collisionFBOs))i[s]||this.destroyFBO(s);return i}getShaderModuleProps(e){const{collisionGroup:t,collisionEnabled:i}=e.props,{collisionFBOs:s,dummyCollisionMap:o}=this,r=s[t];return{collision:{enabled:i&&!!r,collisionFBO:r,dummyCollisionMap:o}}}cleanup(){this.dummyCollisionMap&&(this.dummyCollisionMap.delete(),this.dummyCollisionMap=void 0),this.channels={};for(const e of Object.keys(this.collisionFBOs))this.destroyFBO(e);this.collisionFBOs={},this.lastViewport=void 0}createFBO(e,t){const{width:i,height:s}=e.getDefaultCanvasContext().canvas,o=e.createTexture({format:"rgba8unorm",width:i,height:s,sampler:{minFilter:"nearest",magFilter:"nearest",addressModeU:"clamp-to-edge",addressModeV:"clamp-to-edge"}}),r=e.createTexture({format:"depth16unorm",width:i,height:s});this.collisionFBOs[t]=e.createFramebuffer({id:`collision-${t}`,width:i,height:s,colorAttachments:[o],depthStencilAttachment:r})}destroyFBO(e){var i,s;const t=this.collisionFBOs[e];(i=t.colorAttachments[0])==null||i.destroy(),(s=t.depthStencilAttachment)==null||s.destroy(),t.destroy(),delete this.collisionFBOs[e]}}const yt={getCollisionPriority:{type:"accessor",value:0},collisionEnabled:!0,collisionGroup:{type:"string",value:"default"},collisionTestProps:{}};class ne extends y{getShaders(){return{modules:[gt]}}draw({shaderModuleProps:e}){var t;(t=e.collision)!=null&&t.drawToCollisionMap&&(this.props=this.clone(this.props.collisionTestProps).props)}initializeState(e,t){var s;if(this.getAttributeManager()===null)return;(s=this.context.deck)==null||s._addDefaultEffect(new _t),this.getAttributeManager().add({collisionPriorities:{size:1,stepMode:"dynamic",accessor:"getCollisionPriority"}})}getNeedsPickingBuffer(){return this.props.collisionEnabled}}ne.defaultProps=yt;ne.extensionName="CollisionFilterExtension";const le=`layout(std140) uniform maskUniforms {
  vec4 bounds;
  highp int channel;
  bool enabled;
  bool inverted;
  bool maskByInstance;
} mask;
`,xt=`
vec2 mask_getCoords(vec4 position) {
  return (position.xy - mask.bounds.xy) / (mask.bounds.zw - mask.bounds.xy);
}
`,Pt=`
${le}
${xt}
`,Mt=`
uniform sampler2D mask_texture;

bool mask_isInBounds(vec2 texCoords) {
  if (!mask.enabled) {
    return true;
  }
  vec4 maskColor = texture(mask_texture, texCoords);
  float maskValue = 1.0;
  if (mask.channel == 0) {
    maskValue = maskColor.r;
  } else if (mask.channel == 1) {
    maskValue = maskColor.g;
  } else if (mask.channel == 2) {
    maskValue = maskColor.b;
  } else if (mask.channel == 3) {
    maskValue = maskColor.a;
  }

  if (mask.inverted) {
    return maskValue >= 0.5;
  } else {
    return maskValue < 0.5;
  }
}
`,bt=`
${le}
${Mt}
`,Tt={"vs:#decl":`
out vec2 mask_texCoords;
`,"vs:#main-end":`
   vec4 mask_common_position;
   if (mask.maskByInstance) {
     mask_common_position = project_position(vec4(geometry.worldPosition, 1.0));
   } else {
     mask_common_position = geometry.position;
   }
   mask_texCoords = mask_getCoords(mask_common_position);
`,"fs:#decl":`
in vec2 mask_texCoords;
`,"fs:#main-start":`
  if (mask.enabled) {
    bool mask = mask_isInBounds(mask_texCoords);

    // Debug: show extent of render target
    // fragColor = vec4(mask_texCoords, 0.0, 1.0);
    // fragColor = texture(mask_texture, mask_texCoords);

    if (!mask) discard;
  }
`},Ft=a=>a&&"maskMap"in a?{mask_texture:a.maskMap}:a||{},Ct={name:"mask",dependencies:[_],vs:Pt,fs:bt,inject:Tt,getUniforms:Ft,uniformTypes:{bounds:"vec4<f32>",channel:"i32",enabled:"i32",inverted:"i32",maskByInstance:"i32"}},kt={blendColorOperation:"subtract",blendColorSrcFactor:"zero",blendColorDstFactor:"one",blendAlphaOperation:"subtract",blendAlphaSrcFactor:"zero",blendAlphaDstFactor:"one"};class Lt extends R{constructor(e,t){super(e,t);const{mapSize:i=2048}=t;this.maskMap=e.createTexture({format:"rgba8unorm",width:i,height:i,sampler:{minFilter:"linear",magFilter:"linear",addressModeU:"clamp-to-edge",addressModeV:"clamp-to-edge"}}),this.fbo=e.createFramebuffer({id:"maskmap",width:i,height:i,colorAttachments:[this.maskMap]})}render(e){const t=2**e.channel,i=[255,255,255,255];super.render({...e,clearColor:i,colorMask:t,target:this.fbo,pass:"mask"})}getLayerParameters(e,t,i){return{...e.props.parameters,blend:!0,depthCompare:"always",...kt}}shouldDrawLayer(e){return e.props.operation.includes("mask")}delete(){this.fbo.delete(),this.maskMap.delete()}}function w(a,e){const t=[1/0,1/0,-1/0,-1/0];for(const i of a){const s=i.getBounds();if(s){const o=i.projectPosition(s[0],{viewport:e,autoOffset:!1}),r=i.projectPosition(s[1],{viewport:e,autoOffset:!1});t[0]=Math.min(t[0],o[0]),t[1]=Math.min(t[1],o[1]),t[2]=Math.max(t[2],r[0]),t[3]=Math.max(t[3],r[1])}}return Number.isFinite(t[0])?t:null}const Et=2048;function S(a){const{bounds:e,viewport:t,border:i=0}=a,{isGeospatial:s}=t;if(e[2]<=e[0]||e[3]<=e[1])return null;const o=t.unprojectPosition([(e[0]+e[2])/2,(e[1]+e[3])/2,0]);let{width:r,height:n,zoom:l}=a;if(l===void 0){r=r-i*2,n=n-i*2;const c=Math.min(r/(e[2]-e[0]),n/(e[3]-e[1]));l=Math.min(Math.log2(c),20)}else if(!r||!n){const c=2**l;r=Math.round(Math.abs(e[2]-e[0])*c),n=Math.round(Math.abs(e[3]-e[1])*c);const f=Et-i*2;if(r>f||n>f){const d=f/Math.max(r,n);r=Math.round(r*d),n=Math.round(n*d),l+=Math.log2(d)}}return s?new ve({id:t.id,x:i,y:i,width:r,height:n,longitude:o[0],latitude:o[1],zoom:l,orthographic:!0}):new K({id:t.id,x:i,y:i,width:r,height:n,target:o,zoom:l,flipY:!1})}function At(a,e){let t;t=a.getBounds();const i=a.projectPosition(t.slice(0,2)),s=a.projectPosition(t.slice(2,4));return[i[0],i[1],s[0],s[1]]}function B(a,e,t){if(!a)return[0,0,1,1];const i=At(e),s=Rt(i);return a[2]-a[0]<=s[2]-s[0]&&a[3]-a[1]<=s[3]-s[1]?a:[Math.max(a[0],s[0]),Math.max(a[1],s[1]),Math.min(a[2],s[2]),Math.min(a[3],s[3])]}function Rt(a){const e=a[2]-a[0],t=a[3]-a[1],i=(a[0]+a[2])/2,s=(a[1]+a[3])/2;return[i-e,s-t,i+e,s+t]}class wt{constructor(){this.id="mask-effect",this.props=null,this.useInPicking=!0,this.order=0,this.channels=[],this.masks=null}setup({device:e}){this.dummyMaskMap=e.createTexture({width:1,height:1}),this.maskPass=new Lt(e,{id:"default-mask"}),this.maskMap=this.maskPass.maskMap}preRender({layers:e,layerFilter:t,viewports:i,onViewportActive:s,views:o,effects:r,isPicking:n}){let l=!1;if(n)return{didRender:l};const c=e.filter(h=>h.props.visible&&h.props.operation.includes("mask"));if(c.length===0)return this.masks=null,this.channels.length=0,{didRender:l};this.masks={};const f=this._sortMaskChannels(c),d=i[0],u=!this.lastViewport||!this.lastViewport.equals(d);if(d.resolution!==void 0)return M.warn("MaskExtension is not supported in GlobeView")(),{didRender:l};for(const h in f){const p=this._renderChannel(f[h],{layerFilter:t,onViewportActive:s,views:o,effects:r,viewport:d,viewportChanged:u});l||(l=p)}return{didRender:l}}_renderChannel(e,{layerFilter:t,onViewportActive:i,views:s,effects:o,viewport:r,viewportChanged:n}){let l=!1;const c=this.channels[e.index];if(!c)return l;const f=e===c||e.layers.length!==c.layers.length||e.layers.some((d,u)=>d!==c.layers[u]||d.props.transitions)||e.layerBounds.some((d,u)=>d!==c.layerBounds[u]);if(e.bounds=c.bounds,e.maskBounds=c.maskBounds,this.channels[e.index]=e,f||n){this.lastViewport=r;const d=w(e.layers,r);if(e.bounds=d&&B(d,r),f||!$(e.bounds,c.bounds)){const{maskPass:u,maskMap:h}=this,p=d&&S({bounds:e.bounds,viewport:r,width:h.width,height:h.height,border:1});e.maskBounds=p?p.getBounds():[0,0,1,1],u.render({pass:"mask",channel:e.index,layers:e.layers,layerFilter:t,viewports:p?[p]:[],onViewportActive:i,views:s,effects:o,shaderModuleProps:{project:{devicePixelRatio:1}}}),l=!0}}return this.masks[e.id]={index:e.index,bounds:e.maskBounds,coordinateOrigin:e.coordinateOrigin,coordinateSystem:e.coordinateSystem},l}_sortMaskChannels(e){const t={};let i=0;for(const s of e){const{id:o}=s.root;let r=t[o];if(!r){if(++i>4){M.warn("Too many mask layers. The max supported is 4")();continue}r={id:o,index:this.channels.findIndex(n=>(n==null?void 0:n.id)===o),layers:[],layerBounds:[],coordinateOrigin:s.root.props.coordinateOrigin,coordinateSystem:s.root.props.coordinateSystem},t[o]=r}r.layers.push(s),r.layerBounds.push(s.getBounds())}for(let s=0;s<4;s++){const o=this.channels[s];(!o||!(o.id in t))&&(this.channels[s]=null)}for(const s in t){const o=t[s];o.index<0&&(o.index=this.channels.findIndex(r=>!r),this.channels[o.index]=o)}return t}getShaderModuleProps(){return{mask:{maskMap:this.masks?this.maskMap:this.dummyMaskMap,maskChannels:this.masks}}}cleanup(){this.dummyMaskMap&&(this.dummyMaskMap.delete(),this.dummyMaskMap=void 0),this.maskPass&&(this.maskPass.delete(),this.maskPass=void 0,this.maskMap=void 0),this.lastViewport=void 0,this.masks=null,this.channels.length=0}}const St={maskId:"",maskByInstance:void 0,maskInverted:!1};class ce extends y{initializeState(){var e;(e=this.context.deck)==null||e._addDefaultEffect(new wt)}getShaders(){let e="instancePositions"in this.getAttributeManager().attributes;return this.props.maskByInstance!==void 0&&(e=!!this.props.maskByInstance),this.state.maskByInstance=e,{modules:[Ct]}}draw({context:e,shaderModuleProps:t}){const i={};i.maskByInstance=!!this.state.maskByInstance;const{maskId:s,maskInverted:o}=this.props,{maskChannels:r}=t.mask||{},{viewport:n}=e;if(r&&r[s]){const{index:l,bounds:c,coordinateOrigin:f}=r[s];let{coordinateSystem:d}=r[s];i.enabled=!0,i.channel=l,i.inverted=o,d===k.DEFAULT&&(d=n.isGeospatial?k.LNGLAT:k.CARTESIAN);const u={modelMatrix:null,fromCoordinateOrigin:f,fromCoordinateSystem:d},h=this.projectPosition([c[0],c[1],0],u),p=this.projectPosition([c[2],c[3],0],u);i.bounds=[h[0],h[1],p[0],p[1]]}else s&&M.warn(`Could not find a mask layer with id: ${s}`)(),i.enabled=!1;this.setShaderModuleProps({mask:i})}}ce.defaultProps=St;ce.extensionName="MaskExtension";const m={NONE:0,WRITE_HEIGHT_MAP:1,USE_HEIGHT_MAP:2,USE_COVER:3,USE_COVER_ONLY:4,SKIP:5},Bt=Object.keys(m).map(a=>`const float TERRAIN_MODE_${a} = ${m[a]}.0;`).join(`
`),N=Bt+`
layout(std140) uniform terrainUniforms {
  float mode;
  vec4 bounds;
} terrain;

uniform sampler2D terrain_map;
`,E={name:"terrain",dependencies:[_],vs:N+"out vec3 commonPos;",fs:N+"in vec3 commonPos;",inject:{"vs:#main-start":`
if (terrain.mode == TERRAIN_MODE_SKIP) {
  gl_Position = vec4(0.0);
  return;
}
`,"vs:DECKGL_FILTER_GL_POSITION":`
commonPos = geometry.position.xyz;
if (terrain.mode == TERRAIN_MODE_WRITE_HEIGHT_MAP) {
  vec2 texCoords = (commonPos.xy - terrain.bounds.xy) / terrain.bounds.zw;
  position = vec4(texCoords * 2.0 - 1.0, 0.0, 1.0);
  commonPos.z += project.commonOrigin.z;
}
if (terrain.mode == TERRAIN_MODE_USE_HEIGHT_MAP) {
  vec3 anchor = geometry.worldPosition;
  anchor.z = 0.0;
  vec3 anchorCommon = project_position(anchor);
  vec2 texCoords = (anchorCommon.xy - terrain.bounds.xy) / terrain.bounds.zw;
  if (texCoords.x >= 0.0 && texCoords.y >= 0.0 && texCoords.x <= 1.0 && texCoords.y <= 1.0) {
    float terrainZ = texture(terrain_map, texCoords).r;
    geometry.position.z += terrainZ;
    position = project_common_position_to_clipspace(geometry.position);
  }
}
    `,"fs:#main-start":`
if (terrain.mode == TERRAIN_MODE_WRITE_HEIGHT_MAP) {
  fragColor = vec4(commonPos.z, 0.0, 0.0, 1.0);
  return;
}
    `,"fs:DECKGL_FILTER_COLOR":`
if ((terrain.mode == TERRAIN_MODE_USE_COVER) || (terrain.mode == TERRAIN_MODE_USE_COVER_ONLY)) {
  vec2 texCoords = (commonPos.xy - terrain.bounds.xy) / terrain.bounds.zw;
  vec4 pixel = texture(terrain_map, texCoords);
  if (terrain.mode == TERRAIN_MODE_USE_COVER_ONLY) {
    color = pixel;
  } else {
    // pixel is premultiplied
    color = pixel + color * (1.0 - pixel.a);
  }
  return;
}
    `},getUniforms:(a={})=>{if(!a.dummyHeightMap)return{};if("terrainSkipRender"in a||"drawToTerrainHeightMap"in a){const{drawToTerrainHeightMap:e,heightMap:t,heightMapBounds:i,dummyHeightMap:s,terrainCover:o,useTerrainHeightMap:r,terrainSkipRender:n}=a,l=_.getUniforms(a.project),{commonOrigin:c}=l;let f=n?m.SKIP:m.NONE,d=s,u=null;if(e)f=m.WRITE_HEIGHT_MAP,u=i;else if(r&&t)f=m.USE_HEIGHT_MAP,d=t,u=i;else if(o){const h=a.isPicking?o.getPickingFramebuffer():o.getRenderFramebuffer(),p=h==null?void 0:h.colorAttachments[0].texture;a.isPicking&&(f=m.SKIP),p?(d=p,f=f===m.SKIP?m.USE_COVER_ONLY:m.USE_COVER,u=o.bounds):a.isPicking&&!n&&(f=m.NONE)}return{mode:f,terrain_map:d,bounds:u?[u[0]-c[0],u[1]-c[1],u[2]-u[0],u[3]-u[1]]:[0,0,0,0]}}return{mode:m.NONE,terrain_map:a.dummyHeightMap,bounds:[0,0,0,0]}},uniformTypes:{mode:"f32",bounds:"vec4<f32>"}};function A(a,e){return a.createFramebuffer({id:e.id,colorAttachments:[a.createTexture({id:e.id,...e.float&&{format:"rgba32float",type:5126},dimension:"2d",width:1,height:1,sampler:e.interpolate===!1?{minFilter:"nearest",magFilter:"nearest"}:{minFilter:"linear",magFilter:"linear"}})]})}class Ot{constructor(e){this.isDirty=!0,this.renderViewport=null,this.bounds=null,this.layers=[],this.targetBounds=null,this.targetBoundsCommon=null,this.targetLayer=e,this.tile=de(e)}get id(){return this.targetLayer.id}get isActive(){return!!this.targetLayer.getCurrentLayer()}shouldUpdate({targetLayer:e,viewport:t,layers:i,layerNeedsRedraw:s}){e&&(this.targetLayer=e);const o=t?this._updateViewport(t):!1;let r=i?this._updateLayers(i):!1;if(s){for(const n of this.layers)if(s[n]){r=!0;break}}return r||o}_updateLayers(e){let t=!1;if(e=this.tile?Dt(this.tile,e):e,e.length!==this.layers.length)t=!0;else for(let i=0;i<e.length;i++)if(e[i].id!==this.layers[i]){t=!0;break}return t&&(this.layers=e.map(i=>i.id)),t}_updateViewport(e){var o;const t=this.targetLayer;let i=!1;if(this.tile&&"boundingBox"in this.tile){if(!this.targetBounds){i=!0,this.targetBounds=this.tile.boundingBox;const r=e.projectPosition(this.targetBounds[0]),n=e.projectPosition(this.targetBounds[1]);this.targetBoundsCommon=[r[0],r[1],n[0],n[1]]}}else this.targetBounds!==t.getBounds()&&(i=!0,this.targetBounds=t.getBounds(),this.targetBoundsCommon=w([t],e));if(!this.targetBoundsCommon)return!1;const s=Math.ceil(e.zoom+.5);if(this.tile)this.bounds=this.targetBoundsCommon;else{const r=(o=this.renderViewport)==null?void 0:o.zoom;i=i||s!==r;const n=B(this.targetBoundsCommon,e),l=this.bounds;i=i||!l||n.some((c,f)=>c!==l[f]),this.bounds=n}return i&&(this.renderViewport=S({bounds:this.bounds,zoom:s,viewport:e})),i}getRenderFramebuffer(){return!this.renderViewport||this.layers.length===0?null:(this.fbo||(this.fbo=A(this.targetLayer.context.device,{id:this.id})),this.fbo)}getPickingFramebuffer(){return!this.renderViewport||this.layers.length===0&&!this.targetLayer.props.pickable?null:(this.pickingFbo||(this.pickingFbo=A(this.targetLayer.context.device,{id:`${this.id}-picking`,interpolate:!1})),this.pickingFbo)}filterLayers(e){return e.filter(({id:t})=>this.layers.includes(t))}delete(){const{fbo:e,pickingFbo:t}=this;e&&(e.colorAttachments[0].destroy(),e.destroy()),t&&(t.colorAttachments[0].destroy(),t.destroy())}}function Dt(a,e){return e.filter(t=>{const i=de(t);return i?It(a.boundingBox,i.boundingBox):!0})}function de(a){for(;a;){const{tile:e}=a.props;if(e)return e;a=a.parent}return null}function It(a,e){return a&&e?a[0][0]<e[1][0]&&e[0][0]<a[1][0]&&a[0][1]<e[1][1]&&e[0][1]<a[1][1]:!1}const jt={blendColorOperation:"max",blendColorSrcFactor:"one",blendColorDstFactor:"one",blendAlphaOperation:"max",blendAlphaSrcFactor:"one",blendAlphaDstFactor:"one"};class Vt extends R{getRenderableLayers(e,t){const{layers:i}=t,s=[],o=this._getDrawLayerParams(e,t,!0);for(let r=0;r<i.length;r++){const n=i[r];!n.isComposite&&o[r].shouldDrawLayer&&s.push(n)}return s}renderHeightMap(e,t){const i=e.getRenderFramebuffer(),s=e.renderViewport;!i||!s||(i.resize(s),this.render({...t,target:i,pass:"terrain-height-map",layers:t.layers,viewports:[s],effects:[],clearColor:[0,0,0,0]}))}renderTerrainCover(e,t){const i=e.getRenderFramebuffer(),s=e.renderViewport;if(!i||!s)return;const o=e.filterLayers(t.layers);i.resize(s),this.render({...t,target:i,pass:`terrain-cover-${e.id}`,layers:o,viewports:[s],clearColor:[0,0,0,0]})}getLayerParameters(e,t,i){return{...e.props.parameters,blend:!0,depthCompare:"always",...e.props.operation.includes("terrain")&&jt}}getShaderModuleProps(e,t,i){return{terrain:{project:i.project}}}}class zt extends ye{constructor(){super(...arguments),this.drawParameters={}}getRenderableLayers(e,t){const{layers:i}=t,s=[];this.drawParameters={},this._resetColorEncoder(t.pickZ);const o=this._getDrawLayerParams(e,t);for(let r=0;r<i.length;r++){const n=i[r];!n.isComposite&&o[r].shouldDrawLayer&&(s.push(n),this.drawParameters[n.id]=o[r].layerParameters)}return s}renderTerrainCover(e,t){var c;const i=e.getPickingFramebuffer(),s=e.renderViewport;if(!i||!s)return;const o=e.filterLayers(t.layers),r=e.targetLayer;r.props.pickable&&o.unshift(r),i.resize(s);const n=this.drawParameters[r.id],l=((c=n==null?void 0:n.blendColor)==null?void 0:c[3])??0;this.render({...t,pickingFBO:i,pass:`terrain-cover-picking-${e.id}`,layers:o,viewports:[s],cullRect:void 0,deviceRect:s,pickZ:!1,clearColor:[0,0,0,l]})}getLayerParameters(e,t,i){let s;return this.drawParameters[e.id]?s=this.drawParameters[e.id]:(s=super.getLayerParameters(e,t,i),s.blend=!0),{...s,depthCompare:"always",blendAlphaSrcFactor:"constant"}}getShaderModuleProps(e,t,i){return{...super.getShaderModuleProps(e,t,i),terrain:{project:i.project}}}}const U=2048;class G{static isSupported(e){return e.isTextureFormatRenderable("rgba32float")}constructor(e){this.renderViewport=null,this.bounds=null,this.layers=[],this.layersBounds=[],this.layersBoundsCommon=null,this.lastViewport=null,this.device=e}getRenderFramebuffer(){return this.renderViewport?(this.fbo||(this.fbo=A(this.device,{id:"height-map",float:!0})),this.fbo):null}shouldUpdate({layers:e,viewport:t}){const i=e.length!==this.layers.length||e.some((o,r)=>o!==this.layers[r]||o.props.transitions||o.getBounds()!==this.layersBounds[r]);i&&(this.layers=e,this.layersBounds=e.map(o=>o.getBounds()),this.layersBoundsCommon=w(e,t));const s=!this.lastViewport||!t.equals(this.lastViewport);if(!this.layersBoundsCommon)this.renderViewport=null;else if(i||s){const o=B(this.layersBoundsCommon,t);if(o[2]<=o[0]||o[3]<=o[1])return this.renderViewport=null,!1;this.bounds=o,this.lastViewport=t;const r=t.scale,n=(o[2]-o[0])*r,l=(o[3]-o[1])*r;return this.renderViewport=n>0||l>0?S({bounds:[t.center[0]-1,t.center[1]-1,t.center[0]+1,t.center[1]+1],zoom:t.zoom,width:Math.min(n,U),height:Math.min(l,U),viewport:t}):null,!0}return!1}delete(){this.fbo&&(this.fbo.colorAttachments[0].delete(),this.fbo.delete())}}class Nt{constructor(){this.id="terrain-effect",this.props=null,this.useInPicking=!0,this.isPicking=!1,this.isDrapingEnabled=!1,this.terrainCovers=new Map}setup({device:e,deck:t}){this.dummyHeightMap=e.createTexture({width:1,height:1,data:new Uint8Array([0,0,0,0])}),this.terrainPass=new Vt(e,{id:"terrain"}),this.terrainPickingPass=new zt(e,{id:"terrain-picking"}),G.isSupported(e)?this.heightMap=new G(e):M.warn("Terrain offset mode is not supported by this browser")(),t._addDefaultShaderModule(E)}preRender(e){var c;if(e.pickZ){this.isDrapingEnabled=!1;return}const{viewports:t}=e,i=e.pass.startsWith("picking");this.isPicking=i,this.isDrapingEnabled=!0;const s=t[0],o=(i?this.terrainPickingPass:this.terrainPass).getRenderableLayers(s,e),r=o.filter(f=>f.props.operation.includes("terrain"));if(r.length===0)return;i||o.filter(d=>d.state.terrainDrawMode==="offset").length>0&&this._updateHeightMap(r,s,e);const n=o.filter(f=>f.state.terrainDrawMode==="drape"),l=(c=e.effects)==null?void 0:c.filter(f=>f!==this);this._updateTerrainCovers(r,n,s,{...e,effects:l})}getShaderModuleProps(e,t){var o,r,n;if(e.props.operation.includes("mask"))return{terrain:{dummyHeightMap:this.dummyHeightMap}};const{terrainDrawMode:i}=e.state,s=this.isDrapingEnabled?this.terrainCovers.get(e.id)??null:null;return this.isPicking&&e.props.operation.includes("terrain")&&(e.state._hasPickingCover=!!(s!=null&&s.getPickingFramebuffer())),{terrain:{project:t.project,isPicking:this.isPicking,heightMap:((r=(o=this.heightMap)==null?void 0:o.getRenderFramebuffer())==null?void 0:r.colorAttachments[0].texture)||null,heightMapBounds:(n=this.heightMap)==null?void 0:n.bounds,dummyHeightMap:this.dummyHeightMap,terrainCover:s,useTerrainHeightMap:i==="offset",terrainSkipRender:i==="drape"||!e.props.operation.includes("draw")}}}cleanup({deck:e}){this.dummyHeightMap&&(this.dummyHeightMap.delete(),this.dummyHeightMap=void 0),this.heightMap&&(this.heightMap.delete(),this.heightMap=void 0);for(const t of this.terrainCovers.values())t.delete();this.terrainCovers.clear(),e._removeDefaultShaderModule(E)}_updateHeightMap(e,t,i){!this.heightMap||!this.heightMap.shouldUpdate({layers:e,viewport:t})||this.terrainPass.renderHeightMap(this.heightMap,{...i,layers:e,shaderModuleProps:{terrain:{heightMapBounds:this.heightMap.bounds,dummyHeightMap:this.dummyHeightMap,drawToTerrainHeightMap:!0},project:{devicePixelRatio:1}}})}_updateTerrainCovers(e,t,i,s){const o={};for(const r of t)r.state.terrainCoverNeedsRedraw&&(o[r.id]=!0,r.state.terrainCoverNeedsRedraw=!1);for(const r of this.terrainCovers.values())r.isDirty=r.isDirty||r.shouldUpdate({layerNeedsRedraw:o});for(const r of e)this._updateTerrainCover(r,t,i,s);this.isPicking||this._pruneTerrainCovers()}_updateTerrainCover(e,t,i,s){const o=this.isPicking?this.terrainPickingPass:this.terrainPass;let r=this.terrainCovers.get(e.id);r||(r=new Ot(e),this.terrainCovers.set(e.id,r));try{const n=r.shouldUpdate({targetLayer:e,viewport:i,layers:t});(this.isPicking||r.isDirty||n)&&(o.renderTerrainCover(r,{...s,layers:t,shaderModuleProps:{terrain:{dummyHeightMap:this.dummyHeightMap,terrainSkipRender:!1},project:{devicePixelRatio:1}}}),this.isPicking||(r.isDirty=!1))}catch(n){e.raiseError(n,`Error rendering terrain cover ${r.id}`)}}_pruneTerrainCovers(){const e=[];for(const[t,i]of this.terrainCovers)i.isActive||e.push(t);for(const t of e)this.terrainCovers.delete(t)}}const Ut={terrainDrawMode:void 0};class fe extends y{getShaders(){return{modules:[E]}}initializeState(){var e;(e=this.context.deck)==null||e._addDefaultEffect(new Nt)}updateState(e){var o;const{props:t,oldProps:i}=e;if(this.state.terrainDrawMode&&t.terrainDrawMode===i.terrainDrawMode&&t.extruded===i.extruded)return;let{terrainDrawMode:s}=t;if(!s){const r=this.props.extruded,n=(o=this.getAttributeManager())==null?void 0:o.attributes,l=n&&"instancePositions"in n;s=r||l?"offset":"drape"}this.setState({terrainDrawMode:s})}onNeedsRedraw(){const e=this.state;e.terrainDrawMode==="drape"&&(e.terrainCoverNeedsRedraw=!0)}}fe.defaultProps=Ut;fe.extensionName="TerrainExtension";export{X as BrushingExtension,Xt as ClipExtension,ne as CollisionFilterExtension,se as DataFilterExtension,ae as FillStyleExtension,Qe as Fp64Extension,ce as MaskExtension,re as PathStyleExtension,fe as _TerrainExtension,Ze as project64};
//# sourceMappingURL=index-CynWJau2.js.map
