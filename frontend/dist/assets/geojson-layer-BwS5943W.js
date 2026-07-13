var Io=Object.defineProperty;var Mo=(o,t,e)=>t in o?Io(o,t,{enumerable:!0,configurable:!0,writable:!0,value:e}):o[t]=e;var B=(o,t,e)=>Mo(o,typeof t!="symbol"?t+"":t,e);import{l as Ro,p as Oo,ax as zo,az as Fo,aA as ko,av as Bo,x as Uo,B as K,aB as Ie,z as Ot,aC as Zt,d as S,m as Ti,aD as Do,r as St,y as wi,o as mt,aE as No,ay as D,v as Me}from"./deep-equal-Dwhz1A9B.js";import{M,u as Go,f as jo,m as Re}from"./shader-Cz896RLg.js";import{c as W,w as Vo,T as me,d as O,P as Y,C as zt,A as q,x as $,y as Kt,z as tt,L as Wo,b as se,f as $o}from"./webgl-developer-tools-BwtbniD_.js";import{g as Ho}from"./array-utils-flat-Bshre25B.js";import{WebGLDevice as Xt}from"./webgl-device-Cfynycx5.js";import{g as Yo}from"./index-CCgdh6fQ.js";const Zo=`out vec4 transform_output;
void main() {
  transform_output = vec4(0);
}`,Ko=`#version 300 es
${Zo}`;function Xo(o){const{input:t,inputChannels:e,output:i}={};if(!t)return Ko;if(!e)throw new Error("inputChannels");const n=qo(e),s=Jo(t,e);return`#version 300 es
in ${n} ${t};
out vec4 ${i};
void main() {
  ${i} = ${s};
}`}function qo(o){switch(o){case 1:return"float";case 2:return"vec2";case 3:return"vec3";case 4:return"vec4";default:throw new Error(`invalid channels: ${o}`)}}function Jo(o,t){switch(t){case 1:return`vec4(${o}, 0.0, 0.0, 1.0)`;case 2:return`vec4(${o}, 0.0, 1.0)`;case 3:return`vec4(${o}, 1.0)`;case 4:return o;default:throw new Error(`invalid channels: ${t}`)}}function Ei(o,t=!0){return o??t}function Ii(o=[0,0,0],t=!0){return t?o.map(e=>e/255):[...o]}function Qo(o,t=!0){const e=Ii(o.slice(0,3),t),i=Number.isFinite(o[3]),n=i?o[3]:1;return[e[0],e[1],e[2],t&&i?n/255:n]}const Oe=`layout(std140) uniform floatColorsUniforms {
  float useByteColors;
} floatColors;

vec3 floatColors_normalize(vec3 inputColor) {
  return floatColors.useByteColors > 0.5 ? inputColor / 255.0 : inputColor;
}

vec4 floatColors_normalize(vec4 inputColor) {
  return floatColors.useByteColors > 0.5 ? inputColor / 255.0 : inputColor;
}

vec4 floatColors_premultiplyAlpha(vec4 inputColor) {
  return vec4(inputColor.rgb * inputColor.a, inputColor.a);
}

vec4 floatColors_unpremultiplyAlpha(vec4 inputColor) {
  return inputColor.a > 0.0 ? vec4(inputColor.rgb / inputColor.a, inputColor.a) : vec4(0.0);
}

vec4 floatColors_premultiply_alpha(vec4 inputColor) {
  return floatColors_premultiplyAlpha(inputColor);
}

vec4 floatColors_unpremultiply_alpha(vec4 inputColor) {
  return floatColors_unpremultiplyAlpha(inputColor);
}
`,tn=`struct floatColorsUniforms {
  useByteColors: f32
};

@group(0) @binding(auto) var<uniform> floatColors : floatColorsUniforms;

fn floatColors_normalize(inputColor: vec3<f32>) -> vec3<f32> {
  return select(inputColor, inputColor / 255.0, floatColors.useByteColors > 0.5);
}

fn floatColors_normalize4(inputColor: vec4<f32>) -> vec4<f32> {
  return select(inputColor, inputColor / 255.0, floatColors.useByteColors > 0.5);
}

fn floatColors_premultiplyAlpha(inputColor: vec4<f32>) -> vec4<f32> {
  return vec4<f32>(inputColor.rgb * inputColor.a, inputColor.a);
}

fn floatColors_unpremultiplyAlpha(inputColor: vec4<f32>) -> vec4<f32> {
  return select(
    vec4<f32>(0.0),
    vec4<f32>(inputColor.rgb / inputColor.a, inputColor.a),
    inputColor.a > 0.0
  );
}

fn floatColors_premultiply_alpha(inputColor: vec4<f32>) -> vec4<f32> {
  return floatColors_premultiplyAlpha(inputColor);
}

fn floatColors_unpremultiply_alpha(inputColor: vec4<f32>) -> vec4<f32> {
  return floatColors_unpremultiplyAlpha(inputColor);
}
`,Mi={name:"floatColors",props:{},uniforms:{},vs:Oe,fs:Oe,source:tn,uniformTypes:{useByteColors:"f32"},defaultUniforms:{useByteColors:!0}},en=[0,1,1,1],on=`layout(std140) uniform pickingUniforms {
  float isActive;
  float isAttribute;
  float isHighlightActive;
  float useByteColors;
  vec3 highlightedObjectColor;
  vec4 highlightColor;
} picking;

out vec4 picking_vRGBcolor_Avalid;

// Normalize unsigned byte color to 0-1 range
vec3 picking_normalizeColor(vec3 color) {
  return picking.useByteColors > 0.5 ? color / 255.0 : color;
}

// Normalize unsigned byte color to 0-1 range
vec4 picking_normalizeColor(vec4 color) {
  return picking.useByteColors > 0.5 ? color / 255.0 : color;
}

bool picking_isColorZero(vec3 color) {
  return dot(color, vec3(1.0)) < 0.00001;
}

bool picking_isColorValid(vec3 color) {
  return dot(color, vec3(1.0)) > 0.00001;
}

// Check if this vertex is highlighted 
bool isVertexHighlighted(vec3 vertexColor) {
  vec3 highlightedObjectColor = picking_normalizeColor(picking.highlightedObjectColor);
  return
    bool(picking.isHighlightActive) && picking_isColorZero(abs(vertexColor - highlightedObjectColor));
}

// Set the current picking color
void picking_setPickingColor(vec3 pickingColor) {
  pickingColor = picking_normalizeColor(pickingColor);

  if (bool(picking.isActive)) {
    // Use alpha as the validity flag. If pickingColor is [0, 0, 0] fragment is non-pickable
    picking_vRGBcolor_Avalid.a = float(picking_isColorValid(pickingColor));

    if (!bool(picking.isAttribute)) {
      // Stores the picking color so that the fragment shader can render it during picking
      picking_vRGBcolor_Avalid.rgb = pickingColor;
    }
  } else {
    // Do the comparison with selected item color in vertex shader as it should mean fewer compares
    picking_vRGBcolor_Avalid.a = float(isVertexHighlighted(pickingColor));
  }
}

void picking_setPickingAttribute(float value) {
  if (bool(picking.isAttribute)) {
    picking_vRGBcolor_Avalid.r = value;
  }
}

void picking_setPickingAttribute(vec2 value) {
  if (bool(picking.isAttribute)) {
    picking_vRGBcolor_Avalid.rg = value;
  }
}

void picking_setPickingAttribute(vec3 value) {
  if (bool(picking.isAttribute)) {
    picking_vRGBcolor_Avalid.rgb = value;
  }
}
`,nn=`layout(std140) uniform pickingUniforms {
  float isActive;
  float isAttribute;
  float isHighlightActive;
  float useByteColors;
  vec3 highlightedObjectColor;
  vec4 highlightColor;
} picking;

in vec4 picking_vRGBcolor_Avalid;

/*
 * Returns highlight color if this item is selected.
 */
vec4 picking_filterHighlightColor(vec4 color) {
  // If we are still picking, we don't highlight
  if (picking.isActive > 0.5) {
    return color;
  }

  bool selected = bool(picking_vRGBcolor_Avalid.a);

  if (selected) {
    // Blend in highlight color based on its alpha value
    float highLightAlpha = picking.highlightColor.a;
    float blendedAlpha = highLightAlpha + color.a * (1.0 - highLightAlpha);
    float highLightRatio = highLightAlpha / blendedAlpha;

    vec3 blendedRGB = mix(color.rgb, picking.highlightColor.rgb, highLightRatio);
    return vec4(blendedRGB, blendedAlpha);
  } else {
    return color;
  }
}

/*
 * Returns picking color if picking enabled else unmodified argument.
 */
vec4 picking_filterPickingColor(vec4 color) {
  if (bool(picking.isActive)) {
    if (picking_vRGBcolor_Avalid.a == 0.0) {
      discard;
    }
    return picking_vRGBcolor_Avalid;
  }
  return color;
}

/*
 * Returns picking color if picking is enabled if not
 * highlight color if this item is selected, otherwise unmodified argument.
 */
vec4 picking_filterColor(vec4 color) {
  vec4 highlightColor = picking_filterHighlightColor(color);
  return picking_filterPickingColor(highlightColor);
}
`,ze={props:{},uniforms:{},name:"picking",uniformTypes:{isActive:"f32",isAttribute:"f32",isHighlightActive:"f32",useByteColors:"f32",highlightedObjectColor:"vec3<f32>",highlightColor:"vec4<f32>"},defaultUniforms:{isActive:!1,isAttribute:!1,isHighlightActive:!1,useByteColors:!0,highlightedObjectColor:[0,0,0],highlightColor:en},vs:on,fs:nn,getUniforms:sn};function sn(o={},t){const e={},i=Ei(o.useByteColors,!0);if(o.highlightedObjectColor!==void 0)if(o.highlightedObjectColor===null)e.isHighlightActive=!1;else{e.isHighlightActive=!0;const n=o.highlightedObjectColor.slice(0,3);e.highlightedObjectColor=n}return o.highlightColor&&(e.highlightColor=Qo(o.highlightColor,i)),o.isActive!==void 0&&(e.isActive=!!o.isActive,e.isAttribute=!!o.isAttribute),o.useByteColors!==void 0&&(e.useByteColors=!!o.useByteColors),e}const Fe=`precision highp int;

// #if (defined(SHADER_TYPE_FRAGMENT) && defined(LIGHTING_FRAGMENT)) || (defined(SHADER_TYPE_VERTEX) && defined(LIGHTING_VERTEX))
struct AmbientLight {
  vec3 color;
};

struct PointLight {
  vec3 color;
  vec3 position;
  vec3 attenuation; // 2nd order x:Constant-y:Linear-z:Exponential
};

struct SpotLight {
  vec3 color;
  vec3 position;
  vec3 direction;
  vec3 attenuation;
  vec2 coneCos;
};

struct DirectionalLight {
  vec3 color;
  vec3 direction;
};

struct UniformLight {
  vec3 color;
  vec3 position;
  vec3 direction;
  vec3 attenuation;
  vec2 coneCos;
};

layout(std140) uniform lightingUniforms {
  int enabled;
  int directionalLightCount;
  int pointLightCount;
  int spotLightCount;
  vec3 ambientColor;
  UniformLight lights[5];
} lighting;

PointLight lighting_getPointLight(int index) {
  UniformLight light = lighting.lights[index];
  return PointLight(light.color, light.position, light.attenuation);
}

SpotLight lighting_getSpotLight(int index) {
  UniformLight light = lighting.lights[lighting.pointLightCount + index];
  return SpotLight(light.color, light.position, light.direction, light.attenuation, light.coneCos);
}

DirectionalLight lighting_getDirectionalLight(int index) {
  UniformLight light =
    lighting.lights[lighting.pointLightCount + lighting.spotLightCount + index];
  return DirectionalLight(light.color, light.direction);
}

float getPointLightAttenuation(PointLight pointLight, float distance) {
  return pointLight.attenuation.x
       + pointLight.attenuation.y * distance
       + pointLight.attenuation.z * distance * distance;
}

float getSpotLightAttenuation(SpotLight spotLight, vec3 positionWorldspace) {
  vec3 light_direction = normalize(positionWorldspace - spotLight.position);
  float coneFactor = smoothstep(
    spotLight.coneCos.y,
    spotLight.coneCos.x,
    dot(normalize(spotLight.direction), light_direction)
  );
  float distanceAttenuation = getPointLightAttenuation(
    PointLight(spotLight.color, spotLight.position, spotLight.attenuation),
    distance(spotLight.position, positionWorldspace)
  );
  return distanceAttenuation / max(coneFactor, 0.0001);
}

// #endif
`,rn=`// #if (defined(SHADER_TYPE_FRAGMENT) && defined(LIGHTING_FRAGMENT)) || (defined(SHADER_TYPE_VERTEX) && defined(LIGHTING_VERTEX))
const MAX_LIGHTS: i32 = 5;

struct AmbientLight {
  color: vec3<f32>,
};

struct PointLight {
  color: vec3<f32>,
  position: vec3<f32>,
  attenuation: vec3<f32>, // 2nd order x:Constant-y:Linear-z:Exponential
};

struct SpotLight {
  color: vec3<f32>,
  position: vec3<f32>,
  direction: vec3<f32>,
  attenuation: vec3<f32>,
  coneCos: vec2<f32>,
};

struct DirectionalLight {
  color: vec3<f32>,
  direction: vec3<f32>,
};

struct UniformLight {
  color: vec3<f32>,
  position: vec3<f32>,
  direction: vec3<f32>,
  attenuation: vec3<f32>,
  coneCos: vec2<f32>,
};

struct lightingUniforms {
  enabled: i32,
  directionalLightCount: i32,
  pointLightCount: i32,
  spotLightCount: i32,
  ambientColor: vec3<f32>,
  lights: array<UniformLight, 5>,
};

@group(2) @binding(auto) var<uniform> lighting : lightingUniforms;

fn lighting_getPointLight(index: i32) -> PointLight {
  let light = lighting.lights[index];
  return PointLight(light.color, light.position, light.attenuation);
}

fn lighting_getSpotLight(index: i32) -> SpotLight {
  let light = lighting.lights[lighting.pointLightCount + index];
  return SpotLight(light.color, light.position, light.direction, light.attenuation, light.coneCos);
}

fn lighting_getDirectionalLight(index: i32) -> DirectionalLight {
  let light = lighting.lights[lighting.pointLightCount + lighting.spotLightCount + index];
  return DirectionalLight(light.color, light.direction);
}

fn getPointLightAttenuation(pointLight: PointLight, distance: f32) -> f32 {
  return pointLight.attenuation.x
       + pointLight.attenuation.y * distance
       + pointLight.attenuation.z * distance * distance;
}

fn getSpotLightAttenuation(spotLight: SpotLight, positionWorldspace: vec3<f32>) -> f32 {
  let lightDirection = normalize(positionWorldspace - spotLight.position);
  let coneFactor = smoothstep(
    spotLight.coneCos.y,
    spotLight.coneCos.x,
    dot(normalize(spotLight.direction), lightDirection)
  );
  let distanceAttenuation = getPointLightAttenuation(
    PointLight(spotLight.color, spotLight.position, spotLight.attenuation),
    distance(spotLight.position, positionWorldspace)
  );
  return distanceAttenuation / max(coneFactor, 0.0001);
}
`,Z=5,an={color:"vec3<f32>",position:"vec3<f32>",direction:"vec3<f32>",attenuation:"vec3<f32>",coneCos:"vec2<f32>"},Ri={props:{},uniforms:{},name:"lighting",defines:{},uniformTypes:{enabled:"i32",directionalLightCount:"i32",pointLightCount:"i32",spotLightCount:"i32",ambientColor:"vec3<f32>",lights:[an,Z]},defaultUniforms:Tt(),bindingLayout:[{name:"lighting",group:2}],firstBindingSlot:0,source:rn,vs:Fe,fs:Fe,getUniforms:ln};function ln(o,t={}){if(o=o&&{...o},!o)return Tt();o.lights&&(o={...o,...un(o.lights),lights:void 0});const{useByteColors:e,ambientLight:i,pointLights:n,spotLights:s,directionalLights:r}=o||{};if(!(i||n&&n.length>0||s&&s.length>0||r&&r.length>0))return{...Tt(),enabled:0};const l={...Tt(),...cn({useByteColors:e,ambientLight:i,pointLights:n,spotLights:s,directionalLights:r})};return o.enabled!==void 0&&(l.enabled=o.enabled?1:0),l}function cn({useByteColors:o,ambientLight:t,pointLights:e=[],spotLights:i=[],directionalLights:n=[]}){const s=Oi();let r=0,a=0,l=0,c=0;for(const u of e){if(r>=Z)break;s[r]={...s[r],color:yt(u,o),position:u.position,attenuation:u.attenuation||[1,0,0]},r++,a++}for(const u of i){if(r>=Z)break;s[r]={...s[r],color:yt(u,o),position:u.position,direction:u.direction,attenuation:u.attenuation||[1,0,0],coneCos:dn(u)},r++,l++}for(const u of n){if(r>=Z)break;s[r]={...s[r],color:yt(u,o),direction:u.direction},r++,c++}return e.length+i.length+n.length>Z&&Ro.warn(`MAX_LIGHTS exceeded, truncating to ${Z}`)(),{ambientColor:yt(t,o),directionalLightCount:c,pointLightCount:a,spotLightCount:l,lights:s}}function un(o){var e,i,n;const t={pointLights:[],spotLights:[],directionalLights:[]};for(const s of o||[])switch(s.type){case"ambient":t.ambientLight=s;break;case"directional":(e=t.directionalLights)==null||e.push(s);break;case"point":(i=t.pointLights)==null||i.push(s);break;case"spot":(n=t.spotLights)==null||n.push(s);break}return t}function yt(o={},t){const{color:e=[0,0,0],intensity:i=1}=o;return Ii(e,Ei(t,!0)).map(s=>s*i)}function Tt(){return{enabled:1,directionalLightCount:0,pointLightCount:0,spotLightCount:0,ambientColor:[.1,.1,.1],lights:Oi()}}function Oi(){return Array.from({length:Z},()=>fn())}function fn(){return{color:[1,1,1],position:[1,1,2],direction:[1,1,1],attenuation:[1,0,0],coneCos:[1,0]}}function dn(o){const t=o.innerConeAngle??0,e=o.outerConeAngle??Math.PI/4;return[Math.cos(t),Math.cos(e)]}const zi=`layout(std140) uniform phongMaterialUniforms {
  uniform bool unlit;
  uniform float ambient;
  uniform float diffuse;
  uniform float shininess;
  uniform vec3  specularColor;
} material;
`,Fi=`layout(std140) uniform phongMaterialUniforms {
  uniform bool unlit;
  uniform float ambient;
  uniform float diffuse;
  uniform float shininess;
  uniform vec3  specularColor;
} material;

vec3 lighting_getLightColor(vec3 surfaceColor, vec3 light_direction, vec3 view_direction, vec3 normal_worldspace, vec3 color) {
  vec3 halfway_direction = normalize(light_direction + view_direction);
  float lambertian = dot(light_direction, normal_worldspace);
  float specular = 0.0;
  if (lambertian > 0.0) {
    float specular_angle = max(dot(normal_worldspace, halfway_direction), 0.0);
    specular = pow(specular_angle, material.shininess);
  }
  lambertian = max(lambertian, 0.0);
  return (lambertian * material.diffuse * surfaceColor + specular * floatColors_normalize(material.specularColor)) * color;
}

vec3 lighting_getLightColor(vec3 surfaceColor, vec3 cameraPosition, vec3 position_worldspace, vec3 normal_worldspace) {
  vec3 lightColor = surfaceColor;

  if (material.unlit) {
    return surfaceColor;
  }

  if (lighting.enabled == 0) {
    return lightColor;
  }

  vec3 view_direction = normalize(cameraPosition - position_worldspace);
  lightColor = material.ambient * surfaceColor * lighting.ambientColor;

  for (int i = 0; i < lighting.pointLightCount; i++) {
    PointLight pointLight = lighting_getPointLight(i);
    vec3 light_position_worldspace = pointLight.position;
    vec3 light_direction = normalize(light_position_worldspace - position_worldspace);
    float light_attenuation = getPointLightAttenuation(pointLight, distance(light_position_worldspace, position_worldspace));
    lightColor += lighting_getLightColor(surfaceColor, light_direction, view_direction, normal_worldspace, pointLight.color / light_attenuation);
  }

  for (int i = 0; i < lighting.spotLightCount; i++) {
    SpotLight spotLight = lighting_getSpotLight(i);
    vec3 light_position_worldspace = spotLight.position;
    vec3 light_direction = normalize(light_position_worldspace - position_worldspace);
    float light_attenuation = getSpotLightAttenuation(spotLight, position_worldspace);
    lightColor += lighting_getLightColor(surfaceColor, light_direction, view_direction, normal_worldspace, spotLight.color / light_attenuation);
  }

  for (int i = 0; i < lighting.directionalLightCount; i++) {
    DirectionalLight directionalLight = lighting_getDirectionalLight(i);
    lightColor += lighting_getLightColor(surfaceColor, -directionalLight.direction, view_direction, normal_worldspace, directionalLight.color);
  }
  
  return lightColor;
}
`,ki=`struct phongMaterialUniforms {
  unlit: u32,
  ambient: f32,
  diffuse: f32,
  shininess: f32,
  specularColor: vec3<f32>,
};

@group(3) @binding(auto) var<uniform> phongMaterial : phongMaterialUniforms;

fn lighting_getLightColor(surfaceColor: vec3<f32>, light_direction: vec3<f32>, view_direction: vec3<f32>, normal_worldspace: vec3<f32>, color: vec3<f32>) -> vec3<f32> {
  let halfway_direction: vec3<f32> = normalize(light_direction + view_direction);
  var lambertian: f32 = dot(light_direction, normal_worldspace);
  var specular: f32 = 0.0;
  if (lambertian > 0.0) {
    let specular_angle = max(dot(normal_worldspace, halfway_direction), 0.0);
    specular = pow(specular_angle, phongMaterial.shininess);
  }
  lambertian = max(lambertian, 0.0);
  return (
    lambertian * phongMaterial.diffuse * surfaceColor +
    specular * floatColors_normalize(phongMaterial.specularColor)
  ) * color;
}

fn lighting_getLightColor2(surfaceColor: vec3<f32>, cameraPosition: vec3<f32>, position_worldspace: vec3<f32>, normal_worldspace: vec3<f32>) -> vec3<f32> {
  var lightColor: vec3<f32> = surfaceColor;

  if (phongMaterial.unlit != 0u) {
    return surfaceColor;
  }

  if (lighting.enabled == 0) {
    return lightColor;
  }

  let view_direction: vec3<f32> = normalize(cameraPosition - position_worldspace);
  lightColor = phongMaterial.ambient * surfaceColor * lighting.ambientColor;

  for (var i: i32 = 0; i < lighting.pointLightCount; i++) {
    let pointLight: PointLight = lighting_getPointLight(i);
    let light_position_worldspace: vec3<f32> = pointLight.position;
    let light_direction: vec3<f32> = normalize(light_position_worldspace - position_worldspace);
    let light_attenuation = getPointLightAttenuation(
      pointLight,
      distance(light_position_worldspace, position_worldspace)
    );
    lightColor += lighting_getLightColor(
      surfaceColor,
      light_direction,
      view_direction,
      normal_worldspace,
      pointLight.color / light_attenuation
    );
  }

  for (var i: i32 = 0; i < lighting.spotLightCount; i++) {
    let spotLight: SpotLight = lighting_getSpotLight(i);
    let light_position_worldspace: vec3<f32> = spotLight.position;
    let light_direction: vec3<f32> = normalize(light_position_worldspace - position_worldspace);
    let light_attenuation = getSpotLightAttenuation(spotLight, position_worldspace);
    lightColor += lighting_getLightColor(
      surfaceColor,
      light_direction,
      view_direction,
      normal_worldspace,
      spotLight.color / light_attenuation
    );
  }

  for (var i: i32 = 0; i < lighting.directionalLightCount; i++) {
    let directionalLight: DirectionalLight = lighting_getDirectionalLight(i);
    lightColor += lighting_getLightColor(surfaceColor, -directionalLight.direction, view_direction, normal_worldspace, directionalLight.color);
  }  
  
  return lightColor;
}

fn lighting_getSpecularLightColor(cameraPosition: vec3<f32>, position_worldspace: vec3<f32>, normal_worldspace: vec3<f32>) -> vec3<f32>{
  var lightColor = vec3<f32>(0, 0, 0);
  let surfaceColor = vec3<f32>(0, 0, 0);

  if (lighting.enabled != 0) {
    let view_direction = normalize(cameraPosition - position_worldspace);

    for (var i: i32 = 0; i < lighting.pointLightCount; i++) {
      let pointLight: PointLight = lighting_getPointLight(i);
      let light_position_worldspace: vec3<f32> = pointLight.position;
      let light_direction: vec3<f32> = normalize(light_position_worldspace - position_worldspace);
      let light_attenuation = getPointLightAttenuation(
        pointLight,
        distance(light_position_worldspace, position_worldspace)
      );
      lightColor += lighting_getLightColor(
        surfaceColor,
        light_direction,
        view_direction,
        normal_worldspace,
        pointLight.color / light_attenuation
      );
    }

    for (var i: i32 = 0; i < lighting.spotLightCount; i++) {
      let spotLight: SpotLight = lighting_getSpotLight(i);
      let light_position_worldspace: vec3<f32> = spotLight.position;
      let light_direction: vec3<f32> = normalize(light_position_worldspace - position_worldspace);
      let light_attenuation = getSpotLightAttenuation(spotLight, position_worldspace);
      lightColor += lighting_getLightColor(
        surfaceColor,
        light_direction,
        view_direction,
        normal_worldspace,
        spotLight.color / light_attenuation
      );
    }

    for (var i: i32 = 0; i < lighting.directionalLightCount; i++) {
        let directionalLight: DirectionalLight = lighting_getDirectionalLight(i);
        lightColor += lighting_getLightColor(surfaceColor, -directionalLight.direction, view_direction, normal_worldspace, directionalLight.color);
    }
  }
  return lightColor;
}
`,gn=[38.25,38.25,38.25],Nt={props:{},name:"gouraudMaterial",bindingLayout:[{name:"gouraudMaterial",group:3}],vs:Fi.replace("phongMaterial","gouraudMaterial"),fs:zi.replace("phongMaterial","gouraudMaterial"),source:ki.replaceAll("phongMaterial","gouraudMaterial"),defines:{LIGHTING_VERTEX:!0},dependencies:[Ri,Mi],uniformTypes:{unlit:"i32",ambient:"f32",diffuse:"f32",shininess:"f32",specularColor:"vec3<f32>"},defaultUniforms:{unlit:!1,ambient:.35,diffuse:.6,shininess:32,specularColor:gn},getUniforms(o){return{...Nt.defaultUniforms,...o}}},hn=[38.25,38.25,38.25],Bi={name:"phongMaterial",firstBindingSlot:0,bindingLayout:[{name:"phongMaterial",group:3}],dependencies:[Ri,Mi],source:ki,vs:zi,fs:Fi,defines:{LIGHTING_FRAGMENT:!0},uniformTypes:{unlit:"i32",ambient:"f32",diffuse:"f32",shininess:"f32",specularColor:"vec3<f32>"},defaultUniforms:{unlit:!1,ambient:.35,diffuse:.6,shininess:32,specularColor:hn},getUniforms(o){return{...Bi.defaultUniforms,...o}}},pn=`

@must_use
fn deckgl_premultiplied_alpha(fragColor: vec4<f32>) -> vec4<f32> {
    return vec4(fragColor.rgb * fragColor.a, fragColor.a); 
};
`,ye={name:"color",dependencies:[],source:pn,getUniforms:o=>({})},vn=`// Define a structure to hold both the clip-space position and the common position.
struct ProjectResult {
  clipPosition: vec4<f32>,
  commonPosition: vec4<f32>,
};

// This function mimics the GLSL version with the 'out' parameter by returning both values.
fn project_position_to_clipspace_and_commonspace(
    position: vec3<f32>,
    position64Low: vec3<f32>,
    offset: vec3<f32>
) -> ProjectResult {
  // Compute the projected position.
  let projectedPosition: vec3<f32> = project_position_vec3_f64(position, position64Low);

  // Start with the provided offset.
  var finalOffset: vec3<f32> = offset;

  // Get whether a rotation is needed and the rotation matrix.
  let rotationResult = project_needs_rotation(projectedPosition);

  // If rotation is needed, update the offset.
  if (rotationResult.needsRotation) {
    finalOffset = rotationResult.transform * offset;
  }

  // Compute the common position.
  let commonPosition: vec4<f32> = vec4<f32>(projectedPosition + finalOffset, 1.0);

  // Convert to clip-space.
  let clipPosition: vec4<f32> = project_common_position_to_clipspace(commonPosition);

  return ProjectResult(clipPosition, commonPosition);
}

// A convenience overload that returns only the clip-space position.
fn project_position_to_clipspace(
    position: vec3<f32>,
    position64Low: vec3<f32>,
    offset: vec3<f32>
) -> vec4<f32> {
  return project_position_to_clipspace_and_commonspace(position, position64Low, offset).clipPosition;
}
`,mn=`vec4 project_position_to_clipspace(
  vec3 position, vec3 position64Low, vec3 offset, out vec4 commonPosition
) {
  vec3 projectedPosition = project_position(position, position64Low);
  mat3 rotation;
  if (project_needs_rotation(projectedPosition, rotation)) {
    // offset is specified as ENU
    // when in globe projection, rotate offset so that the ground alighs with the surface of the globe
    offset = rotation * offset;
  }
  commonPosition = vec4(projectedPosition + offset, 1.0);
  return project_common_position_to_clipspace(commonPosition);
}

vec4 project_position_to_clipspace(
  vec3 position, vec3 position64Low, vec3 offset
) {
  vec4 commonPosition;
  return project_position_to_clipspace(position, position64Low, offset, commonPosition);
}
`,G={name:"project32",dependencies:[Oo],source:vn,vs:mn},yn=`struct pickingUniforms {
  isActive: f32,
  isAttribute: f32,
  isHighlightActive: f32,
  useByteColors: f32,
  highlightedObjectColor: vec3<f32>,
  highlightColor: vec4<f32>,
};

@group(0) @binding(auto) var<uniform> picking: pickingUniforms;

fn picking_normalizeColor(color: vec3<f32>) -> vec3<f32> {
  return select(color, color / 255.0, picking.useByteColors > 0.5);
}

fn picking_normalizeColor4(color: vec4<f32>) -> vec4<f32> {
  return select(color, color / 255.0, picking.useByteColors > 0.5);
}

fn picking_isColorZero(color: vec3<f32>) -> bool {
  return dot(color, vec3<f32>(1.0)) < 0.00001;
}

fn picking_isColorValid(color: vec3<f32>) -> bool {
  return dot(color, vec3<f32>(1.0)) > 0.00001;
}
`,j={...ze,source:yn,defaultUniforms:{...ze.defaultUniforms,useByteColors:!0},inject:{"vs:DECKGL_FILTER_GL_POSITION":`
    // for picking depth values
    picking_setPickingAttribute(position.z / position.w);
  `,"vs:DECKGL_FILTER_COLOR":`
  picking_setPickingColor(geometry.pickingColor);
  `,"fs:DECKGL_FILTER_COLOR":{order:99,injection:`
  // use highlight color if this fragment belongs to the selected object.
  color = picking_filterHighlightColor(color);

  // use picking color if rendering to picking FBO.
  color = picking_filterPickingColor(color);
    `}}},ke=[0,0,0];function qt(o,t,e=!1){const i=t.projectPosition(o);if(e&&t instanceof Uo){const[n,s,r=0]=o,a=t.getDistanceScales([n,s]);i[2]=r*a.unitsPerMeter[2]}return i}function xn(o){const{viewport:t,modelMatrix:e,coordinateOrigin:i}=o;let{coordinateSystem:n,fromCoordinateSystem:s,fromCoordinateOrigin:r}=o;return n==="default"&&(n=t.isGeospatial?"lnglat":"cartesian"),s===void 0?s=n:s==="default"&&(s=t.isGeospatial?"lnglat":"cartesian"),r===void 0&&(r=i),{viewport:t,coordinateSystem:n,coordinateOrigin:i,modelMatrix:e,fromCoordinateSystem:s,fromCoordinateOrigin:r}}function xe(o,{viewport:t,modelMatrix:e,coordinateSystem:i,coordinateOrigin:n,offsetMode:s}){let[r,a,l=0]=o;switch(e&&([r,a,l]=zo([],[r,a,l,1],e)),i){case"default":return xe(o,{viewport:t,modelMatrix:e,coordinateSystem:t.isGeospatial?"lnglat":"cartesian",coordinateOrigin:n,offsetMode:s});case"lnglat":return qt([r,a,l],t,s);case"lnglat-offsets":return qt([r+n[0],a+n[1],l+(n[2]||0)],t,s);case"meter-offsets":return qt(Fo(n,[r,a,l]),t,s);case"cartesian":return t.isGeospatial?[r+n[0],a+n[1],l+n[2]]:t.projectPosition([r,a,l]);default:throw new Error(`Invalid coordinateSystem: ${i}`)}}function _n(o,t){const{viewport:e,coordinateSystem:i,coordinateOrigin:n,modelMatrix:s,fromCoordinateSystem:r,fromCoordinateOrigin:a}=xn(t),{autoOffset:l=!0}=t,{geospatialOrigin:c=ke,shaderCoordinateOrigin:u=ke,offsetMode:f=!1}=l?ko(e,i,n):{},d=xe(o,{viewport:e,modelMatrix:s,coordinateSystem:r,coordinateOrigin:a,offsetMode:f});if(f){const g=e.projectPosition(c||u);Bo(d,d,g)}return d}const ct=class ct{constructor(t,e=ct.defaultProps){B(this,"device");B(this,"model");B(this,"transformFeedback");if(!ct.isSupported(t))throw new Error("BufferTransform not yet implemented on WebGPU");this.device=t,this.model=new M(this.device,{id:e.id||"buffer-transform-model",fs:e.fs||Xo(),topology:e.topology||"point-list",varyings:e.outputs||e.varyings,...e}),this.transformFeedback=this.device.createTransformFeedback({layout:this.model.pipeline.shaderLayout,buffers:e.feedbackBuffers}),this.model.setTransformFeedback(this.transformFeedback),Object.seal(this)}static isSupported(t){var e;return((e=t==null?void 0:t.info)==null?void 0:e.type)==="webgl"}destroy(){this.model&&this.model.destroy()}delete(){this.destroy()}run(t){t!=null&&t.inputBuffers&&this.model.setAttributes(t.inputBuffers),t!=null&&t.outputBuffers&&this.transformFeedback.setBuffers(t.outputBuffers);const e=this.device.beginRenderPass(t);this.model.draw(e),e.end()}getBuffer(t){return this.transformFeedback.getBuffer(t)}readAsync(t){const e=this.getBuffer(t);if(!e)throw new Error("BufferTransform#getBuffer");if(e instanceof K)return e.readAsync();const{buffer:i,byteOffset:n=0,byteLength:s=i.byteLength}=e;return i.readAsync(n,s)}};B(ct,"defaultProps",{...M.defaultProps,outputs:void 0,feedbackBuffers:void 0});let ut=ct;class N{constructor(t){B(this,"id");B(this,"topology");B(this,"vertexCount");B(this,"indices");B(this,"attributes");B(this,"userData",{});const{attributes:e={},indices:i=null,vertexCount:n=null}=t;this.id=t.id||Go("geometry"),this.topology=t.topology,i&&(this.indices=ArrayBuffer.isView(i)?{value:i,size:1}:i),this.attributes={};for(const[s,r]of Object.entries(e)){const a=ArrayBuffer.isView(r)?{value:r}:r;if(!ArrayBuffer.isView(a.value))throw new Error(`${this._print(s)}: must be typed array or object with value as typed array`);if((s==="POSITION"||s==="positions")&&!a.size&&(a.size=3),s==="indices"){if(this.indices)throw new Error("Multiple indices detected");this.indices=a}else this.attributes[s]=a}this.indices&&this.indices.isIndexed!==void 0&&(this.indices=Object.assign({},this.indices),delete this.indices.isIndexed),this.vertexCount=n||this._calculateVertexCount(this.attributes,this.indices)}getVertexCount(){return this.vertexCount}getAttributes(){return this.indices?{indices:this.indices,...this.attributes}:this.attributes}_print(t){return`Geometry ${this.id} attribute ${t}`}_setAttributes(t,e){return this}_calculateVertexCount(t,e){if(e)return e.value.length;let i=1/0;for(const n of Object.values(t)){const{value:s,size:r,constant:a}=n;!a&&s&&r!==void 0&&r>=1&&(i=Math.min(i,s.length/r))}return i}}function Cn(o){switch(o){case"float64":return Float64Array;case"uint8":case"unorm8":return Uint8ClampedArray;default:return Ho(o)}}const Pn=Ie.getDataType.bind(Ie);function xt(o,t,e){if(t.size>4)return null;const i=e==="webgpu"&&t.type==="uint8"?"unorm8":t.type;return{attribute:o,format:t.size>1?`${i}x${t.size}`:t.type,byteOffset:t.offset||0}}function X(o){return o.stride||o.size*o.bytesPerElement}function bn(o,t){return o.type===t.type&&o.size===t.size&&X(o)===X(t)&&(o.offset||0)===(t.offset||0)}function re(o,t){t.offset&&S.removed("shaderAttribute.offset","vertexOffset, elementOffset")();const e=X(o),i=t.vertexOffset!==void 0?t.vertexOffset:o.vertexOffset||0,n=t.elementOffset||0,s=i*e+n*o.bytesPerElement+(o.offset||0);return{...t,offset:s,stride:e}}function Ln(o,t){const e=re(o,t);return{high:e,low:{...e,offset:e.offset+o.size*4}}}class An{constructor(t,e,i){this._buffer=null,this.device=t,this.id=e.id||"",this.size=e.size||1;const n=e.logicalType||e.type,s=n==="float64";let{defaultValue:r}=e;r=Number.isFinite(r)?[r]:r||new Array(this.size).fill(0);let a;s?a="float32":!n&&e.isIndexed?a="uint32":a=n||"float32";let l=Cn(n||a);this.doublePrecision=s,s&&e.fp64===!1&&(l=Float32Array),this.value=null,this.settings={...e,defaultType:l,defaultValue:r,logicalType:n,type:a,normalized:a.includes("norm"),size:this.size,bytesPerElement:l.BYTES_PER_ELEMENT},this.state={...i,externalBuffer:null,bufferAccessor:this.settings,allocatedValue:null,numInstances:0,bounds:null,constant:!1}}get isConstant(){return this.state.constant}get buffer(){return this._buffer}get byteOffset(){const t=this.getAccessor();return t.vertexOffset?t.vertexOffset*X(t):0}get numInstances(){return this.state.numInstances}set numInstances(t){this.state.numInstances=t}delete(){this._buffer&&(this._buffer.delete(),this._buffer=null),Ot.release(this.state.allocatedValue)}getBuffer(){return this.state.constant?null:this.state.externalBuffer||this._buffer}getValue(t=this.id,e=null){const i={};if(this.state.constant){const n=this.value;if(e){const s=re(this.getAccessor(),e),r=s.offset/n.BYTES_PER_ELEMENT,a=s.size||this.size;i[t]=n.subarray(r,r+a)}else i[t]=n}else i[t]=this.getBuffer();return this.doublePrecision&&(this.value instanceof Float64Array?i[`${t}64Low`]=i[t]:i[`${t}64Low`]=new Float32Array(this.size)),i}_getBufferLayout(t=this.id,e=null){const i=this.getAccessor(),n=[],s={name:this.id,byteStride:X(i)};if(this.doublePrecision){const r=Ln(i,e||{});n.push(xt(t,{...i,...r.high},this.device.type),xt(`${t}64Low`,{...i,...r.low},this.device.type))}else if(e){const r=re(i,e);n.push(xt(t,{...i,...r},this.device.type))}else n.push(xt(t,i,this.device.type));return s.attributes=n.filter(Boolean),s}setAccessor(t){this.state.bufferAccessor=t}getAccessor(){return this.state.bufferAccessor}getBounds(){if(this.state.bounds)return this.state.bounds;let t=null;if(this.state.constant&&this.value){const e=Array.from(this.value);t=[e,e]}else{const{value:e,numInstances:i,size:n}=this,s=i*n;if(e&&s&&e.length>=s){const r=new Array(n).fill(1/0),a=new Array(n).fill(-1/0);for(let l=0;l<s;)for(let c=0;c<n;c++){const u=e[l++];u<r[c]&&(r[c]=u),u>a[c]&&(a[c]=u)}t=[r,a]}}return this.state.bounds=t,t}setData(t){const{state:e}=this;let i;ArrayBuffer.isView(t)?i={value:t}:t instanceof K?i={buffer:t}:i=t;const n={...this.settings,...i};if(ArrayBuffer.isView(i.value)){if(!i.type)if(this.doublePrecision&&i.value instanceof Float64Array)n.type="float32";else{const r=Pn(i.value);n.type=n.normalized?r.replace("int","norm"):r}n.bytesPerElement=i.value.BYTES_PER_ELEMENT,n.stride=X(n)}if(e.bounds=null,i.constant){let s=i.value;if(s=this._normalizeValue(s,[],0),this.settings.normalized&&(s=this.normalizeConstant(s)),!(!e.constant||!this._areValuesEqual(s,this.value)))return!1;e.externalBuffer=null,e.constant=!0,this.value=ArrayBuffer.isView(s)?s:new Float32Array(s)}else if(i.buffer){const s=i.buffer;e.externalBuffer=s,e.constant=!1,this.value=i.value||null}else if(i.value){this._checkExternalBuffer(i);let s=i.value;e.externalBuffer=null,e.constant=!1,this.value=s;let{buffer:r}=this;const a=X(n),l=(n.vertexOffset||0)*a;if(this.doublePrecision&&s instanceof Float64Array&&(s=Zt(s,n)),this.settings.isIndexed){const u=this.settings.defaultType;s.constructor!==u&&(s=new u(s))}const c=s.byteLength+l+a*2;(!r||r.byteLength<c)&&(r=this._createBuffer(c)),r.write(s,l)}return this.setAccessor(n),!0}updateSubBuffer(t={}){this.state.bounds=null;const e=this.value,{startOffset:i=0,endOffset:n}=t;this.buffer.write(this.doublePrecision&&e instanceof Float64Array?Zt(e,{size:this.size,startIndex:i,endIndex:n}):e.subarray(i,n),i*e.BYTES_PER_ELEMENT+this.byteOffset)}allocate(t,e=!1){const{state:i}=this,n=i.allocatedValue,s=Ot.allocate(n,t+1,{size:this.size,type:this.settings.defaultType,copy:e});this.value=s;const{byteOffset:r}=this;let{buffer:a}=this;return(!a||a.byteLength<s.byteLength+r)&&(a=this._createBuffer(s.byteLength+r),e&&n&&a.write(n instanceof Float64Array?Zt(n,this):n,r)),i.allocatedValue=s,i.constant=!1,i.externalBuffer=null,this.setAccessor(this.settings),!0}_checkExternalBuffer(t){const{value:e}=t;if(!ArrayBuffer.isView(e))throw new Error(`Attribute ${this.id} value is not TypedArray`);const i=this.settings.defaultType;let n=!1;if(this.doublePrecision&&(n=e.BYTES_PER_ELEMENT<4),n)throw new Error(`Attribute ${this.id} does not support ${e.constructor.name}`);!(e instanceof i)&&this.settings.normalized&&!("normalized"in t)&&S.warn(`Attribute ${this.id} is normalized`)()}normalizeConstant(t){switch(this.settings.type){case"snorm8":return new Float32Array(t).map(e=>(e+128)/255*2-1);case"snorm16":return new Float32Array(t).map(e=>(e+32768)/65535*2-1);case"unorm8":return new Float32Array(t).map(e=>e/255);case"unorm16":return new Float32Array(t).map(e=>e/65535);default:return t}}_normalizeValue(t,e,i){const{defaultValue:n,size:s}=this.settings;if(Number.isFinite(t))return e[i]=t,e;if(!t){let r=s;for(;--r>=0;)e[i+r]=n[r];return e}switch(s){case 4:e[i+3]=Number.isFinite(t[3])?t[3]:n[3];case 3:e[i+2]=Number.isFinite(t[2])?t[2]:n[2];case 2:e[i+1]=Number.isFinite(t[1])?t[1]:n[1];case 1:e[i+0]=Number.isFinite(t[0])?t[0]:n[0];break;default:let r=s;for(;--r>=0;)e[i+r]=Number.isFinite(t[r])?t[r]:n[r]}return e}_areValuesEqual(t,e){if(!t||!e)return!1;const{size:i}=this;for(let n=0;n<i;n++)if(t[n]!==e[n])return!1;return!0}_createBuffer(t){var n;this._buffer&&this._buffer.destroy();const{isIndexed:e,type:i}=this.settings;return this._buffer=this.device.createBuffer({...(n=this._buffer)==null?void 0:n.props,id:this.id,usage:(e?K.INDEX:K.VERTEX)|K.COPY_DST,indexType:e?i:void 0,byteLength:t}),this._buffer}}const Be=[],Ue=[];function it(o,t=0,e=1/0){let i=Be;const n={index:-1,data:o,target:[]};return o?typeof o[Symbol.iterator]=="function"?i=o:o.length>0&&(Ue.length=o.length,i=Ue):i=Be,(t>0||Number.isFinite(e))&&(i=(Array.isArray(i)?i:Array.from(i)).slice(t,e),n.index=t-1),{iterable:i,objectInfo:n}}function Ui(o){return o&&o[Symbol.asyncIterator]}function Di(o,t){const{size:e,stride:i,offset:n,startIndices:s,nested:r}=t,a=o.BYTES_PER_ELEMENT,l=i?i/a:e,c=n?n/a:0,u=Math.floor((o.length-c)/l);return(f,{index:d,target:g})=>{if(!s){const x=d*l+c;for(let _=0;_<e;_++)g[_]=o[x+_];return g}const h=s[d],p=s[d+1]||u;let v;if(r){v=new Array(p-h);for(let x=h;x<p;x++){const _=x*l+c;g=new Array(e);for(let y=0;y<e;y++)g[y]=o[_+y];v[x-h]=g}}else if(l===e)v=o.subarray(h*e+c,p*e+c);else{v=new o.constructor((p-h)*e);let x=0;for(let _=h;_<p;_++){const y=_*l+c;for(let m=0;m<e;m++)v[x++]=o[y+m]}}return v}}const Sn=[],wt=[[0,1/0]];function Tn(o,t){if(o===wt||(t[0]<0&&(t[0]=0),t[0]>=t[1]))return o;const e=[],i=o.length;let n=0;for(let s=0;s<i;s++){const r=o[s];r[1]<t[0]?(e.push(r),n=s+1):r[0]>t[1]?e.push(r):t=[Math.min(r[0],t[0]),Math.max(r[1],t[1])]}return e.splice(n,0,t),e}const wn={interpolation:{duration:0,easing:o=>o},spring:{stiffness:.05,damping:.5}};function Ni(o,t){if(!o)return null;Number.isFinite(o)&&(o={type:"interpolation",duration:o});const e=o.type||"interpolation";return{...wn[e],...t,...o,type:e}}class Gi extends An{constructor(t,e){super(t,e,{startIndices:null,lastExternalBuffer:null,binaryValue:null,binaryAccessor:null,needsUpdate:!0,needsRedraw:!1,layoutChanged:!1,updateRanges:wt}),this.constant=!1,this.settings.update=e.update||(e.accessor?this._autoUpdater:void 0),Object.seal(this.settings),Object.seal(this.state),this._validateAttributeUpdaters()}get startIndices(){return this.state.startIndices}set startIndices(t){this.state.startIndices=t}needsUpdate(){return this.state.needsUpdate}needsRedraw({clearChangedFlags:t=!1}={}){const e=this.state.needsRedraw;return this.state.needsRedraw=e&&!t,e}layoutChanged(){return this.state.layoutChanged}setAccessor(t){var e;(e=this.state).layoutChanged||(e.layoutChanged=!bn(t,this.getAccessor())),super.setAccessor(t)}getUpdateTriggers(){const{accessor:t}=this.settings;return[this.id].concat(typeof t!="function"&&t||[])}supportsTransition(){return!!this.settings.transition}getTransitionSetting(t){if(!t||!this.supportsTransition())return null;const{accessor:e}=this.settings,i=this.settings.transition,n=Array.isArray(e)?t[e.find(s=>t[s])]:t[e];return Ni(n,i)}setNeedsUpdate(t=this.id,e){if(this.state.needsUpdate=this.state.needsUpdate||t,this.setNeedsRedraw(t),e){const{startRow:i=0,endRow:n=1/0}=e;this.state.updateRanges=Tn(this.state.updateRanges,[i,n])}else this.state.updateRanges=wt}clearNeedsUpdate(){this.state.needsUpdate=!1,this.state.updateRanges=Sn}setNeedsRedraw(t=this.id){this.state.needsRedraw=this.state.needsRedraw||t}allocate(t){const{state:e,settings:i}=this;return i.noAlloc?!1:i.update?(super.allocate(t,e.updateRanges!==wt),!0):!1}updateBuffer({numInstances:t,data:e,props:i,context:n}){if(!this.needsUpdate())return!1;const{state:{updateRanges:s},settings:{update:r,noAlloc:a}}=this;let l=!0;if(r){for(const[c,u]of s)r.call(n,this,{data:e,startRow:c,endRow:u,props:i,numInstances:t});if(this.value)if(this.constant||!this.buffer||this.buffer.byteLength<this.value.byteLength+this.byteOffset)this.constant?this.setConstantValue(n,this.value):this.setData({value:this.value,constant:this.constant}),this.constant=!1;else for(const[c,u]of s){const f=Number.isFinite(c)?this.getVertexOffset(c):0,d=Number.isFinite(u)?this.getVertexOffset(u):a||!Number.isFinite(t)?this.value.length:t*this.size;super.updateSubBuffer({startOffset:f,endOffset:d})}this._checkAttributeArray()}else l=!1;return this.clearNeedsUpdate(),this.setNeedsRedraw(),l}setConstantValue(t,e){if(e===void 0||typeof e=="function")return!1;const i=this.settings.transform&&t?this.settings.transform.call(t,e):e;return this.device.type==="webgpu"?this.setConstantBufferValue(i,this.numInstances):(this.setData({constant:!0,value:i})&&this.setNeedsRedraw(),this.clearNeedsUpdate(),!0)}setConstantBufferValue(t,e){const i=this.settings.defaultType,n=this._normalizeValue(t,new i(this.size),0);if(this._hasConstantBufferValue(n,e))return this.constant=!1,this.clearNeedsUpdate(),!1;const s=new i(Math.max(e,1)*this.size);for(let a=0;a<s.length;a+=this.size)s.set(n,a);const r=this.setData({value:s});return this.constant=!1,this.clearNeedsUpdate(),r&&this.setNeedsRedraw(),r}_hasConstantBufferValue(t,e){const i=this.value,n=Math.max(e,1)*this.size;if(!ArrayBuffer.isView(i)||i.length!==n||i.length%this.size!==0)return!1;for(let s=0;s<i.length;s+=this.size)for(let r=0;r<this.size;r++)if(i[s+r]!==t[r])return!1;return!0}setExternalBuffer(t){const{state:e}=this;return t?(this.clearNeedsUpdate(),e.lastExternalBuffer===t||(e.lastExternalBuffer=t,this.setNeedsRedraw(),this.setData(t)),!0):(e.lastExternalBuffer=null,!1)}setBinaryValue(t,e=null){const{state:i,settings:n}=this;if(!t)return i.binaryValue=null,i.binaryAccessor=null,!1;if(n.noAlloc)return!1;if(i.binaryValue===t)return this.clearNeedsUpdate(),!0;if(i.binaryValue=t,this.setNeedsRedraw(),n.transform||e!==this.startIndices){ArrayBuffer.isView(t)&&(t={value:t});const r=t;W(ArrayBuffer.isView(r.value),`invalid ${n.accessor}`);const a=!!r.size&&r.size!==this.size;return i.binaryAccessor=Di(r.value,{size:r.size||this.size,stride:r.stride,offset:r.offset,startIndices:e,nested:a}),!1}return this.clearNeedsUpdate(),this.setData(t),!0}getVertexOffset(t){const{startIndices:e}=this;return(e?t<e.length?e[t]:this.numInstances:t)*this.size}getValue(){const t=this.settings.shaderAttributes,e=super.getValue();if(!t)return e;for(const i in t)Object.assign(e,super.getValue(i,t[i]));return e}getBufferLayout(t){this.state.layoutChanged=!1;const e=this.settings.shaderAttributes,i=super._getBufferLayout(),{stepMode:n}=this.settings;if(n==="dynamic"?i.stepMode=t?t.isInstanced?"instance":"vertex":"instance":i.stepMode=n??"vertex",!e)return i;for(const s in e){const r=super._getBufferLayout(s,e[s]);i.attributes.push(...r.attributes)}return i}_autoUpdater(t,{data:e,startRow:i,endRow:n,props:s,numInstances:r}){const{settings:a,state:l,value:c,size:u,startIndices:f}=t,{accessor:d,transform:g}=a,h=l.binaryAccessor||(typeof d=="function"?d:s[d]);W(typeof h=="function",`accessor "${d}" is not a function`);let p=t.getVertexOffset(i);const{iterable:v,objectInfo:x}=it(e,i,n);for(const _ of v){x.index++;let y=h(_,x);if(g&&(y=g.call(this,y)),f){const m=(x.index<f.length-1?f[x.index+1]:r)-f[x.index];if(y&&Array.isArray(y[0])){let C=p;for(const L of y)t._normalizeValue(L,c,C),C+=u}else y&&y.length>u?c.set(y,p):(t._normalizeValue(y,x.target,0),Vo({target:c,source:x.target,start:p,count:m}));p+=m*u}else t._normalizeValue(y,c,p),p+=u}}_validateAttributeUpdaters(){const{settings:t}=this;if(!(t.noAlloc||typeof t.update=="function"))throw new Error(`Attribute ${this.id} missing update or accessor`)}_checkAttributeArray(){const{value:t}=this,e=Math.min(4,this.size);if(t&&t.length>=e){let i=!0;switch(e){case 4:i=i&&Number.isFinite(t[3]);case 3:i=i&&Number.isFinite(t[2]);case 2:i=i&&Number.isFinite(t[1]);case 1:i=i&&Number.isFinite(t[0]);break;default:i=!1}if(!i)throw new Error(`Illegal attribute generated for ${this.id}`)}}}function Jt(o){const{source:t,target:e,start:i=0,size:n,getData:s}=o,r=o.end||e.length,a=t.length,l=r-i;if(a>l){e.set(t.subarray(0,l),i);return}if(e.set(t,i),!s)return;let c=a;for(;c<l;){const u=s(c,t);for(let f=0;f<n;f++)e[i+c]=u[f]||0,c++}}function En({source:o,target:t,size:e,getData:i,sourceStartIndices:n,targetStartIndices:s}){if(!n||!s)return Jt({source:o,target:t,size:e,getData:i}),t;let r=0,a=0;const l=i&&((u,f)=>i(u+a,f)),c=Math.min(n.length,s.length);for(let u=1;u<c;u++){const f=n[u]*e,d=s[u]*e;Jt({source:o.subarray(r,f),target:t,start:a,end:d,size:e,getData:l}),r=f,a=d}return a<t.length&&Jt({source:[],target:t,start:a,size:e,getData:l}),t}function In(o){const{device:t,settings:e,value:i}=o,n=new Gi(t,e);return n.setData({value:i instanceof Float64Array?new Float64Array(0):new Float32Array(0),normalized:e.normalized}),n}function ji(o){switch(o){case 1:return"float";case 2:return"vec2";case 3:return"vec3";case 4:return"vec4";default:throw new Error(`No defined attribute type for size "${o}"`)}}function Vi(o){switch(o){case 1:return"float32";case 2:return"float32x2";case 3:return"float32x3";case 4:return"float32x4";default:throw new Error("invalid type size")}}function Wi(o){o.push(o.shift())}function Mn(o,t){const{doublePrecision:e,settings:i,value:n,size:s}=o,r=e&&n instanceof Float64Array?2:1;let a=0;const{shaderAttributes:l}=o.settings;if(l)for(const c of Object.values(l))a=Math.max(a,c.vertexOffset??0);return(i.noAlloc?n.length:(t+a)*s)*r}function $i({device:o,source:t,target:e}){return(!e||e.byteLength<t.byteLength)&&(e==null||e.destroy(),e=o.createBuffer({byteLength:t.byteLength,usage:t.usage})),e}function Hi({device:o,buffer:t,attribute:e,fromLength:i,toLength:n,fromStartIndices:s,getData:r=a=>a}){const a=e.doublePrecision&&e.value instanceof Float64Array?2:1,l=e.size*a,c=e.byteOffset,u=e.settings.bytesPerElement<4?c/e.settings.bytesPerElement*4:c,f=e.startIndices,d=s&&f,g=e.isConstant;if(!d&&t&&i>=n)return t;const h=e.value instanceof Float64Array?Float32Array:e.value.constructor,p=g?e.value:new h(e.getBuffer().readSyncWebGL(c,n*h.BYTES_PER_ELEMENT).buffer);if(e.settings.normalized&&!g){const y=r;r=(m,C)=>e.normalizeConstant(y(m,C))}const v=g?(y,m)=>r(p,m):(y,m)=>r(p.subarray(y+c,y+c+l),m),x=t?new Float32Array(t.readSyncWebGL(u,i*4).buffer):new Float32Array(0),_=new Float32Array(n);return En({source:x,target:_,sourceStartIndices:s,targetStartIndices:f,size:l,getData:v}),(!t||t.byteLength<_.byteLength+u)&&(t==null||t.destroy(),t=o.createBuffer({byteLength:_.byteLength+u,usage:35050})),t.write(_,u),t}class Yi{constructor({device:t,attribute:e,timeline:i}){this.buffers=[],this.currentLength=0,this.device=t,this.transition=new me(i),this.attribute=e,this.attributeInTransition=In(e),this.currentStartIndices=e.startIndices}get inProgress(){return this.transition.inProgress}start(t,e,i=1/0){this.settings=t,this.currentStartIndices=this.attribute.startIndices,this.currentLength=Mn(this.attribute,e),this.transition.start({...t,duration:i})}update(){const t=this.transition.update();return t&&this.onUpdate(),t}setBuffer(t){this.attributeInTransition.setData({buffer:t,normalized:this.attribute.settings.normalized,value:this.attributeInTransition.value})}cancel(){this.transition.cancel()}delete(){this.cancel();for(const t of this.buffers)t.destroy();this.buffers.length=0}}class Rn extends Yi{constructor({device:t,attribute:e,timeline:i}){super({device:t,attribute:e,timeline:i}),this.type="interpolation",this.transform=kn(t,e)}start(t,e){const i=this.currentLength,n=this.currentStartIndices;if(super.start(t,e,t.duration),t.duration<=0){this.transition.cancel();return}const{buffers:s,attribute:r}=this;Wi(s),s[0]=Hi({device:this.device,buffer:s[0],attribute:r,fromLength:i,toLength:this.currentLength,fromStartIndices:n,getData:t.enter}),s[1]=$i({device:this.device,source:s[0],target:s[1]}),this.setBuffer(s[1]);const{transform:a}=this,l=a.model;let c=Math.floor(this.currentLength/r.size);Zi(r)&&(c/=2),l.setVertexCount(c),r.isConstant?(l.setAttributes({aFrom:s[0]}),l.setConstantAttributes({aTo:r.value})):l.setAttributes({aFrom:s[0],aTo:r.getBuffer()}),a.transformFeedback.setBuffers({vCurrent:s[1]})}onUpdate(){const{duration:t,easing:e}=this.settings,{time:i}=this.transition;let n=i/t;e&&(n=e(n));const{model:s}=this.transform,r={time:n};s.shaderInputs.setProps({interpolation:r}),this.transform.run({discard:!0})}delete(){super.delete(),this.transform.destroy()}}const On=`layout(std140) uniform interpolationUniforms {
  float time;
} interpolation;
`,De={name:"interpolation",vs:On,uniformTypes:{time:"f32"}},zn=`#version 300 es
#define SHADER_NAME interpolation-transition-vertex-shader

in ATTRIBUTE_TYPE aFrom;
in ATTRIBUTE_TYPE aTo;
out ATTRIBUTE_TYPE vCurrent;

void main(void) {
  vCurrent = mix(aFrom, aTo, interpolation.time);
  gl_Position = vec4(0.0);
}
`,Fn=`#version 300 es
#define SHADER_NAME interpolation-transition-vertex-shader

in ATTRIBUTE_TYPE aFrom;
in ATTRIBUTE_TYPE aFrom64Low;
in ATTRIBUTE_TYPE aTo;
in ATTRIBUTE_TYPE aTo64Low;
out ATTRIBUTE_TYPE vCurrent;
out ATTRIBUTE_TYPE vCurrent64Low;

vec2 mix_fp64(vec2 a, vec2 b, float x) {
  vec2 range = sub_fp64(b, a);
  return sum_fp64(a, mul_fp64(range, vec2(x, 0.0)));
}

void main(void) {
  for (int i=0; i<ATTRIBUTE_SIZE; i++) {
    vec2 value = mix_fp64(vec2(aFrom[i], aFrom64Low[i]), vec2(aTo[i], aTo64Low[i]), interpolation.time);
    vCurrent[i] = value.x;
    vCurrent64Low[i] = value.y;
  }
  gl_Position = vec4(0.0);
}
`;function Zi(o){return o.doublePrecision&&o.value instanceof Float64Array}function kn(o,t){const e=t.size,i=ji(e),n=Vi(e),s=t.getBufferLayout();return Zi(t)?new ut(o,{vs:Fn,bufferLayout:[{name:"aFrom",byteStride:8*e,attributes:[{attribute:"aFrom",format:n,byteOffset:0},{attribute:"aFrom64Low",format:n,byteOffset:4*e}]},{name:"aTo",byteStride:8*e,attributes:[{attribute:"aTo",format:n,byteOffset:0},{attribute:"aTo64Low",format:n,byteOffset:4*e}]}],modules:[jo,De],defines:{ATTRIBUTE_TYPE:i,ATTRIBUTE_SIZE:e},moduleSettings:{},varyings:["vCurrent","vCurrent64Low"],bufferMode:35980,disableWarnings:!0}):new ut(o,{vs:zn,bufferLayout:[{name:"aFrom",format:n},{name:"aTo",format:s.attributes[0].format}],modules:[De],defines:{ATTRIBUTE_TYPE:i},varyings:["vCurrent"],disableWarnings:!0})}class Bn extends Yi{constructor({device:t,attribute:e,timeline:i}){super({device:t,attribute:e,timeline:i}),this.type="spring",this.texture=Vn(t),this.framebuffer=Wn(t,this.texture),this.transform=jn(t,e)}start(t,e){const i=this.currentLength,n=this.currentStartIndices;super.start(t,e);const{buffers:s,attribute:r}=this;for(let l=0;l<2;l++)s[l]=Hi({device:this.device,buffer:s[l],attribute:r,fromLength:i,toLength:this.currentLength,fromStartIndices:n,getData:t.enter});s[2]=$i({device:this.device,source:s[0],target:s[2]}),this.setBuffer(s[1]);const{model:a}=this.transform;a.setVertexCount(Math.floor(this.currentLength/r.size)),r.isConstant?a.setConstantAttributes({aTo:r.value}):a.setAttributes({aTo:r.getBuffer()})}onUpdate(){const{buffers:t,transform:e,framebuffer:i,transition:n}=this,s=this.settings;e.model.setAttributes({aPrev:t[0],aCur:t[1]}),e.transformFeedback.setBuffers({vNext:t[2]});const r={stiffness:s.stiffness,damping:s.damping};e.model.shaderInputs.setProps({spring:r}),e.run({framebuffer:i,discard:!1,parameters:{viewport:[0,0,1,1]},clearColor:[0,0,0,0]}),Wi(t),this.setBuffer(t[1]),this.device.readPixelsToArrayWebGL(i)[0]>0||n.end()}delete(){super.delete(),this.transform.destroy(),this.texture.destroy(),this.framebuffer.destroy()}}const Un=`layout(std140) uniform springUniforms {
  float damping;
  float stiffness;
} spring;
`,Dn={name:"spring",vs:Un,uniformTypes:{damping:"f32",stiffness:"f32"}},Nn=`#version 300 es
#define SHADER_NAME spring-transition-vertex-shader

#define EPSILON 0.00001

in ATTRIBUTE_TYPE aPrev;
in ATTRIBUTE_TYPE aCur;
in ATTRIBUTE_TYPE aTo;
out ATTRIBUTE_TYPE vNext;
out float vIsTransitioningFlag;

ATTRIBUTE_TYPE getNextValue(ATTRIBUTE_TYPE cur, ATTRIBUTE_TYPE prev, ATTRIBUTE_TYPE dest) {
  ATTRIBUTE_TYPE velocity = cur - prev;
  ATTRIBUTE_TYPE delta = dest - cur;
  ATTRIBUTE_TYPE force = delta * spring.stiffness;
  ATTRIBUTE_TYPE resistance = velocity * spring.damping;
  return force - resistance + velocity + cur;
}

void main(void) {
  bool isTransitioning = length(aCur - aPrev) > EPSILON || length(aTo - aCur) > EPSILON;
  vIsTransitioningFlag = isTransitioning ? 1.0 : 0.0;

  vNext = getNextValue(aCur, aPrev, aTo);
  gl_Position = vec4(0, 0, 0, 1);
  gl_PointSize = 100.0;
}
`,Gn=`#version 300 es
#define SHADER_NAME spring-transition-is-transitioning-fragment-shader

in float vIsTransitioningFlag;

out vec4 fragColor;

void main(void) {
  if (vIsTransitioningFlag == 0.0) {
    discard;
  }
  fragColor = vec4(1.0);
}`;function jn(o,t){const e=ji(t.size),i=Vi(t.size);return new ut(o,{vs:Nn,fs:Gn,bufferLayout:[{name:"aPrev",format:i},{name:"aCur",format:i},{name:"aTo",format:t.getBufferLayout().attributes[0].format}],varyings:["vNext"],modules:[Dn],defines:{ATTRIBUTE_TYPE:e},parameters:{depthCompare:"always",blendColorOperation:"max",blendColorSrcFactor:"one",blendColorDstFactor:"one",blendAlphaOperation:"max",blendAlphaSrcFactor:"one",blendAlphaDstFactor:"one"}})}function Vn(o){return o.createTexture({data:new Uint8Array(4),format:"rgba8unorm",width:1,height:1})}function Wn(o,t){return o.createFramebuffer({id:"spring-transition-is-transitioning-framebuffer",width:1,height:1,colorAttachments:[t]})}const $n={interpolation:Rn,spring:Bn};class Hn{constructor(t,{id:e,timeline:i}){if(!t)throw new Error("AttributeTransitionManager is constructed without device");this.id=e,this.device=t,this.timeline=i,this.transitions={},this.needsRedraw=!1,this.numInstances=1}finalize(){for(const t in this.transitions)this._removeTransition(t)}update({attributes:t,transitions:e,numInstances:i}){this.numInstances=i||1;for(const n in t){const s=t[n],r=s.getTransitionSetting(e);r&&this._updateAttribute(n,s,r)}for(const n in this.transitions){const s=t[n];(!s||!s.getTransitionSetting(e))&&this._removeTransition(n)}}hasAttribute(t){const e=this.transitions[t];return e&&e.inProgress}getAttributes(){const t={};for(const e in this.transitions){const i=this.transitions[e];i.inProgress&&(t[e]=i.attributeInTransition)}return t}run(){if(this.numInstances===0)return!1;for(const e in this.transitions)this.transitions[e].update()&&(this.needsRedraw=!0);const t=this.needsRedraw;return this.needsRedraw=!1,t}_removeTransition(t){this.transitions[t].delete(),delete this.transitions[t]}_updateAttribute(t,e,i){const n=this.transitions[t];let s=!n||n.type!==i.type;if(s){n&&this._removeTransition(t);const r=$n[i.type];r?this.transitions[t]=new r({attribute:e,timeline:this.timeline,device:this.device}):(S.error(`unsupported transition type '${i.type}'`)(),s=!1)}(s||e.needsRedraw())&&(this.needsRedraw=!0,this.transitions[t].start(i,this.numInstances))}}const Ne="attributeManager.invalidate",Yn="attributeManager.updateStart",Zn="attributeManager.updateEnd",Kn="attribute.updateStart",Xn="attribute.allocate",qn="attribute.updateEnd";class Jn{constructor(t,{id:e="attribute-manager",stats:i,timeline:n}={}){this.mergeBoundsMemoized=Ti(Do),this.id=e,this.device=t,this.attributes={},this.updateTriggers={},this.needsRedraw=!0,this.userData={},this.stats=i,this.attributeTransitionManager=new Hn(t,{id:`${e}-transitions`,timeline:n}),Object.seal(this)}finalize(){for(const t in this.attributes)this.attributes[t].delete();this.attributeTransitionManager.finalize()}getNeedsRedraw(t={clearRedrawFlags:!1}){const e=this.needsRedraw;return this.needsRedraw=this.needsRedraw&&!t.clearRedrawFlags,e&&this.id}setNeedsRedraw(){this.needsRedraw=!0}add(t){this._add(t)}addInstanced(t){this._add(t,{stepMode:"instance"})}remove(t){for(const e of t)this.attributes[e]!==void 0&&(this.attributes[e].delete(),delete this.attributes[e])}invalidate(t,e){const i=this._invalidateTrigger(t,e);O(Ne,this,t,i)}invalidateAll(t){for(const e in this.attributes)this.attributes[e].setNeedsUpdate(e,t);O(Ne,this,"all")}update({data:t,numInstances:e,startIndices:i=null,transitions:n,props:s={},buffers:r={},context:a={}}){let l=!1;O(Yn,this),this.stats&&this.stats.get("Update Attributes").timeStart();for(const c in this.attributes){const u=this.attributes[c],f=u.settings.accessor;u.startIndices=i,u.numInstances=e,s[c]&&S.removed(`props.${c}`,`data.attributes.${c}`)(),u.setExternalBuffer(r[c])||u.setBinaryValue(typeof f=="string"?r[f]:void 0,t.startIndices)||typeof f=="string"&&!r[f]&&u.setConstantValue(a,s[f])||u.needsUpdate()&&(l=!0,this._updateAttribute({attribute:u,numInstances:e,data:t,props:s,context:a})),this.needsRedraw=this.needsRedraw||u.needsRedraw()}l&&O(Zn,this,e),this.stats&&(this.stats.get("Update Attributes").timeEnd(),l&&this.stats.get("Attributes updated").incrementCount()),this.attributeTransitionManager.update({attributes:this.attributes,numInstances:e,transitions:n})}updateTransition(){const{attributeTransitionManager:t}=this,e=t.run();return this.needsRedraw=this.needsRedraw||e,e}getAttributes(){return{...this.attributes,...this.attributeTransitionManager.getAttributes()}}getBounds(t){const e=t.map(i=>{var n;return(n=this.attributes[i])==null?void 0:n.getBounds()});return this.mergeBoundsMemoized(e)}getChangedAttributes(t={clearChangedFlags:!1}){const{attributes:e,attributeTransitionManager:i}=this,n={...i.getAttributes()};for(const s in e){const r=e[s];r.needsRedraw(t)&&!i.hasAttribute(s)&&(n[s]=r)}return n}getBufferLayouts(t){return Object.values(this.getAttributes()).map(e=>e.getBufferLayout(t))}_add(t,e){for(const i in t){const n=t[i],s={...n,id:i,size:n.isIndexed&&1||n.size||1,...e};this.attributes[i]=new Gi(this.device,s)}this._mapUpdateTriggersToAttributes()}_mapUpdateTriggersToAttributes(){const t={};for(const e in this.attributes)this.attributes[e].getUpdateTriggers().forEach(n=>{t[n]||(t[n]=[]),t[n].push(e)});this.updateTriggers=t}_invalidateTrigger(t,e){const{attributes:i,updateTriggers:n}=this,s=n[t];return s&&s.forEach(r=>{const a=i[r];a&&a.setNeedsUpdate(a.id,e)}),s}_updateAttribute(t){const{attribute:e,numInstances:i}=t;if(O(Kn,e),e.constant){e.setConstantValue(t.context,e.value);return}e.allocate(i)&&O(Xn,e,i),e.updateBuffer(t)&&(this.needsRedraw=!0,O(qn,e,i))}}class Qn extends me{get value(){return this._value}_onUpdate(){const{time:t,settings:{fromValue:e,toValue:i,duration:n,easing:s}}=this,r=s(t/n);this._value=St(e,i,r)}}const Ge=1e-5;function je(o,t,e,i,n){const s=t-o,a=(e-t)*n,l=-s*i;return a+l+s+t}function ts(o,t,e,i,n){if(Array.isArray(e)){const s=[];for(let r=0;r<e.length;r++)s[r]=je(o[r],t[r],e[r],i,n);return s}return je(o,t,e,i,n)}function Ve(o,t){if(Array.isArray(o)){let e=0;for(let i=0;i<o.length;i++){const n=o[i]-t[i];e+=n*n}return Math.sqrt(e)}return Math.abs(o-t)}class es extends me{get value(){return this._currValue}_onUpdate(){const{fromValue:t,toValue:e,damping:i,stiffness:n}=this.settings,{_prevValue:s=t,_currValue:r=t}=this;let a=ts(s,r,e,i,n);const l=Ve(a,e),c=Ve(a,r);l<Ge&&c<Ge&&(a=e,this.end()),this._prevValue=r,this._currValue=a}}const is={interpolation:Qn,spring:es};class os{constructor(t){this.transitions=new Map,this.timeline=t}get active(){return this.transitions.size>0}add(t,e,i,n){const{transitions:s}=this;if(s.has(t)){const l=s.get(t),{value:c=l.settings.fromValue}=l;e=c,this.remove(t)}if(n=Ni(n),!n)return;const r=is[n.type];if(!r){S.error(`unsupported transition type '${n.type}'`)();return}const a=new r(this.timeline);a.start({...n,fromValue:e,toValue:i}),s.set(t,a)}remove(t){const{transitions:e}=this;e.has(t)&&(e.get(t).cancel(),e.delete(t))}update(){const t={};for(const[e,i]of this.transitions)i.update(),t[e]=i.value,i.inProgress||this.remove(e);return t}clear(){for(const t of this.transitions.keys())this.remove(t)}}function ns(o){const t=o[Y];for(const e in t){const i=t[e],{validate:n}=i;if(n&&!n(o[e],i))throw new Error(`Invalid prop ${e}: ${o[e]}`)}}function ss(o,t){const e=Ki({newProps:o,oldProps:t,propTypes:o[Y],ignoreProps:{data:null,updateTriggers:null,extensions:null,transitions:null}}),i=as(o,t);let n=!1;return i||(n=ls(o,t)),{dataChanged:i,propsChanged:e,updateTriggersChanged:n,extensionsChanged:cs(o,t),transitionsChanged:rs(o,t)}}function rs(o,t){if(!o.transitions)return!1;const e={},i=o[Y];let n=!1;for(const s in o.transitions){const r=i[s],a=r&&r.type;(a==="number"||a==="color"||a==="array")&&ae(o[s],t[s],r)&&(e[s]=!0,n=!0)}return n?e:!1}function Ki({newProps:o,oldProps:t,ignoreProps:e={},propTypes:i={},triggerName:n="props"}){if(t===o)return!1;if(typeof o!="object"||o===null)return`${n} changed shallowly`;if(typeof t!="object"||t===null)return`${n} changed shallowly`;for(const s of Object.keys(o))if(!(s in e)){if(!(s in t))return`${n}.${s} added`;const r=ae(o[s],t[s],i[s]);if(r)return`${n}.${s} ${r}`}for(const s of Object.keys(t))if(!(s in e)){if(!(s in o))return`${n}.${s} dropped`;if(!Object.hasOwnProperty.call(o,s)){const r=ae(o[s],t[s],i[s]);if(r)return`${n}.${s} ${r}`}}return!1}function ae(o,t,e){let i=e&&e.equal;return i&&!i(o,t,e)||!i&&(i=o&&t&&o.equals,i&&!i.call(o,t))?"changed deeply":!i&&t!==o?"changed shallowly":null}function as(o,t){if(t===null)return"oldProps is null, initial diff";let e=!1;const{dataComparator:i,_dataDiff:n}=o;return i?i(o.data,t.data)||(e="Data comparator detected a change"):o.data!==t.data&&(e="A new data container was supplied"),e&&n&&(e=n(o.data,t.data)||e),e}function ls(o,t){if(t===null)return{all:!0};if("all"in o.updateTriggers&&We(o,t,"all"))return{all:!0};const e={};let i=!1;for(const n in o.updateTriggers)n!=="all"&&We(o,t,n)&&(e[n]=!0,i=!0);return i?e:!1}function cs(o,t){if(t===null)return!0;const e=t.extensions,{extensions:i}=o;if(i===e)return!1;if(!e||!i||i.length!==e.length)return!0;for(let n=0;n<i.length;n++)if(!i[n].equals(e[n]))return!0;return!1}function We(o,t,e){let i=o.updateTriggers[e];i=i??{};let n=t.updateTriggers[e];return n=n??{},Ki({oldProps:n,newProps:i,triggerName:e})}const us="count(): argument not an object",fs="count(): argument not a container";function ds(o){if(!hs(o))throw new Error(us);if(typeof o.count=="function")return o.count();if(Number.isFinite(o.size))return o.size;if(Number.isFinite(o.length))return o.length;if(gs(o))return Object.keys(o).length;throw new Error(fs)}function gs(o){return o!==null&&typeof o=="object"&&o.constructor===Object}function hs(o){return o!==null&&typeof o=="object"}const ps={minFilter:"linear",mipmapFilter:"linear",magFilter:"linear",addressModeU:"clamp-to-edge",addressModeV:"clamp-to-edge"},le={};function vs(o,t,e,i){if(e instanceof wi)return e;e.constructor&&e.constructor.name!=="Object"&&(e={data:e});let n=null;e.compressed&&(n={minFilter:"linear",mipmapFilter:e.data.length>1?"nearest":"linear"});const{width:s,height:r}=e.data,a=t.createTexture({...e,sampler:{...ps,...n,...i},mipLevels:t.getMipLevelCount(s,r)});return t.type==="webgl"?a.generateMipmapsWebGL():t.type==="webgpu"&&t.generateMipmapsWebGPU(a),le[a.id]=o,a}function ms(o,t){!t||!(t instanceof wi)||le[t.id]===o&&(t.delete(),delete le[t.id])}const ys={boolean:{validate(o,t){return!0},equal(o,t,e){return!!o==!!t}},number:{validate(o,t){return Number.isFinite(o)&&(!("max"in t)||o<=t.max)&&(!("min"in t)||o>=t.min)}},color:{validate(o,t){return t.optional&&!o||ce(o)&&(o.length===3||o.length===4)},equal(o,t,e){return mt(o,t,1)}},accessor:{validate(o,t){const e=Ft(o);return e==="function"||e===Ft(t.value)},equal(o,t,e){return typeof t=="function"?!0:mt(o,t,1)}},array:{validate(o,t){return t.optional&&!o||ce(o)},equal(o,t,e){const{compare:i}=e,n=Number.isInteger(i)?i:i?1:0;return i?mt(o,t,n):o===t}},object:{equal(o,t,e){if(e.ignore)return!0;const{compare:i}=e,n=Number.isInteger(i)?i:i?1:0;return i?mt(o,t,n):o===t}},function:{validate(o,t){return t.optional&&!o||typeof o=="function"},equal(o,t,e){return!e.compare&&e.ignore!==!1||o===t}},data:{transform:(o,t,e)=>{if(!o)return o;const{dataTransform:i}=e.props;return i?i(o):typeof o.shape=="string"&&o.shape.endsWith("-table")&&Array.isArray(o.data)?o.data:o}},image:{transform:(o,t,e)=>{const i=e.context;return!i||!i.device?null:vs(e.id,i.device,o,{...t.parameters,...e.props.textureParameters})},release:(o,t,e)=>{ms(e.id,o)}}};function xs(o){const t={},e={},i={};for(const[n,s]of Object.entries(o)){const r=s==null?void 0:s.deprecatedFor;if(r)i[n]=Array.isArray(r)?r:[r];else{const a=_s(n,s);t[n]=a,e[n]=a.value}}return{propTypes:t,defaultProps:e,deprecatedProps:i}}function _s(o,t){switch(Ft(t)){case"object":return nt(o,t);case"array":return nt(o,{type:"array",value:t,compare:!1});case"boolean":return nt(o,{type:"boolean",value:t});case"number":return nt(o,{type:"number",value:t});case"function":return nt(o,{type:"function",value:t,compare:!0});default:return{name:o,type:"unknown",value:t}}}function nt(o,t){return"type"in t?{name:o,...ys[t.type],...t}:"value"in t?{name:o,type:Ft(t.value),...t}:{name:o,type:"object",value:t}}function ce(o){return Array.isArray(o)||ArrayBuffer.isView(o)}function Ft(o){return ce(o)?"array":o===null?"null":typeof o}function Cs(o,t){let e;for(let s=t.length-1;s>=0;s--){const r=t[s];"extensions"in r&&(e=r.extensions)}const i=ue(o.constructor,e),n=Object.create(i);n[zt]=o,n[q]={},n[$]={};for(let s=0;s<t.length;++s){const r=t[s];for(const a in r)n[a]=r[a]}return Object.freeze(n),n}const Ps="_mergedDefaultProps";function ue(o,t){if(!(o instanceof Gt.constructor))return{};let e=Ps;if(t)for(const n of t){const s=n.constructor;s&&(e+=`:${s.extensionName||s.name}`)}const i=Xi(o,e);return i||(o[e]=bs(o,t||[]))}function bs(o,t){if(!o.prototype)return null;const i=Object.getPrototypeOf(o),n=ue(i),s=Xi(o,"defaultProps")||{},r=xs(s),a=Object.assign(Object.create(null),n,r.defaultProps),l=Object.assign(Object.create(null),n==null?void 0:n[Y],r.propTypes),c=Object.assign(Object.create(null),n==null?void 0:n[Kt],r.deprecatedProps);for(const u of t){const f=ue(u.constructor);f&&(Object.assign(a,f),Object.assign(l,f[Y]),Object.assign(c,f[Kt]))}return Ls(a,o),Ss(a,l),As(a,c),a[Y]=l,a[Kt]=c,t.length===0&&!_e(o,"_propTypes")&&(o._propTypes=l),a}function Ls(o,t){const e=ws(t);Object.defineProperties(o,{id:{writable:!0,value:e}})}function As(o,t){for(const e in t)Object.defineProperty(o,e,{enumerable:!1,set(i){const n=`${this.id}: ${e}`;for(const s of t[e])_e(this,s)||(this[s]=i);S.deprecated(n,t[e].join("/"))()}})}function Ss(o,t){const e={},i={};for(const n in t){const s=t[n],{name:r,value:a}=s;s.async&&(e[r]=a,i[r]=Ts(r))}o[tt]=e,o[q]={},Object.defineProperties(o,i)}function Ts(o){return{enumerable:!0,set(t){typeof t=="string"||t instanceof Promise||Ui(t)?this[q][o]=t:this[$][o]=t},get(){if(this[$]){if(o in this[$])return this[$][o]||this[tt][o];if(o in this[q]){const t=this[zt]&&this[zt].internalState;if(t&&t.hasAsyncProp(o))return t.getAsyncProp(o)||this[tt][o]}}return this[tt][o]}}}function _e(o,t){return Object.prototype.hasOwnProperty.call(o,t)}function Xi(o,t){return _e(o,t)&&o[t]}function ws(o){const t=o.componentName;return t||S.warn(`${o.name}.componentName not specified`)(),t||o.name}let Es=0;class Gt{constructor(...t){this.props=Cs(this,t),this.id=this.props.id,this.count=Es++}clone(t){const{props:e}=this,i={};for(const n in e[tt])n in e[$]?i[n]=e[$][n]:n in e[q]&&(i[n]=e[q][n]);return new this.constructor({...e,...i,...t})}}Gt.componentName="Component";Gt.defaultProps={};const Is=Object.freeze({});class Ms{constructor(t){this.component=t,this.asyncProps={},this.onAsyncPropUpdated=()=>{},this.oldProps=null,this.oldAsyncProps=null}finalize(){for(const t in this.asyncProps){const e=this.asyncProps[t];e&&e.type&&e.type.release&&e.type.release(e.resolvedValue,e.type,this.component)}this.asyncProps={},this.component=null,this.resetOldProps()}getOldProps(){return this.oldAsyncProps||this.oldProps||Is}resetOldProps(){this.oldAsyncProps=null,this.oldProps=this.component?this.component.props:null}hasAsyncProp(t){return t in this.asyncProps}getAsyncProp(t){const e=this.asyncProps[t];return e&&e.resolvedValue}isAsyncPropLoading(t){if(t){const e=this.asyncProps[t];return!!(e&&e.pendingLoadCount>0&&e.pendingLoadCount!==e.resolvedLoadCount)}for(const e in this.asyncProps)if(this.isAsyncPropLoading(e))return!0;return!1}reloadAsyncProp(t,e){this._watchPromise(t,Promise.resolve(e))}setAsyncProps(t){this.component=t[zt]||this.component;const e=t[$]||{},i=t[q]||t,n=t[tt]||{};for(const s in e){const r=e[s];this._createAsyncPropData(s,n[s]),this._updateAsyncProp(s,r),e[s]=this.getAsyncProp(s)}for(const s in i){const r=i[s];this._createAsyncPropData(s,n[s]),this._updateAsyncProp(s,r)}}_fetch(t,e){return null}_onResolve(t,e){}_onError(t,e){}_updateAsyncProp(t,e){if(this._didAsyncInputValueChange(t,e)){if(typeof e=="string"&&(e=this._fetch(t,e)),e instanceof Promise){this._watchPromise(t,e);return}if(Ui(e)){this._resolveAsyncIterable(t,e);return}this._setPropValue(t,e)}}_freezeAsyncOldProps(){if(!this.oldAsyncProps&&this.oldProps){this.oldAsyncProps=Object.create(this.oldProps);for(const t in this.asyncProps)Object.defineProperty(this.oldAsyncProps,t,{enumerable:!0,value:this.oldProps[t]})}}_didAsyncInputValueChange(t,e){const i=this.asyncProps[t];return e===i.resolvedValue||e===i.lastValue?!1:(i.lastValue=e,!0)}_setPropValue(t,e){this._freezeAsyncOldProps();const i=this.asyncProps[t];i&&(e=this._postProcessValue(i,e),i.resolvedValue=e,i.pendingLoadCount++,i.resolvedLoadCount=i.pendingLoadCount)}_setAsyncPropValue(t,e,i){const n=this.asyncProps[t];n&&i>=n.resolvedLoadCount&&e!==void 0&&(this._freezeAsyncOldProps(),n.resolvedValue=e,n.resolvedLoadCount=i,this.onAsyncPropUpdated(t,e))}_watchPromise(t,e){const i=this.asyncProps[t];if(i){i.pendingLoadCount++;const n=i.pendingLoadCount;e.then(s=>{this.component&&(s=this._postProcessValue(i,s),this._setAsyncPropValue(t,s,n),this._onResolve(t,s))}).catch(s=>{this._onError(t,s)})}}async _resolveAsyncIterable(t,e){if(t!=="data"){this._setPropValue(t,e);return}const i=this.asyncProps[t];if(!i)return;i.pendingLoadCount++;const n=i.pendingLoadCount;let s=[],r=0;for await(const a of e){if(!this.component)return;const{dataTransform:l}=this.component.props;l?s=l(a,s):s=s.concat(a),Object.defineProperty(s,"__diff",{enumerable:!1,value:[{startRow:r,endRow:s.length}]}),r=s.length,this._setAsyncPropValue(t,s,n)}this._onResolve(t,s)}_postProcessValue(t,e){const i=t.type;return i&&this.component&&(i.release&&i.release(t.resolvedValue,i,this.component),i.transform)?i.transform(e,i,this.component):e}_createAsyncPropData(t,e){if(!this.asyncProps[t]){const n=this.component&&this.component.props[Y];this.asyncProps[t]={type:n&&n[t],lastValue:null,resolvedValue:e,pendingLoadCount:0,resolvedLoadCount:0}}}}class Rs extends Ms{constructor({attributeManager:t,layer:e}){super(e),this.attributeManager=t,this.needsRedraw=!0,this.needsUpdate=!0,this.subLayers=null,this.usesPickingColorCache=!1}get layer(){return this.component}_fetch(t,e){const i=this.layer,n=i==null?void 0:i.props.fetch;return n?n(e,{propName:t,layer:i}):super._fetch(t,e)}_onResolve(t,e){const i=this.layer;if(i){const n=i.props.onDataLoad;t==="data"&&n&&n(e,{propName:t,layer:i})}}_onError(t,e){const i=this.layer;i&&i.raiseError(e,`loading ${t} of ${this.layer}`)}}const Os="layer.changeFlag",zs="layer.initialize",Fs="layer.update",ks="layer.finalize",Bs="layer.matched",$e=2**24-1,Us=Object.freeze([]),Ds=Ti(({oldViewport:o,viewport:t})=>o.equals(t));let F=new Uint8ClampedArray(0);const Ns={data:{type:"data",value:Us,async:!0},dataComparator:{type:"function",value:null,optional:!0},_dataDiff:{type:"function",value:o=>o&&o.__diff,optional:!0},dataTransform:{type:"function",value:null,optional:!0},onDataLoad:{type:"function",value:null,optional:!0},onError:{type:"function",value:null,optional:!0},fetch:{type:"function",value:(o,{propName:t,layer:e,loaders:i,loadOptions:n,signal:s})=>{var l;const{resourceManager:r}=e.context;n=n||e.getLoadOptions(),i=i||e.props.loaders,s&&(n={...n,core:{...n==null?void 0:n.core,fetch:{...(l=n==null?void 0:n.core)==null?void 0:l.fetch,signal:s}}});let a=r.contains(o);return!a&&!n&&(r.add({resourceId:o,data:se(o,i),persistent:!1}),a=!0),a?r.subscribe({resourceId:o,onChange:c=>{var u;return(u=e.internalState)==null?void 0:u.reloadAsyncProp(t,c)},consumerId:e.id,requestId:t}):se(o,i,n)}},updateTriggers:{},visible:!0,pickable:!1,opacity:{type:"number",min:0,max:1,value:1},operation:"draw",onHover:{type:"function",value:null,optional:!0},onClick:{type:"function",value:null,optional:!0},onDragStart:{type:"function",value:null,optional:!0},onDrag:{type:"function",value:null,optional:!0},onDragEnd:{type:"function",value:null,optional:!0},coordinateSystem:"default",coordinateOrigin:{type:"array",value:[0,0,0],compare:!0},modelMatrix:{type:"array",value:null,compare:!0,optional:!0},wrapLongitude:!1,positionFormat:"XYZ",colorFormat:"RGBA",parameters:{type:"object",value:{},optional:!0,compare:2},loadOptions:{type:"object",value:null,optional:!0,ignore:!0},transitions:null,extensions:[],loaders:{type:"array",value:[],optional:!0,ignore:!0},getPolygonOffset:{type:"function",value:({layerIndex:o})=>[0,-o*100]},highlightedObjectIndex:null,autoHighlight:!1,highlightColor:{type:"accessor",value:[0,0,128,128]}};class k extends Gt{constructor(){super(...arguments),this.internalState=null,this.lifecycle=Wo.NO_STATE,this.parent=null}static get componentName(){return Object.prototype.hasOwnProperty.call(this,"layerName")?this.layerName:""}get root(){let t=this;for(;t.parent;)t=t.parent;return t}toString(){return`${this.constructor.layerName||this.constructor.name}({id: '${this.props.id}'})`}project(t){W(this.internalState);const e=this.internalState.viewport||this.context.viewport,i=xe(t,{viewport:e,modelMatrix:this.props.modelMatrix,coordinateOrigin:this.props.coordinateOrigin,coordinateSystem:this.props.coordinateSystem}),[n,s,r]=No(i,e.pixelProjectionMatrix);return t.length===2?[n,s]:[n,s,r]}unproject(t){return W(this.internalState),(this.internalState.viewport||this.context.viewport).unproject(t)}projectPosition(t,e){W(this.internalState);const i=this.internalState.viewport||this.context.viewport;return _n(t,{viewport:i,modelMatrix:this.props.modelMatrix,coordinateOrigin:this.props.coordinateOrigin,coordinateSystem:this.props.coordinateSystem,...e})}get isComposite(){return!1}get isDrawable(){return!0}setState(t){this.setChangeFlags({stateChanged:!0}),Object.assign(this.state,t),this.setNeedsRedraw()}setNeedsRedraw(){this.internalState&&(this.internalState.needsRedraw=!0)}setNeedsUpdate(){this.internalState&&(this.context.layerManager.setNeedsUpdate(String(this)),this.internalState.needsUpdate=!0)}get isLoaded(){return this.internalState?!this.internalState.isAsyncPropLoading():!1}get wrapLongitude(){return this.props.wrapLongitude}isPickable(){return this.props.pickable&&this.props.visible}getModels(){const t=this.state;return t&&(t.models||t.model&&[t.model])||[]}setShaderModuleProps(...t){for(const e of this.getModels())e.shaderInputs.setProps(...t)}getAttributeManager(){return this.internalState&&this.internalState.attributeManager}getCurrentLayer(){return this.internalState&&this.internalState.layer}getLoadOptions(){return this.props.loadOptions}use64bitPositions(){const{coordinateSystem:t}=this.props;return t==="default"||t==="lnglat"||t==="cartesian"}onHover(t,e){return this.props.onHover&&this.props.onHover(t,e)||!1}onClick(t,e){return this.props.onClick&&this.props.onClick(t,e)||!1}nullPickingColor(){return[0,0,0]}encodePickingColor(t,e=[]){return e[0]=t+1&255,e[1]=t+1>>8&255,e[2]=t+1>>8>>8&255,e}decodePickingColor(t){W(t instanceof Uint8Array);const[e,i,n]=t;return e+i*256+n*65536-1}getNumInstances(){return Number.isFinite(this.props.numInstances)?this.props.numInstances:this.state&&this.state.numInstances!==void 0?this.state.numInstances:ds(this.props.data)}getStartIndices(){return this.props.startIndices?this.props.startIndices:this.state&&this.state.startIndices?this.state.startIndices:null}getBounds(){var t;return(t=this.getAttributeManager())==null?void 0:t.getBounds(["positions","instancePositions"])}getShaders(t){t=Re(t,{disableWarnings:!0,modules:this.context.defaultShaderModules});for(const e of this.props.extensions)t=Re(t,e.getShaders.call(this,e));return t}shouldUpdateState(t){return t.changeFlags.propsOrDataChanged}updateState(t){const e=this.getAttributeManager(),{dataChanged:i}=t.changeFlags;if(i&&e)if(Array.isArray(i))for(const n of i)e.invalidateAll(n);else e.invalidateAll();if(e){const{props:n}=t,s=this.internalState.hasPickingBuffer,r=Number.isInteger(n.highlightedObjectIndex)||!!n.pickable||n.extensions.some(a=>a.getNeedsPickingBuffer.call(this,a));if(s!==r){this.internalState.hasPickingBuffer=r;const{pickingColors:a,instancePickingColors:l}=e.attributes,c=a||l;c&&(r&&c.constant&&(c.constant=!1,e.invalidate(c.id)),!c.value&&!r&&(c.constant=!0,c.value=[0,0,0]))}}}finalizeState(t){for(const i of this.getModels())i.destroy();const e=this.getAttributeManager();e&&e.finalize(),this.context&&this.context.resourceManager.unsubscribe({consumerId:this.id}),this.internalState&&(this.internalState.uniformTransitions.clear(),this.internalState.finalize())}draw(t){for(const e of this.getModels())e.draw(t.renderPass)}getPickingInfo({info:t,mode:e,sourceLayer:i}){const{index:n}=t;return n>=0&&Array.isArray(this.props.data)&&(t.object=this.props.data[n]),t}raiseError(t,e){var i,n,s,r;e&&(t=new Error(`${e}: ${t.message}`,{cause:t})),(n=(i=this.props).onError)!=null&&n.call(i,t)||(r=(s=this.context)==null?void 0:s.onError)==null||r.call(s,t,this)}getNeedsRedraw(t={clearRedrawFlags:!1}){return this._getNeedsRedraw(t)}needsUpdate(){return this.internalState?this.internalState.needsUpdate||this.hasUniformTransition()||this.shouldUpdateState(this._getUpdateParams()):!1}hasUniformTransition(){var t;return((t=this.internalState)==null?void 0:t.uniformTransitions.active)||!1}activateViewport(t){if(!this.internalState)return;const e=this.internalState.viewport;this.internalState.viewport=t,(!e||!Ds({oldViewport:e,viewport:t}))&&(this.setChangeFlags({viewportChanged:!0}),this.isComposite?this.needsUpdate()&&this.setNeedsUpdate():this._update())}invalidateAttribute(t="all"){const e=this.getAttributeManager();e&&(t==="all"?e.invalidateAll():e.invalidate(t))}updateAttributes(t){let e=!1;for(const i in t)t[i].layoutChanged()&&(e=!0);for(const i of this.getModels())this._setModelAttributes(i,t,e)}_updateAttributes(){const t=this.getAttributeManager();if(!t)return;const e=this.props,i=this.getNumInstances(),n=this.getStartIndices();t.update({data:e.data,numInstances:i,startIndices:n,props:e,transitions:e.transitions,buffers:e.data.attributes,context:this});const s=t.getChangedAttributes({clearChangedFlags:!0});this.updateAttributes(s)}_updateAttributeTransition(){const t=this.getAttributeManager();t&&t.updateTransition()}_updateUniformTransition(){const{uniformTransitions:t}=this.internalState;if(t.active){const e=t.update(),i=Object.create(this.props);for(const n in e)Object.defineProperty(i,n,{value:e[n]});return i}return this.props}calculateInstancePickingColors(t,{numInstances:e}){if(t.constant)return;const i=Math.floor(F.length/4);this.internalState.usesPickingColorCache=!0;const n=e>0&&F[0]===0;if(i<e||n){e>$e&&S.warn("Layer has too many data objects. Picking might not be able to distinguish all objects.")(),F=Ot.allocate(F,e,{size:4,copy:!0,maxCount:Math.max(e,$e)});const s=Math.floor(F.length/4),r=[0,0,0],a=n?0:i;for(let l=a;l<s;l++)this.encodePickingColor(l,r),F[l*4+0]=r[0],F[l*4+1]=r[1],F[l*4+2]=r[2],F[l*4+3]=0}t.value=F.subarray(0,e*4)}_setModelAttributes(t,e,i=!1){var a;if(!Object.keys(e).length)return;if(i){const l=this.getAttributeManager();t.setBufferLayout(l.getBufferLayouts(t)),e=l.getAttributes()}const n=((a=t.userData)==null?void 0:a.excludeAttributes)||{},s={},r={};for(const l in e){if(n[l])continue;const c=e[l].getValue();for(const u in c){const f=c[u];f instanceof K?e[l].settings.isIndexed?t.setIndexBuffer(f):s[u]=f:f&&(r[u]=f)}}t.setAttributes(s),t.setConstantAttributes(r)}disablePickingIndex(t){const e=this.props.data;if(!("attributes"in e)){this._disablePickingIndex(t);return}const{pickingColors:i,instancePickingColors:n}=this.getAttributeManager().attributes,s=i||n,r=s&&e.attributes&&e.attributes[s.id];if(r&&r.value){const a=r.value,l=this.encodePickingColor(t);for(let c=0;c<e.length;c++){const u=s.getVertexOffset(c);a[u]===l[0]&&a[u+1]===l[1]&&a[u+2]===l[2]&&this._disablePickingIndex(c)}}else this._disablePickingIndex(t)}_disablePickingIndex(t){const{pickingColors:e,instancePickingColors:i}=this.getAttributeManager().attributes,n=e||i;if(!n)return;const s=n.getVertexOffset(t),r=n.getVertexOffset(t+1);n.buffer.write(new Uint8Array(r-s),s)}restorePickingColors(){const{pickingColors:t,instancePickingColors:e}=this.getAttributeManager().attributes,i=t||e;i&&(this.internalState.usesPickingColorCache&&i.value.buffer!==F.buffer&&(i.value=F.subarray(0,i.value.length)),i.updateSubBuffer({startOffset:0}))}_initialize(){W(!this.internalState),O(zs,this);const t=this._getAttributeManager();t&&t.addInstanced({instancePickingColors:{type:"uint8",size:4,noAlloc:!0,update:this.calculateInstancePickingColors}}),this.internalState=new Rs({attributeManager:t,layer:this}),this._clearChangeFlags(),this.state={},Object.defineProperty(this.state,"attributeManager",{get:()=>(S.deprecated("layer.state.attributeManager","layer.getAttributeManager()")(),t)}),this.internalState.uniformTransitions=new os(this.context.timeline),this.internalState.onAsyncPropUpdated=this._onAsyncPropUpdated.bind(this),this.internalState.setAsyncProps(this.props),this.initializeState(this.context);for(const e of this.props.extensions)e.initializeState.call(this,this.context,e);this.setChangeFlags({dataChanged:"init",propsChanged:"init",viewportChanged:!0,extensionsChanged:!0}),this._update()}_transferState(t){O(Bs,this,this===t);const{state:e,internalState:i}=t;this!==t&&(this.internalState=i,this.state=e,this.internalState.setAsyncProps(this.props),this._diffProps(this.props,this.internalState.getOldProps()))}_update(){const t=this.needsUpdate();if(O(Fs,this,t),!t)return;this.context.stats.get("Layer updates").incrementCount();const e=this.props,i=this.context,n=this.internalState,s=i.viewport,r=this._updateUniformTransition();n.propsInTransition=r,i.viewport=n.viewport||s,this.props=r;try{const a=this._getUpdateParams(),l=this.getModels();if(i.device)this.updateState(a);else try{this.updateState(a)}catch{}for(const u of this.props.extensions)u.updateState.call(this,a,u);this.setNeedsRedraw(),this._updateAttributes();const c=this.getModels()[0]!==l[0];this._postUpdate(a,c)}finally{i.viewport=s,this.props=e,this._clearChangeFlags(),n.needsUpdate=!1,n.resetOldProps()}}_finalize(){O(ks,this),this.finalizeState(this.context);for(const t of this.props.extensions)t.finalizeState.call(this,this.context,t)}_drawLayer({renderPass:t,shaderModuleProps:e=null,uniforms:i={},parameters:n={}}){this._updateAttributeTransition();const s=this.props,r=this.context;this.props=this.internalState.propsInTransition||s;try{e&&this.setShaderModuleProps(e);const{getPolygonOffset:a}=this.props,l=a&&a(i)||[0,0];r.device instanceof Xt&&r.device.setParametersWebGL({polygonOffset:l});const c=r.device instanceof Xt?null:Gs(n);if(js(this.getModels(),t,n,c),r.device instanceof Xt)r.device.withParametersWebGL(n,()=>{const u={renderPass:t,shaderModuleProps:e,uniforms:i,parameters:n,context:r};for(const f of this.props.extensions)f.draw.call(this,u,f);this.draw(u)});else{c!=null&&c.renderPassParameters&&t.setParameters(c.renderPassParameters);const u={renderPass:t,shaderModuleProps:e,uniforms:i,parameters:n,context:r};for(const f of this.props.extensions)f.draw.call(this,u,f);this.draw(u)}}finally{this.props=s}}getChangeFlags(){var t;return(t=this.internalState)==null?void 0:t.changeFlags}setChangeFlags(t){if(!this.internalState)return;const{changeFlags:e}=this.internalState;for(const n in t)if(t[n]){let s=!1;switch(n){case"dataChanged":const r=t[n],a=e[n];r&&Array.isArray(a)&&(e.dataChanged=Array.isArray(r)?a.concat(r):r,s=!0);default:e[n]||(e[n]=t[n],s=!0)}s&&O(Os,this,n,t)}const i=!!(e.dataChanged||e.updateTriggersChanged||e.propsChanged||e.extensionsChanged);e.propsOrDataChanged=i,e.somethingChanged=i||e.viewportChanged||e.stateChanged}_clearChangeFlags(){this.internalState.changeFlags={dataChanged:!1,propsChanged:!1,updateTriggersChanged:!1,viewportChanged:!1,stateChanged:!1,extensionsChanged:!1,propsOrDataChanged:!1,somethingChanged:!1}}_diffProps(t,e){var n;const i=ss(t,e);if(i.updateTriggersChanged)for(const s in i.updateTriggersChanged)i.updateTriggersChanged[s]&&this.invalidateAttribute(s);if(i.transitionsChanged)for(const s in i.transitionsChanged)this.internalState.uniformTransitions.add(s,e[s],t[s],(n=t.transitions)==null?void 0:n[s]);return this.setChangeFlags(i)}validateProps(){ns(this.props)}updateAutoHighlight(t){this.props.autoHighlight&&!Number.isInteger(this.props.highlightedObjectIndex)&&this._updateAutoHighlight(t)}_updateAutoHighlight(t){const e={highlightedObjectColor:t.picked?t.color:null},{highlightColor:i}=this.props;t.picked&&typeof i=="function"&&(e.highlightColor=i(t)),this.setShaderModuleProps({picking:e}),this.setNeedsRedraw()}_getAttributeManager(){const t=this.context;return new Jn(t.device,{id:this.props.id,stats:t.stats,timeline:t.timeline})}_postUpdate(t,e){const{props:i,oldProps:n}=t,s=this.state.model;s!=null&&s.isInstanced&&s.setInstanceCount(this.getNumInstances());const{autoHighlight:r,highlightedObjectIndex:a,highlightColor:l}=i;if(e||n.autoHighlight!==r||n.highlightedObjectIndex!==a||n.highlightColor!==l){const c={};Array.isArray(l)&&(c.highlightColor=l),(e||n.autoHighlight!==r||a!==n.highlightedObjectIndex)&&(c.highlightedObjectColor=Number.isFinite(a)&&a>=0?this.encodePickingColor(a):null),this.setShaderModuleProps({picking:c})}}_getUpdateParams(){return{props:this.props,oldProps:this.internalState.getOldProps(),context:this.context,changeFlags:this.internalState.changeFlags}}_getNeedsRedraw(t){if(!this.internalState)return!1;let e=!1;e=e||this.internalState.needsRedraw&&this.id;const i=this.getAttributeManager(),n=i?i.getNeedsRedraw(t):!1;if(e=e||n,e)for(const s of this.props.extensions)s.onNeedsRedraw.call(this,s);return this.internalState.needsRedraw=this.internalState.needsRedraw&&!t.clearRedrawFlags,e}_onAsyncPropUpdated(){this._diffProps(this.props,this.internalState.getOldProps()),this.setNeedsUpdate()}}k.defaultProps=Ns;k.layerName="Layer";function Gs(o){const{blendConstant:t,...e}=o;return t?{pipelineParameters:e,renderPassParameters:{blendConstant:t}}:{pipelineParameters:e}}function js(o,t,e,i){for(const n of o)n.device.type==="webgpu"?(Vs(n,t),n.setParameters({...n.parameters,...i==null?void 0:i.pipelineParameters})):n.setParameters(e)}function Vs(o,t){var r,a;const e=t.props.framebuffer||(t.framebuffer??null);if(!e)return;const i=e.colorAttachments.map(l=>{var c;return((c=l==null?void 0:l.texture)==null?void 0:c.format)??null}),n=(a=(r=e.depthStencilAttachment)==null?void 0:r.texture)==null?void 0:a.format,s=o;(!Ws(s.props.colorAttachmentFormats,i)||s.props.depthStencilAttachmentFormat!==n)&&(s.props.colorAttachmentFormats=i,s.props.depthStencilAttachmentFormat=n,s._setPipelineNeedsUpdate("attachment formats"))}function Ws(o,t){if(o===t)return!0;if(!o||!t||o.length!==t.length)return!1;for(let e=0;e<o.length;e++)if(o[e]!==t[e])return!1;return!0}const $s="compositeLayer.renderLayers";class jt extends k{get isComposite(){return!0}get isDrawable(){return!1}get isLoaded(){return super.isLoaded&&this.getSubLayers().every(t=>t.isLoaded)}getSubLayers(){return this.internalState&&this.internalState.subLayers||[]}initializeState(t){}setState(t){super.setState(t),this.setNeedsUpdate()}getPickingInfo({info:t}){const{object:e}=t;return e&&e.__source&&e.__source.parent&&e.__source.parent.id===this.id&&(t.object=e.__source.object,t.index=e.__source.index),t}filterSubLayer(t){return!0}shouldRenderSubLayer(t,e){return e&&e.length}getSubLayerClass(t,e){const{_subLayerProps:i}=this.props;return i&&i[t]&&i[t].type||e}getSubLayerRow(t,e,i){return t.__source={parent:this,object:e,index:i},t}getSubLayerAccessor(t){if(typeof t=="function"){const e={index:-1,data:this.props.data,target:[]};return(i,n)=>i&&i.__source?(e.index=i.__source.index,t(i.__source.object,e)):t(i,n)}return t}getSubLayerProps(t={}){var R;const{opacity:e,pickable:i,visible:n,parameters:s,getPolygonOffset:r,highlightedObjectIndex:a,autoHighlight:l,highlightColor:c,coordinateSystem:u,coordinateOrigin:f,wrapLongitude:d,positionFormat:g,modelMatrix:h,extensions:p,fetch:v,operation:x,_subLayerProps:_}=this.props,y={id:"",updateTriggers:{},opacity:e,pickable:i,visible:n,parameters:s,getPolygonOffset:r,highlightedObjectIndex:a,autoHighlight:l,highlightColor:c,coordinateSystem:u,coordinateOrigin:f,wrapLongitude:d,positionFormat:g,modelMatrix:h,extensions:p,fetch:v,operation:x},m=_&&t.id&&_[t.id],C=m&&m.updateTriggers,L=t.id||"sublayer";if(m){const w=this.props[Y],P=t.type?t.type._propTypes:{};for(const T in m){const I=P[T]||w[T];I&&I.type==="accessor"&&(m[T]=this.getSubLayerAccessor(m[T]))}}Object.assign(y,t,m),y.id=`${this.props.id}-${L}`,y.updateTriggers={all:(R=this.props.updateTriggers)==null?void 0:R.all,...t.updateTriggers,...C};for(const w of p){const P=w.getSubLayerProps.call(this,w);P&&Object.assign(y,P,{updateTriggers:Object.assign(y.updateTriggers,P.updateTriggers)})}return y}_updateAutoHighlight(t){for(const e of this.getSubLayers())e.updateAutoHighlight(t)}_getAttributeManager(){return null}_postUpdate(t,e){let i=this.internalState.subLayers;const n=!i||this.needsUpdate();if(n){const s=this.renderLayers();i=$o(s,Boolean),this.internalState.subLayers=i}O($s,this,n,i);for(const s of i)s.parent=this}}jt.layerName="CompositeLayer";class qi{constructor(t){this.indexStarts=[0],this.vertexStarts=[0],this.vertexCount=0,this.instanceCount=0;const{attributes:e={}}=t;this.typedArrayManager=Ot,this.attributes={},this._attributeDefs=e,this.opts=t,this.updateGeometry(t)}updateGeometry(t){Object.assign(this.opts,t);const{data:e,buffers:i={},getGeometry:n,geometryBuffer:s,positionFormat:r,dataChanged:a,normalize:l=!0}=this.opts;if(this.data=e,this.getGeometry=n,this.positionSize=s&&s.size||(r==="XY"?2:3),this.buffers=i,this.normalize=l,s&&(W(e.startIndices),this.getGeometry=this.getGeometryFromBuffer(s),l||(i.vertexPositions=s)),this.geometryBuffer=i.vertexPositions,Array.isArray(a))for(const c of a)this._rebuildGeometry(c);else this._rebuildGeometry()}updatePartialGeometry({startRow:t,endRow:e}){this._rebuildGeometry({startRow:t,endRow:e})}getGeometryFromBuffer(t){const e=t.value||t;return ArrayBuffer.isView(e)?Di(e,{size:this.positionSize,offset:t.offset,stride:t.stride,startIndices:this.data.startIndices}):null}_allocate(t,e){const{attributes:i,buffers:n,_attributeDefs:s,typedArrayManager:r}=this;for(const a in s)if(a in n)r.release(i[a]),i[a]=null;else{const l=s[a];l.copy=e,i[a]=r.allocate(i[a],t,l)}}_forEachGeometry(t,e,i){const{data:n,getGeometry:s}=this,{iterable:r,objectInfo:a}=it(n,e,i);for(const l of r){a.index++;const c=s?s(l,a):null;t(c,a.index)}}_rebuildGeometry(t){if(!this.data)return;let{indexStarts:e,vertexStarts:i,instanceCount:n}=this;const{data:s,geometryBuffer:r}=this,{startRow:a=0,endRow:l=1/0}=t||{},c={};if(t||(e=[0],i=[0]),this.normalize||!r)this._forEachGeometry((f,d)=>{const g=f&&this.normalizeGeometry(f);c[d]=g,i[d+1]=i[d]+(g?this.getGeometrySize(g):0)},a,l),n=i[i.length-1];else if(i=s.startIndices,n=i[s.length]||0,ArrayBuffer.isView(r))n=n||r.length/this.positionSize;else if(r instanceof K){const f=this.positionSize*4;n=n||r.byteLength/f}else if(r.buffer){const f=r.stride||this.positionSize*4;n=n||r.buffer.byteLength/f}else if(r.value){const f=r.value,d=r.stride/f.BYTES_PER_ELEMENT||this.positionSize;n=n||f.length/d}this._allocate(n,!!t),this.indexStarts=e,this.vertexStarts=i,this.instanceCount=n;const u={};this._forEachGeometry((f,d)=>{const g=c[d]||f;u.vertexStart=i[d],u.indexStart=e[d];const h=d<i.length-1?i[d+1]:n;u.geometrySize=h-i[d],u.geometryIndex=d,this.updateGeometryAttributes(g,u)},a,l),this.vertexCount=e[e.length-1]}}const He=`layout(std140) uniform arcUniforms {
  bool greatCircle;
  bool useShortestPath;
  float numSegments;
  float widthScale;
  float widthMinPixels;
  float widthMaxPixels;
  highp int widthUnits;
} arc;
`,Hs={name:"arc",vs:He,fs:He,uniformTypes:{greatCircle:"f32",useShortestPath:"f32",numSegments:"f32",widthScale:"f32",widthMinPixels:"f32",widthMaxPixels:"f32",widthUnits:"i32"}},Ys=`#version 300 es
#define SHADER_NAME arc-layer-vertex-shader
in vec4 instanceSourceColors;
in vec4 instanceTargetColors;
in vec3 instanceSourcePositions;
in vec3 instanceSourcePositions64Low;
in vec3 instanceTargetPositions;
in vec3 instanceTargetPositions64Low;
in vec3 instancePickingColors;
in float instanceWidths;
in float instanceHeights;
in float instanceTilts;
out vec4 vColor;
out vec2 uv;
out float isValid;
float paraboloid(float distance, float sourceZ, float targetZ, float ratio) {
float deltaZ = targetZ - sourceZ;
float dh = distance * instanceHeights;
if (dh == 0.0) {
return sourceZ + deltaZ * ratio;
}
float unitZ = deltaZ / dh;
float p2 = unitZ * unitZ + 1.0;
float dir = step(deltaZ, 0.0);
float z0 = mix(sourceZ, targetZ, dir);
float r = mix(ratio, 1.0 - ratio, dir);
return sqrt(r * (p2 - r)) * dh + z0;
}
vec2 getExtrusionOffset(vec2 line_clipspace, float offset_direction, float width) {
vec2 dir_screenspace = normalize(line_clipspace * project.viewportSize);
dir_screenspace = vec2(-dir_screenspace.y, dir_screenspace.x);
return dir_screenspace * offset_direction * width / 2.0;
}
float getSegmentRatio(float index) {
return smoothstep(0.0, 1.0, index / (arc.numSegments - 1.0));
}
vec3 interpolateFlat(vec3 source, vec3 target, float segmentRatio) {
float distance = length(source.xy - target.xy);
float z = paraboloid(distance, source.z, target.z, segmentRatio);
float tiltAngle = radians(instanceTilts);
vec2 tiltDirection = normalize(target.xy - source.xy);
vec2 tilt = vec2(-tiltDirection.y, tiltDirection.x) * z * sin(tiltAngle);
return vec3(
mix(source.xy, target.xy, segmentRatio) + tilt,
z * cos(tiltAngle)
);
}
float getAngularDist (vec2 source, vec2 target) {
vec2 sourceRadians = radians(source);
vec2 targetRadians = radians(target);
vec2 sin_half_delta = sin((sourceRadians - targetRadians) / 2.0);
vec2 shd_sq = sin_half_delta * sin_half_delta;
float a = shd_sq.y + cos(sourceRadians.y) * cos(targetRadians.y) * shd_sq.x;
return 2.0 * asin(sqrt(a));
}
vec3 interpolateGreatCircle(vec3 source, vec3 target, vec3 source3D, vec3 target3D, float angularDist, float t) {
vec2 lngLat;
if(abs(angularDist - PI) < 0.001) {
lngLat = (1.0 - t) * source.xy + t * target.xy;
} else {
float a = sin((1.0 - t) * angularDist);
float b = sin(t * angularDist);
vec3 p = source3D.yxz * a + target3D.yxz * b;
lngLat = degrees(vec2(atan(p.y, -p.x), atan(p.z, length(p.xy))));
}
float z = paraboloid(angularDist * EARTH_RADIUS, source.z, target.z, t);
return vec3(lngLat, z);
}
void main(void) {
geometry.worldPosition = instanceSourcePositions;
geometry.worldPositionAlt = instanceTargetPositions;
float segmentIndex = float(gl_VertexID / 2);
float segmentSide = mod(float(gl_VertexID), 2.) == 0. ? -1. : 1.;
float segmentRatio = getSegmentRatio(segmentIndex);
float prevSegmentRatio = getSegmentRatio(max(0.0, segmentIndex - 1.0));
float nextSegmentRatio = getSegmentRatio(min(arc.numSegments - 1.0, segmentIndex + 1.0));
float indexDir = mix(-1.0, 1.0, step(segmentIndex, 0.0));
isValid = 1.0;
uv = vec2(segmentRatio, segmentSide);
geometry.uv = uv;
geometry.pickingColor = instancePickingColors;
vec4 curr;
vec4 next;
vec3 source;
vec3 target;
if ((arc.greatCircle || project.projectionMode == PROJECTION_MODE_GLOBE) && project.coordinateSystem == COORDINATE_SYSTEM_LNGLAT) {
source = project_globe_(vec3(instanceSourcePositions.xy, 0.0));
target = project_globe_(vec3(instanceTargetPositions.xy, 0.0));
float angularDist = getAngularDist(instanceSourcePositions.xy, instanceTargetPositions.xy);
vec3 prevPos = interpolateGreatCircle(instanceSourcePositions, instanceTargetPositions, source, target, angularDist, prevSegmentRatio);
vec3 currPos = interpolateGreatCircle(instanceSourcePositions, instanceTargetPositions, source, target, angularDist, segmentRatio);
vec3 nextPos = interpolateGreatCircle(instanceSourcePositions, instanceTargetPositions, source, target, angularDist, nextSegmentRatio);
if (abs(currPos.x - prevPos.x) > 180.0) {
indexDir = -1.0;
isValid = 0.0;
} else if (abs(currPos.x - nextPos.x) > 180.0) {
indexDir = 1.0;
isValid = 0.0;
}
nextPos = indexDir < 0.0 ? prevPos : nextPos;
nextSegmentRatio = indexDir < 0.0 ? prevSegmentRatio : nextSegmentRatio;
if (isValid == 0.0) {
nextPos.x += nextPos.x > 0.0 ? -360.0 : 360.0;
float t = ((currPos.x > 0.0 ? 180.0 : -180.0) - currPos.x) / (nextPos.x - currPos.x);
currPos = mix(currPos, nextPos, t);
segmentRatio = mix(segmentRatio, nextSegmentRatio, t);
}
vec3 currPos64Low = mix(instanceSourcePositions64Low, instanceTargetPositions64Low, segmentRatio);
vec3 nextPos64Low = mix(instanceSourcePositions64Low, instanceTargetPositions64Low, nextSegmentRatio);
curr = project_position_to_clipspace(currPos, currPos64Low, vec3(0.0), geometry.position);
next = project_position_to_clipspace(nextPos, nextPos64Low, vec3(0.0));
} else {
vec3 source_world = instanceSourcePositions;
vec3 target_world = instanceTargetPositions;
if (arc.useShortestPath) {
source_world.x = mod(source_world.x + 180., 360.0) - 180.;
target_world.x = mod(target_world.x + 180., 360.0) - 180.;
float deltaLng = target_world.x - source_world.x;
if (deltaLng > 180.) target_world.x -= 360.;
if (deltaLng < -180.) source_world.x -= 360.;
}
source = project_position(source_world, instanceSourcePositions64Low);
target = project_position(target_world, instanceTargetPositions64Low);
float antiMeridianX = 0.0;
if (arc.useShortestPath) {
if (project.projectionMode == PROJECTION_MODE_WEB_MERCATOR_AUTO_OFFSET) {
antiMeridianX = -(project.coordinateOrigin.x + 180.) / 360. * TILE_SIZE;
}
float thresholdRatio = (antiMeridianX - source.x) / (target.x - source.x);
if (prevSegmentRatio <= thresholdRatio && nextSegmentRatio > thresholdRatio) {
isValid = 0.0;
indexDir = sign(segmentRatio - thresholdRatio);
segmentRatio = thresholdRatio;
}
}
nextSegmentRatio = indexDir < 0.0 ? prevSegmentRatio : nextSegmentRatio;
vec3 currPos = interpolateFlat(source, target, segmentRatio);
vec3 nextPos = interpolateFlat(source, target, nextSegmentRatio);
if (arc.useShortestPath) {
if (nextPos.x < antiMeridianX) {
currPos.x += TILE_SIZE;
nextPos.x += TILE_SIZE;
}
}
curr = project_common_position_to_clipspace(vec4(currPos, 1.0));
next = project_common_position_to_clipspace(vec4(nextPos, 1.0));
geometry.position = vec4(currPos, 1.0);
}
float widthPixels = clamp(
project_size_to_pixel(instanceWidths * arc.widthScale, arc.widthUnits),
arc.widthMinPixels, arc.widthMaxPixels
);
vec3 offset = vec3(
getExtrusionOffset((next.xy - curr.xy) * indexDir, segmentSide, widthPixels),
0.0);
DECKGL_FILTER_SIZE(offset, geometry);
DECKGL_FILTER_GL_POSITION(curr, geometry);
gl_Position = curr + vec4(project_pixel_size_to_clipspace(offset.xy), 0.0, 0.0);
vec4 color = mix(instanceSourceColors, instanceTargetColors, segmentRatio);
vColor = vec4(color.rgb, color.a * layer.opacity);
DECKGL_FILTER_COLOR(vColor, geometry);
}
`,Zs=`#version 300 es
#define SHADER_NAME arc-layer-fragment-shader
precision highp float;
in vec4 vColor;
in vec2 uv;
in float isValid;
out vec4 fragColor;
void main(void) {
if (isValid == 0.0) {
discard;
}
fragColor = vColor;
geometry.uv = uv;
DECKGL_FILTER_COLOR(fragColor, geometry);
}
`,kt=[0,0,0,255],Ks={getSourcePosition:{type:"accessor",value:o=>o.sourcePosition},getTargetPosition:{type:"accessor",value:o=>o.targetPosition},getSourceColor:{type:"accessor",value:kt},getTargetColor:{type:"accessor",value:kt},getWidth:{type:"accessor",value:1},getHeight:{type:"accessor",value:1},getTilt:{type:"accessor",value:0},greatCircle:!1,numSegments:{type:"number",value:50,min:1},widthUnits:"pixels",widthScale:{type:"number",value:1,min:0},widthMinPixels:{type:"number",value:0,min:0},widthMaxPixels:{type:"number",value:Number.MAX_SAFE_INTEGER,min:0}};class Ji extends k{getBounds(){var t;return(t=this.getAttributeManager())==null?void 0:t.getBounds(["instanceSourcePositions","instanceTargetPositions"])}getShaders(){return super.getShaders({vs:Ys,fs:Zs,modules:[G,j,Hs]})}get wrapLongitude(){return!1}initializeState(){this.getAttributeManager().addInstanced({instanceSourcePositions:{size:3,type:"float64",fp64:this.use64bitPositions(),transition:!0,accessor:"getSourcePosition"},instanceTargetPositions:{size:3,type:"float64",fp64:this.use64bitPositions(),transition:!0,accessor:"getTargetPosition"},instanceSourceColors:{size:this.props.colorFormat.length,type:"unorm8",transition:!0,accessor:"getSourceColor",defaultValue:kt},instanceTargetColors:{size:this.props.colorFormat.length,type:"unorm8",transition:!0,accessor:"getTargetColor",defaultValue:kt},instanceWidths:{size:1,transition:!0,accessor:"getWidth",defaultValue:1},instanceHeights:{size:1,transition:!0,accessor:"getHeight",defaultValue:1},instanceTilts:{size:1,transition:!0,accessor:"getTilt",defaultValue:0}})}updateState(t){var e;super.updateState(t),t.changeFlags.extensionsChanged&&((e=this.state.model)==null||e.destroy(),this.state.model=this._getModel(),this.getAttributeManager().invalidateAll())}draw({uniforms:t}){const{widthUnits:e,widthScale:i,widthMinPixels:n,widthMaxPixels:s,greatCircle:r,wrapLongitude:a,numSegments:l}=this.props,c={numSegments:l,widthUnits:D[e],widthScale:i,widthMinPixels:n,widthMaxPixels:s,greatCircle:r,useShortestPath:a},u=this.state.model;u.shaderInputs.setProps({arc:c}),u.setVertexCount(l*2),u.draw(this.context.renderPass)}_getModel(){return new M(this.context.device,{...this.getShaders(),id:this.props.id,bufferLayout:this.getAttributeManager().getBufferLayouts(),topology:"triangle-strip",isInstanced:!0})}}Ji.layerName="ArcLayer";Ji.defaultProps=Ks;const Xs=new Uint32Array([0,2,1,0,3,2]),qs=new Float32Array([0,1,0,0,1,0,1,1]);function Js(o,t){if(!t)return Qs(o);const e=Math.max(Math.abs(o[0][0]-o[3][0]),Math.abs(o[1][0]-o[2][0])),i=Math.max(Math.abs(o[1][1]-o[0][1]),Math.abs(o[2][1]-o[3][1])),n=Math.ceil(e/t)+1,s=Math.ceil(i/t)+1,r=(n-1)*(s-1)*6,a=new Uint32Array(r),l=new Float32Array(n*s*2),c=new Float64Array(n*s*3);let u=0,f=0;for(let d=0;d<n;d++){const g=d/(n-1);for(let h=0;h<s;h++){const p=h/(s-1),v=tr(o,g,p);c[u*3+0]=v[0],c[u*3+1]=v[1],c[u*3+2]=v[2]||0,l[u*2+0]=g,l[u*2+1]=1-p,d>0&&h>0&&(a[f++]=u-s,a[f++]=u-s-1,a[f++]=u-1,a[f++]=u-s,a[f++]=u-1,a[f++]=u),u++}}return{vertexCount:r,positions:c,indices:a,texCoords:l}}function Qs(o){const t=new Float64Array(12);for(let e=0;e<o.length;e++)t[e*3+0]=o[e][0],t[e*3+1]=o[e][1],t[e*3+2]=o[e][2]||0;return{vertexCount:6,positions:t,indices:Xs,texCoords:qs}}function tr(o,t,e){return St(St(o[0],o[1],e),St(o[3],o[2],e),t)}const Ye=`layout(std140) uniform bitmapUniforms {
  vec4 bounds;
  float coordinateConversion;
  float desaturate;
  vec3 tintColor;
  vec4 transparentColor;
} bitmap;
`,er={name:"bitmap",vs:Ye,fs:Ye,uniformTypes:{bounds:"vec4<f32>",coordinateConversion:"f32",desaturate:"f32",tintColor:"vec3<f32>",transparentColor:"vec4<f32>"}},ir=`#version 300 es
#define SHADER_NAME bitmap-layer-vertex-shader

in vec2 texCoords;
in vec3 positions;
in vec3 positions64Low;

out vec2 vTexCoord;
out vec2 vTexPos;

const vec3 pickingColor = vec3(1.0, 0.0, 0.0);

void main(void) {
  geometry.worldPosition = positions;
  geometry.uv = texCoords;
  geometry.pickingColor = pickingColor;

  gl_Position = project_position_to_clipspace(positions, positions64Low, vec3(0.0), geometry.position);
  DECKGL_FILTER_GL_POSITION(gl_Position, geometry);

  vTexCoord = texCoords;

  if (bitmap.coordinateConversion < -0.5) {
    vTexPos = geometry.position.xy + project.commonOrigin.xy;
  } else if (bitmap.coordinateConversion > 0.5) {
    vTexPos = geometry.worldPosition.xy;
  }

  vec4 color = vec4(0.0);
  DECKGL_FILTER_COLOR(color, geometry);
}
`,or=`
vec3 packUVsIntoRGB(vec2 uv) {
  // Extract the top 8 bits. We want values to be truncated down so we can add a fraction
  vec2 uv8bit = floor(uv * 256.);

  // Calculate the normalized remainders of u and v parts that do not fit into 8 bits
  // Scale and clamp to 0-1 range
  vec2 uvFraction = fract(uv * 256.);
  vec2 uvFraction4bit = floor(uvFraction * 16.);

  // Remainder can be encoded in blue channel, encode as 4 bits for pixel coordinates
  float fractions = uvFraction4bit.x + uvFraction4bit.y * 16.;

  return vec3(uv8bit, fractions) / 255.;
}
`,nr=`#version 300 es
#define SHADER_NAME bitmap-layer-fragment-shader

#ifdef GL_ES
precision highp float;
#endif

uniform sampler2D bitmapTexture;

in vec2 vTexCoord;
in vec2 vTexPos;

out vec4 fragColor;

/* projection utils */
const float TILE_SIZE = 512.0;
const float PI = 3.1415926536;
const float WORLD_SCALE = TILE_SIZE / PI / 2.0;

// from degrees to Web Mercator
vec2 lnglat_to_mercator(vec2 lnglat) {
  float x = lnglat.x;
  float y = clamp(lnglat.y, -89.9, 89.9);
  return vec2(
    radians(x) + PI,
    PI + log(tan(PI * 0.25 + radians(y) * 0.5))
  ) * WORLD_SCALE;
}

// from Web Mercator to degrees
vec2 mercator_to_lnglat(vec2 xy) {
  xy /= WORLD_SCALE;
  return degrees(vec2(
    xy.x - PI,
    atan(exp(xy.y - PI)) * 2.0 - PI * 0.5
  ));
}
/* End projection utils */

// apply desaturation
vec3 color_desaturate(vec3 color) {
  float luminance = (color.r + color.g + color.b) * 0.333333333;
  return mix(color, vec3(luminance), bitmap.desaturate);
}

// apply tint
vec3 color_tint(vec3 color) {
  return color * bitmap.tintColor;
}

// blend with background color
vec4 apply_opacity(vec3 color, float alpha) {
  if (bitmap.transparentColor.a == 0.0) {
    return vec4(color, alpha);
  }
  float blendedAlpha = alpha + bitmap.transparentColor.a * (1.0 - alpha);
  float highLightRatio = alpha / blendedAlpha;
  vec3 blendedRGB = mix(bitmap.transparentColor.rgb, color, highLightRatio);
  return vec4(blendedRGB, blendedAlpha);
}

vec2 getUV(vec2 pos) {
  return vec2(
    (pos.x - bitmap.bounds[0]) / (bitmap.bounds[2] - bitmap.bounds[0]),
    (pos.y - bitmap.bounds[3]) / (bitmap.bounds[1] - bitmap.bounds[3])
  );
}

${or}

void main(void) {
  vec2 uv = vTexCoord;
  if (bitmap.coordinateConversion < -0.5) {
    vec2 lnglat = mercator_to_lnglat(vTexPos);
    uv = getUV(lnglat);
  } else if (bitmap.coordinateConversion > 0.5) {
    vec2 commonPos = lnglat_to_mercator(vTexPos);
    uv = getUV(commonPos);
  }
  vec4 bitmapColor = texture(bitmapTexture, uv);

  fragColor = apply_opacity(color_tint(color_desaturate(bitmapColor.rgb)), bitmapColor.a * layer.opacity);

  geometry.uv = uv;
  DECKGL_FILTER_COLOR(fragColor, geometry);

  if (bool(picking.isActive) && !bool(picking.isAttribute)) {
    // Since instance information is not used, we can use picking color for pixel index
    fragColor.rgb = packUVsIntoRGB(uv);
  }
}
`,sr={image:{type:"image",value:null,async:!0},bounds:{type:"array",value:[1,0,0,1],compare:!0},_imageCoordinateSystem:"default",desaturate:{type:"number",min:0,max:1,value:0},transparentColor:{type:"color",value:[0,0,0,0]},tintColor:{type:"color",value:[255,255,255]},textureParameters:{type:"object",ignore:!0,value:null}};class Qi extends k{getShaders(){return super.getShaders({vs:ir,fs:nr,modules:[G,j,er]})}initializeState(){const t=this.getAttributeManager();t.remove(["instancePickingColors"]);const e=!0;t.add({indices:{size:1,isIndexed:!0,update:i=>i.value=this.state.mesh.indices,noAlloc:e},positions:{size:3,type:"float64",fp64:this.use64bitPositions(),update:i=>i.value=this.state.mesh.positions,noAlloc:e},texCoords:{size:2,update:i=>i.value=this.state.mesh.texCoords,noAlloc:e}})}updateState({props:t,oldProps:e,changeFlags:i}){var s;const n=this.getAttributeManager();if(i.extensionsChanged&&((s=this.state.model)==null||s.destroy(),this.state.model=this._getModel(),n.invalidateAll()),t.bounds!==e.bounds){const r=this.state.mesh,a=this._createMesh();this.state.model.setVertexCount(a.vertexCount);for(const l in a)r&&r[l]!==a[l]&&n.invalidate(l);this.setState({mesh:a,...this._getCoordinateUniforms()})}else t._imageCoordinateSystem!==e._imageCoordinateSystem&&this.setState(this._getCoordinateUniforms())}getPickingInfo(t){const{image:e}=this.props,i=t.info;if(!i.color||!e)return i.bitmap=null,i;const{width:n,height:s}=e;i.index=0;const r=rr(i.color);return i.bitmap={size:{width:n,height:s},uv:r,pixel:[Math.floor(r[0]*n),Math.floor(r[1]*s)]},i}disablePickingIndex(){this.setState({disablePicking:!0})}restorePickingColors(){this.setState({disablePicking:!1})}_updateAutoHighlight(t){super._updateAutoHighlight({...t,color:this.encodePickingColor(0)})}_createMesh(){const{bounds:t}=this.props;let e=t;return Ze(t)&&(e=[[t[0],t[1]],[t[0],t[3]],[t[2],t[3]],[t[2],t[1]]]),Js(e,this.context.viewport.resolution)}_getModel(){return new M(this.context.device,{...this.getShaders(),id:this.props.id,bufferLayout:this.getAttributeManager().getBufferLayouts(),topology:"triangle-list",isInstanced:!1})}draw(t){const{shaderModuleProps:e}=t,{model:i,coordinateConversion:n,bounds:s,disablePicking:r}=this.state,{image:a,desaturate:l,transparentColor:c,tintColor:u}=this.props;if(!(e.picking.isActive&&r)&&a&&i){const f={bitmapTexture:a,bounds:s,coordinateConversion:n,desaturate:l,tintColor:u.slice(0,3).map(d=>d/255),transparentColor:c.map(d=>d/255)};i.shaderInputs.setProps({bitmap:f}),i.draw(this.context.renderPass)}}_getCoordinateUniforms(){let{_imageCoordinateSystem:t}=this.props;if(t!=="default"){const{bounds:e}=this.props;if(!Ze(e))throw new Error("_imageCoordinateSystem only supports rectangular bounds");const i=this.context.viewport.resolution?"lnglat":"cartesian";if(t=t==="lnglat"?"lnglat":"cartesian",t==="lnglat"&&i==="cartesian")return{coordinateConversion:-1,bounds:e};if(t==="cartesian"&&i==="lnglat"){const n=Me([e[0],e[1]]),s=Me([e[2],e[3]]);return{coordinateConversion:1,bounds:[n[0],n[1],s[0],s[1]]}}}return{coordinateConversion:0,bounds:[0,0,0,0]}}}Qi.layerName="BitmapLayer";Qi.defaultProps=sr;function rr(o){const[t,e,i]=o,n=(i&240)/256,s=(i&15)/16;return[(t+s)/256,(e+n)/256]}function Ze(o){return Number.isFinite(o[0])}const Ke=`layout(std140) uniform iconUniforms {
  float sizeScale;
  vec2 iconsTextureDim;
  float sizeBasis;
  float sizeMinPixels;
  float sizeMaxPixels;
  bool billboard;
  highp int sizeUnits;
  float alphaCutoff;
} icon;
`,ar={name:"icon",vs:Ke,fs:Ke,uniformTypes:{sizeScale:"f32",iconsTextureDim:"vec2<f32>",sizeBasis:"f32",sizeMinPixels:"f32",sizeMaxPixels:"f32",billboard:"f32",sizeUnits:"i32",alphaCutoff:"f32"}},lr=`#version 300 es
#define SHADER_NAME icon-layer-vertex-shader
in vec2 positions;
in vec3 instancePositions;
in vec3 instancePositions64Low;
in float instanceSizes;
in float instanceAngles;
in vec4 instanceColors;
in vec3 instancePickingColors;
in vec4 instanceIconFrames;
in float instanceColorModes;
in vec2 instanceOffsets;
in vec2 instancePixelOffset;
out float vColorMode;
out vec4 vColor;
out vec2 vTextureCoords;
out vec2 uv;
vec2 rotate_by_angle(vec2 vertex, float angle) {
float angle_radian = angle * PI / 180.0;
float cos_angle = cos(angle_radian);
float sin_angle = sin(angle_radian);
mat2 rotationMatrix = mat2(cos_angle, -sin_angle, sin_angle, cos_angle);
return rotationMatrix * vertex;
}
void main(void) {
geometry.worldPosition = instancePositions;
geometry.uv = positions;
geometry.pickingColor = instancePickingColors;
uv = positions;
vec2 iconSize = instanceIconFrames.zw;
float sizePixels = clamp(
project_size_to_pixel(instanceSizes * icon.sizeScale, icon.sizeUnits),
icon.sizeMinPixels, icon.sizeMaxPixels
);
float iconConstraint = icon.sizeBasis == 0.0 ? iconSize.x : iconSize.y;
float instanceScale = iconConstraint == 0.0 ? 0.0 : sizePixels / iconConstraint;
vec2 pixelOffset = positions / 2.0 * iconSize + instanceOffsets;
pixelOffset = rotate_by_angle(pixelOffset, instanceAngles) * instanceScale;
pixelOffset += instancePixelOffset;
pixelOffset.y *= -1.0;
if (icon.billboard)  {
gl_Position = project_position_to_clipspace(instancePositions, instancePositions64Low, vec3(0.0), geometry.position);
DECKGL_FILTER_GL_POSITION(gl_Position, geometry);
vec3 offset = vec3(pixelOffset, 0.0);
DECKGL_FILTER_SIZE(offset, geometry);
gl_Position.xy += project_pixel_size_to_clipspace(offset.xy);
} else {
vec3 offset_common = vec3(project_pixel_size(pixelOffset), 0.0);
DECKGL_FILTER_SIZE(offset_common, geometry);
gl_Position = project_position_to_clipspace(instancePositions, instancePositions64Low, offset_common, geometry.position);
DECKGL_FILTER_GL_POSITION(gl_Position, geometry);
}
vTextureCoords = mix(
instanceIconFrames.xy,
instanceIconFrames.xy + iconSize,
(positions.xy + 1.0) / 2.0
) / icon.iconsTextureDim;
vColor = instanceColors;
DECKGL_FILTER_COLOR(vColor, geometry);
vColorMode = instanceColorModes;
}
`,cr=`#version 300 es
#define SHADER_NAME icon-layer-fragment-shader
precision highp float;
uniform sampler2D iconsTexture;
in float vColorMode;
in vec4 vColor;
in vec2 vTextureCoords;
in vec2 uv;
out vec4 fragColor;
void main(void) {
geometry.uv = uv;
vec4 texColor = texture(iconsTexture, vTextureCoords);
vec3 color = mix(texColor.rgb, vColor.rgb, vColorMode);
float a = texColor.a * layer.opacity * vColor.a;
if (a < icon.alphaCutoff) {
discard;
}
fragColor = vec4(color, a);
DECKGL_FILTER_COLOR(fragColor, geometry);
}
`,ur=`struct IconUniforms {
  sizeScale: f32,
  iconsTextureDim: vec2<f32>,
  sizeBasis: f32,
  sizeMinPixels: f32,
  sizeMaxPixels: f32,
  billboard: i32,
  sizeUnits: i32,
  alphaCutoff: f32
};

@group(0) @binding(auto) var<uniform> icon: IconUniforms;
@group(0) @binding(auto) var iconsTexture : texture_2d<f32>;
@group(0) @binding(auto) var iconsTextureSampler : sampler;

fn rotate_by_angle(vertex: vec2<f32>, angle_deg: f32) -> vec2<f32> {
  let angle_radian = angle_deg * PI / 180.0;
  let c = cos(angle_radian);
  let s = sin(angle_radian);
  let rotation = mat2x2<f32>(vec2<f32>(c, s), vec2<f32>(-s, c));
  return rotation * vertex;
}

struct Attributes {
  @location(0) positions: vec2<f32>,

  @location(1) instancePositions: vec3<f32>,
  @location(2) instancePositions64Low: vec3<f32>,
  @location(3) instanceSizes: f32,
  @location(4) instanceAngles: f32,
  @location(5) instanceColors: vec4<f32>,
  @location(6) instancePickingColors: vec3<f32>,
  @location(7) instanceIconFrames: vec4<f32>,
  @location(8) instanceColorModes: f32,
  @location(9) instanceOffsets: vec2<f32>,
  @location(10) instancePixelOffset: vec2<f32>,
};

struct Varyings {
  @builtin(position) position: vec4<f32>,

  @location(0) vColorMode: f32,
  @location(1) vColor: vec4<f32>,
  @location(2) vTextureCoords: vec2<f32>,
  @location(3) uv: vec2<f32>,
  @location(4) pickingColor: vec3<f32>,
};

@vertex
fn vertexMain(inp: Attributes) -> Varyings {
  // write geometry fields used by filters + FS
  geometry.worldPosition = inp.instancePositions;
  geometry.uv = inp.positions;
  geometry.pickingColor = inp.instancePickingColors;

  var outp: Varyings;
  outp.uv = inp.positions;

  let iconSize = inp.instanceIconFrames.zw;

  // convert size in meters to pixels, then clamp
  let sizePixels = clamp(
    project_unit_size_to_pixel(inp.instanceSizes * icon.sizeScale, icon.sizeUnits),
    icon.sizeMinPixels, icon.sizeMaxPixels
  );

  // scale icon height to match instanceSize
  let iconConstraint = select(iconSize.y, iconSize.x, icon.sizeBasis == 0.0);
  let instanceScale = select(sizePixels / iconConstraint, 0.0, iconConstraint == 0.0);

  // scale and rotate vertex in "pixel" units; then add per-instance pixel offset
  var pixelOffset = inp.positions / 2.0 * iconSize + inp.instanceOffsets;
  pixelOffset = rotate_by_angle(pixelOffset, inp.instanceAngles) * instanceScale;
  pixelOffset = pixelOffset + inp.instancePixelOffset;
  pixelOffset.y = pixelOffset.y * -1.0;

  if (icon.billboard != 0) {
    var pos = project_position_to_clipspace(inp.instancePositions, inp.instancePositions64Low, vec3<f32>(0.0)); // TODO, &geometry.position);
    // DECKGL_FILTER_GL_POSITION(pos, geometry);

    var offset = vec3<f32>(pixelOffset, 0.0);
    // DECKGL_FILTER_SIZE(offset, geometry);
    let clipOffset = project_pixel_size_to_clipspace(offset.xy);
    pos = vec4<f32>(pos.x + clipOffset.x, pos.y + clipOffset.y, pos.z, pos.w);
    outp.position = pos;
  } else {
    var offset_common = vec3<f32>(project_pixel_size_vec2(pixelOffset), 0.0);
    // DECKGL_FILTER_SIZE(offset_common, geometry);
    var pos = project_position_to_clipspace(inp.instancePositions, inp.instancePositions64Low, offset_common); // TODO, &geometry.position);
    // DECKGL_FILTER_GL_POSITION(pos, geometry);
    outp.position = pos;
  }

  let uvMix = (inp.positions.xy + vec2<f32>(1.0, 1.0)) * 0.5;
  outp.vTextureCoords = mix(inp.instanceIconFrames.xy, inp.instanceIconFrames.xy + iconSize, uvMix) / icon.iconsTextureDim;

  outp.vColor = inp.instanceColors;
  // DECKGL_FILTER_COLOR(outp.vColor, geometry);

  outp.vColorMode = inp.instanceColorModes;
  outp.pickingColor = inp.instancePickingColors;

  return outp;
}

@fragment
fn fragmentMain(inp: Varyings) -> @location(0) vec4<f32> {
  // expose to deck.gl filter hooks
  geometry.uv = inp.uv;

  let texColor = textureSample(iconsTexture, iconsTextureSampler, inp.vTextureCoords);

  // if colorMode == 0, use pixel color from the texture
  // if colorMode == 1 (or picking), use texture as transparency mask
  let rgb = mix(texColor.rgb, inp.vColor.rgb, inp.vColorMode);
  let a = texColor.a * layer.opacity * inp.vColor.a;

  if (a < icon.alphaCutoff) {
    discard;
  }

  if (picking.isActive > 0.5) {
    if (!picking_isColorValid(inp.pickingColor)) {
      discard;
    }
    return vec4<f32>(inp.pickingColor, 1.0);
  }

  var fragColor = deckgl_premultiplied_alpha(vec4<f32>(rgb, a));

  if (picking.isHighlightActive > 0.5) {
    let highlightedObjectColor = picking_normalizeColor(picking.highlightedObjectColor);
    if (picking_isColorZero(abs(inp.pickingColor - highlightedObjectColor))) {
      let highLightAlpha = picking.highlightColor.a;
      let blendedAlpha = highLightAlpha + fragColor.a * (1.0 - highLightAlpha);
      if (blendedAlpha > 0.0) {
        let highLightRatio = highLightAlpha / blendedAlpha;
        fragColor = vec4<f32>(
          mix(fragColor.rgb, picking.highlightColor.rgb, highLightRatio),
          blendedAlpha
        );
      } else {
        fragColor = vec4<f32>(fragColor.rgb, 0.0);
      }
    }
  }

  return fragColor;
}
`,fr=1024,dr=4,Xe=()=>{},qe={minFilter:"linear",mipmapFilter:"linear",magFilter:"linear",addressModeU:"clamp-to-edge",addressModeV:"clamp-to-edge"},gr={x:0,y:0,width:0,height:0};function hr(o){return Math.pow(2,Math.ceil(Math.log2(o)))}function pr(o,t,e,i){const n=Math.min(e/t.width,i/t.height),s=Math.floor(t.width*n),r=Math.floor(t.height*n);return n===1?{image:t,width:s,height:r}:(o.canvas.height=r,o.canvas.width=s,o.clearRect(0,0,s,r),o.drawImage(t,0,0,t.width,t.height,0,0,s,r),{image:o.canvas,width:s,height:r})}function ft(o){return o&&(o.id||o.url)}function to(o){const{device:t}=o;t.type==="webgl"?o.generateMipmapsWebGL():t.type==="webgpu"&&t.generateMipmapsWebGPU(o)}function vr(o,t,e,i){const{width:n,height:s,device:r}=o,a=r.createTexture({format:"rgba8unorm",width:t,height:e,sampler:i,mipLevels:r.getMipLevelCount(t,e)}),l=r.createCommandEncoder();l.copyTextureToTexture({sourceTexture:o,destinationTexture:a,width:n,height:s});const c=l.finish();return r.submit(c),to(a),o.destroy(),a}function Je(o,t,e){for(let i=0;i<t.length;i++){const{icon:n,xOffset:s}=t[i],r=ft(n);o[r]={...n,x:s,y:e}}}function mr({icons:o,buffer:t,mapping:e={},xOffset:i=0,yOffset:n=0,rowHeight:s=0,canvasWidth:r}){let a=[];for(let l=0;l<o.length;l++){const c=o[l],u=ft(c);if(!e[u]){const{height:f,width:d}=c;i+d+t>r&&(Je(e,a,n),i=0,n=s+n+t,s=0,a=[]),a.push({icon:c,xOffset:i}),i=i+d+t,s=Math.max(s,f)}}return a.length>0&&Je(e,a,n),{mapping:e,rowHeight:s,xOffset:i,yOffset:n,canvasWidth:r,canvasHeight:hr(s+n+t)}}function yr(o,t,e){if(!o||!t)return null;e=e||{};const i={},{iterable:n,objectInfo:s}=it(o);for(const r of n){s.index++;const a=t(r,s),l=ft(a);if(!a)throw new Error("Icon is missing.");if(!a.url)throw new Error("Icon url is missing.");!i[l]&&(!e[l]||a.url!==e[l].url)&&(i[l]={...a,source:r,sourceIndex:s.index})}return i}class xr{constructor(t,{onUpdate:e=Xe,onError:i=Xe}){this._loadOptions=null,this._texture=null,this._externalTexture=null,this._mapping={},this._samplerParameters=null,this._pendingCount=0,this._autoPacking=!1,this._xOffset=0,this._yOffset=0,this._rowHeight=0,this._buffer=dr,this._canvasWidth=fr,this._canvasHeight=0,this._canvas=null,this.device=t,this.onUpdate=e,this.onError=i}finalize(){var t;(t=this._texture)==null||t.delete()}getTexture(){return this._texture||this._externalTexture}getIconMapping(t){const e=this._autoPacking?ft(t):t;return this._mapping[e]||gr}setProps({loadOptions:t,autoPacking:e,iconAtlas:i,iconMapping:n,textureParameters:s}){var r;t&&(this._loadOptions=t),e!==void 0&&(this._autoPacking=e),n&&(this._mapping=n),i&&((r=this._texture)==null||r.delete(),this._texture=null,this._externalTexture=i),s&&(this._samplerParameters=s)}get isLoaded(){return this._pendingCount===0}packIcons(t,e){if(!this._autoPacking||typeof document>"u")return;const i=Object.values(yr(t,e,this._mapping)||{});if(i.length>0){const{mapping:n,xOffset:s,yOffset:r,rowHeight:a,canvasHeight:l}=mr({icons:i,buffer:this._buffer,canvasWidth:this._canvasWidth,mapping:this._mapping,rowHeight:this._rowHeight,xOffset:this._xOffset,yOffset:this._yOffset});this._rowHeight=a,this._mapping=n,this._xOffset=s,this._yOffset=r,this._canvasHeight=l,this._texture||(this._texture=this.device.createTexture({format:"rgba8unorm",data:null,width:this._canvasWidth,height:this._canvasHeight,sampler:this._samplerParameters||qe,mipLevels:this.device.getMipLevelCount(this._canvasWidth,this._canvasHeight)})),this._texture.height!==this._canvasHeight&&(this._texture=vr(this._texture,this._canvasWidth,this._canvasHeight,this._samplerParameters||qe)),this.onUpdate(!0),this._canvas=this._canvas||document.createElement("canvas"),this._loadIcons(i)}}_loadIcons(t){const e=this._canvas.getContext("2d",{willReadFrequently:!0});for(const i of t)this._pendingCount++,se(i.url,this._loadOptions).then(n=>{var v;const s=ft(i),r=this._mapping[s],{x:a,y:l,width:c,height:u}=r,{image:f,width:d,height:g}=pr(e,n,c,u),h=a+(c-d)/2,p=l+(u-g)/2;(v=this._texture)==null||v.copyExternalImage({image:f,x:h,y:p,width:d,height:g}),r.x=h,r.y=p,r.width=d,r.height=g,this._texture&&to(this._texture),this.onUpdate(d!==c||g!==u)}).catch(n=>{this.onError({url:i.url,source:i.source,sourceIndex:i.sourceIndex,loadOptions:this._loadOptions,error:n})}).finally(()=>{this._pendingCount--})}}const eo=[0,0,0,255],_r={iconAtlas:{type:"image",value:null,async:!0},iconMapping:{type:"object",value:{},async:!0},sizeScale:{type:"number",value:1,min:0},billboard:!0,sizeUnits:"pixels",sizeBasis:"height",sizeMinPixels:{type:"number",min:0,value:0},sizeMaxPixels:{type:"number",min:0,value:Number.MAX_SAFE_INTEGER},alphaCutoff:{type:"number",value:.05,min:0,max:1},getPosition:{type:"accessor",value:o=>o.position},getIcon:{type:"accessor",value:o=>o.icon},getColor:{type:"accessor",value:eo},getSize:{type:"accessor",value:1},getAngle:{type:"accessor",value:0},getPixelOffset:{type:"accessor",value:[0,0]},onIconError:{type:"function",value:null,optional:!0},textureParameters:{type:"object",ignore:!0,value:null}};class Vt extends k{getShaders(){return super.getShaders({vs:lr,fs:cr,source:ur,modules:[G,ye,j,ar]})}initializeState(){this.state={iconManager:new xr(this.context.device,{onUpdate:this._onUpdate.bind(this),onError:this._onError.bind(this)})},this.getAttributeManager().addInstanced({instancePositions:{size:3,type:"float64",fp64:this.use64bitPositions(),transition:!0,accessor:"getPosition"},instanceSizes:{size:1,transition:!0,accessor:"getSize",defaultValue:1},instanceIconDefs:{size:7,accessor:"getIcon",transform:this.getInstanceIconDef,shaderAttributes:{instanceOffsets:{size:2,elementOffset:0},instanceIconFrames:{size:4,elementOffset:2},instanceColorModes:{size:1,elementOffset:6}}},instanceColors:{size:this.props.colorFormat.length,type:"unorm8",transition:!0,accessor:"getColor",defaultValue:eo},instanceAngles:{size:1,transition:!0,accessor:"getAngle"},instancePixelOffset:{size:2,transition:!0,accessor:"getPixelOffset"}})}updateState(t){var g;super.updateState(t);const{props:e,oldProps:i,changeFlags:n}=t,s=this.getAttributeManager(),{iconAtlas:r,iconMapping:a,data:l,getIcon:c,textureParameters:u}=e,{iconManager:f}=this.state;if(typeof r=="string")return;const d=r||this.internalState.isAsyncPropLoading("iconAtlas");f.setProps({loadOptions:e.loadOptions,autoPacking:!d,iconAtlas:r,iconMapping:d?a:null,textureParameters:u}),d?i.iconMapping!==e.iconMapping&&s.invalidate("getIcon"):(n.dataChanged||n.updateTriggersChanged&&(n.updateTriggersChanged.all||n.updateTriggersChanged.getIcon))&&f.packIcons(l,c),n.extensionsChanged&&((g=this.state.model)==null||g.destroy(),this.state.model=this._getModel(),s.invalidateAll())}get isLoaded(){return super.isLoaded&&this.state.iconManager.isLoaded}finalizeState(t){super.finalizeState(t),this.state.iconManager.finalize()}draw({uniforms:t}){const{sizeScale:e,sizeBasis:i,sizeMinPixels:n,sizeMaxPixels:s,sizeUnits:r,billboard:a,alphaCutoff:l}=this.props,{iconManager:c}=this.state,u=c.getTexture();if(u){const f=this.state.model,d={iconsTexture:u,iconsTextureDim:[u.width,u.height],sizeUnits:D[r],sizeScale:e,sizeBasis:i==="height"?1:0,sizeMinPixels:n,sizeMaxPixels:s,billboard:a,alphaCutoff:l};f.shaderInputs.setProps({icon:d}),f.draw(this.context.renderPass)}}_getModel(){const t=[-1,-1,1,-1,-1,1,1,1];return new M(this.context.device,{...this.getShaders(),id:this.props.id,bufferLayout:this.getAttributeManager().getBufferLayouts(),geometry:new N({topology:"triangle-strip",attributes:{positions:{size:2,value:new Float32Array(t)}}}),isInstanced:!0})}_onUpdate(t){var e;t?((e=this.getAttributeManager())==null||e.invalidate("getIcon"),this.setNeedsUpdate()):this.setNeedsRedraw()}_onError(t){var i;const e=(i=this.getCurrentLayer())==null?void 0:i.props.onIconError;e?e(t):S.error(t.error.message)()}getInstanceIconDef(t){const{x:e,y:i,width:n,height:s,mask:r,anchorX:a=n/2,anchorY:l=s/2}=this.state.iconManager.getIconMapping(t);return[n/2-a,s/2-l,e,i,n,s,r?1:0]}}Vt.defaultProps=_r;Vt.layerName="IconLayer";const Qe=`layout(std140) uniform pointCloudUniforms {
  float radiusPixels;
  highp int sizeUnits;
} pointCloud;
`,Cr={name:"pointCloud",source:"",vs:Qe,fs:Qe,uniformTypes:{radiusPixels:"f32",sizeUnits:"i32"}},Pr=`#version 300 es
#define SHADER_NAME point-cloud-layer-vertex-shader
in vec3 positions;
in vec3 instanceNormals;
in vec4 instanceColors;
in vec3 instancePositions;
in vec3 instancePositions64Low;
in vec3 instancePickingColors;
out vec4 vColor;
out vec2 unitPosition;
void main(void) {
geometry.worldPosition = instancePositions;
geometry.normal = project_normal(instanceNormals);
unitPosition = positions.xy;
geometry.uv = unitPosition;
geometry.pickingColor = instancePickingColors;
vec3 offset = vec3(positions.xy * project_size_to_pixel(pointCloud.radiusPixels, pointCloud.sizeUnits), 0.0);
DECKGL_FILTER_SIZE(offset, geometry);
gl_Position = project_position_to_clipspace(instancePositions, instancePositions64Low, vec3(0.), geometry.position);
DECKGL_FILTER_GL_POSITION(gl_Position, geometry);
gl_Position.xy += project_pixel_size_to_clipspace(offset.xy);
vec3 lightColor = lighting_getLightColor(instanceColors.rgb, project.cameraPosition, geometry.position.xyz, geometry.normal);
vColor = vec4(lightColor, instanceColors.a * layer.opacity);
DECKGL_FILTER_COLOR(vColor, geometry);
}
`,br=`#version 300 es
#define SHADER_NAME point-cloud-layer-fragment-shader
precision highp float;
in vec4 vColor;
in vec2 unitPosition;
out vec4 fragColor;
void main(void) {
geometry.uv = unitPosition.xy;
float distToCenter = length(unitPosition);
if (distToCenter > 1.0) {
discard;
}
fragColor = vColor;
DECKGL_FILTER_COLOR(fragColor, geometry);
}
`,Lr=`struct PointCloudUniforms {
  radiusPixels: f32,
  sizeUnits: i32,
};

@group(0) @binding(0)
var<uniform> pointCloudUniforms: PointCloudUniforms;

struct ConstantAttributes {
  instanceNormals: vec3<f32>,
  instanceColors: vec4<f32>,
  instancePositions: vec3<f32>,
  instancePositions64Low: vec3<f32>,
  instancePickingColors: vec3<f32>
};

const constants = ConstantAttributes(
  vec3<f32>(1.0, 0.0, 0.0),
  vec4<f32>(0.0, 0.0, 0.0, 1.0),
  vec3<f32>(0.0),
  vec3<f32>(0.0),
  vec3<f32>(0.0)
);

struct Attributes {
  @builtin(instance_index) instanceIndex : u32,
  @builtin(vertex_index) vertexIndex : u32,
  @location(0) positions: vec3<f32>,
  @location(1) instancePositions: vec3<f32>,
  @location(2) instancePositions64Low: vec3<f32>,
  @location(3) instanceNormals: vec3<f32>,
  @location(4) instanceColors: vec4<f32>,
  @location(5) instancePickingColors: vec3<f32>
};

struct Varyings {
  @builtin(position) position: vec4<f32>,
  @location(0) vColor: vec4<f32>,
  @location(1) unitPosition: vec2<f32>,
  @location(2) pickingColor: vec3<f32>,
};

@vertex
fn vertexMain(attributes: Attributes) -> Varyings {
  var varyings: Varyings;

  geometry.worldPosition = attributes.instancePositions;

  let centerResult = project_position_to_clipspace_and_commonspace(
    attributes.instancePositions,
    attributes.instancePositions64Low,
    vec3<f32>(0.0)
  );
  geometry.position = centerResult.commonPosition;
  geometry.normal = project_normal(attributes.instanceNormals);

  // position on the containing square in [-1, 1] space
  varyings.unitPosition = attributes.positions.xy;
  geometry.uv = varyings.unitPosition;
  geometry.pickingColor = attributes.instancePickingColors;

  // Find the center of the point and add the current vertex
  let offset = vec3<f32>(
    attributes.positions.xy *
      project_unit_size_to_pixel(pointCloudUniforms.radiusPixels, pointCloudUniforms.sizeUnits),
    0.0
  );
  // DECKGL_FILTER_SIZE(offset, geometry);

  varyings.position = centerResult.clipPosition;
  // DECKGL_FILTER_GL_POSITION(gl_Position, geometry);
  let clipPixels = project_pixel_size_to_clipspace(offset.xy);
  varyings.position.x += clipPixels.x;
  varyings.position.y += clipPixels.y;

  // Apply lighting
  let lightColor = lighting_getLightColor2(attributes.instanceColors.rgb, project.cameraPosition, geometry.position.xyz, geometry.normal);

  // Apply opacity to instance color, or return instance picking color
  varyings.vColor = vec4(lightColor, attributes.instanceColors.a * layer.opacity);
  // DECKGL_FILTER_COLOR(vColor, geometry);
  varyings.pickingColor = attributes.instancePickingColors;

  return varyings;
}

@fragment
fn fragmentMain(varyings: Varyings) -> @location(0) vec4<f32> {
  // var geometry: Geometry;
  // geometry.uv = unitPosition.xy;

  let distToCenter = length(varyings.unitPosition);
  if (distToCenter > 1.0) {
    discard;
  }

  var fragColor: vec4<f32>;

  fragColor = varyings.vColor;

  if (picking.isActive > 0.5) {
    if (!picking_isColorValid(varyings.pickingColor)) {
      discard;
    }
    return vec4<f32>(varyings.pickingColor, 1.0);
  }

  if (picking.isHighlightActive > 0.5) {
    let highlightedObjectColor = picking_normalizeColor(picking.highlightedObjectColor);
    if (picking_isColorZero(abs(varyings.pickingColor - highlightedObjectColor))) {
      let highLightAlpha = picking.highlightColor.a;
      let blendedAlpha = highLightAlpha + fragColor.a * (1.0 - highLightAlpha);
      if (blendedAlpha > 0.0) {
        let highLightRatio = highLightAlpha / blendedAlpha;
        fragColor = vec4<f32>(
          mix(fragColor.rgb, picking.highlightColor.rgb, highLightRatio),
          blendedAlpha
        );
      } else {
        fragColor = vec4<f32>(fragColor.rgb, 0.0);
      }
    }
  }

  // Apply premultiplied alpha as required by transparent canvas
  fragColor = deckgl_premultiplied_alpha(fragColor);

  return fragColor;
}
`,io=[0,0,0,255],oo=[0,0,1],Ar={sizeUnits:"pixels",pointSize:{type:"number",min:0,value:10},getPosition:{type:"accessor",value:o=>o.position},getNormal:{type:"accessor",value:oo},getColor:{type:"accessor",value:io},material:!0,radiusPixels:{deprecatedFor:"pointSize"}};function Sr(o){const{header:t,attributes:e}=o;if(!(!t||!e)&&(o.length=t.vertexCount,e.POSITION&&(e.instancePositions=e.POSITION),e.NORMAL&&(e.instanceNormals=e.NORMAL),e.COLOR_0)){const{size:i,value:n}=e.COLOR_0;e.instanceColors={size:i,type:"unorm8",value:n}}}class no extends k{getShaders(){return super.getShaders({vs:Pr,fs:br,source:Lr,modules:[G,ye,Nt,j,Cr]})}initializeState(){this.getAttributeManager().addInstanced({instancePositions:{size:3,type:"float64",fp64:this.use64bitPositions(),transition:!0,accessor:"getPosition"},instanceNormals:{size:3,transition:!0,accessor:"getNormal",defaultValue:oo},instanceColors:{size:this.props.colorFormat.length,type:"unorm8",transition:!0,accessor:"getColor",defaultValue:io}})}updateState(t){var n;const{changeFlags:e,props:i}=t;super.updateState(t),e.extensionsChanged&&((n=this.state.model)==null||n.destroy(),this.state.model=this._getModel(),this.getAttributeManager().invalidateAll()),e.dataChanged&&Sr(i.data)}draw({uniforms:t}){const{pointSize:e,sizeUnits:i}=this.props,n=this.state.model,s={sizeUnits:D[i],radiusPixels:e};n.shaderInputs.setProps({pointCloud:s}),n.draw(this.context.renderPass)}_getModel(){const t=[];for(let e=0;e<3;e++){const i=e/3*Math.PI*2;t.push(Math.cos(i)*2,Math.sin(i)*2,0)}return new M(this.context.device,{...this.getShaders(),id:this.props.id,bufferLayout:this.getAttributeManager().getBufferLayouts(),geometry:new N({topology:"triangle-list",attributes:{positions:new Float32Array(t)}}),isInstanced:!0})}}no.layerName="PointCloudLayer";no.defaultProps=Ar;const ti=`layout(std140) uniform scatterplotUniforms {
  float radiusScale;
  float radiusMinPixels;
  float radiusMaxPixels;
  float lineWidthScale;
  float lineWidthMinPixels;
  float lineWidthMaxPixels;
  float stroked;
  float filled;
  bool antialiasing;
  bool billboard;
  highp int radiusUnits;
  highp int lineWidthUnits;
} scatterplot;
`,Tr={name:"scatterplot",vs:ti,fs:ti,source:"",uniformTypes:{radiusScale:"f32",radiusMinPixels:"f32",radiusMaxPixels:"f32",lineWidthScale:"f32",lineWidthMinPixels:"f32",lineWidthMaxPixels:"f32",stroked:"f32",filled:"f32",antialiasing:"f32",billboard:"f32",radiusUnits:"i32",lineWidthUnits:"i32"}},wr=`#version 300 es
#define SHADER_NAME scatterplot-layer-vertex-shader
in vec3 positions;
in vec3 instancePositions;
in vec3 instancePositions64Low;
in float instanceRadius;
in float instanceLineWidths;
in vec4 instanceFillColors;
in vec4 instanceLineColors;
in vec3 instancePickingColors;
in vec2 instancePixelOffset;
out vec4 vFillColor;
out vec4 vLineColor;
out vec2 unitPosition;
out float innerUnitRadius;
out float outerRadiusPixels;
void main(void) {
geometry.worldPosition = instancePositions;
outerRadiusPixels = clamp(
project_size_to_pixel(scatterplot.radiusScale * instanceRadius, scatterplot.radiusUnits),
scatterplot.radiusMinPixels, scatterplot.radiusMaxPixels
);
float lineWidthPixels = clamp(
project_size_to_pixel(scatterplot.lineWidthScale * instanceLineWidths, scatterplot.lineWidthUnits),
scatterplot.lineWidthMinPixels, scatterplot.lineWidthMaxPixels
);
outerRadiusPixels += scatterplot.stroked * lineWidthPixels / 2.0;
float edgePadding = scatterplot.antialiasing ? (outerRadiusPixels + SMOOTH_EDGE_RADIUS) / outerRadiusPixels : 1.0;
unitPosition = edgePadding * positions.xy;
geometry.uv = unitPosition;
geometry.pickingColor = instancePickingColors;
innerUnitRadius = 1.0 - scatterplot.stroked * lineWidthPixels / outerRadiusPixels;
if (scatterplot.billboard) {
gl_Position = project_position_to_clipspace(instancePositions, instancePositions64Low, vec3(0.0), geometry.position);
DECKGL_FILTER_GL_POSITION(gl_Position, geometry);
vec3 offset = edgePadding * positions * outerRadiusPixels;
offset.xy += instancePixelOffset;
DECKGL_FILTER_SIZE(offset, geometry);
gl_Position.xy += project_pixel_size_to_clipspace(offset.xy);
} else {
vec3 offset = edgePadding * positions * project_pixel_size(outerRadiusPixels);
offset.xy += project_pixel_size(instancePixelOffset);
DECKGL_FILTER_SIZE(offset, geometry);
gl_Position = project_position_to_clipspace(instancePositions, instancePositions64Low, offset, geometry.position);
DECKGL_FILTER_GL_POSITION(gl_Position, geometry);
}
vFillColor = vec4(instanceFillColors.rgb, instanceFillColors.a * layer.opacity);
DECKGL_FILTER_COLOR(vFillColor, geometry);
vLineColor = vec4(instanceLineColors.rgb, instanceLineColors.a * layer.opacity);
DECKGL_FILTER_COLOR(vLineColor, geometry);
}
`,Er=`#version 300 es
#define SHADER_NAME scatterplot-layer-fragment-shader
precision highp float;
in vec4 vFillColor;
in vec4 vLineColor;
in vec2 unitPosition;
in float innerUnitRadius;
in float outerRadiusPixels;
out vec4 fragColor;
void main(void) {
geometry.uv = unitPosition;
float distToCenter = length(unitPosition) * outerRadiusPixels;
float inCircle = scatterplot.antialiasing ?
smoothedge(distToCenter, outerRadiusPixels) :
step(distToCenter, outerRadiusPixels);
if (inCircle == 0.0) {
discard;
}
if (scatterplot.stroked > 0.5) {
float isLine = scatterplot.antialiasing ?
smoothedge(innerUnitRadius * outerRadiusPixels, distToCenter) :
step(innerUnitRadius * outerRadiusPixels, distToCenter);
if (scatterplot.filled > 0.5) {
fragColor = mix(vFillColor, vLineColor, isLine);
} else {
if (isLine == 0.0) {
discard;
}
fragColor = vec4(vLineColor.rgb, vLineColor.a * isLine);
}
} else if (scatterplot.filled < 0.5) {
discard;
} else {
fragColor = vFillColor;
}
fragColor.a *= inCircle;
DECKGL_FILTER_COLOR(fragColor, geometry);
}
`,Ir=`// Main shaders

struct ScatterplotUniforms {
  radiusScale: f32,
  radiusMinPixels: f32,
  radiusMaxPixels: f32,
  lineWidthScale: f32,
  lineWidthMinPixels: f32,
  lineWidthMaxPixels: f32,
  stroked: f32,
  filled: i32,
  antialiasing: i32,
  billboard: i32,
  radiusUnits: i32,
  lineWidthUnits: i32,
};

struct ConstantAttributeUniforms {
 instancePositions: vec3<f32>,
 instancePositions64Low: vec3<f32>,
 instanceRadius: f32,
 instanceLineWidths: f32,
 instanceFillColors: vec4<f32>,
 instanceLineColors: vec4<f32>,
 instancePickingColors: vec3<f32>,
 instancePixelOffset: vec2<f32>,

 instancePositionsConstant: i32,
 instancePositions64LowConstant: i32,
 instanceRadiusConstant: i32,
 instanceLineWidthsConstant: i32,
 instanceFillColorsConstant: i32,
 instanceLineColorsConstant: i32,
 instancePickingColorsConstant: i32,
 instancePixelOffsetConstant: i32
};

@group(0) @binding(0) var<uniform> scatterplot: ScatterplotUniforms;

struct ConstantAttributes {
  instancePositions: vec3<f32>,
  instancePositions64Low: vec3<f32>,
  instanceRadius: f32,
  instanceLineWidths: f32,
  instanceFillColors: vec4<f32>,
  instanceLineColors: vec4<f32>,
  instancePickingColors: vec3<f32>,
  instancePixelOffset: vec2<f32>
};

const constants = ConstantAttributes(
  vec3<f32>(0.0),
  vec3<f32>(0.0),
  0.0,
  0.0,
  vec4<f32>(0.0, 0.0, 0.0, 1.0),
  vec4<f32>(0.0, 0.0, 0.0, 1.0),
  vec3<f32>(0.0),
  vec2<f32>(0.0)
);

struct Attributes {
  @builtin(instance_index) instanceIndex : u32,
  @builtin(vertex_index) vertexIndex : u32,
  @location(0) positions: vec3<f32>,
  @location(1) instancePositions: vec3<f32>,
  @location(2) instancePositions64Low: vec3<f32>,
  @location(3) instanceRadius: f32,
  @location(4) instanceLineWidths: f32,
  @location(5) instanceFillColors: vec4<f32>,
  @location(6) instanceLineColors: vec4<f32>,
  @location(7) instancePickingColors: vec3<f32>,
  @location(8) instancePixelOffset: vec2<f32>
};

struct Varyings {
  @builtin(position) position: vec4<f32>,
  @location(0) vFillColor: vec4<f32>,
  @location(1) vLineColor: vec4<f32>,
  @location(2) unitPosition: vec2<f32>,
  @location(3) innerUnitRadius: f32,
  @location(4) outerRadiusPixels: f32,
  @location(5) pickingColor: vec3<f32>,
};

@vertex
fn vertexMain(attributes: Attributes) -> Varyings {
  var varyings: Varyings;

  // Draw an inline geometry constant array clip space triangle to verify that rendering works.
  // var positions = array<vec2<f32>, 3>(vec2(0.0, 0.5), vec2(-0.5, -0.5), vec2(0.5, -0.5));
  // if (attributes.instanceIndex == 0) {
  //   varyings.position = vec4<f32>(positions[attributes.vertexIndex], 0.0, 1.0);
  //   return varyings;
  // }

  geometry.worldPosition = attributes.instancePositions;

  // Multiply out radius and clamp to limits
  varyings.outerRadiusPixels = clamp(
    project_unit_size_to_pixel(scatterplot.radiusScale * attributes.instanceRadius, scatterplot.radiusUnits),
    scatterplot.radiusMinPixels, scatterplot.radiusMaxPixels
  );

  // Multiply out line width and clamp to limits
  let lineWidthPixels = clamp(
    project_unit_size_to_pixel(scatterplot.lineWidthScale * attributes.instanceLineWidths, scatterplot.lineWidthUnits),
    scatterplot.lineWidthMinPixels, scatterplot.lineWidthMaxPixels
  );

  // outer radius needs to offset by half stroke width
  varyings.outerRadiusPixels += scatterplot.stroked * lineWidthPixels / 2.0;
  // Expand geometry to accommodate edge smoothing
  let edgePadding = select(
    (varyings.outerRadiusPixels + SMOOTH_EDGE_RADIUS) / varyings.outerRadiusPixels,
    1.0,
    scatterplot.antialiasing != 0
  );

  // position on the containing square in [-1, 1] space
  varyings.unitPosition = edgePadding * attributes.positions.xy;
  geometry.uv = varyings.unitPosition;
  geometry.pickingColor = attributes.instancePickingColors;

  varyings.innerUnitRadius = 1.0 - scatterplot.stroked * lineWidthPixels / varyings.outerRadiusPixels;

  if (scatterplot.billboard != 0) {
    varyings.position = project_position_to_clipspace(attributes.instancePositions, attributes.instancePositions64Low, vec3<f32>(0.0)); // TODO , geometry.position);
    // DECKGL_FILTER_GL_POSITION(varyings.position, geometry);
    var offset = edgePadding * attributes.positions * varyings.outerRadiusPixels;
    offset = vec3<f32>(offset.xy + attributes.instancePixelOffset, offset.z);
    // DECKGL_FILTER_SIZE(offset, geometry);
    let clipPixels = project_pixel_size_to_clipspace(offset.xy);
    varyings.position = vec4<f32>(varyings.position.x + clipPixels.x, varyings.position.y + clipPixels.y, varyings.position.z, varyings.position.w);
  } else {
    var offset = edgePadding * attributes.positions * project_pixel_size_float(varyings.outerRadiusPixels);
    offset = vec3<f32>(offset.xy + project_pixel_size_vec2(attributes.instancePixelOffset), offset.z);
    // DECKGL_FILTER_SIZE(offset, geometry);
    varyings.position = project_position_to_clipspace(attributes.instancePositions, attributes.instancePositions64Low, offset); // TODO , geometry.position);
    // DECKGL_FILTER_GL_POSITION(varyings.position, geometry);
  }

  // Apply opacity to instance color, or return instance picking color
  varyings.vFillColor = vec4<f32>(attributes.instanceFillColors.rgb, attributes.instanceFillColors.a * layer.opacity);
  // DECKGL_FILTER_COLOR(varyings.vFillColor, geometry);
  varyings.vLineColor = vec4<f32>(attributes.instanceLineColors.rgb, attributes.instanceLineColors.a * layer.opacity);
  // DECKGL_FILTER_COLOR(varyings.vLineColor, geometry);
  varyings.pickingColor = attributes.instancePickingColors;

  return varyings;
}

@fragment
fn fragmentMain(varyings: Varyings) -> @location(0) vec4<f32> {
  // var geometry: Geometry;
  // geometry.uv = unitPosition;

  let distToCenter = length(varyings.unitPosition) * varyings.outerRadiusPixels;
  let inCircle = select(
    smoothedge(distToCenter, varyings.outerRadiusPixels),
    step(distToCenter, varyings.outerRadiusPixels),
    scatterplot.antialiasing != 0
  );

  if (inCircle == 0.0) {
    discard;
  }

  var fragColor: vec4<f32>;

  if (scatterplot.stroked != 0) {
    let isLine = select(
      smoothedge(varyings.innerUnitRadius * varyings.outerRadiusPixels, distToCenter),
      step(varyings.innerUnitRadius * varyings.outerRadiusPixels, distToCenter),
      scatterplot.antialiasing != 0
    );

    if (scatterplot.filled != 0) {
      fragColor = mix(varyings.vFillColor, varyings.vLineColor, isLine);
    } else {
      if (isLine == 0.0) {
        discard;
      }
      fragColor = vec4<f32>(varyings.vLineColor.rgb, varyings.vLineColor.a * isLine);
    }
  } else if (scatterplot.filled == 0) {
    discard;
  } else {
    fragColor = varyings.vFillColor;
  }

  fragColor.a *= inCircle;

  if (picking.isActive > 0.5) {
    if (!picking_isColorValid(varyings.pickingColor)) {
      discard;
    }
    return vec4<f32>(varyings.pickingColor, 1.0);
  }

  if (picking.isHighlightActive > 0.5) {
    let highlightedObjectColor = picking_normalizeColor(picking.highlightedObjectColor);
    if (picking_isColorZero(abs(varyings.pickingColor - highlightedObjectColor))) {
      let highLightAlpha = picking.highlightColor.a;
      let blendedAlpha = highLightAlpha + fragColor.a * (1.0 - highLightAlpha);
      if (blendedAlpha > 0.0) {
        let highLightRatio = highLightAlpha / blendedAlpha;
        fragColor = vec4<f32>(
          mix(fragColor.rgb, picking.highlightColor.rgb, highLightRatio),
          blendedAlpha
        );
      } else {
        fragColor = vec4<f32>(fragColor.rgb, 0.0);
      }
    }
  }

  // Apply premultiplied alpha as required by transparent canvas
  fragColor = deckgl_premultiplied_alpha(fragColor);

  return fragColor;
  // return vec4<f32>(0, 0, 1, 1);
}
`,ei=[0,0,0,255],Mr={radiusUnits:"meters",radiusScale:{type:"number",min:0,value:1},radiusMinPixels:{type:"number",min:0,value:0},radiusMaxPixels:{type:"number",min:0,value:Number.MAX_SAFE_INTEGER},lineWidthUnits:"meters",lineWidthScale:{type:"number",min:0,value:1},lineWidthMinPixels:{type:"number",min:0,value:0},lineWidthMaxPixels:{type:"number",min:0,value:Number.MAX_SAFE_INTEGER},stroked:!1,filled:!0,billboard:!1,antialiasing:!0,getPosition:{type:"accessor",value:o=>o.position},getRadius:{type:"accessor",value:1},getFillColor:{type:"accessor",value:ei},getLineColor:{type:"accessor",value:ei},getLineWidth:{type:"accessor",value:1},getPixelOffset:{type:"accessor",value:[0,0]},strokeWidth:{deprecatedFor:"getLineWidth"},outline:{deprecatedFor:"stroked"},getColor:{deprecatedFor:["getFillColor","getLineColor"]}};class Ce extends k{getShaders(){return super.getShaders({vs:wr,fs:Er,source:Ir,modules:[G,ye,j,Tr]})}initializeState(){this.getAttributeManager().addInstanced({instancePositions:{size:3,type:"float64",fp64:this.use64bitPositions(),transition:!0,accessor:"getPosition"},instanceRadius:{size:1,transition:!0,accessor:"getRadius",defaultValue:1},instanceFillColors:{size:this.props.colorFormat.length,transition:!0,type:"unorm8",accessor:"getFillColor",defaultValue:[0,0,0,255]},instanceLineColors:{size:this.props.colorFormat.length,transition:!0,type:"unorm8",accessor:"getLineColor",defaultValue:[0,0,0,255]},instanceLineWidths:{size:1,transition:!0,accessor:"getLineWidth",defaultValue:1},instancePixelOffset:{size:2,transition:!0,accessor:"getPixelOffset"}})}updateState(t){var e;super.updateState(t),t.changeFlags.extensionsChanged&&((e=this.state.model)==null||e.destroy(),this.state.model=this._getModel(),this.getAttributeManager().invalidateAll())}draw({uniforms:t}){const{radiusUnits:e,radiusScale:i,radiusMinPixels:n,radiusMaxPixels:s,stroked:r,filled:a,billboard:l,antialiasing:c,lineWidthUnits:u,lineWidthScale:f,lineWidthMinPixels:d,lineWidthMaxPixels:g}=this.props,h={stroked:r,filled:a,billboard:l,antialiasing:c,radiusUnits:D[e],radiusScale:i,radiusMinPixels:n,radiusMaxPixels:s,lineWidthUnits:D[u],lineWidthScale:f,lineWidthMinPixels:d,lineWidthMaxPixels:g},p=this.state.model;p.shaderInputs.setProps({scatterplot:h}),p.draw(this.context.renderPass)}_getModel(){const t=[-1,-1,0,1,-1,0,-1,1,0,1,1,0];return new M(this.context.device,{...this.getShaders(),id:this.props.id,bufferLayout:this.getAttributeManager().getBufferLayouts(),geometry:new N({topology:"triangle-strip",attributes:{positions:{size:3,value:new Float32Array(t)}}}),isInstanced:!0})}}Ce.defaultProps=Mr;Ce.layerName="ScatterplotLayer";const Pe={CLOCKWISE:1,COUNTER_CLOCKWISE:-1};function be(o,t,e={}){return Rr(o,e)!==t?(zr(o,e),!0):!1}function Rr(o,t={}){return Math.sign(Or(o,t))}const ii={x:0,y:1,z:2};function Or(o,t={}){const{start:e=0,end:i=o.length,plane:n="xy"}=t,s=t.size||2;let r=0;const a=ii[n[0]],l=ii[n[1]];for(let c=e,u=i-s;c<i;c+=s)r+=(o[c+a]-o[u+a])*(o[c+l]+o[u+l]),u=c;return r/2}function zr(o,t){const{start:e=0,end:i=o.length,size:n=2}=t,s=(i-e)/n,r=Math.floor(s/2);for(let a=0;a<r;++a){const l=e+a*n,c=e+(s-1-a)*n;for(let u=0;u<n;++u){const f=o[l+u];o[l+u]=o[c+u],o[c+u]=f}}}function U(o,t){const e=t.length,i=o.length;if(i>0){let n=!0;for(let s=0;s<e;s++)if(o[i-e+s]!==t[s]){n=!1;break}if(n)return!1}for(let n=0;n<e;n++)o[i+n]=t[n];return!0}function fe(o,t){const e=t.length;for(let i=0;i<e;i++)o[i]=t[i]}function dt(o,t,e,i,n=[]){const s=i+t*e;for(let r=0;r<e;r++)n[r]=o[s+r];return n}function de(o,t,e,i,n=[]){let s,r;if(e&8)s=(i[3]-o[1])/(t[1]-o[1]),r=3;else if(e&4)s=(i[1]-o[1])/(t[1]-o[1]),r=1;else if(e&2)s=(i[2]-o[0])/(t[0]-o[0]),r=2;else if(e&1)s=(i[0]-o[0])/(t[0]-o[0]),r=0;else return null;for(let a=0;a<o.length;a++)n[a]=(r&1)===a?i[r]:s*(t[a]-o[a])+o[a];return n}function Et(o,t){let e=0;return o[0]<t[0]?e|=1:o[0]>t[2]&&(e|=2),o[1]<t[1]?e|=4:o[1]>t[3]&&(e|=8),e}function so(o,t){const{size:e=2,broken:i=!1,gridResolution:n=10,gridOffset:s=[0,0],startIndex:r=0,endIndex:a=o.length}=t||{},l=(a-r)/e;let c=[];const u=[c],f=dt(o,0,e,r);let d,g;const h=ao(f,n,s,[]),p=[];U(c,f);for(let v=1;v<l;v++){for(d=dt(o,v,e,r,d),g=Et(d,h);g;){de(f,d,g,h,p);const x=Et(p,h);x&&(de(f,p,x,h,p),g=x),U(c,p),fe(f,p),kr(h,n,g),i&&c.length>e&&(c=[],u.push(c),U(c,f)),g=Et(d,h)}U(c,d),fe(f,d)}return i?u:u[0]}const oi=0,Fr=1;function ro(o,t=null,e){if(!o.length)return[];const{size:i=2,gridResolution:n=10,gridOffset:s=[0,0],edgeTypes:r=!1}=e||{},a=[],l=[{pos:o,types:r?new Array(o.length/i).fill(Fr):null,holes:t||[]}],c=[[],[]];let u=[];for(;l.length;){const{pos:f,types:d,holes:g}=l.shift();Br(f,i,g[0]||f.length,c),u=ao(c[0],n,s,u);const h=Et(c[1],u);if(h){let p=ni(f,d,i,0,g[0]||f.length,u,h);const v={pos:p[0].pos,types:p[0].types,holes:[]},x={pos:p[1].pos,types:p[1].types,holes:[]};l.push(v,x);for(let _=0;_<g.length;_++)p=ni(f,d,i,g[_],g[_+1]||f.length,u,h),p[0]&&(v.holes.push(v.pos.length),v.pos=_t(v.pos,p[0].pos),r&&(v.types=_t(v.types,p[0].types))),p[1]&&(x.holes.push(x.pos.length),x.pos=_t(x.pos,p[1].pos),r&&(x.types=_t(x.types,p[1].types)))}else{const p={positions:f};r&&(p.edgeTypes=d),g.length&&(p.holeIndices=g),a.push(p)}}return a}function ni(o,t,e,i,n,s,r){const a=(n-i)/e,l=[],c=[],u=[],f=[],d=[];let g,h,p;const v=dt(o,a-1,e,i);let x=Math.sign(r&8?v[1]-s[3]:v[0]-s[2]),_=t&&t[a-1],y=0,m=0;for(let C=0;C<a;C++)g=dt(o,C,e,i,g),h=Math.sign(r&8?g[1]-s[3]:g[0]-s[2]),p=t&&t[i/e+C],h&&x&&x!==h&&(de(v,g,r,s,d),U(l,d)&&u.push(_),U(c,d)&&f.push(_)),h<=0?(U(l,g)&&u.push(p),y-=h):u.length&&(u[u.length-1]=oi),h>=0?(U(c,g)&&f.push(p),m+=h):f.length&&(f[f.length-1]=oi),fe(v,g),x=h,_=p;return[y?{pos:l,types:t&&u}:null,m?{pos:c,types:t&&f}:null]}function ao(o,t,e,i){const n=Math.floor((o[0]-e[0])/t)*t+e[0],s=Math.floor((o[1]-e[1])/t)*t+e[1];return i[0]=n,i[1]=s,i[2]=n+t,i[3]=s+t,i}function kr(o,t,e){e&8?(o[1]+=t,o[3]+=t):e&4?(o[1]-=t,o[3]-=t):e&2?(o[0]+=t,o[2]+=t):e&1&&(o[0]-=t,o[2]-=t)}function Br(o,t,e,i){let n=1/0,s=-1/0,r=1/0,a=-1/0;for(let l=0;l<e;l+=t){const c=o[l],u=o[l+1];n=c<n?c:n,s=c>s?c:s,r=u<r?u:r,a=u>a?u:a}return i[0][0]=n,i[0][1]=r,i[1][0]=s,i[1][1]=a,i}function _t(o,t){for(let e=0;e<t.length;e++)o.push(t[e]);return o}const Ur=85.051129;function Dr(o,t){const{size:e=2,startIndex:i=0,endIndex:n=o.length,normalize:s=!0}=t||{},r=o.slice(i,n);lo(r,e,0,n-i);const a=so(r,{size:e,broken:!0,gridResolution:360,gridOffset:[-180,-180]});if(s)for(const l of a)co(l,e);return a}function Nr(o,t=null,e){const{size:i=2,normalize:n=!0,edgeTypes:s=!1}=e||{};t=t||[];const r=[],a=[];let l=0,c=0;for(let f=0;f<=t.length;f++){const d=t[f]||o.length,g=c,h=Gr(o,i,l,d);for(let p=h;p<d;p++)r[c++]=o[p];for(let p=l;p<h;p++)r[c++]=o[p];lo(r,i,g,c),jr(r,i,g,c,e==null?void 0:e.maxLatitude),l=d,a[f]=c}a.pop();const u=ro(r,a,{size:i,gridResolution:360,gridOffset:[-180,-180],edgeTypes:s});if(n)for(const f of u)co(f.positions,i);return u}function Gr(o,t,e,i){let n=-1,s=-1;for(let r=e+1;r<i;r+=t){const a=Math.abs(o[r]);a>n&&(n=a,s=r-1)}return s}function jr(o,t,e,i,n=Ur){const s=o[e],r=o[i-t];if(Math.abs(s-r)>180){const a=dt(o,0,t,e);a[0]+=Math.round((r-s)/360)*360,U(o,a),a[1]=Math.sign(a[1])*n,U(o,a),a[0]=s,U(o,a)}}function lo(o,t,e,i){let n=o[0],s;for(let r=e;r<i;r+=t){s=o[r];const a=s-n;(a>180||a<-180)&&(s-=Math.round(a/360)*360),o[r]=n=s}}function co(o,t){let e;const i=o.length/t;for(let s=0;s<i&&(e=o[s*t],(e+180)%360===0);s++);const n=-Math.round(e/360)*360;if(n!==0)for(let s=0;s<i;s++)o[s*t]+=n}class Vr extends N{constructor(t){const{indices:e,attributes:i}=Wr(t);super({...t,indices:e,attributes:i})}}function Wr(o){const{radius:t,height:e=1,nradial:i=10}=o;let{vertices:n}=o;n&&(S.assert(n.length>=i),n=n.flatMap(g=>[g[0],g[1]]),be(n,Pe.COUNTER_CLOCKWISE));const s=e>0,r=i+1,a=s?r*3+1:i,l=Math.PI*2/i,c=new Uint16Array(s?i*3*2:0),u=new Float32Array(a*3),f=new Float32Array(a*3);let d=0;if(s){for(let g=0;g<r;g++){const h=g*l,p=g%i,v=Math.sin(h),x=Math.cos(h);for(let _=0;_<2;_++)u[d+0]=n?n[p*2]:x*t,u[d+1]=n?n[p*2+1]:v*t,u[d+2]=(1/2-_)*e,f[d+0]=n?n[p*2]:x,f[d+1]=n?n[p*2+1]:v,d+=3}u[d+0]=u[d-3],u[d+1]=u[d-2],u[d+2]=u[d-1],d+=3}for(let g=s?0:1;g<r;g++){const h=Math.floor(g/2)*Math.sign(.5-g%2),p=h*l,v=(h+i)%i,x=Math.sin(p),_=Math.cos(p);u[d+0]=n?n[v*2]:_*t,u[d+1]=n?n[v*2+1]:x*t,u[d+2]=e/2,f[d+2]=1,d+=3}if(s){let g=0;for(let h=0;h<i;h++)c[g++]=h*2+0,c[g++]=h*2+2,c[g++]=h*2+0,c[g++]=h*2+1,c[g++]=h*2+1,c[g++]=h*2+3}return{indices:c,attributes:{POSITION:{size:3,value:u},NORMAL:{size:3,value:f}}}}const si=`layout(std140) uniform columnUniforms {
  float radius;
  float angle;
  vec2 offset;
  bool extruded;
  bool stroked;
  bool isStroke;
  float coverage;
  float elevationScale;
  float edgeDistance;
  float widthScale;
  float widthMinPixels;
  float widthMaxPixels;
  highp int radiusUnits;
  highp int widthUnits;
} column;
`,$r={name:"column",vs:si,fs:si,uniformTypes:{radius:"f32",angle:"f32",offset:"vec2<f32>",extruded:"f32",stroked:"f32",isStroke:"f32",coverage:"f32",elevationScale:"f32",edgeDistance:"f32",widthScale:"f32",widthMinPixels:"f32",widthMaxPixels:"f32",radiusUnits:"i32",widthUnits:"i32"}},Hr=`#version 300 es
#define SHADER_NAME column-layer-vertex-shader
in vec3 positions;
in vec3 normals;
in vec3 instancePositions;
in float instanceElevations;
in vec3 instancePositions64Low;
in vec4 instanceFillColors;
in vec4 instanceLineColors;
in float instanceStrokeWidths;
in vec3 instancePickingColors;
out vec4 vColor;
#ifdef FLAT_SHADING
out vec3 cameraPosition;
out vec4 position_commonspace;
#endif
void main(void) {
geometry.worldPosition = instancePositions;
vec4 color = column.isStroke ? instanceLineColors : instanceFillColors;
mat2 rotationMatrix = mat2(cos(column.angle), sin(column.angle), -sin(column.angle), cos(column.angle));
float elevation = 0.0;
float strokeOffsetRatio = 1.0;
if (column.extruded) {
elevation = instanceElevations * (positions.z + 1.0) / 2.0 * column.elevationScale;
} else if (column.stroked) {
float widthPixels = clamp(
project_size_to_pixel(instanceStrokeWidths * column.widthScale, column.widthUnits),
column.widthMinPixels, column.widthMaxPixels) / 2.0;
float halfOffset = project_pixel_size(widthPixels) / project_size(column.edgeDistance * column.coverage * column.radius);
if (column.isStroke) {
strokeOffsetRatio -= sign(positions.z) * halfOffset;
} else {
strokeOffsetRatio -= halfOffset;
}
}
float shouldRender = float(color.a > 0.0 && instanceElevations >= 0.0);
float dotRadius = column.radius * column.coverage * shouldRender;
geometry.pickingColor = instancePickingColors;
vec3 centroidPosition = vec3(instancePositions.xy, instancePositions.z + elevation);
vec3 centroidPosition64Low = instancePositions64Low;
vec2 offset = (rotationMatrix * positions.xy * strokeOffsetRatio + column.offset) * dotRadius;
if (column.radiusUnits == UNIT_METERS) {
offset = project_size(offset);
} else if (column.radiusUnits == UNIT_PIXELS) {
offset = project_pixel_size(offset);
}
vec3 pos = vec3(offset, 0.);
DECKGL_FILTER_SIZE(pos, geometry);
gl_Position = project_position_to_clipspace(centroidPosition, centroidPosition64Low, pos, geometry.position);
geometry.normal = project_normal(vec3(rotationMatrix * normals.xy, normals.z));
DECKGL_FILTER_GL_POSITION(gl_Position, geometry);
if (column.extruded && !column.isStroke) {
#ifdef FLAT_SHADING
cameraPosition = project.cameraPosition;
position_commonspace = geometry.position;
vColor = vec4(color.rgb, color.a * layer.opacity);
#else
vec3 lightColor = lighting_getLightColor(color.rgb, project.cameraPosition, geometry.position.xyz, geometry.normal);
vColor = vec4(lightColor, color.a * layer.opacity);
#endif
} else {
vColor = vec4(color.rgb, color.a * layer.opacity);
}
DECKGL_FILTER_COLOR(vColor, geometry);
}
`,Yr=`#version 300 es
#define SHADER_NAME column-layer-fragment-shader
precision highp float;
out vec4 fragColor;
in vec4 vColor;
#ifdef FLAT_SHADING
in vec3 cameraPosition;
in vec4 position_commonspace;
#endif
void main(void) {
fragColor = vColor;
geometry.uv = vec2(0.);
#ifdef FLAT_SHADING
if (column.extruded && !column.isStroke && !bool(picking.isActive)) {
vec3 normal = normalize(cross(dFdx(position_commonspace.xyz), dFdy(position_commonspace.xyz)));
fragColor.rgb = lighting_getLightColor(vColor.rgb, cameraPosition, position_commonspace.xyz, normal);
}
#endif
DECKGL_FILTER_COLOR(fragColor, geometry);
}
`,Bt=[0,0,0,255],Zr={diskResolution:{type:"number",min:4,value:20},vertices:null,radius:{type:"number",min:0,value:1e3},angle:{type:"number",value:0},offset:{type:"array",value:[0,0]},coverage:{type:"number",min:0,max:1,value:1},elevationScale:{type:"number",min:0,value:1},radiusUnits:"meters",lineWidthUnits:"meters",lineWidthScale:1,lineWidthMinPixels:0,lineWidthMaxPixels:Number.MAX_SAFE_INTEGER,extruded:!0,wireframe:!1,filled:!0,stroked:!1,flatShading:!1,getPosition:{type:"accessor",value:o=>o.position},getFillColor:{type:"accessor",value:Bt},getLineColor:{type:"accessor",value:Bt},getLineWidth:{type:"accessor",value:1},getElevation:{type:"accessor",value:1e3},material:!0,getColor:{deprecatedFor:["getFillColor","getLineColor"]}};class uo extends k{getShaders(){const t={},{flatShading:e}=this.props;return e&&(t.FLAT_SHADING=1),super.getShaders({vs:Hr,fs:Yr,defines:t,modules:[G,e?Bi:Nt,j,$r]})}initializeState(){this.getAttributeManager().addInstanced({instancePositions:{size:3,type:"float64",fp64:this.use64bitPositions(),transition:!0,accessor:"getPosition"},instanceElevations:{size:1,transition:!0,accessor:"getElevation"},instanceFillColors:{size:this.props.colorFormat.length,type:"unorm8",transition:!0,accessor:"getFillColor",defaultValue:Bt},instanceLineColors:{size:this.props.colorFormat.length,type:"unorm8",transition:!0,accessor:"getLineColor",defaultValue:Bt},instanceStrokeWidths:{size:1,accessor:"getLineWidth",transition:!0}})}updateState(t){var a;super.updateState(t);const{props:e,oldProps:i,changeFlags:n}=t,s=n.extensionsChanged||e.flatShading!==i.flatShading;s&&((a=this.state.models)==null||a.forEach(l=>l.destroy()),this.setState(this._getModels()),this.getAttributeManager().invalidateAll());const r=this.getNumInstances();this.state.fillModel.setInstanceCount(r),this.state.wireframeModel.setInstanceCount(r),(s||e.diskResolution!==i.diskResolution||e.vertices!==i.vertices||(e.extruded||e.stroked)!==(i.extruded||i.stroked))&&this._updateGeometry(e)}getGeometry(t,e,i){const n=new Vr({radius:1,height:i?2:0,vertices:e,nradial:t});let s=0;if(e)for(let r=0;r<t;r++){const a=e[r],l=Math.sqrt(a[0]*a[0]+a[1]*a[1]);s+=l/t}else s=1;return this.setState({edgeDistance:Math.cos(Math.PI/t)*s}),n}_getModels(){const t=this.getShaders(),e=this.getAttributeManager().getBufferLayouts(),i=new M(this.context.device,{...t,id:`${this.props.id}-fill`,bufferLayout:e,isInstanced:!0}),n=new M(this.context.device,{...t,id:`${this.props.id}-wireframe`,bufferLayout:e,isInstanced:!0});return{fillModel:i,wireframeModel:n,models:[n,i]}}_updateGeometry({diskResolution:t,vertices:e,extruded:i,stroked:n}){const s=this.getGeometry(t,e,i||n);this.setState({fillVertexCount:s.attributes.POSITION.value.length/3});const r=this.state.fillModel,a=this.state.wireframeModel,{POSITION:l,NORMAL:c}=s.attributes,u=new N({topology:"triangle-strip",attributes:{POSITION:l,NORMAL:c}});r.setGeometry(u),a.setGeometry(s),a.setTopology("line-list")}draw({uniforms:t}){const{lineWidthUnits:e,lineWidthScale:i,lineWidthMinPixels:n,lineWidthMaxPixels:s,radiusUnits:r,elevationScale:a,extruded:l,filled:c,stroked:u,wireframe:f,offset:d,coverage:g,radius:h,angle:p}=this.props,v=this.state.fillModel,x=this.state.wireframeModel,{fillVertexCount:_,edgeDistance:y}=this.state,m={radius:h,angle:p/180*Math.PI,offset:d,extruded:l,stroked:u,coverage:g,elevationScale:a,edgeDistance:y,radiusUnits:D[r],widthUnits:D[e],widthScale:i,widthMinPixels:n,widthMaxPixels:s};l&&f&&(x.shaderInputs.setProps({column:{...m,isStroke:!0}}),x.draw(this.context.renderPass)),c&&(v.setVertexCount(_),v.shaderInputs.setProps({column:{...m,isStroke:!1}}),v.draw(this.context.renderPass)),!l&&u&&(v.setVertexCount(_*2/3),v.shaderInputs.setProps({column:{...m,isStroke:!0}}),v.draw(this.context.renderPass))}}uo.layerName="ColumnLayer";uo.defaultProps=Zr;function Kr(o,t,e,i){let n;if(Array.isArray(o[0])){const s=o.length*t;n=new Array(s);for(let r=0;r<o.length;r++)for(let a=0;a<t;a++)n[r*t+a]=o[r][a]||0}else n=o;return e?so(n,{size:t,gridResolution:e}):i?Dr(n,{size:t}):n}const Xr=1,qr=2,Qt=4;class Jr extends qi{constructor(t){super({...t,attributes:{positions:{size:3,padding:18,initialize:!0,type:t.fp64?Float64Array:Float32Array},segmentTypes:{size:1,type:Uint8ClampedArray}}})}get(t){return this.attributes[t]}getGeometryFromBuffer(t){return this.normalize?super.getGeometryFromBuffer(t):null}normalizeGeometry(t){return this.normalize?Kr(t,this.positionSize,this.opts.resolution,this.opts.wrapLongitude):t}getGeometrySize(t){if(ri(t)){let i=0;for(const n of t)i+=this.getGeometrySize(n);return i}const e=this.getPathLength(t);return e<2?0:this.isClosed(t)?e<3?0:e+2:e}updateGeometryAttributes(t,e){if(e.geometrySize!==0)if(t&&ri(t))for(const i of t){const n=this.getGeometrySize(i);e.geometrySize=n,this.updateGeometryAttributes(i,e),e.vertexStart+=n}else this._updateSegmentTypes(t,e),this._updatePositions(t,e)}_updateSegmentTypes(t,e){const i=this.attributes.segmentTypes,n=t?this.isClosed(t):!1,{vertexStart:s,geometrySize:r}=e;i.fill(0,s,s+r),n?(i[s]=Qt,i[s+r-2]=Qt):(i[s]+=Xr,i[s+r-2]+=qr),i[s+r-1]=Qt}_updatePositions(t,e){const{positions:i}=this.attributes;if(!i||!t)return;const{vertexStart:n,geometrySize:s}=e,r=new Array(3);for(let a=n,l=0;l<s;a++,l++)this.getPointOnPath(t,l,r),i[a*3]=r[0],i[a*3+1]=r[1],i[a*3+2]=r[2]}getPathLength(t){return t.length/this.positionSize}getPointOnPath(t,e,i=[]){const{positionSize:n}=this;e*n>=t.length&&(e+=1-t.length/n);const s=e*n;return i[0]=t[s],i[1]=t[s+1],i[2]=n===3&&t[s+2]||0,i}isClosed(t){if(!this.normalize)return!!this.opts.loop;const{positionSize:e}=this,i=t.length-e;return t[0]===t[i]&&t[1]===t[i+1]&&(e===2||t[2]===t[i+2])}}function ri(o){return Array.isArray(o[0])}const ai=`layout(std140) uniform pathUniforms {
  float widthScale;
  float widthMinPixels;
  float widthMaxPixels;
  float jointType;
  float capType;
  float miterLimit;
  bool billboard;
  highp int widthUnits;
} path;
`,Qr={name:"path",vs:ai,fs:ai,uniformTypes:{widthScale:"f32",widthMinPixels:"f32",widthMaxPixels:"f32",jointType:"f32",capType:"f32",miterLimit:"f32",billboard:"f32",widthUnits:"i32"}},ta=`#version 300 es
#define SHADER_NAME path-layer-vertex-shader
in vec2 positions;
in float instanceTypes;
in vec3 instanceStartPositions;
in vec3 instanceEndPositions;
in vec3 instanceLeftPositions;
in vec3 instanceRightPositions;
in vec3 instanceLeftPositions64Low;
in vec3 instanceStartPositions64Low;
in vec3 instanceEndPositions64Low;
in vec3 instanceRightPositions64Low;
in float instanceStrokeWidths;
in vec4 instanceColors;
in vec3 instancePickingColors;
uniform float opacity;
out vec4 vColor;
out vec2 vCornerOffset;
out float vMiterLength;
out vec2 vPathPosition;
out float vPathLength;
out float vJointType;
const float EPSILON = 0.001;
const vec3 ZERO_OFFSET = vec3(0.0);
float flipIfTrue(bool flag) {
return -(float(flag) * 2. - 1.);
}
vec3 getLineJoinOffset(
vec3 prevPoint, vec3 currPoint, vec3 nextPoint,
vec2 width
) {
bool isEnd = positions.x > 0.0;
float sideOfPath = positions.y;
float isJoint = float(sideOfPath == 0.0);
vec3 deltaA3 = (currPoint - prevPoint);
vec3 deltaB3 = (nextPoint - currPoint);
mat3 rotationMatrix;
bool needsRotation = !path.billboard && project_needs_rotation(currPoint, rotationMatrix);
if (needsRotation) {
deltaA3 = deltaA3 * rotationMatrix;
deltaB3 = deltaB3 * rotationMatrix;
}
vec2 deltaA = deltaA3.xy / width;
vec2 deltaB = deltaB3.xy / width;
float lenA = length(deltaA);
float lenB = length(deltaB);
vec2 dirA = lenA > 0. ? normalize(deltaA) : vec2(0.0, 0.0);
vec2 dirB = lenB > 0. ? normalize(deltaB) : vec2(0.0, 0.0);
vec2 perpA = vec2(-dirA.y, dirA.x);
vec2 perpB = vec2(-dirB.y, dirB.x);
vec2 tangent = dirA + dirB;
tangent = length(tangent) > 0. ? normalize(tangent) : perpA;
vec2 miterVec = vec2(-tangent.y, tangent.x);
vec2 dir = isEnd ? dirA : dirB;
vec2 perp = isEnd ? perpA : perpB;
float L = isEnd ? lenA : lenB;
float sinHalfA = abs(dot(miterVec, perp));
float cosHalfA = abs(dot(dirA, miterVec));
float turnDirection = flipIfTrue(dirA.x * dirB.y >= dirA.y * dirB.x);
float cornerPosition = sideOfPath * turnDirection;
float miterSize = 1.0 / max(sinHalfA, EPSILON);
miterSize = mix(
min(miterSize, max(lenA, lenB) / max(cosHalfA, EPSILON)),
miterSize,
step(0.0, cornerPosition)
);
vec2 offsetVec = mix(miterVec * miterSize, perp, step(0.5, cornerPosition))
* (sideOfPath + isJoint * turnDirection);
bool isStartCap = lenA == 0.0 || (!isEnd && (instanceTypes == 1.0 || instanceTypes == 3.0));
bool isEndCap = lenB == 0.0 || (isEnd && (instanceTypes == 2.0 || instanceTypes == 3.0));
bool isCap = isStartCap || isEndCap;
if (isCap) {
offsetVec = mix(perp * sideOfPath, dir * path.capType * 4.0 * flipIfTrue(isStartCap), isJoint);
vJointType = path.capType;
} else {
vJointType = path.jointType;
}
vPathLength = L;
vCornerOffset = offsetVec;
vMiterLength = dot(vCornerOffset, miterVec * turnDirection);
vMiterLength = isCap ? isJoint : vMiterLength;
vec2 offsetFromStartOfPath = vCornerOffset + deltaA * float(isEnd);
vPathPosition = vec2(
dot(offsetFromStartOfPath, perp),
dot(offsetFromStartOfPath, dir)
);
geometry.uv = vPathPosition;
float isValid = step(instanceTypes, 3.5);
vec3 offset = vec3(offsetVec * width * isValid, 0.0);
if (needsRotation) {
offset = rotationMatrix * offset;
}
return offset;
}
void clipLine(inout vec4 position, vec4 refPosition) {
if (position.w < EPSILON) {
float r = (EPSILON - refPosition.w) / (position.w - refPosition.w);
position = refPosition + (position - refPosition) * r;
}
}
void main() {
geometry.pickingColor = instancePickingColors;
vColor = vec4(instanceColors.rgb, instanceColors.a * layer.opacity);
float isEnd = positions.x;
vec3 prevPosition = mix(instanceLeftPositions, instanceStartPositions, isEnd);
vec3 prevPosition64Low = mix(instanceLeftPositions64Low, instanceStartPositions64Low, isEnd);
vec3 currPosition = mix(instanceStartPositions, instanceEndPositions, isEnd);
vec3 currPosition64Low = mix(instanceStartPositions64Low, instanceEndPositions64Low, isEnd);
vec3 nextPosition = mix(instanceEndPositions, instanceRightPositions, isEnd);
vec3 nextPosition64Low = mix(instanceEndPositions64Low, instanceRightPositions64Low, isEnd);
geometry.worldPosition = currPosition;
vec2 widthPixels = vec2(clamp(
project_size_to_pixel(instanceStrokeWidths * path.widthScale, path.widthUnits),
path.widthMinPixels, path.widthMaxPixels) / 2.0);
vec3 width;
if (path.billboard) {
vec4 prevPositionScreen = project_position_to_clipspace(prevPosition, prevPosition64Low, ZERO_OFFSET);
vec4 currPositionScreen = project_position_to_clipspace(currPosition, currPosition64Low, ZERO_OFFSET, geometry.position);
vec4 nextPositionScreen = project_position_to_clipspace(nextPosition, nextPosition64Low, ZERO_OFFSET);
clipLine(prevPositionScreen, currPositionScreen);
clipLine(nextPositionScreen, currPositionScreen);
clipLine(currPositionScreen, mix(nextPositionScreen, prevPositionScreen, isEnd));
width = vec3(widthPixels, 0.0);
DECKGL_FILTER_SIZE(width, geometry);
vec3 offset = getLineJoinOffset(
prevPositionScreen.xyz / prevPositionScreen.w,
currPositionScreen.xyz / currPositionScreen.w,
nextPositionScreen.xyz / nextPositionScreen.w,
project_pixel_size_to_clipspace(width.xy)
);
DECKGL_FILTER_GL_POSITION(currPositionScreen, geometry);
gl_Position = vec4(currPositionScreen.xyz + offset * currPositionScreen.w, currPositionScreen.w);
} else {
prevPosition = project_position(prevPosition, prevPosition64Low);
currPosition = project_position(currPosition, currPosition64Low);
nextPosition = project_position(nextPosition, nextPosition64Low);
width = vec3(project_pixel_size(widthPixels), 0.0);
DECKGL_FILTER_SIZE(width, geometry);
vec3 offset = getLineJoinOffset(prevPosition, currPosition, nextPosition, width.xy);
geometry.position = vec4(currPosition + offset, 1.0);
gl_Position = project_common_position_to_clipspace(geometry.position);
DECKGL_FILTER_GL_POSITION(gl_Position, geometry);
}
DECKGL_FILTER_COLOR(vColor, geometry);
}
`,ea=`#version 300 es
#define SHADER_NAME path-layer-fragment-shader
precision highp float;
in vec4 vColor;
in vec2 vCornerOffset;
in float vMiterLength;
in vec2 vPathPosition;
in float vPathLength;
in float vJointType;
out vec4 fragColor;
void main(void) {
geometry.uv = vPathPosition;
if (vPathPosition.y < 0.0 || vPathPosition.y > vPathLength) {
if (vJointType > 0.5 && length(vCornerOffset) > 1.0) {
discard;
}
if (vJointType < 0.5 && vMiterLength > path.miterLimit + 1.0) {
discard;
}
}
fragColor = vColor;
DECKGL_FILTER_COLOR(fragColor, geometry);
}
`,fo=[0,0,0,255],ia={widthUnits:"meters",widthScale:{type:"number",min:0,value:1},widthMinPixels:{type:"number",min:0,value:0},widthMaxPixels:{type:"number",min:0,value:Number.MAX_SAFE_INTEGER},jointRounded:!1,capRounded:!1,miterLimit:{type:"number",min:0,value:4},billboard:!1,_pathType:null,getPath:{type:"accessor",value:o=>o.path},getColor:{type:"accessor",value:fo},getWidth:{type:"accessor",value:1},rounded:{deprecatedFor:["jointRounded","capRounded"]}},te={enter:(o,t)=>t.length?t.subarray(t.length-o.length):o};class Wt extends k{getShaders(){return super.getShaders({vs:ta,fs:ea,modules:[G,j,Qr]})}get wrapLongitude(){return!1}getBounds(){var t;return(t=this.getAttributeManager())==null?void 0:t.getBounds(["vertexPositions"])}initializeState(){this.getAttributeManager().addInstanced({vertexPositions:{size:3,vertexOffset:1,type:"float64",fp64:this.use64bitPositions(),transition:te,accessor:"getPath",update:this.calculatePositions,noAlloc:!0,shaderAttributes:{instanceLeftPositions:{vertexOffset:0},instanceStartPositions:{vertexOffset:1},instanceEndPositions:{vertexOffset:2},instanceRightPositions:{vertexOffset:3}}},instanceTypes:{size:1,type:"uint8",update:this.calculateSegmentTypes,noAlloc:!0},instanceStrokeWidths:{size:1,accessor:"getWidth",transition:te,defaultValue:1},instanceColors:{size:this.props.colorFormat.length,type:"unorm8",accessor:"getColor",transition:te,defaultValue:fo},instancePickingColors:{size:4,type:"uint8",accessor:(i,{index:n,target:s})=>this.encodePickingColor(i&&i.__source?i.__source.index:n,s)}}),this.setState({pathTesselator:new Jr({fp64:this.use64bitPositions()})})}updateState(t){var r;super.updateState(t);const{props:e,changeFlags:i}=t,n=this.getAttributeManager();if(i.dataChanged||i.updateTriggersChanged&&(i.updateTriggersChanged.all||i.updateTriggersChanged.getPath)){const{pathTesselator:a}=this.state,l=e.data.attributes||{};a.updateGeometry({data:e.data,geometryBuffer:l.getPath,buffers:l,normalize:!e._pathType,loop:e._pathType==="loop",getGeometry:e.getPath,positionFormat:e.positionFormat,wrapLongitude:e.wrapLongitude,resolution:this.context.viewport.resolution,dataChanged:i.dataChanged}),this.setState({numInstances:a.instanceCount,startIndices:a.vertexStarts}),i.dataChanged||n.invalidateAll()}i.extensionsChanged&&((r=this.state.model)==null||r.destroy(),this.state.model=this._getModel(),n.invalidateAll())}getPickingInfo(t){const e=super.getPickingInfo(t),{index:i}=e,n=this.props.data;return n[0]&&n[0].__source&&(e.object=n.find(s=>s.__source.index===i)),e}disablePickingIndex(t){const e=this.props.data;if(e[0]&&e[0].__source)for(let i=0;i<e.length;i++)e[i].__source.index===t&&this._disablePickingIndex(i);else super.disablePickingIndex(t)}draw({uniforms:t}){const{jointRounded:e,capRounded:i,billboard:n,miterLimit:s,widthUnits:r,widthScale:a,widthMinPixels:l,widthMaxPixels:c}=this.props,u=this.state.model,f={jointType:Number(e),capType:Number(i),billboard:n,widthUnits:D[r],widthScale:a,miterLimit:s,widthMinPixels:l,widthMaxPixels:c};u.shaderInputs.setProps({path:f}),u.draw(this.context.renderPass)}_getModel(){const t=[0,1,2,1,4,2,1,3,4,3,5,4],e=[0,0,0,-1,0,1,1,-1,1,1,1,0];return new M(this.context.device,{...this.getShaders(),id:this.props.id,bufferLayout:this.getAttributeManager().getBufferLayouts(),geometry:new N({topology:"triangle-list",attributes:{indices:new Uint16Array(t),positions:{value:new Float32Array(e),size:2}}}),isInstanced:!0})}calculatePositions(t){const{pathTesselator:e}=this.state;t.startIndices=e.vertexStarts,t.value=e.get("positions")}calculateSegmentTypes(t){const{pathTesselator:e}=this.state;t.startIndices=e.vertexStarts,t.value=e.get("segmentTypes")}}Wt.defaultProps=ia;Wt.layerName="PathLayer";var Le={exports:{}};Le.exports=$t;Le.exports.default=$t;function $t(o,t,e){e=e||2;var i=t&&t.length,n=i?t[0]*e:o.length,s=go(o,0,n,e,!0),r=[];if(!s||s.next===s.prev)return r;var a,l,c,u,f,d,g;if(i&&(s=aa(o,t,s,e)),o.length>80*e){a=c=o[0],l=u=o[1];for(var h=e;h<n;h+=e)f=o[h],d=o[h+1],f<a&&(a=f),d<l&&(l=d),f>c&&(c=f),d>u&&(u=d);g=Math.max(c-a,u-l),g=g!==0?32767/g:0}return gt(s,r,e,a,l,g,0),r}function go(o,t,e,i,n){var s,r;if(n===pe(o,t,e,i)>0)for(s=t;s<e;s+=i)r=li(s,o[s],o[s+1],r);else for(s=e-i;s>=t;s-=i)r=li(s,o[s],o[s+1],r);return r&&Ht(r,r.next)&&(pt(r),r=r.next),r}function J(o,t){if(!o)return o;t||(t=o);var e=o,i;do if(i=!1,!e.steiner&&(Ht(e,e.next)||b(e.prev,e,e.next)===0)){if(pt(e),e=t=e.prev,e===e.next)break;i=!0}else e=e.next;while(i||e!==t);return t}function gt(o,t,e,i,n,s,r){if(o){!r&&s&&da(o,i,n,s);for(var a=o,l,c;o.prev!==o.next;){if(l=o.prev,c=o.next,s?na(o,i,n,s):oa(o)){t.push(l.i/e|0),t.push(o.i/e|0),t.push(c.i/e|0),pt(o),o=c.next,a=c.next;continue}if(o=c,o===a){r?r===1?(o=sa(J(o),t,e),gt(o,t,e,i,n,s,2)):r===2&&ra(o,t,e,i,n,s):gt(J(o),t,e,i,n,s,1);break}}}}function oa(o){var t=o.prev,e=o,i=o.next;if(b(t,e,i)>=0)return!1;for(var n=t.x,s=e.x,r=i.x,a=t.y,l=e.y,c=i.y,u=n<s?n<r?n:r:s<r?s:r,f=a<l?a<c?a:c:l<c?l:c,d=n>s?n>r?n:r:s>r?s:r,g=a>l?a>c?a:c:l>c?l:c,h=i.next;h!==t;){if(h.x>=u&&h.x<=d&&h.y>=f&&h.y<=g&&Q(n,a,s,l,r,c,h.x,h.y)&&b(h.prev,h,h.next)>=0)return!1;h=h.next}return!0}function na(o,t,e,i){var n=o.prev,s=o,r=o.next;if(b(n,s,r)>=0)return!1;for(var a=n.x,l=s.x,c=r.x,u=n.y,f=s.y,d=r.y,g=a<l?a<c?a:c:l<c?l:c,h=u<f?u<d?u:d:f<d?f:d,p=a>l?a>c?a:c:l>c?l:c,v=u>f?u>d?u:d:f>d?f:d,x=ge(g,h,t,e,i),_=ge(p,v,t,e,i),y=o.prevZ,m=o.nextZ;y&&y.z>=x&&m&&m.z<=_;){if(y.x>=g&&y.x<=p&&y.y>=h&&y.y<=v&&y!==n&&y!==r&&Q(a,u,l,f,c,d,y.x,y.y)&&b(y.prev,y,y.next)>=0||(y=y.prevZ,m.x>=g&&m.x<=p&&m.y>=h&&m.y<=v&&m!==n&&m!==r&&Q(a,u,l,f,c,d,m.x,m.y)&&b(m.prev,m,m.next)>=0))return!1;m=m.nextZ}for(;y&&y.z>=x;){if(y.x>=g&&y.x<=p&&y.y>=h&&y.y<=v&&y!==n&&y!==r&&Q(a,u,l,f,c,d,y.x,y.y)&&b(y.prev,y,y.next)>=0)return!1;y=y.prevZ}for(;m&&m.z<=_;){if(m.x>=g&&m.x<=p&&m.y>=h&&m.y<=v&&m!==n&&m!==r&&Q(a,u,l,f,c,d,m.x,m.y)&&b(m.prev,m,m.next)>=0)return!1;m=m.nextZ}return!0}function sa(o,t,e){var i=o;do{var n=i.prev,s=i.next.next;!Ht(n,s)&&ho(n,i,i.next,s)&&ht(n,s)&&ht(s,n)&&(t.push(n.i/e|0),t.push(i.i/e|0),t.push(s.i/e|0),pt(i),pt(i.next),i=o=s),i=i.next}while(i!==o);return J(i)}function ra(o,t,e,i,n,s){var r=o;do{for(var a=r.next.next;a!==r.prev;){if(r.i!==a.i&&pa(r,a)){var l=po(r,a);r=J(r,r.next),l=J(l,l.next),gt(r,t,e,i,n,s,0),gt(l,t,e,i,n,s,0);return}a=a.next}r=r.next}while(r!==o)}function aa(o,t,e,i){var n=[],s,r,a,l,c;for(s=0,r=t.length;s<r;s++)a=t[s]*i,l=s<r-1?t[s+1]*i:o.length,c=go(o,a,l,i,!1),c===c.next&&(c.steiner=!0),n.push(ha(c));for(n.sort(la),s=0;s<n.length;s++)e=ca(n[s],e);return e}function la(o,t){return o.x-t.x}function ca(o,t){var e=ua(o,t);if(!e)return t;var i=po(e,o);return J(i,i.next),J(e,e.next)}function ua(o,t){var e=t,i=o.x,n=o.y,s=-1/0,r;do{if(n<=e.y&&n>=e.next.y&&e.next.y!==e.y){var a=e.x+(n-e.y)*(e.next.x-e.x)/(e.next.y-e.y);if(a<=i&&a>s&&(s=a,r=e.x<e.next.x?e:e.next,a===i))return r}e=e.next}while(e!==t);if(!r)return null;var l=r,c=r.x,u=r.y,f=1/0,d;e=r;do i>=e.x&&e.x>=c&&i!==e.x&&Q(n<u?i:s,n,c,u,n<u?s:i,n,e.x,e.y)&&(d=Math.abs(n-e.y)/(i-e.x),ht(e,o)&&(d<f||d===f&&(e.x>r.x||e.x===r.x&&fa(r,e)))&&(r=e,f=d)),e=e.next;while(e!==l);return r}function fa(o,t){return b(o.prev,o,t.prev)<0&&b(t.next,o,o.next)<0}function da(o,t,e,i){var n=o;do n.z===0&&(n.z=ge(n.x,n.y,t,e,i)),n.prevZ=n.prev,n.nextZ=n.next,n=n.next;while(n!==o);n.prevZ.nextZ=null,n.prevZ=null,ga(n)}function ga(o){var t,e,i,n,s,r,a,l,c=1;do{for(e=o,o=null,s=null,r=0;e;){for(r++,i=e,a=0,t=0;t<c&&(a++,i=i.nextZ,!!i);t++);for(l=c;a>0||l>0&&i;)a!==0&&(l===0||!i||e.z<=i.z)?(n=e,e=e.nextZ,a--):(n=i,i=i.nextZ,l--),s?s.nextZ=n:o=n,n.prevZ=s,s=n;e=i}s.nextZ=null,c*=2}while(r>1);return o}function ge(o,t,e,i,n){return o=(o-e)*n|0,t=(t-i)*n|0,o=(o|o<<8)&16711935,o=(o|o<<4)&252645135,o=(o|o<<2)&858993459,o=(o|o<<1)&1431655765,t=(t|t<<8)&16711935,t=(t|t<<4)&252645135,t=(t|t<<2)&858993459,t=(t|t<<1)&1431655765,o|t<<1}function ha(o){var t=o,e=o;do(t.x<e.x||t.x===e.x&&t.y<e.y)&&(e=t),t=t.next;while(t!==o);return e}function Q(o,t,e,i,n,s,r,a){return(n-r)*(t-a)>=(o-r)*(s-a)&&(o-r)*(i-a)>=(e-r)*(t-a)&&(e-r)*(s-a)>=(n-r)*(i-a)}function pa(o,t){return o.next.i!==t.i&&o.prev.i!==t.i&&!va(o,t)&&(ht(o,t)&&ht(t,o)&&ma(o,t)&&(b(o.prev,o,t.prev)||b(o,t.prev,t))||Ht(o,t)&&b(o.prev,o,o.next)>0&&b(t.prev,t,t.next)>0)}function b(o,t,e){return(t.y-o.y)*(e.x-t.x)-(t.x-o.x)*(e.y-t.y)}function Ht(o,t){return o.x===t.x&&o.y===t.y}function ho(o,t,e,i){var n=Pt(b(o,t,e)),s=Pt(b(o,t,i)),r=Pt(b(e,i,o)),a=Pt(b(e,i,t));return!!(n!==s&&r!==a||n===0&&Ct(o,e,t)||s===0&&Ct(o,i,t)||r===0&&Ct(e,o,i)||a===0&&Ct(e,t,i))}function Ct(o,t,e){return t.x<=Math.max(o.x,e.x)&&t.x>=Math.min(o.x,e.x)&&t.y<=Math.max(o.y,e.y)&&t.y>=Math.min(o.y,e.y)}function Pt(o){return o>0?1:o<0?-1:0}function va(o,t){var e=o;do{if(e.i!==o.i&&e.next.i!==o.i&&e.i!==t.i&&e.next.i!==t.i&&ho(e,e.next,o,t))return!0;e=e.next}while(e!==o);return!1}function ht(o,t){return b(o.prev,o,o.next)<0?b(o,t,o.next)>=0&&b(o,o.prev,t)>=0:b(o,t,o.prev)<0||b(o,o.next,t)<0}function ma(o,t){var e=o,i=!1,n=(o.x+t.x)/2,s=(o.y+t.y)/2;do e.y>s!=e.next.y>s&&e.next.y!==e.y&&n<(e.next.x-e.x)*(s-e.y)/(e.next.y-e.y)+e.x&&(i=!i),e=e.next;while(e!==o);return i}function po(o,t){var e=new he(o.i,o.x,o.y),i=new he(t.i,t.x,t.y),n=o.next,s=t.prev;return o.next=t,t.prev=o,e.next=n,n.prev=e,i.next=e,e.prev=i,s.next=i,i.prev=s,i}function li(o,t,e,i){var n=new he(o,t,e);return i?(n.next=i.next,n.prev=i,i.next.prev=n,i.next=n):(n.prev=n,n.next=n),n}function pt(o){o.next.prev=o.prev,o.prev.next=o.next,o.prevZ&&(o.prevZ.nextZ=o.nextZ),o.nextZ&&(o.nextZ.prevZ=o.prevZ)}function he(o,t,e){this.i=o,this.x=t,this.y=e,this.prev=null,this.next=null,this.z=0,this.prevZ=null,this.nextZ=null,this.steiner=!1}$t.deviation=function(o,t,e,i){var n=t&&t.length,s=n?t[0]*e:o.length,r=Math.abs(pe(o,0,s,e));if(n)for(var a=0,l=t.length;a<l;a++){var c=t[a]*e,u=a<l-1?t[a+1]*e:o.length;r-=Math.abs(pe(o,c,u,e))}var f=0;for(a=0;a<i.length;a+=3){var d=i[a]*e,g=i[a+1]*e,h=i[a+2]*e;f+=Math.abs((o[d]-o[h])*(o[g+1]-o[d+1])-(o[d]-o[g])*(o[h+1]-o[d+1]))}return r===0&&f===0?0:Math.abs((f-r)/r)};function pe(o,t,e,i){for(var n=0,s=t,r=e-i;s<e;s+=i)n+=(o[r]-o[s])*(o[s+1]+o[r+1]),r=s;return n}$t.flatten=function(o){for(var t=o[0][0].length,e={vertices:[],holes:[],dimensions:t},i=0,n=0;n<o.length;n++){for(var s=0;s<o[n].length;s++)for(var r=0;r<t;r++)e.vertices.push(o[n][s][r]);n>0&&(i+=o[n-1].length,e.holes.push(i))}return e};var ya=Le.exports;const xa=Yo(ya),bt=Pe.CLOCKWISE,ci=Pe.COUNTER_CLOCKWISE,H={};function _a(o){if(o=o&&o.positions||o,!Array.isArray(o)&&!ArrayBuffer.isView(o))throw new Error("invalid polygon")}function rt(o){return"positions"in o?o.positions:o}function It(o){return"holeIndices"in o?o.holeIndices:null}function Ca(o){return Array.isArray(o[0])}function Pa(o){return o.length>=1&&o[0].length>=2&&Number.isFinite(o[0][0])}function ba(o){const t=o[0],e=o[o.length-1];return t[0]===e[0]&&t[1]===e[1]&&t[2]===e[2]}function La(o,t,e,i){for(let n=0;n<t;n++)if(o[e+n]!==o[i-t+n])return!1;return!0}function ui(o,t,e,i,n){let s=t;const r=e.length;for(let a=0;a<r;a++)for(let l=0;l<i;l++)o[s++]=e[a][l]||0;if(!ba(e))for(let a=0;a<i;a++)o[s++]=e[0][a]||0;return H.start=t,H.end=s,H.size=i,be(o,n,H),s}function fi(o,t,e,i,n=0,s,r){s=s||e.length;const a=s-n;if(a<=0)return t;let l=t;for(let c=0;c<a;c++)o[l++]=e[n+c];if(!La(e,i,n,s))for(let c=0;c<i;c++)o[l++]=e[n+c];return H.start=t,H.end=l,H.size=i,be(o,r,H),l}function vo(o,t){_a(o);const e=[],i=[];if("positions"in o){const{positions:n,holeIndices:s}=o;if(s){let r=0;for(let a=0;a<=s.length;a++)r=fi(e,r,n,t,s[a-1],s[a],a===0?bt:ci),i.push(r);return i.pop(),{positions:e,holeIndices:i}}o=n}if(!Ca(o))return fi(e,0,o,t,0,e.length,bt),e;if(!Pa(o)){let n=0;for(const[s,r]of o.entries())n=ui(e,n,r,t,s===0?bt:ci),i.push(n);return i.pop(),{positions:e,holeIndices:i}}return ui(e,0,o,t,bt),e}function ee(o,t,e){const i=o.length/3;let n=0;for(let s=0;s<i;s++){const r=(s+1)%i;n+=o[s*3+t]*o[r*3+e],n-=o[r*3+t]*o[s*3+e]}return Math.abs(n/2)}function di(o,t,e,i){const n=o.length/3;for(let s=0;s<n;s++){const r=s*3,a=o[r+0],l=o[r+1],c=o[r+2];o[r+t]=a,o[r+e]=l,o[r+i]=c}}function Aa(o,t,e,i){let n=It(o);n&&(n=n.map(a=>a/t));let s=rt(o);const r=i&&t===3;if(e){const a=s.length;s=s.slice();const l=[];for(let c=0;c<a;c+=t){l[0]=s[c],l[1]=s[c+1],r&&(l[2]=s[c+2]);const u=e(l);s[c]=u[0],s[c+1]=u[1],r&&(s[c+2]=u[2])}}if(r){const a=ee(s,0,1),l=ee(s,0,2),c=ee(s,1,2);if(!a&&!l&&!c)return[];a>l&&a>c||(l>c?(e||(s=s.slice()),di(s,0,2,1)):(e||(s=s.slice()),di(s,2,0,1)))}return xa(s,n,t)}class Sa extends qi{constructor(t){const{fp64:e,IndexType:i=Uint32Array}=t;super({...t,attributes:{positions:{size:3,type:e?Float64Array:Float32Array},vertexValid:{type:Uint16Array,size:1},indices:{type:i,size:1}}})}get(t){const{attributes:e}=this;return t==="indices"?e.indices&&e.indices.subarray(0,this.vertexCount):e[t]}updateGeometry(t){super.updateGeometry(t);const e=this.buffers.indices;if(e)this.vertexCount=(e.value||e).length;else if(this.data&&!this.getGeometry)throw new Error("missing indices buffer")}normalizeGeometry(t){if(this.normalize){const e=vo(t,this.positionSize);return this.opts.resolution?ro(rt(e),It(e),{size:this.positionSize,gridResolution:this.opts.resolution,edgeTypes:!0}):this.opts.wrapLongitude?Nr(rt(e),It(e),{size:this.positionSize,maxLatitude:86,edgeTypes:!0}):e}return t}getGeometrySize(t){if(gi(t)){let e=0;for(const i of t)e+=this.getGeometrySize(i);return e}return rt(t).length/this.positionSize}getGeometryFromBuffer(t){return this.normalize||!this.buffers.indices?super.getGeometryFromBuffer(t):null}updateGeometryAttributes(t,e){if(t&&gi(t))for(const i of t){const n=this.getGeometrySize(i);e.geometrySize=n,this.updateGeometryAttributes(i,e),e.vertexStart+=n,e.indexStart=this.indexStarts[e.geometryIndex+1]}else{const i=t;this._updateIndices(i,e),this._updatePositions(i,e),this._updateVertexValid(i,e)}}_updateIndices(t,{geometryIndex:e,vertexStart:i,indexStart:n}){const{attributes:s,indexStarts:r,typedArrayManager:a}=this;let l=s.indices;if(!l||!t)return;let c=n;const u=Aa(t,this.positionSize,this.opts.preproject,this.opts.full3d);l=a.allocate(l,n+u.length,{copy:!0});for(let f=0;f<u.length;f++)l[c++]=u[f]+i;r[e+1]=n+u.length,s.indices=l}_updatePositions(t,{vertexStart:e,geometrySize:i}){const{attributes:{positions:n},positionSize:s}=this;if(!n||!t)return;const r=rt(t);for(let a=e,l=0;l<i;a++,l++){const c=r[l*s],u=r[l*s+1],f=s>2?r[l*s+2]:0;n[a*3]=c,n[a*3+1]=u,n[a*3+2]=f}}_updateVertexValid(t,{vertexStart:e,geometrySize:i}){const{positionSize:n}=this,s=this.attributes.vertexValid,r=t&&It(t);if(t&&t.edgeTypes?s.set(t.edgeTypes,e):s.fill(1,e,e+i),r)for(let a=0;a<r.length;a++)s[e+r[a]/n-1]=0;s[e+i-1]=0}}function gi(o){return Array.isArray(o)&&o.length>0&&!Number.isFinite(o[0])}const hi=`layout(std140) uniform solidPolygonUniforms {
  bool extruded;
  bool isWireframe;
  float elevationScale;
} solidPolygon;
`,Ta={name:"solidPolygon",vs:hi,fs:hi,uniformTypes:{extruded:"f32",isWireframe:"f32",elevationScale:"f32"}},mo=`in vec4 fillColors;
in vec4 lineColors;
in vec3 pickingColors;
out vec4 vColor;
struct PolygonProps {
vec3 positions;
vec3 positions64Low;
vec3 normal;
float elevations;
};
vec3 project_offset_normal(vec3 vector) {
if (project.coordinateSystem == COORDINATE_SYSTEM_LNGLAT ||
project.coordinateSystem == COORDINATE_SYSTEM_LNGLAT_OFFSETS) {
return normalize(vector * project.commonUnitsPerWorldUnit);
}
return project_normal(vector);
}
void calculatePosition(PolygonProps props) {
vec3 pos = props.positions;
vec3 pos64Low = props.positions64Low;
vec3 normal = props.normal;
vec4 colors = solidPolygon.isWireframe ? lineColors : fillColors;
geometry.worldPosition = props.positions;
geometry.pickingColor = pickingColors;
if (solidPolygon.extruded) {
pos.z += props.elevations * solidPolygon.elevationScale;
}
gl_Position = project_position_to_clipspace(pos, pos64Low, vec3(0.), geometry.position);
DECKGL_FILTER_GL_POSITION(gl_Position, geometry);
if (solidPolygon.extruded) {
#ifdef IS_SIDE_VERTEX
normal = project_offset_normal(normal);
#else
normal = project_normal(normal);
#endif
geometry.normal = normal;
vec3 lightColor = lighting_getLightColor(colors.rgb, project.cameraPosition, geometry.position.xyz, geometry.normal);
vColor = vec4(lightColor, colors.a * layer.opacity);
} else {
vColor = vec4(colors.rgb, colors.a * layer.opacity);
}
DECKGL_FILTER_COLOR(vColor, geometry);
}
`,wa=`#version 300 es
#define SHADER_NAME solid-polygon-layer-vertex-shader
in vec3 vertexPositions;
in vec3 vertexPositions64Low;
in float elevations;
${mo}
void main(void) {
PolygonProps props;
props.positions = vertexPositions;
props.positions64Low = vertexPositions64Low;
props.elevations = elevations;
props.normal = vec3(0.0, 0.0, 1.0);
calculatePosition(props);
}
`,Ea=`#version 300 es
#define SHADER_NAME solid-polygon-layer-vertex-shader-side
#define IS_SIDE_VERTEX
in vec2 positions;
in vec3 vertexPositions;
in vec3 nextVertexPositions;
in vec3 vertexPositions64Low;
in vec3 nextVertexPositions64Low;
in float elevations;
in float instanceVertexValid;
${mo}
void main(void) {
if(instanceVertexValid < 0.5){
gl_Position = vec4(0.);
return;
}
PolygonProps props;
vec3 pos;
vec3 pos64Low;
vec3 nextPos;
vec3 nextPos64Low;
#if RING_WINDING_ORDER_CW == 1
pos = vertexPositions;
pos64Low = vertexPositions64Low;
nextPos = nextVertexPositions;
nextPos64Low = nextVertexPositions64Low;
#else
pos = nextVertexPositions;
pos64Low = nextVertexPositions64Low;
nextPos = vertexPositions;
nextPos64Low = vertexPositions64Low;
#endif
props.positions = mix(pos, nextPos, positions.x);
props.positions64Low = mix(pos64Low, nextPos64Low, positions.x);
props.normal = vec3(
pos.y - nextPos.y + (pos64Low.y - nextPos64Low.y),
nextPos.x - pos.x + (nextPos64Low.x - pos64Low.x),
0.0);
props.elevations = elevations * positions.y;
calculatePosition(props);
}
`,Ia=`#version 300 es
#define SHADER_NAME solid-polygon-layer-fragment-shader
precision highp float;
in vec4 vColor;
out vec4 fragColor;
void main(void) {
fragColor = vColor;
geometry.uv = vec2(0.);
DECKGL_FILTER_COLOR(fragColor, geometry);
}
`,Ut=[0,0,0,255],Ma={filled:!0,extruded:!1,wireframe:!1,_normalize:!0,_windingOrder:"CW",_full3d:!1,elevationScale:{type:"number",min:0,value:1},getPolygon:{type:"accessor",value:o=>o.polygon},getElevation:{type:"accessor",value:1e3},getFillColor:{type:"accessor",value:Ut},getLineColor:{type:"accessor",value:Ut},material:!0},Lt={enter:(o,t)=>t.length?t.subarray(t.length-o.length):o};class Yt extends k{getShaders(t){return super.getShaders({vs:t==="top"?wa:Ea,fs:Ia,defines:{RING_WINDING_ORDER_CW:!this.props._normalize&&this.props._windingOrder==="CCW"?0:1},modules:[G,Nt,j,Ta]})}get wrapLongitude(){return!1}getBounds(){var t;return(t=this.getAttributeManager())==null?void 0:t.getBounds(["vertexPositions"])}initializeState(){const{viewport:t}=this.context;let{coordinateSystem:e}=this.props;const{_full3d:i}=this.props;t.isGeospatial&&e==="default"&&(e="lnglat");let n;e==="lnglat"&&(i?n=t.projectPosition.bind(t):n=t.projectFlat.bind(t)),this.setState({numInstances:0,polygonTesselator:new Sa({preproject:n,fp64:this.use64bitPositions(),IndexType:Uint32Array})});const s=this.getAttributeManager(),r=!0;s.remove(["instancePickingColors"]),s.add({indices:{size:1,isIndexed:!0,update:this.calculateIndices,noAlloc:r},vertexPositions:{size:3,type:"float64",stepMode:"dynamic",fp64:this.use64bitPositions(),transition:Lt,accessor:"getPolygon",update:this.calculatePositions,noAlloc:r,shaderAttributes:{nextVertexPositions:{vertexOffset:1}}},instanceVertexValid:{size:1,type:"uint16",stepMode:"instance",update:this.calculateVertexValid,noAlloc:r},elevations:{size:1,stepMode:"dynamic",transition:Lt,accessor:"getElevation"},fillColors:{size:this.props.colorFormat.length,type:"unorm8",stepMode:"dynamic",transition:Lt,accessor:"getFillColor",defaultValue:Ut},lineColors:{size:this.props.colorFormat.length,type:"unorm8",stepMode:"dynamic",transition:Lt,accessor:"getLineColor",defaultValue:Ut},pickingColors:{size:4,type:"uint8",stepMode:"dynamic",accessor:(a,{index:l,target:c})=>this.encodePickingColor(a&&a.__source?a.__source.index:l,c)}})}getPickingInfo(t){const e=super.getPickingInfo(t),{index:i}=e,n=this.props.data;return n[0]&&n[0].__source&&(e.object=n.find(s=>s.__source.index===i)),e}disablePickingIndex(t){const e=this.props.data;if(e[0]&&e[0].__source)for(let i=0;i<e.length;i++)e[i].__source.index===t&&this._disablePickingIndex(i);else super.disablePickingIndex(t)}draw({uniforms:t}){const{extruded:e,filled:i,wireframe:n,elevationScale:s}=this.props,{topModel:r,sideModel:a,wireframeModel:l,polygonTesselator:c}=this.state,u={extruded:!!e,elevationScale:s,isWireframe:!1};l&&n&&(l.setInstanceCount(c.instanceCount-1),l.shaderInputs.setProps({solidPolygon:{...u,isWireframe:!0}}),l.draw(this.context.renderPass)),a&&i&&(a.setInstanceCount(c.instanceCount-1),a.shaderInputs.setProps({solidPolygon:u}),a.draw(this.context.renderPass)),r&&i&&(r.setVertexCount(c.vertexCount),r.shaderInputs.setProps({solidPolygon:u}),r.draw(this.context.renderPass))}updateState(t){var a;super.updateState(t),this.updateGeometry(t);const{props:e,oldProps:i,changeFlags:n}=t,s=this.getAttributeManager();(n.extensionsChanged||e.filled!==i.filled||e.extruded!==i.extruded)&&((a=this.state.models)==null||a.forEach(l=>l.destroy()),this.setState(this._getModels()),s.invalidateAll())}updateGeometry({props:t,oldProps:e,changeFlags:i}){if(i.dataChanged||i.updateTriggersChanged&&(i.updateTriggersChanged.all||i.updateTriggersChanged.getPolygon)){const{polygonTesselator:s}=this.state,r=t.data.attributes||{};s.updateGeometry({data:t.data,normalize:t._normalize,geometryBuffer:r.getPolygon,buffers:r,getGeometry:t.getPolygon,positionFormat:t.positionFormat,wrapLongitude:t.wrapLongitude,resolution:this.context.viewport.resolution,fp64:this.use64bitPositions(),dataChanged:i.dataChanged,full3d:t._full3d}),this.setState({numInstances:s.instanceCount,startIndices:s.vertexStarts}),i.dataChanged||this.getAttributeManager().invalidateAll()}}_getModels(){const{id:t,filled:e,extruded:i}=this.props;let n,s,r;if(e){const a=this.getShaders("top");a.defines.NON_INSTANCED_MODEL=1;const l=this.getAttributeManager().getBufferLayouts({isInstanced:!1});n=new M(this.context.device,{...a,id:`${t}-top`,topology:"triangle-list",bufferLayout:l,isIndexed:!0,userData:{excludeAttributes:{instanceVertexValid:!0}}})}if(i){const a=this.getAttributeManager().getBufferLayouts({isInstanced:!0});s=new M(this.context.device,{...this.getShaders("side"),id:`${t}-side`,bufferLayout:a,geometry:new N({topology:"triangle-strip",attributes:{positions:{size:2,value:new Float32Array([1,0,0,0,1,1,0,1])}}}),isInstanced:!0,userData:{excludeAttributes:{indices:!0}}}),r=new M(this.context.device,{...this.getShaders("side"),id:`${t}-wireframe`,bufferLayout:a,geometry:new N({topology:"line-strip",attributes:{positions:{size:2,value:new Float32Array([1,0,0,0,0,1,1,1])}}}),isInstanced:!0,userData:{excludeAttributes:{indices:!0}}})}return{models:[s,r,n].filter(Boolean),topModel:n,sideModel:s,wireframeModel:r}}calculateIndices(t){const{polygonTesselator:e}=this.state;t.startIndices=e.indexStarts,t.value=e.get("indices")}calculatePositions(t){const{polygonTesselator:e}=this.state;t.startIndices=e.vertexStarts,t.value=e.get("positions")}calculateVertexValid(t){t.value=this.state.polygonTesselator.get("vertexValid")}}Yt.defaultProps=Ma;Yt.layerName="SolidPolygonLayer";function yo({data:o,getIndex:t,dataRange:e,replace:i}){const{startRow:n=0,endRow:s=1/0}=e,r=o.length;let a=r,l=r;for(let d=0;d<r;d++){const g=t(o[d]);if(a>d&&g>=n&&(a=d),g>=s){l=d;break}}let c=a;const f=l-a!==i.length?o.slice(l):void 0;for(let d=0;d<i.length;d++)o[c++]=i[d];if(f){for(let d=0;d<f.length;d++)o[c++]=f[d];o.length=c}return{startRow:a,endRow:a+i.length}}const xo=[0,0,0,255],Ra=[0,0,0,255],Oa={stroked:!0,filled:!0,extruded:!1,elevationScale:1,wireframe:!1,_normalize:!0,_windingOrder:"CW",lineWidthUnits:"meters",lineWidthScale:1,lineWidthMinPixels:0,lineWidthMaxPixels:Number.MAX_SAFE_INTEGER,lineJointRounded:!1,lineMiterLimit:4,getPolygon:{type:"accessor",value:o=>o.polygon},getFillColor:{type:"accessor",value:Ra},getLineColor:{type:"accessor",value:xo},getLineWidth:{type:"accessor",value:1},getElevation:{type:"accessor",value:1e3},material:!0};class _o extends jt{initializeState(){this.state={paths:[],pathsDiff:null},this.props.getLineDashArray&&S.removed("getLineDashArray","PathStyleExtension")()}updateState({changeFlags:t}){const e=t.dataChanged||t.updateTriggersChanged&&(t.updateTriggersChanged.all||t.updateTriggersChanged.getPolygon);if(e&&Array.isArray(t.dataChanged)){const i=this.state.paths.slice(),n=t.dataChanged.map(s=>yo({data:i,getIndex:r=>r.__source.index,dataRange:s,replace:this._getPaths(s)}));this.setState({paths:i,pathsDiff:n})}else e&&this.setState({paths:this._getPaths(),pathsDiff:null})}_getPaths(t={}){const{data:e,getPolygon:i,positionFormat:n,_normalize:s}=this.props,r=[],a=n==="XY"?2:3,{startRow:l,endRow:c}=t,{iterable:u,objectInfo:f}=it(e,l,c);for(const d of u){f.index++;let g=i(d,f);s&&(g=vo(g,a));const{holeIndices:h}=g,p=g.positions||g;if(h)for(let v=0;v<=h.length;v++){const x=p.slice(h[v-1]||0,h[v]||p.length);r.push(this.getSubLayerRow({path:x},d,f.index))}else r.push(this.getSubLayerRow({path:p},d,f.index))}return r}renderLayers(){const{data:t,_dataDiff:e,stroked:i,filled:n,extruded:s,wireframe:r,_normalize:a,_windingOrder:l,elevationScale:c,transitions:u,positionFormat:f}=this.props,{lineWidthUnits:d,lineWidthScale:g,lineWidthMinPixels:h,lineWidthMaxPixels:p,lineJointRounded:v,lineMiterLimit:x,lineDashJustified:_}=this.props,{getFillColor:y,getLineColor:m,getLineWidth:C,getLineDashArray:L,getElevation:R,getPolygon:w,updateTriggers:P,material:T}=this.props,{paths:I,pathsDiff:z}=this.state,V=this.getSubLayerClass("fill",Yt),ot=this.getSubLayerClass("stroke",Wt),vt=this.shouldRenderSubLayer("fill",I)&&new V({_dataDiff:e,extruded:s,elevationScale:c,filled:n,wireframe:r,_normalize:a,_windingOrder:l,getElevation:R,getFillColor:y,getLineColor:s&&r?m:xo,material:T,transitions:u},this.getSubLayerProps({id:"fill",updateTriggers:P&&{getPolygon:P.getPolygon,getElevation:P.getElevation,getFillColor:P.getFillColor,lineColors:s&&r,getLineColor:P.getLineColor}}),{data:t,positionFormat:f,getPolygon:w}),E=!s&&i&&this.shouldRenderSubLayer("stroke",I)&&new ot({_dataDiff:z&&(()=>z),widthUnits:d,widthScale:g,widthMinPixels:h,widthMaxPixels:p,jointRounded:v,miterLimit:x,dashJustified:_,_pathType:"loop",transitions:u&&{getWidth:u.getLineWidth,getColor:u.getLineColor,getPath:u.getPolygon},getColor:this.getSubLayerAccessor(m),getWidth:this.getSubLayerAccessor(C),getDashArray:this.getSubLayerAccessor(L)},this.getSubLayerProps({id:"stroke",updateTriggers:P&&{getWidth:P.getLineWidth,getColor:P.getLineColor,getDashArray:P.getLineDashArray}}),{data:I,positionFormat:f,getPath:A=>A.path});return[!s&&vt,E,s&&vt]}}_o.layerName="PolygonLayer";_o.defaultProps=Oa;function za(o,t){if(!o)return null;const e="startIndices"in o?o.startIndices[t]:t,i=o.featureIds.value[e];return e!==-1?Fa(o,i,e):null}function Fa(o,t,e){const i={properties:{...o.properties[t]}};for(const n in o.numericProps)i.properties[n]=o.numericProps[n].value[e];return i}function ka(o,t){const e={points:null,lines:null,polygons:null};for(const i in e){const n=o[i].globalFeatureIds.value;e[i]=new Uint8ClampedArray(n.length*4);const s=[];for(let r=0;r<n.length;r++)t(n[r],s),e[i][r*4+0]=s[0],e[i][r*4+1]=s[1],e[i][r*4+2]=s[2],e[i][r*4+3]=255}return e}const pi=`layout(std140) uniform sdfUniforms {
  float gamma;
  bool enabled;
  float buffer;
  float outlineBuffer;
  vec4 outlineColor;
} sdf;
`,Ba={name:"sdf",vs:pi,fs:pi,uniformTypes:{gamma:"f32",enabled:"f32",buffer:"f32",outlineBuffer:"f32",outlineColor:"vec4<f32>"}},at={none:0,start:1,center:2,end:3},Ua=`layout(std140) uniform textUniforms {
  highp vec2 cutoffPixels;
  highp ivec2 align;
  highp float fontSize;
  bool flipY;
} text;

#define ALIGN_MODE_START ${at.start}
#define ALIGN_MODE_CENTER ${at.center}
#define ALIGN_MODE_END ${at.end}
`,Co={name:"text",vs:Ua,getUniforms:({contentCutoffPixels:o=[0,0],contentAlignHorizontal:t="none",contentAlignVertical:e="none",fontSize:i,viewport:n})=>({cutoffPixels:o,align:[at[t],at[e]],fontSize:i,flipY:(n==null?void 0:n.flipY)??!1}),uniformTypes:{cutoffPixels:"vec2<f32>",align:"vec2<i32>",fontSize:"f32",flipY:"f32"}},Da=`#version 300 es
#define SHADER_NAME multi-icon-layer-vertex-shader
in vec2 positions;
in vec3 instancePositions;
in vec3 instancePositions64Low;
in float instanceSizes;
in float instanceAngles;
in vec4 instanceColors;
in vec3 instancePickingColors;
in vec4 instanceIconFrames;
in float instanceColorModes;
in vec2 instanceOffsets;
in vec2 instancePixelOffset;
in vec4 instanceClipRect;
out float vColorMode;
out vec4 vColor;
out vec2 vTextureCoords;
out vec2 uv;
vec2 rotate_by_angle(vec2 vertex, float angle) {
float angle_radian = angle * PI / 180.0;
float cos_angle = cos(angle_radian);
float sin_angle = sin(angle_radian);
mat2 rotationMatrix = mat2(cos_angle, -sin_angle, sin_angle, cos_angle);
return rotationMatrix * vertex;
}
float getPixelOffsetFromAlignment(float anchor, float extent, float clipStart, float clipEnd, int mode) {
if (clipEnd < clipStart) return 0.0;
if (mode == ALIGN_MODE_START) {
return max(- (anchor + clipStart), 0.0);
}
if (mode == ALIGN_MODE_CENTER) {
float _min = max(0., anchor + clipStart);
float _max = min(extent, anchor + clipEnd);
return _min < _max ? (_min + _max) / 2.0 - anchor : 0.0;
}
if (mode == ALIGN_MODE_END) {
return min(extent - (anchor + clipEnd), 0.);
}
return 0.0;
}
void main(void) {
geometry.worldPosition = instancePositions;
geometry.uv = positions;
geometry.pickingColor = instancePickingColors;
uv = positions;
vec2 iconSize = instanceIconFrames.zw;
float sizePixels = clamp(
project_size_to_pixel(instanceSizes * icon.sizeScale, icon.sizeUnits),
icon.sizeMinPixels, icon.sizeMaxPixels
);
float instanceScale = sizePixels / text.fontSize;
vec2 pixelOffset = positions / 2.0 * iconSize + instanceOffsets;
pixelOffset = rotate_by_angle(pixelOffset, instanceAngles) * instanceScale;
pixelOffset += instancePixelOffset;
pixelOffset.y *= -1.0;
vec2 anchorPosScreen;
if (icon.billboard)  {
gl_Position = project_position_to_clipspace(instancePositions, instancePositions64Low, vec3(0.0), geometry.position);
anchorPosScreen = gl_Position.xy / gl_Position.w;
DECKGL_FILTER_GL_POSITION(gl_Position, geometry);
vec3 offset = vec3(pixelOffset, 0.0);
DECKGL_FILTER_SIZE(offset, geometry);
gl_Position.xy += project_pixel_size_to_clipspace(offset.xy);
} else {
vec3 offset_common = vec3(project_pixel_size(pixelOffset), 0.0);
if (text.flipY) {
offset_common.y *= -1.;
}
DECKGL_FILTER_SIZE(offset_common, geometry);
vec4 anchorPos = project_position_to_clipspace(instancePositions, instancePositions64Low, vec3(0.0));
anchorPosScreen = anchorPos.xy / anchorPos.w;
gl_Position = project_position_to_clipspace(instancePositions, instancePositions64Low, offset_common, geometry.position);
DECKGL_FILTER_GL_POSITION(gl_Position, geometry);
}
anchorPosScreen = vec2(anchorPosScreen.x + 1.0, 1.0 - anchorPosScreen.y) / 2.0 * project.viewportSize / project.devicePixelRatio;
vec2 xy = project_size_to_pixel(instanceClipRect.xy);
vec2 wh = project_size_to_pixel(instanceClipRect.zw);
if (text.flipY) {
xy.y = -xy.y - wh.y;
}
if (text.align.x > 0 || text.align.y > 0) {
vec2 viewportPixels = project.viewportSize / project.devicePixelRatio;
vec2 scrollPixels = vec2(
getPixelOffsetFromAlignment(anchorPosScreen.x, viewportPixels.x, xy.x, xy.x + wh.x, text.align.x),
-getPixelOffsetFromAlignment(anchorPosScreen.y, viewportPixels.y, -xy.y - wh.y, -xy.y, text.align.y)
);
pixelOffset += scrollPixels;
gl_Position.xy += project_pixel_size_to_clipspace(scrollPixels);
}
if (instanceClipRect.z >= 0.) {
if (pixelOffset.x < xy.x || pixelOffset.x > xy.x + wh.x) {
gl_Position = vec4(0.0);
}
else if (text.cutoffPixels.x > 0.) {
float vpWidth = project.viewportSize.x / project.devicePixelRatio;
float l = max(anchorPosScreen.x + xy.x, 0.0);
float r = min(anchorPosScreen.x + xy.x + wh.x, vpWidth);
if (r - l < text.cutoffPixels.x) {
gl_Position = vec4(0.0);
}
}
}
if (instanceClipRect.w >= 0.) {
if (pixelOffset.y < xy.y || pixelOffset.y > xy.y + wh.y) {
gl_Position = vec4(0.0);
}
else if (text.cutoffPixels.y > 0.) {
float vpHeight = project.viewportSize.y / project.devicePixelRatio;
float t = max(anchorPosScreen.y - xy.y - wh.y, 0.0);
float b = min(anchorPosScreen.y - xy.y, vpHeight);
if (b - t < text.cutoffPixels.y) {
gl_Position = vec4(0.0);
}
}
}
vTextureCoords = mix(
instanceIconFrames.xy,
instanceIconFrames.xy + iconSize,
(positions.xy + 1.0) / 2.0
) / icon.iconsTextureDim;
vColor = instanceColors;
DECKGL_FILTER_COLOR(vColor, geometry);
vColorMode = instanceColorModes;
}
`,Na=`#version 300 es
#define SHADER_NAME multi-icon-layer-fragment-shader
precision highp float;
uniform sampler2D iconsTexture;
in vec4 vColor;
in vec2 vTextureCoords;
in vec2 uv;
out vec4 fragColor;
void main(void) {
geometry.uv = uv;
if (!bool(picking.isActive)) {
float alpha = texture(iconsTexture, vTextureCoords).a;
vec4 color = vColor;
if (sdf.enabled) {
float distance = alpha;
alpha = smoothstep(sdf.buffer - sdf.gamma, sdf.buffer + sdf.gamma, distance);
if (sdf.outlineBuffer > 0.0) {
float inFill = alpha;
float inBorder = smoothstep(sdf.outlineBuffer - sdf.gamma, sdf.outlineBuffer + sdf.gamma, distance);
color = mix(sdf.outlineColor, vColor, inFill);
alpha = inBorder;
}
}
float a = alpha * color.a;
if (a < icon.alphaCutoff) {
discard;
}
fragColor = vec4(color.rgb, a * layer.opacity);
}
DECKGL_FILTER_COLOR(fragColor, geometry);
}
`,ie=192/256,Ga={getIconOffsets:{type:"accessor",value:o=>o.offsets},getContentBox:{type:"accessor",value:[0,0,-1,-1]},fontSize:1,alphaCutoff:.001,smoothing:.1,outlineWidth:0,outlineColor:{type:"color",value:[0,0,0,255]},contentCutoffPixels:{type:"array",value:[0,0]},contentAlignHorizontal:"none",contentAlignVertical:"none"};class Ae extends Vt{getShaders(){const t=super.getShaders();return{...t,modules:[...t.modules,Co,Ba],vs:Da,fs:Na}}initializeState(){super.initializeState();const t=this.getAttributeManager(),e=t.attributes.instanceIconDefs;e.settings.update=this.calculateInstanceIconDefs,t.addInstanced({instancePickingColors:{type:"uint8",size:4,accessor:(i,{index:n,target:s})=>this.encodePickingColor(n,s)},instanceClipRect:{size:4,accessor:"getContentBox",defaultValue:[0,0,-1,-1]}})}updateState(t){super.updateState(t);const{props:e,oldProps:i,changeFlags:n}=t,{outlineColor:s}=e;if(n.updateTriggersChanged&&(n.updateTriggersChanged.getIcon||n.updateTriggersChanged.getIconOffsets)&&this.getAttributeManager().invalidate("instanceIconDefs"),s!==i.outlineColor){const r=[s[0]/255,s[1]/255,s[2]/255,(s[3]??255)/255];this.setState({outlineColor:r})}!e.sdf&&e.outlineWidth&&S.warn(`${this.id}: fontSettings.sdf is required to render outline`)()}draw(t){const{sdf:e,smoothing:i,fontSize:n,outlineWidth:s,contentCutoffPixels:r,contentAlignHorizontal:a,contentAlignVertical:l}=this.props,{outlineColor:c}=this.state,u=s?Math.max(i,ie*(1-s)):-1,f=this.state.model,d={buffer:ie,outlineBuffer:u,gamma:i,enabled:!!e,outlineColor:c},g={contentCutoffPixels:r,contentAlignHorizontal:a,contentAlignVertical:l,fontSize:n,viewport:this.context.viewport};if(f.shaderInputs.setProps({sdf:d,text:g}),super.draw(t),e&&s){const{iconManager:h}=this.state;h.getTexture()&&(f.shaderInputs.setProps({sdf:{...d,outlineBuffer:ie}}),f.draw(this.context.renderPass))}}calculateInstanceIconDefs(t,{startRow:e,endRow:i}){const{data:n,getIcon:s,getIconOffsets:r}=this.props;let a=t.getVertexOffset(e);const l=t.value,{iterable:c,objectInfo:u}=it(n,e,i);for(const f of c){u.index++;const d=s(f,u),g=r(f,u);if(d){let h=0;for(const p of Array.from(d)){const v=super.getInstanceIconDef(p);v[0]=g[h*2],v[1]+=g[h*2+1],v[6]=1,l.set(v,a),a+=t.size,h++}}}}}Ae.defaultProps=Ga;Ae.layerName="MultiIconLayer";const lt=1e20,Se=new Float64Array(256);for(let o=0;o<256;o++){const t=.5-Math.pow(o/255,.45454545454545453);Se[o]=t*Math.abs(t)}Se[255]=-lt;class ja{constructor({fontSize:t=24,buffer:e=3,radius:i=8,cutoff:n=.25,fontFamily:s="sans-serif",fontWeight:r="normal",fontStyle:a="normal",lang:l=null}={}){this.buffer=e,this.radius=i,this.cutoff=n,this.lang=l;const c=this.size=t+e*4,u=this._createCanvas(c),f=this.ctx=u.getContext("2d",{willReadFrequently:!0});f.font=`${a} ${r} ${t}px ${s}`,f.textBaseline="alphabetic",f.textAlign="left",f.fillStyle="black",this.gridOuter=new Float64Array(c*c),this.gridInner=new Float64Array(c*c),this.f=new Float64Array(c),this.z=new Float64Array(c+1),this.v=new Uint16Array(c)}_createCanvas(t){if(typeof OffscreenCanvas<"u")return new OffscreenCanvas(t,t);const e=document.createElement("canvas");return e.width=e.height=t,e}draw(t){const{width:e,actualBoundingBoxAscent:i,actualBoundingBoxDescent:n,actualBoundingBoxLeft:s,actualBoundingBoxRight:r}=this.ctx.measureText(t),a=Math.ceil(i),l=Math.floor(-s),c=Math.max(0,Math.min(this.size-this.buffer,Math.ceil(r)-l)),u=Math.max(0,Math.min(this.size-this.buffer,a+Math.ceil(n))),f=c+2*this.buffer,d=u+2*this.buffer,g=Math.max(f*d,0),h=new Uint8ClampedArray(g),p={data:h,width:f,height:d,glyphWidth:c,glyphHeight:u,glyphTop:a,glyphLeft:l,glyphAdvance:e};if(c===0||u===0)return p;const{ctx:v,buffer:x,gridInner:_,gridOuter:y}=this;this.lang&&(v.lang=this.lang),v.clearRect(x,x,c,u),v.fillText(t,x-l,x+a);const m=v.getImageData(x,x,c,u);y.fill(lt,0,g),_.fill(0,0,g);let C=3;for(let P=0;P<u;P++){let T=(P+x)*f+x;for(let I=0;I<c;I++,C+=4,T++){const z=m.data[C];if(z===0)continue;const V=Se[z];y[T]=Math.max(0,V),_[T]=Math.max(0,-V)}}vi(y,0,0,f,d,f,this.f,this.v,this.z);const L=Math.min(x,1);vi(_,x-L,x-L,c+2*L,u+2*L,f,this.f,this.v,this.z);const R=255/this.radius,w=255*(1-this.cutoff);for(let P=0;P<g;P++){const T=Math.sqrt(y[P])-Math.sqrt(_[P]);h[P]=Math.round(w-R*T)}return p}}function vi(o,t,e,i,n,s,r,a,l){for(let c=t;c<t+i;c++)mi(o,e*s+c,s,n,r,a,l);for(let c=e;c<e+n;c++)mi(o,c*s+t,1,i,r,a,l)}function mi(o,t,e,i,n,s,r){s[0]=0,r[0]=-lt,r[1]=lt,n[0]=o[t];for(let a=1,l=0,c=0;a<i;a++){n[a]=o[t+a*e];const u=a*a;do{const f=s[l];c=(n[a]-n[f]+u-f*f)/(a-f)/2}while(c<=r[l]&&--l>-1);l++,s[l]=a,r[l]=c,r[l+1]=lt}for(let a=0,l=0;a<i;a++){for(;r[l+1]<a;)l++;const c=s[l],u=a-c;o[t+a*e]=n[c]+u*u}}const Va=32,Wa=[];function $a(o){return Math.pow(2,Math.ceil(Math.log2(o)))}function Ha({characterSet:o,measureText:t,buffer:e,maxCanvasWidth:i,mapping:n={},xOffset:s=0,yOffsetMin:r=0,yOffsetMax:a=0}){let l=s,c=r,u=a;for(const f of o)if(!n[f]){const{advance:d,width:g,ascent:h,descent:p}=t(f),v=h+p;l+g+e*2>i&&(l=0,c=u),n[f]={x:l+e,y:c+e,width:g,height:v,advance:d,anchorX:g/2,anchorY:h},l+=g+e*2,u=Math.max(u,c+v+e*2)}return{mapping:n,xOffset:l,yOffsetMin:c,yOffsetMax:u,canvasHeight:$a(u)}}function Po(o,t,e,i){var s;let n=0;for(let r=t;r<e;r++){const a=o[r];n+=((s=i[a])==null?void 0:s.advance)||0}return n}function bo(o,t,e,i,n,s){let r=t,a=0;for(let l=t;l<e;l++){const c=Po(o,l,l+1,n);a+c>i&&(r<l&&s.push(l),r=l,a=0),a+=c}return a}function Ya(o,t,e,i,n,s){let r=t,a=t,l=t,c=0;for(let u=t;u<e;u++)if((o[u]===" "||o[u+1]===" "||u+1===e)&&(l=u+1),l>a){let f=Po(o,a,l,n);c+f>i&&(r<a&&(s.push(a),r=a,c=0),f>i&&(f=bo(o,a,l,i,n,s),r=s[s.length-1])),a=l,c+=f}return c}function Za(o,t,e,i,n=0,s){s===void 0&&(s=o.length);const r=[];return t==="break-all"?bo(o,n,s,e,i,r):Ya(o,n,s,e,i,r),r}function Ka(o,t,e,i,n,s){let r=0,a=0;for(let l=t;l<e;l++){const c=o[l],u=i[c];u&&(a=Math.max(a,u.height))}for(let l=t;l<e;l++){const c=o[l],u=i[c];u?(n[l]=r+u.anchorX,r+=u.advance):(S.warn(`Missing character: ${c} (${c.codePointAt(0)})`)(),n[l]=r,r+=Va)}s[0]=r,s[1]=a}function Xa(o,t,e,i,n,s){const r=Array.from(o),a=r.length,l=new Array(a),c=new Array(a),u=new Array(a),f=(i==="break-word"||i==="break-all")&&isFinite(n)&&n>0,d=[0,0],g=[0,0];let h=0,p=t+e/2,v=0,x=0;for(let _=0;_<=a;_++){const y=r[_];if((y===`
`||_===a)&&(x=_),x>v){const m=f?Za(r,i,n,s,v,x):Wa;for(let C=0;C<=m.length;C++){const L=C===0?v:m[C-1],R=C<m.length?m[C]:x;Ka(r,L,R,s,l,g);for(let w=L;w<R;w++)c[w]=p,u[w]=g[0];h++,p+=e,d[0]=Math.max(d[0],g[0])}v=x}y===`
`&&(l[v]=0,c[v]=0,u[v]=0,v++)}return d[1]=h*e,{x:l,y:c,rowWidth:u,size:d}}function qa({value:o,length:t,stride:e,offset:i,startIndices:n,characterSet:s}){const r=o.BYTES_PER_ELEMENT,a=e?e/r:1,l=i?i/r:0,c=n[t]||Math.ceil((o.length-l)/a),u=s&&new Set,f=new Array(t);let d=o;if(a>1||l>0){const g=o.constructor;d=new g(c);for(let h=0;h<c;h++)d[h]=o[h*a+l]}for(let g=0;g<t;g++){const h=n[g],p=n[g+1]||c,v=d.subarray(h,p);f[g]=String.fromCodePoint.apply(null,v),u&&v.forEach(u.add,u)}if(u)for(const g of u)s.add(String.fromCodePoint(g));return{texts:f,characterCount:c}}class Lo{constructor(t=5){this._cache={},this._order=[],this.limit=t}get(t){const e=this._cache[t];return e&&(this._deleteOrder(t),this._appendOrder(t)),e}set(t,e){this._cache[t]?(this.delete(t),this._cache[t]=e,this._appendOrder(t)):(Object.keys(this._cache).length===this.limit&&this.delete(this._order[0]),this._cache[t]=e,this._appendOrder(t))}delete(t){this._cache[t]&&(delete this._cache[t],this._deleteOrder(t))}_deleteOrder(t){const e=this._order.indexOf(t);e>=0&&this._order.splice(e,1)}_appendOrder(t){this._order.push(t)}}function Ja(){const o=[];for(let t=32;t<128;t++)o.push(String.fromCharCode(t));return o}const et={fontFamily:"Monaco, monospace",fontWeight:"normal",characterSet:Ja(),fontSize:64,buffer:4,sdf:!1,cutoff:.25,radius:12,smoothing:.1},yi=1024,xi=.9,_i=.3,Ao=3;let Dt=new Lo(Ao);function Qa(o,t){let e;typeof t=="string"?e=new Set(Array.from(t)):e=new Set(t);const i=Dt.get(o);if(!i)return e;for(const n in i.mapping)e.has(n)&&e.delete(n);return e}function tl(o,t){for(let e=0;e<o.length;e++)t.data[4*e+3]=o[e]}function Ci(o,t,e,i){o.font=`${i} ${e}px ${t}`,o.fillStyle="#000",o.textBaseline="alphabetic",o.textAlign="left"}function el(o,t,e){if(e===void 0){const n=o.measureText("A");return n.fontBoundingBoxAscent?{advance:0,width:0,ascent:Math.ceil(n.fontBoundingBoxAscent),descent:Math.ceil(n.fontBoundingBoxDescent)}:{advance:0,width:0,ascent:t*xi,descent:t*_i}}const i=o.measureText(e);return i.actualBoundingBoxAscent?{advance:i.width,width:Math.ceil(i.actualBoundingBoxRight-i.actualBoundingBoxLeft),ascent:Math.ceil(i.actualBoundingBoxAscent),descent:Math.ceil(i.actualBoundingBoxDescent)}:{advance:i.width,width:i.width,ascent:t*xi,descent:t*_i}}function il(o){S.assert(Number.isFinite(o)&&o>=Ao,"Invalid cache limit"),Dt=new Lo(o)}class ol{constructor(){this.props={...et}}get atlas(){return this._atlas}get mapping(){return this._atlas&&this._atlas.mapping}setProps(t={}){Object.assign(this.props,t),t._getFontRenderer&&(this._getFontRenderer=t._getFontRenderer),this._key=this._getKey();const e=Qa(this._key,this.props.characterSet),i=Dt.get(this._key);if(i&&e.size===0){this._atlas!==i&&(this._atlas=i);return}const n=this._generateFontAtlas(e,i);this._atlas=n,Dt.set(this._key,n)}_generateFontAtlas(t,e){const{fontFamily:i,fontWeight:n,fontSize:s,buffer:r,sdf:a,radius:l,cutoff:c}=this.props;let u=e&&e.data;u||(u=document.createElement("canvas"),u.width=yi);const f=u.getContext("2d",{willReadFrequently:!0});Ci(f,i,s,n);const d=m=>el(f,s,m);let g;this._getFontRenderer?g=this._getFontRenderer(this.props):a&&(g={measure:d,draw:nl(this.props)});const{mapping:h,canvasHeight:p,xOffset:v,yOffsetMin:x,yOffsetMax:_}=Ha({measureText:m=>g?g.measure(m):d(m),buffer:r,characterSet:t,maxCanvasWidth:yi,...e&&{mapping:e.mapping,xOffset:e.xOffset,yOffsetMin:e.yOffsetMin,yOffsetMax:e.yOffsetMax}});if(u.height!==p){const m=u.height>0?f.getImageData(0,0,u.width,u.height):null;u.height=p,m&&f.putImageData(m,0,0)}if(Ci(f,i,s,n),g)for(const m of t){const C=h[m],{data:L,left:R=0,top:w=0}=g.draw(m),P=C.x-R,T=C.y-w,I=Math.max(0,Math.round(P)),z=Math.max(0,Math.round(T)),V=Math.min(L.width,u.width-I),ot=Math.min(L.height,u.height-z);f.putImageData(L,I,z,0,0,V,ot),C.x+=I-P,C.y+=z-T}else for(const m of t){const C=h[m];f.fillText(m,C.x,C.y+C.anchorY)}const y=g?g.measure():d();return{baselineOffset:(y.ascent-y.descent)/2,xOffset:v,yOffsetMin:x,yOffsetMax:_,mapping:h,data:u,width:u.width,height:u.height}}_getKey(){const{fontFamily:t,fontWeight:e,fontSize:i,buffer:n,sdf:s,radius:r,cutoff:a}=this.props;return s?`${t} ${e} ${i} ${n} ${r} ${a}`:`${t} ${e} ${i} ${n}`}}function nl({fontSize:o,buffer:t,radius:e,cutoff:i,fontFamily:n,fontWeight:s}){const r=new ja({fontSize:o,buffer:t,radius:e,cutoff:i,fontFamily:n,fontWeight:`${s}`});return a=>{const{data:l,width:c,height:u}=r.draw(a),f=new ImageData(c,u);return tl(l,f),{data:f,left:t,top:t}}}const Pi=`layout(std140) uniform textBackgroundUniforms {
  bool billboard;
  float sizeScale;
  float sizeMinPixels;
  float sizeMaxPixels;
  vec4 borderRadius;
  vec4 padding;
  highp int sizeUnits;
  bool stroked;
} textBackground;
`,sl={name:"textBackground",vs:Pi,fs:Pi,uniformTypes:{billboard:"f32",sizeScale:"f32",sizeMinPixels:"f32",sizeMaxPixels:"f32",borderRadius:"vec4<f32>",padding:"vec4<f32>",sizeUnits:"i32",stroked:"f32"}},rl=`#version 300 es
#define SHADER_NAME text-background-layer-vertex-shader
in vec2 positions;
in vec3 instancePositions;
in vec3 instancePositions64Low;
in vec4 instanceRects;
in vec4 instanceClipRect;
in float instanceSizes;
in float instanceAngles;
in vec2 instancePixelOffsets;
in float instanceLineWidths;
in vec4 instanceFillColors;
in vec4 instanceLineColors;
in vec3 instancePickingColors;
out vec4 vFillColor;
out vec4 vLineColor;
out float vLineWidth;
out vec2 uv;
out vec2 dimensions;
vec2 rotate_by_angle(vec2 vertex, float angle) {
float angle_radian = radians(angle);
float cos_angle = cos(angle_radian);
float sin_angle = sin(angle_radian);
mat2 rotationMatrix = mat2(cos_angle, -sin_angle, sin_angle, cos_angle);
return rotationMatrix * vertex;
}
void main(void) {
geometry.worldPosition = instancePositions;
geometry.uv = positions;
geometry.pickingColor = instancePickingColors;
uv = positions;
vLineWidth = instanceLineWidths;
float sizePixels = clamp(
project_size_to_pixel(instanceSizes * textBackground.sizeScale, textBackground.sizeUnits),
textBackground.sizeMinPixels, textBackground.sizeMaxPixels
);
float instanceScale = sizePixels / text.fontSize;
dimensions = instanceRects.zw * instanceScale + textBackground.padding.xy + textBackground.padding.zw;
vec2 pixelOffset = (positions * instanceRects.zw + instanceRects.xy) * instanceScale + mix(-textBackground.padding.xy, textBackground.padding.zw, positions);
pixelOffset = rotate_by_angle(pixelOffset, instanceAngles);
pixelOffset += instancePixelOffsets;
pixelOffset.y *= -1.0;
vec2 xy = project_size_to_pixel(instanceClipRect.xy);
vec2 wh = project_size_to_pixel(instanceClipRect.zw);
if (text.flipY) {
xy.y = -xy.y - wh.y;
}
if (instanceClipRect.z >= 0.0) {
dimensions.x = wh.x;
pixelOffset.x = xy.x + uv.x * wh.x + mix(-textBackground.padding.x, textBackground.padding.z, uv.x);
}
if (instanceClipRect.w >= 0.0) {
dimensions.y = wh.y;
pixelOffset.y = xy.y + uv.y * wh.y + mix(-textBackground.padding.y, textBackground.padding.w, uv.y);
}
if (textBackground.billboard)  {
gl_Position = project_position_to_clipspace(instancePositions, instancePositions64Low, vec3(0.0), geometry.position);
DECKGL_FILTER_GL_POSITION(gl_Position, geometry);
vec3 offset = vec3(pixelOffset, 0.0);
DECKGL_FILTER_SIZE(offset, geometry);
gl_Position.xy += project_pixel_size_to_clipspace(offset.xy);
} else {
vec3 offset_common = vec3(project_pixel_size(pixelOffset), 0.0);
if (text.flipY) {
offset_common.y *= -1.;
}
DECKGL_FILTER_SIZE(offset_common, geometry);
gl_Position = project_position_to_clipspace(instancePositions, instancePositions64Low, offset_common, geometry.position);
DECKGL_FILTER_GL_POSITION(gl_Position, geometry);
}
vFillColor = vec4(instanceFillColors.rgb, instanceFillColors.a * layer.opacity);
DECKGL_FILTER_COLOR(vFillColor, geometry);
vLineColor = vec4(instanceLineColors.rgb, instanceLineColors.a * layer.opacity);
DECKGL_FILTER_COLOR(vLineColor, geometry);
}
`,al=`#version 300 es
#define SHADER_NAME text-background-layer-fragment-shader
precision highp float;
in vec4 vFillColor;
in vec4 vLineColor;
in float vLineWidth;
in vec2 uv;
in vec2 dimensions;
out vec4 fragColor;
float round_rect(vec2 p, vec2 size, vec4 radii) {
vec2 pixelPositionCB = (p - 0.5) * size;
vec2 sizeCB = size * 0.5;
float maxBorderRadius = min(size.x, size.y) * 0.5;
vec4 borderRadius = vec4(min(radii, maxBorderRadius));
borderRadius.xy =
(pixelPositionCB.x > 0.0) ? borderRadius.xy : borderRadius.zw;
borderRadius.x = (pixelPositionCB.y > 0.0) ? borderRadius.x : borderRadius.y;
vec2 q = abs(pixelPositionCB) - sizeCB + borderRadius.x;
return -(min(max(q.x, q.y), 0.0) + length(max(q, 0.0)) - borderRadius.x);
}
float rect(vec2 p, vec2 size) {
vec2 pixelPosition = p * size;
return min(min(pixelPosition.x, size.x - pixelPosition.x),
min(pixelPosition.y, size.y - pixelPosition.y));
}
vec4 get_stroked_fragColor(float dist) {
float isBorder = smoothedge(dist, vLineWidth);
return mix(vFillColor, vLineColor, isBorder);
}
void main(void) {
geometry.uv = uv;
if (textBackground.borderRadius != vec4(0.0)) {
float distToEdge = round_rect(uv, dimensions, textBackground.borderRadius);
float shapeAlpha = smoothedge(-distToEdge, 0.0);
if (shapeAlpha == 0.0) {
discard;
}
if (textBackground.stroked) {
fragColor = get_stroked_fragColor(distToEdge);
} else {
fragColor = vFillColor;
}
fragColor.a *= shapeAlpha;
} else {
if (textBackground.stroked) {
float distToEdge = rect(uv, dimensions);
fragColor = get_stroked_fragColor(distToEdge);
} else {
fragColor = vFillColor;
}
}
DECKGL_FILTER_COLOR(fragColor, geometry);
}
`,ll={billboard:!0,sizeScale:1,sizeUnits:"pixels",sizeMinPixels:0,sizeMaxPixels:Number.MAX_SAFE_INTEGER,fontSize:1,borderRadius:{type:"object",value:0},padding:{type:"array",value:[0,0,0,0]},getPosition:{type:"accessor",value:o=>o.position},getSize:{type:"accessor",value:1},getAngle:{type:"accessor",value:0},getPixelOffset:{type:"accessor",value:[0,0]},getBoundingRect:{type:"accessor",value:[0,0,0,0]},getClipRect:{type:"accessor",value:[0,0,-1,-1]},getFillColor:{type:"accessor",value:[0,0,0,255]},getLineColor:{type:"accessor",value:[0,0,0,255]},getLineWidth:{type:"accessor",value:1}};class Te extends k{getShaders(){return super.getShaders({vs:rl,fs:al,modules:[G,j,sl,Co]})}initializeState(){this.getAttributeManager().addInstanced({instancePositions:{size:3,type:"float64",fp64:this.use64bitPositions(),transition:!0,accessor:"getPosition"},instanceSizes:{size:1,transition:!0,accessor:"getSize",defaultValue:1},instanceAngles:{size:1,transition:!0,accessor:"getAngle"},instanceRects:{size:4,accessor:"getBoundingRect"},instanceClipRect:{size:4,accessor:"getClipRect",defaultValue:[0,0,-1,-1]},instancePixelOffsets:{size:2,transition:!0,accessor:"getPixelOffset"},instanceFillColors:{size:4,transition:!0,type:"unorm8",accessor:"getFillColor",defaultValue:[0,0,0,255]},instanceLineColors:{size:4,transition:!0,type:"unorm8",accessor:"getLineColor",defaultValue:[0,0,0,255]},instanceLineWidths:{size:1,transition:!0,accessor:"getLineWidth",defaultValue:1}})}updateState(t){var i;super.updateState(t);const{changeFlags:e}=t;e.extensionsChanged&&((i=this.state.model)==null||i.destroy(),this.state.model=this._getModel(),this.getAttributeManager().invalidateAll())}draw({uniforms:t}){const{billboard:e,sizeScale:i,sizeUnits:n,sizeMinPixels:s,sizeMaxPixels:r,getLineWidth:a,fontSize:l}=this.props;let{padding:c,borderRadius:u}=this.props;c.length<4&&(c=[c[0],c[1],c[0],c[1]]),Array.isArray(u)||(u=[u,u,u,u]);const f=this.state.model,d={billboard:e,stroked:!!a,borderRadius:u,padding:c,sizeUnits:D[n],sizeScale:i,sizeMinPixels:s,sizeMaxPixels:r},g={fontSize:l,viewport:this.context.viewport};f.shaderInputs.setProps({textBackground:d,text:g}),f.draw(this.context.renderPass)}_getModel(){const t=[0,0,1,0,0,1,1,1];return new M(this.context.device,{...this.getShaders(),id:this.props.id,bufferLayout:this.getAttributeManager().getBufferLayouts(),geometry:new N({topology:"triangle-strip",vertexCount:4,attributes:{positions:{size:2,value:new Float32Array(t)}}}),isInstanced:!0})}}Te.defaultProps=ll;Te.layerName="TextBackgroundLayer";const bi={start:1,middle:0,end:-1},Li={top:1,center:0,bottom:-1},oe=[0,0,0,255],cl=1,ul={billboard:!0,sizeScale:1,sizeUnits:"pixels",sizeMinPixels:0,sizeMaxPixels:Number.MAX_SAFE_INTEGER,background:!1,getBackgroundColor:{type:"accessor",value:[255,255,255,255]},getBorderColor:{type:"accessor",value:oe},getBorderWidth:{type:"accessor",value:0},backgroundBorderRadius:{type:"object",value:0},backgroundPadding:{type:"array",value:[0,0,0,0]},characterSet:{type:"object",value:et.characterSet},fontFamily:et.fontFamily,fontWeight:et.fontWeight,lineHeight:cl,outlineWidth:{type:"number",value:0,min:0},outlineColor:{type:"color",value:oe},fontSettings:{type:"object",value:{},compare:1},wordBreak:"break-word",maxWidth:{type:"number",value:-1},contentCutoffPixels:{type:"array",value:[0,0]},contentAlignHorizontal:"none",contentAlignVertical:"none",getText:{type:"accessor",value:o=>o.text},getPosition:{type:"accessor",value:o=>o.position},getColor:{type:"accessor",value:oe},getSize:{type:"accessor",value:32},getAngle:{type:"accessor",value:0},getTextAnchor:{type:"accessor",value:"middle"},getAlignmentBaseline:{type:"accessor",value:"center"},getPixelOffset:{type:"accessor",value:[0,0]},getContentBox:{type:"accessor",value:[0,0,-1,-1]},backgroundColor:{deprecatedFor:["background","getBackgroundColor"]}};class we extends jt{constructor(){super(...arguments),this.getBoundingRect=(t,e)=>{const{size:[i,n]}=this.transformParagraph(t,e),{getTextAnchor:s,getAlignmentBaseline:r}=this.props,a=bi[typeof s=="function"?s(t,e):s],l=Li[typeof r=="function"?r(t,e):r];return[(a-1)*i/2,(l-1)*n/2,i,n]},this.getIconOffsets=(t,e)=>{const{getTextAnchor:i,getAlignmentBaseline:n}=this.props,{x:s,y:r,rowWidth:a,size:[,l]}=this.transformParagraph(t,e),c=bi[typeof i=="function"?i(t,e):i],u=Li[typeof n=="function"?n(t,e):n],f=s.length,d=new Array(f*2);let g=0;for(let h=0;h<f;h++)d[g++]=(c-1)*a[h]/2+s[h],d[g++]=(u-1)*l/2+r[h];return d}}initializeState(){this.state={styleVersion:0,fontAtlasManager:new ol},this.props.maxWidth>0&&S.once(1,"v8.9 breaking change: TextLayer maxWidth is now relative to text size")()}updateState(t){const{props:e,oldProps:i,changeFlags:n}=t;(n.dataChanged||n.updateTriggersChanged&&(n.updateTriggersChanged.all||n.updateTriggersChanged.getText))&&this._updateText(),(this._updateFontAtlas()||e.lineHeight!==i.lineHeight||e.wordBreak!==i.wordBreak||e.maxWidth!==i.maxWidth)&&this.setState({styleVersion:this.state.styleVersion+1})}getPickingInfo({info:t}){return t.object=t.index>=0?this.props.data[t.index]:null,t}_updateFontAtlas(){const{fontSettings:t,fontFamily:e,fontWeight:i,_getFontRenderer:n}=this.props,{fontAtlasManager:s,characterSet:r}=this.state,a={...t,characterSet:r,fontFamily:e,fontWeight:i,_getFontRenderer:n};if(!s.mapping)return s.setProps(a),!0;for(const l in a)if(a[l]!==s.props[l])return s.setProps(a),!0;return!1}_updateText(){var l;const{data:t,characterSet:e}=this.props,i=(l=t.attributes)==null?void 0:l.getText;let{getText:n}=this.props,s=t.startIndices,r;const a=e==="auto"&&new Set;if(i&&s){const{texts:c,characterCount:u}=qa({...ArrayBuffer.isView(i)?{value:i}:i,length:t.length,startIndices:s,characterSet:a});r=u,n=(f,{index:d})=>c[d]}else{const{iterable:c,objectInfo:u}=it(t);s=[0],r=0;for(const f of c){u.index++;const d=Array.from(n(f,u)||"");a&&d.forEach(a.add,a),r+=d.length,s.push(r)}}this.setState({getText:n,startIndices:s,numInstances:r,characterSet:a||e})}transformParagraph(t,e){const{fontAtlasManager:i}=this.state,n=i.mapping,{baselineOffset:s}=i.atlas,{fontSize:r}=i.props,a=this.state.getText,{wordBreak:l,lineHeight:c,maxWidth:u}=this.props,f=a(t,e)||"";return Xa(f,s,c*r,l,u*r,n)}renderLayers(){const{startIndices:t,numInstances:e,getText:i,fontAtlasManager:{atlas:n,mapping:s},styleVersion:r}=this.state,{data:a,_dataDiff:l,getPosition:c,getColor:u,getSize:f,getAngle:d,getPixelOffset:g,getBackgroundColor:h,getBorderColor:p,getBorderWidth:v,getContentBox:x,backgroundBorderRadius:_,backgroundPadding:y,background:m,billboard:C,fontSettings:L,outlineWidth:R,outlineColor:w,sizeScale:P,sizeUnits:T,sizeMinPixels:I,sizeMaxPixels:z,contentCutoffPixels:V,contentAlignHorizontal:ot,contentAlignVertical:vt,transitions:E,updateTriggers:A}=this.props,wo=this.getSubLayerClass("characters",Ae),Eo=this.getSubLayerClass("background",Te),{fontSize:Ee}=this.state.fontAtlasManager.props;return[m&&new Eo({getFillColor:h,getLineColor:p,getLineWidth:v,borderRadius:_,padding:y,getPosition:c,getSize:f,getAngle:d,getPixelOffset:g,getClipRect:x,billboard:C,sizeScale:P,sizeUnits:T,sizeMinPixels:I,sizeMaxPixels:z,fontSize:Ee,transitions:E&&{getPosition:E.getPosition,getAngle:E.getAngle,getSize:E.getSize,getFillColor:E.getBackgroundColor,getLineColor:E.getBorderColor,getLineWidth:E.getBorderWidth,getPixelOffset:E.getPixelOffset}},this.getSubLayerProps({id:"background",updateTriggers:{getPosition:A.getPosition,getAngle:A.getAngle,getSize:A.getSize,getFillColor:A.getBackgroundColor,getLineColor:A.getBorderColor,getLineWidth:A.getBorderWidth,getPixelOffset:A.getPixelOffset,getBoundingRect:{getText:A.getText,getTextAnchor:A.getTextAnchor,getAlignmentBaseline:A.getAlignmentBaseline,styleVersion:r}}}),{data:a.attributes&&a.attributes.background?{length:a.length,attributes:a.attributes.background}:a,_dataDiff:l,autoHighlight:!1,getBoundingRect:this.getBoundingRect}),new wo({sdf:L.sdf,smoothing:Number.isFinite(L.smoothing)?L.smoothing:et.smoothing,outlineWidth:R/(L.radius||et.radius),outlineColor:w,iconAtlas:n,iconMapping:s,getPosition:c,getColor:u,getSize:f,getAngle:d,getPixelOffset:g,getContentBox:x,billboard:C,sizeScale:P,sizeUnits:T,sizeMinPixels:I,sizeMaxPixels:z,fontSize:Ee,contentCutoffPixels:V,contentAlignHorizontal:ot,contentAlignVertical:vt,transitions:E&&{getPosition:E.getPosition,getAngle:E.getAngle,getColor:E.getColor,getSize:E.getSize,getPixelOffset:E.getPixelOffset,getContentBox:E.getContentBox}},this.getSubLayerProps({id:"characters",updateTriggers:{all:A.getText,getPosition:A.getPosition,getAngle:A.getAngle,getColor:A.getColor,getSize:A.getSize,getPixelOffset:A.getPixelOffset,getContentBox:A.getContentBox,getIconOffsets:{getTextAnchor:A.getTextAnchor,getAlignmentBaseline:A.getAlignmentBaseline,styleVersion:r}}}),{data:a,_dataDiff:l,startIndices:t,numInstances:e,getIconOffsets:this.getIconOffsets,getIcon:i})]}static set fontAtlasCacheLimit(t){il(t)}}we.defaultProps=ul;we.layerName="TextLayer";const Mt={circle:{type:Ce,props:{filled:"filled",stroked:"stroked",lineWidthMaxPixels:"lineWidthMaxPixels",lineWidthMinPixels:"lineWidthMinPixels",lineWidthScale:"lineWidthScale",lineWidthUnits:"lineWidthUnits",pointRadiusMaxPixels:"radiusMaxPixels",pointRadiusMinPixels:"radiusMinPixels",pointRadiusScale:"radiusScale",pointRadiusUnits:"radiusUnits",pointAntialiasing:"antialiasing",pointBillboard:"billboard",getFillColor:"getFillColor",getLineColor:"getLineColor",getLineWidth:"getLineWidth",getPointRadius:"getRadius"}},icon:{type:Vt,props:{iconAtlas:"iconAtlas",iconMapping:"iconMapping",iconSizeMaxPixels:"sizeMaxPixels",iconSizeMinPixels:"sizeMinPixels",iconSizeScale:"sizeScale",iconSizeUnits:"sizeUnits",iconAlphaCutoff:"alphaCutoff",iconBillboard:"billboard",getIcon:"getIcon",getIconAngle:"getAngle",getIconColor:"getColor",getIconPixelOffset:"getPixelOffset",getIconSize:"getSize"}},text:{type:we,props:{textSizeMaxPixels:"sizeMaxPixels",textSizeMinPixels:"sizeMinPixels",textSizeScale:"sizeScale",textSizeUnits:"sizeUnits",textBackground:"background",textBackgroundPadding:"backgroundPadding",textFontFamily:"fontFamily",textFontWeight:"fontWeight",textLineHeight:"lineHeight",textMaxWidth:"maxWidth",textOutlineColor:"outlineColor",textOutlineWidth:"outlineWidth",textWordBreak:"wordBreak",textCharacterSet:"characterSet",textBillboard:"billboard",textFontSettings:"fontSettings",getText:"getText",getTextAngle:"getAngle",getTextColor:"getColor",getTextPixelOffset:"getPixelOffset",getTextSize:"getSize",getTextAnchor:"getTextAnchor",getTextAlignmentBaseline:"getAlignmentBaseline",getTextBackgroundColor:"getBackgroundColor",getTextBorderColor:"getBorderColor",getTextBorderWidth:"getBorderWidth"}}},Rt={type:Wt,props:{lineWidthUnits:"widthUnits",lineWidthScale:"widthScale",lineWidthMinPixels:"widthMinPixels",lineWidthMaxPixels:"widthMaxPixels",lineJointRounded:"jointRounded",lineCapRounded:"capRounded",lineMiterLimit:"miterLimit",lineBillboard:"billboard",getLineColor:"getColor",getLineWidth:"getWidth"}},ve={type:Yt,props:{extruded:"extruded",filled:"filled",wireframe:"wireframe",elevationScale:"elevationScale",material:"material",_full3d:"_full3d",getElevation:"getElevation",getFillColor:"getFillColor",getLineColor:"getLineColor"}};function st({type:o,props:t}){const e={};for(const i in t)e[i]=o.defaultProps[t[i]];return e}function ne(o,t){const{transitions:e,updateTriggers:i}=o.props,n={updateTriggers:{},transitions:e&&{getPosition:e.geometry}};for(const s in t){const r=t[s];let a=o.props[s];s.startsWith("get")&&(a=o.getSubLayerAccessor(a),n.updateTriggers[r]=i[s],e&&(n.transitions[r]=e[s])),n[r]=a}return n}function fl(o){if(Array.isArray(o))return o;switch(S.assert(o.type,"GeoJSON does not have type"),o.type){case"Feature":return[o];case"FeatureCollection":return S.assert(Array.isArray(o.features),"GeoJSON does not have features array"),o.features;default:return[{geometry:o}]}}function Ai(o,t,e={}){const i={pointFeatures:[],lineFeatures:[],polygonFeatures:[],polygonOutlineFeatures:[]},{startRow:n=0,endRow:s=o.length}=e;for(let r=n;r<s;r++){const a=o[r],{geometry:l}=a;if(l)if(l.type==="GeometryCollection"){S.assert(Array.isArray(l.geometries),"GeoJSON does not have geometries array");const{geometries:c}=l;for(let u=0;u<c.length;u++){const f=c[u];Si(f,i,t,a,r)}}else Si(l,i,t,a,r)}return i}function Si(o,t,e,i,n){const{type:s,coordinates:r}=o,{pointFeatures:a,lineFeatures:l,polygonFeatures:c,polygonOutlineFeatures:u}=t;if(!gl(s,r)){S.warn(`${s} coordinates are malformed`)();return}switch(s){case"Point":a.push(e({geometry:o},i,n));break;case"MultiPoint":r.forEach(f=>{a.push(e({geometry:{type:"Point",coordinates:f}},i,n))});break;case"LineString":l.push(e({geometry:o},i,n));break;case"MultiLineString":r.forEach(f=>{l.push(e({geometry:{type:"LineString",coordinates:f}},i,n))});break;case"Polygon":c.push(e({geometry:o},i,n)),r.forEach(f=>{u.push(e({geometry:{type:"LineString",coordinates:f}},i,n))});break;case"MultiPolygon":r.forEach(f=>{c.push(e({geometry:{type:"Polygon",coordinates:f}},i,n)),f.forEach(d=>{u.push(e({geometry:{type:"LineString",coordinates:d}},i,n))})});break}}const dl={Point:1,MultiPoint:2,LineString:2,MultiLineString:3,Polygon:3,MultiPolygon:4};function gl(o,t){let e=dl[o];for(S.assert(e,`Unknown GeoJSON type ${o}`);t&&--e>0;)t=t[0];return t&&Number.isFinite(t[0])}function So(){return{points:{},lines:{},polygons:{},polygonsOutline:{}}}function At(o){return o.geometry.coordinates}function hl(o,t){const e=So(),{pointFeatures:i,lineFeatures:n,polygonFeatures:s,polygonOutlineFeatures:r}=o;return e.points.data=i,e.points._dataDiff=t.pointFeatures&&(()=>t.pointFeatures),e.points.getPosition=At,e.lines.data=n,e.lines._dataDiff=t.lineFeatures&&(()=>t.lineFeatures),e.lines.getPath=At,e.polygons.data=s,e.polygons._dataDiff=t.polygonFeatures&&(()=>t.polygonFeatures),e.polygons.getPolygon=At,e.polygonsOutline.data=r,e.polygonsOutline._dataDiff=t.polygonOutlineFeatures&&(()=>t.polygonOutlineFeatures),e.polygonsOutline.getPath=At,e}function pl(o,t){const e=So(),{points:i,lines:n,polygons:s}=o,r=ka(o,t);e.points.data={length:i.positions.value.length/i.positions.size,attributes:{...i.attributes,getPosition:i.positions,instancePickingColors:{size:4,value:r.points}},properties:i.properties,numericProps:i.numericProps,featureIds:i.featureIds},e.lines.data={length:n.pathIndices.value.length-1,startIndices:n.pathIndices.value,attributes:{...n.attributes,getPath:n.positions,instancePickingColors:{size:4,value:r.lines}},properties:n.properties,numericProps:n.numericProps,featureIds:n.featureIds},e.lines._pathType="open";const a=s.positions.value.length/s.positions.size,l=Array(a).fill(1);for(const c of s.primitivePolygonIndices.value)l[c-1]=0;return e.polygons.data={length:s.polygonIndices.value.length-1,startIndices:s.polygonIndices.value,attributes:{...s.attributes,getPolygon:s.positions,instanceVertexValid:{size:1,value:new Uint16Array(l)},pickingColors:{size:4,value:r.polygons}},properties:s.properties,numericProps:s.numericProps,featureIds:s.featureIds},e.polygons._normalize=!1,s.triangles&&(e.polygons.data.attributes.indices=s.triangles.value),e.polygonsOutline.data={length:s.primitivePolygonIndices.value.length-1,startIndices:s.primitivePolygonIndices.value,attributes:{...s.attributes,getPath:s.positions,instancePickingColors:{size:4,value:r.polygons}},properties:s.properties,numericProps:s.numericProps,featureIds:s.featureIds},e.polygonsOutline._pathType="open",e}const vl=["points","linestrings","polygons"],ml={...st(Mt.circle),...st(Mt.icon),...st(Mt.text),...st(Rt),...st(ve),stroked:!0,filled:!0,extruded:!1,wireframe:!1,_full3d:!1,iconAtlas:{type:"object",value:null},iconMapping:{type:"object",value:{}},getIcon:{type:"accessor",value:o=>o.properties.icon},getText:{type:"accessor",value:o=>o.properties.text},pointType:"circle",getRadius:{deprecatedFor:"getPointRadius"}};class To extends jt{initializeState(){this.state={layerProps:{},features:{},featuresDiff:{}}}updateState({props:t,changeFlags:e}){if(!e.dataChanged)return;const{data:i}=this.props,n=i&&"points"in i&&"polygons"in i&&"lines"in i;this.setState({binary:n}),n?this._updateStateBinary({props:t,changeFlags:e}):this._updateStateJSON({props:t,changeFlags:e})}_updateStateBinary({props:t,changeFlags:e}){const i=pl(t.data,this.encodePickingColor);this.setState({layerProps:i})}_updateStateJSON({props:t,changeFlags:e}){const i=fl(t.data),n=this.getSubLayerRow.bind(this);let s={};const r={};if(Array.isArray(e.dataChanged)){const l=this.state.features;for(const c in l)s[c]=l[c].slice(),r[c]=[];for(const c of e.dataChanged){const u=Ai(i,n,c);for(const f in l)r[f].push(yo({data:s[f],getIndex:d=>d.__source.index,dataRange:c,replace:u[f]}))}}else s=Ai(i,n);const a=hl(s,r);this.setState({features:s,featuresDiff:r,layerProps:a})}getPickingInfo(t){const e=super.getPickingInfo(t),{index:i,sourceLayer:n}=e;return e.featureType=vl.find(s=>n.id.startsWith(`${this.id}-${s}-`)),i>=0&&n.id.startsWith(`${this.id}-points-text`)&&this.state.binary&&(e.index=this.props.data.points.globalFeatureIds.value[i]),e}_updateAutoHighlight(t){const e=`${this.id}-points-`,i=t.featureType==="points";for(const n of this.getSubLayers())n.id.startsWith(e)===i&&n.updateAutoHighlight(t)}_renderPolygonLayer(){var r;const{extruded:t,wireframe:e}=this.props,{layerProps:i}=this.state,n="polygons-fill",s=this.shouldRenderSubLayer(n,(r=i.polygons)==null?void 0:r.data)&&this.getSubLayerClass(n,ve.type);if(s){const a=ne(this,ve.props),l=t&&e;return l||delete a.getLineColor,a.updateTriggers.lineColors=l,new s(a,this.getSubLayerProps({id:n,updateTriggers:a.updateTriggers}),i.polygons)}return null}_renderLineLayers(){var l,c;const{extruded:t,stroked:e}=this.props,{layerProps:i}=this.state,n="polygons-stroke",s="linestrings",r=!t&&e&&this.shouldRenderSubLayer(n,(l=i.polygonsOutline)==null?void 0:l.data)&&this.getSubLayerClass(n,Rt.type),a=this.shouldRenderSubLayer(s,(c=i.lines)==null?void 0:c.data)&&this.getSubLayerClass(s,Rt.type);if(r||a){const u=ne(this,Rt.props);return[r&&new r(u,this.getSubLayerProps({id:n,updateTriggers:u.updateTriggers}),i.polygonsOutline),a&&new a(u,this.getSubLayerProps({id:s,updateTriggers:u.updateTriggers}),i.lines)]}return null}_renderPointLayers(){var a;const{pointType:t}=this.props,{layerProps:e,binary:i}=this.state;let{highlightedObjectIndex:n}=this.props;!i&&Number.isFinite(n)&&(n=e.points.data.findIndex(l=>l.__source.index===n));const s=new Set(t.split("+")),r=[];for(const l of s){const c=`points-${l}`,u=Mt[l],f=u&&this.shouldRenderSubLayer(c,(a=e.points)==null?void 0:a.data)&&this.getSubLayerClass(c,u.type);if(f){const d=ne(this,u.props);let g=e.points;if(l==="text"&&i){const{instancePickingColors:h,...p}=g.data.attributes;g={...g,data:{...g.data,attributes:p}}}r.push(new f(d,this.getSubLayerProps({id:c,updateTriggers:d.updateTriggers,highlightedObjectIndex:n}),g))}}return r}renderLayers(){const{extruded:t}=this.props,e=this._renderPolygonLayer(),i=this._renderLineLayers(),n=this._renderPointLayers();return[!t&&e,i,n,t&&e]}getSubLayerAccessor(t){const{binary:e}=this.state;return!e||typeof t!="function"?super.getSubLayerAccessor(t):(i,n)=>{const{data:s,index:r}=n,a=za(s,r);return t(a,n)}}}To.layerName="GeoJsonLayer";To.defaultProps=ml;export{Ji as A,Qi as B,jt as C,To as G,Vt as I,k as L,Ae as M,_o as P,Ce as S,we as T,Wt as a,uo as b,it as c,Bi as d,j as e,N as f,no as g,ye as h,Yt as i,Te as j,Ri as l,Ii as n,G as p};
//# sourceMappingURL=geojson-layer-BwS5943W.js.map
