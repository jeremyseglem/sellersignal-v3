var es=Object.defineProperty;var ns=(e,t,n)=>t in e?es(e,t,{enumerable:!0,configurable:!0,writable:!0,value:n}):e[t]=n;var T=(e,t,n)=>ns(e,typeof t!="symbol"?t+"":t,n);const Tt=globalThis,et=globalThis.process||{},Tc=globalThis.navigator||{};function ss(e){var s,r;if(typeof window<"u"&&((s=window.process)==null?void 0:s.type)==="renderer"||typeof process<"u"&&((r=process.versions)!=null&&r.electron))return!0;const n=typeof navigator<"u"&&navigator.userAgent;return!!(n&&n.indexOf("Electron")>=0)}function _e(){return!(typeof process=="object"&&String(process)==="[object process]"&&!(process!=null&&process.browser))||ss()}const pn="4.1.1";function Ee(e,t){if(!e)throw new Error("Assertion failed")}function mn(e){if(!e)return 0;let t;switch(typeof e){case"number":t=e;break;case"object":t=e.logLevel||e.priority||0;break;default:return 0}return Ee(Number.isFinite(t)&&t>=0),t}function rs(e){const{logLevel:t,message:n}=e;e.logLevel=mn(t);const s=e.args?Array.from(e.args):[];for(;s.length&&s.shift()!==n;);switch(typeof t){case"string":case"function":n!==void 0&&s.unshift(n),e.message=t;break;case"object":Object.assign(e,t);break}typeof e.message=="function"&&(e.message=e.message());const r=typeof e.message;return Ee(r==="string"||r==="object"),Object.assign(e,{args:s},e.opts)}const rt=()=>{};class is{constructor({level:t=0}={}){this.userData={},this._onceCache=new Set,this._level=t}set level(t){this.setLevel(t)}get level(){return this.getLevel()}setLevel(t){return this._level=t,this}getLevel(){return this._level}warn(t,...n){return this._log("warn",0,t,n,{once:!0})}error(t,...n){return this._log("error",0,t,n)}log(t,n,...s){return this._log("log",t,n,s)}info(t,n,...s){return this._log("info",t,n,s)}once(t,n,...s){return this._log("once",t,n,s,{once:!0})}_log(t,n,s,r,i={}){const o=rs({logLevel:n,message:s,args:this._buildArgs(n,s,r),opts:i});return this._createLogFunction(t,o,i)}_buildArgs(t,n,s){return[t,n,...s]}_createLogFunction(t,n,s){if(!this._shouldLog(n.logLevel))return rt;const r=this._getOnceTag(s.tag??n.tag??n.message);if((s.once||n.once)&&r!==void 0){if(this._onceCache.has(r))return rt;this._onceCache.add(r)}return this._emit(t,n)}_shouldLog(t){return this.getLevel()>=mn(t)}_getOnceTag(t){if(t!==void 0)try{return typeof t=="string"?t:String(t)}catch{return}}}function os(e){try{const t=window[e],n="__storage_test__";return t.setItem(n,n),t.removeItem(n),t}catch{return null}}class cs{constructor(t,n,s="sessionStorage"){this.storage=os(s),this.id=t,this.config=n,this._loadConfiguration()}getConfiguration(){return this.config}setConfiguration(t){if(Object.assign(this.config,t),this.storage){const n=JSON.stringify(this.config);this.storage.setItem(this.id,n)}}_loadConfiguration(){let t={};if(this.storage){const n=this.storage.getItem(this.id);t=n?JSON.parse(n):{}}return Object.assign(this.config,t),this}}function as(e){let t;return e<10?t=`${e.toFixed(2)}ms`:e<100?t=`${e.toFixed(1)}ms`:e<1e3?t=`${e.toFixed(0)}ms`:t=`${(e/1e3).toFixed(2)}s`,t}function ls(e,t=8){const n=Math.max(t-e.length,0);return`${" ".repeat(n)}${e}`}var Nt;(function(e){e[e.BLACK=30]="BLACK",e[e.RED=31]="RED",e[e.GREEN=32]="GREEN",e[e.YELLOW=33]="YELLOW",e[e.BLUE=34]="BLUE",e[e.MAGENTA=35]="MAGENTA",e[e.CYAN=36]="CYAN",e[e.WHITE=37]="WHITE",e[e.BRIGHT_BLACK=90]="BRIGHT_BLACK",e[e.BRIGHT_RED=91]="BRIGHT_RED",e[e.BRIGHT_GREEN=92]="BRIGHT_GREEN",e[e.BRIGHT_YELLOW=93]="BRIGHT_YELLOW",e[e.BRIGHT_BLUE=94]="BRIGHT_BLUE",e[e.BRIGHT_MAGENTA=95]="BRIGHT_MAGENTA",e[e.BRIGHT_CYAN=96]="BRIGHT_CYAN",e[e.BRIGHT_WHITE=97]="BRIGHT_WHITE"})(Nt||(Nt={}));const fs=10;function we(e){return typeof e!="string"?e:(e=e.toUpperCase(),Nt[e]||Nt.WHITE)}function hs(e,t,n){return!_e&&typeof e=="string"&&(t&&(e=`\x1B[${we(t)}m${e}\x1B[39m`),n&&(e=`\x1B[${we(n)+fs}m${e}\x1B[49m`)),e}function us(e,t=["constructor"]){const n=Object.getPrototypeOf(e),s=Object.getOwnPropertyNames(n),r=e;for(const i of s){const o=r[i];typeof o=="function"&&(t.find(c=>i===c)||(r[i]=o.bind(e)))}}function dt(){var t,n,s;let e;if(_e()&&Tt.performance)e=(n=(t=Tt==null?void 0:Tt.performance)==null?void 0:t.now)==null?void 0:n.call(t);else if("hrtime"in et){const r=(s=et==null?void 0:et.hrtime)==null?void 0:s.call(et);e=r[0]*1e3+r[1]/1e6}else e=Date.now();return e}const nt={debug:_e()&&console.debug||console.log,log:console.log,info:console.info,warn:console.warn,error:console.error},Vt={enabled:!0,level:0};class be extends is{constructor({id:t}={id:""}){super({level:0}),this.VERSION=pn,this._startTs=dt(),this._deltaTs=dt(),this.userData={},this.LOG_THROTTLE_TIMEOUT=0,this.id=t,this.userData={},this._storage=new cs(`__probe-${this.id}__`,{[this.id]:Vt}),this.timeStamp(`${this.id} started`),us(this),Object.seal(this)}isEnabled(){return this._getConfiguration().enabled}getLevel(){return this._getConfiguration().level}getTotal(){return Number((dt()-this._startTs).toPrecision(10))}getDelta(){return Number((dt()-this._deltaTs).toPrecision(10))}set priority(t){this.level=t}get priority(){return this.level}getPriority(){return this.level}enable(t=!0){return this._updateConfiguration({enabled:t}),this}setLevel(t){return this._updateConfiguration({level:t}),this}get(t){return this._getConfiguration()[t]}set(t,n){this._updateConfiguration({[t]:n})}settings(){console.table?console.table(this._storage.config):console.log(this._storage.config)}assert(t,n){if(!t)throw new Error(n||"Assertion failed")}warn(t,...n){return this._log("warn",0,t,n,{method:nt.warn,once:!0})}error(t,...n){return this._log("error",0,t,n,{method:nt.error})}deprecated(t,n){return this.warn(`\`${t}\` is deprecated and will be removed in a later version. Use \`${n}\` instead`)}removed(t,n){return this.error(`\`${t}\` has been removed. Use \`${n}\` instead`)}probe(t,n,...s){return this._log("log",t,n,s,{method:nt.log,time:!0,once:!0})}log(t,n,...s){return this._log("log",t,n,s,{method:nt.debug})}info(t,n,...s){return this._log("info",t,n,s,{method:console.info})}once(t,n,...s){return this._log("once",t,n,s,{method:nt.debug||nt.info,once:!0})}table(t,n,s){return n?this._log("table",t,n,s&&[s]||[],{method:console.table||rt,tag:gs(n)}):rt}time(t,n){return this._log("time",t,n,[],{method:console.time?console.time:console.info})}timeEnd(t,n){return this._log("time",t,n,[],{method:console.timeEnd?console.timeEnd:console.info})}timeStamp(t,n){return this._log("time",t,n,[],{method:console.timeStamp||rt})}group(t,n,s={collapsed:!1}){const r=(s.collapsed?console.groupCollapsed:console.group)||console.info;return this._log("group",t,n,[],{method:r})}groupCollapsed(t,n,s={}){return this.group(t,n,Object.assign({},s,{collapsed:!0}))}groupEnd(t){return this._log("groupEnd",t,"",[],{method:console.groupEnd||rt})}withGroup(t,n,s){this.group(t,n)();try{s()}finally{this.groupEnd(t)()}}trace(){console.trace&&console.trace()}_shouldLog(t){return this.isEnabled()&&super._shouldLog(t)}_emit(t,n){const s=n.method;Ee(s),n.total=this.getTotal(),n.delta=this.getDelta(),this._deltaTs=dt();const r=ds(this.id,n.message,n);return s.bind(console,r,...n.args)}_getConfiguration(){return this._storage.config[this.id]||this._updateConfiguration(Vt),this._storage.config[this.id]}_updateConfiguration(t){const n=this._storage.config[this.id]||{...Vt};this._storage.setConfiguration({[this.id]:{...n,...t}})}}be.VERSION=pn;function ds(e,t,n){if(typeof t=="string"){const s=n.time?ls(as(n.total)):"";t=n.time?`${e}: ${s}  ${t}`:`${e}: ${t}`,t=hs(t,n.color,n.background)}return t}function gs(e){for(const t in e)for(const n in e[t])return n||"untitled";return"empty"}const _n=new be({id:"deck"});function yt(e,t){var n;if(!e){const s=new Error(t||"shadertools: assertion failed.");throw(n=Error.captureStackTrace)==null||n.call(Error,s,yt),s}}const Yt={number:{type:"number",validate(e,t){return Number.isFinite(e)&&typeof t=="object"&&(t.max===void 0||e<=t.max)&&(t.min===void 0||e>=t.min)}},array:{type:"array",validate(e,t){return Array.isArray(e)||ArrayBuffer.isView(e)}}};function ps(e){const t={};for(const[n,s]of Object.entries(e))t[n]=ms(s);return t}function ms(e){let t=Oe(e);if(t!=="object")return{value:e,...Yt[t],type:t};if(typeof e=="object")return e?e.type!==void 0?{...e,...Yt[e.type],type:e.type}:e.value===void 0?{type:"object",value:e}:(t=Oe(e.value),{...e,...Yt[t],type:t}):{type:"object",value:null};throw new Error("props")}function Oe(e){return Array.isArray(e)||ArrayBuffer.isView(e)?"array":typeof e}const _s=`#ifdef MODULE_LOGDEPTH
  logdepth_adjustPosition(gl_Position);
#endif
`,Es=`#ifdef MODULE_MATERIAL
  fragColor = material_filterColor(fragColor);
#endif

#ifdef MODULE_LIGHTING
  fragColor = lighting_filterColor(fragColor);
#endif

#ifdef MODULE_FOG
  fragColor = fog_filterColor(fragColor);
#endif

#ifdef MODULE_PICKING
  fragColor = picking_filterHighlightColor(fragColor);
  fragColor = picking_filterPickingColor(fragColor);
#endif

#ifdef MODULE_LOGDEPTH
  logdepth_setFragDepth();
#endif
`,bs={vertex:_s,fragment:Es},Le=/void\s+main\s*\([^)]*\)\s*\{\n?/,Re=/}\n?[^{}]*$/,Xt=[],Lt="__LUMA_INJECT_DECLARATIONS__";function ys(e){const t={vertex:{},fragment:{}};for(const n in e){let s=e[n];const r=Ts(n);typeof s=="string"&&(s={order:0,injection:s}),t[r][n]=s}return t}function Ts(e){const t=e.slice(0,2);switch(t){case"vs":return"vertex";case"fs":return"fragment";default:throw new Error(t)}}function It(e,t,n,s=!1){const r=t==="vertex";for(const i in n){const o=n[i];o.sort((a,l)=>a.order-l.order),Xt.length=o.length;for(let a=0,l=o.length;a<l;++a)Xt[a]=o[a].injection;const c=`${Xt.join(`
`)}
`;switch(i){case"vs:#decl":r&&(e=e.replace(Lt,c));break;case"vs:#main-start":r&&(e=e.replace(Le,a=>a+c));break;case"vs:#main-end":r&&(e=e.replace(Re,a=>c+a));break;case"fs:#decl":r||(e=e.replace(Lt,c));break;case"fs:#main-start":r||(e=e.replace(Le,a=>a+c));break;case"fs:#main-end":r||(e=e.replace(Re,a=>c+a));break;default:e=e.replace(i,a=>a+c)}}return e=e.replace(Lt,""),s&&(e=e.replace(/\}\s*$/,i=>i+bs[t])),e}function Ct(e){e.map(t=>Ms(t))}function Ms(e){if(e.instance)return;Ct(e.dependencies||[]);const{propTypes:t={},deprecations:n=[],inject:s={}}=e,r={normalizedInjections:ys(s),parsedDeprecations:As(n)};t&&(r.propValidators=ps(t)),e.instance=r;let i={};t&&(i=Object.entries(t).reduce((o,[c,a])=>{const l=a==null?void 0:a.value;return l&&(o[c]=l),o},{})),e.defaultUniforms={...e.defaultUniforms,...i}}function En(e,t,n){var s;(s=e.deprecations)==null||s.forEach(r=>{var i;(i=r.regex)!=null&&i.test(t)&&(r.deprecated?n.deprecated(r.old,r.new)():n.removed(r.old,r.new)())})}function As(e){return e.forEach(t=>{switch(t.type){case"function":t.regex=new RegExp(`\\b${t.old}\\(`);break;default:t.regex=new RegExp(`${t.type} ${t.old};`)}}),e}function bn(e){Ct(e);const t={},n={};yn({modules:e,level:0,moduleMap:t,moduleDepth:n});const s=Object.keys(n).sort((r,i)=>n[i]-n[r]).map(r=>t[r]);return Ct(s),s}function yn(e){const{modules:t,level:n,moduleMap:s,moduleDepth:r}=e;if(n>=5)throw new Error("Possible loop in shader dependency graph");for(const i of t)s[i.name]=i,(r[i.name]===void 0||r[i.name]<n)&&(r[i.name]=n);for(const i of t)i.dependencies&&yn({modules:i.dependencies,level:n+1,moduleMap:s,moduleDepth:r})}const Ss=/^(?:uniform\s+)?(?:(?:lowp|mediump|highp)\s+)?[A-Za-z0-9_]+(?:<[^>]+>)?\s+([A-Za-z0-9_]+)(?:\s*\[[^\]]+\])?\s*;/,vs=/((?:layout\s*\([^)]*\)\s*)*)uniform\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{([\s\S]*?)\}\s*([A-Za-z_][A-Za-z0-9_]*)?\s*;/g;function Tn(e){return`${e.name}Uniforms`}function xs(e,t){const n=t==="wgsl"?e.source:t==="vertex"?e.vs:e.fs;if(!n)return null;const s=Tn(e);return Rs(n,t==="wgsl"?"wgsl":"glsl",s)}function ws(e,t){const n=Object.keys(e.uniformTypes||{});if(!n.length)return null;const s=xs(e,t);return s?{moduleName:e.name,uniformBlockName:Tn(e),stage:t,expectedUniformNames:n,actualUniformNames:s,matches:Is(n,s)}:null}function Os(e,t,n={}){var i,o;const s=ws(e,t);if(!s||s.matches)return s;const r=Cs(s);return(o=(i=n.log)==null?void 0:i.error)==null||o.call(i,r,s)(),n.throwOnError!==!1&&yt(!1,r),s}function Mn(e){var s;const t=[],n=js(e);for(const r of n.matchAll(vs)){const i=((s=r[1])==null?void 0:s.trim())||null;t.push({blockName:r[2],body:r[3],instanceName:r[4]||null,layoutQualifier:i,hasLayoutQualifier:!!i,isStd140:!!(i&&/\blayout\s*\([^)]*\bstd140\b[^)]*\)/.exec(i))})}return t}function Ls(e,t,n,s){var o;const r=Mn(e).filter(c=>!c.isStd140),i=new Set;for(const c of r){if(i.has(c.blockName))continue;i.add(c.blockName);const a="",l=c.hasLayoutQualifier?`declares ${Ds(c.layoutQualifier)} instead of layout(std140)`:"does not declare layout(std140)",f=`${a}${t} shader uniform block ${c.blockName} ${l}. luma.gl host-side shader block packing assumes explicit layout(std140) for GLSL uniform blocks. Add \`layout(std140)\` to the block declaration.`;(o=n==null?void 0:n.warn)==null||o.call(n,f,c)()}return r}function Rs(e,t,n){const s=t==="wgsl"?Ps(e,n):Ns(e,n);if(!s)return null;const r=[];for(const i of s.split(`
`)){const o=i.replace(/\/\/.*$/,"").trim();if(!o||o.startsWith("#"))continue;const c=t==="wgsl"?o.match(/^([A-Za-z0-9_]+)\s*:/):o.match(Ss);c&&r.push(c[1])}return r}function Ps(e,t){const n=new RegExp(`\\bstruct\\s+${t}\\b`,"m").exec(e);if(!n)return null;const s=e.indexOf("{",n.index);if(s<0)return null;let r=0;for(let i=s;i<e.length;i++){const o=e[i];if(o==="{"){r++;continue}if(o==="}"&&(r--,r===0))return e.slice(s+1,i)}return null}function Ns(e,t){const n=Mn(e).find(s=>s.blockName===t);return(n==null?void 0:n.body)||null}function Is(e,t){if(e.length!==t.length)return!1;for(let n=0;n<e.length;n++)if(e[n]!==t[n])return!1;return!0}function Cs(e){const{expectedUniformNames:t,actualUniformNames:n}=e,s=t.filter(c=>!n.includes(c)),r=n.filter(c=>!t.includes(c)),i=[`Expected ${t.length} fields, found ${n.length}.`],o=ks(t,n);return o&&i.push(o),s.length&&i.push(`Missing from shader block (${s.length}): ${Pe(s)}.`),r.length&&i.push(`Unexpected in shader block (${r.length}): ${Pe(r)}.`),t.length<=12&&n.length<=12&&(s.length||r.length)&&(i.push(`Expected: ${t.join(", ")}.`),i.push(`Actual: ${n.join(", ")}.`)),`${e.moduleName}: ${e.stage} shader uniform block ${e.uniformBlockName} does not match module.uniformTypes. ${i.join(" ")}`}function js(e){return e.replace(/\/\*[\s\S]*?\*\//g,"").replace(/\/\/.*$/gm,"")}function Ds(e){return e.replace(/\s+/g," ").trim()}function ks(e,t){const n=Math.min(e.length,t.length);for(let s=0;s<n;s++)if(e[s]!==t[s])return`First mismatch at field ${s+1}: expected ${e[s]}, found ${t[s]}.`;return e.length>t.length?`Shader block ends after field ${t.length}; expected next field ${e[t.length]}.`:t.length>e.length?`Shader block has extra field ${t.length}: ${t[e.length]}.`:null}function Pe(e,t=8){if(e.length<=t)return e.join(", ");const n=e.length-t;return`${e.slice(0,t).join(", ")}, ... (${n} more)`}function Us(e){switch(e==null?void 0:e.gpu.toLowerCase()){case"apple":return`#define APPLE_GPU
// Apple optimizes away the calculation necessary for emulated fp64
#define LUMA_FP64_CODE_ELIMINATION_WORKAROUND 1
#define LUMA_FP32_TAN_PRECISION_WORKAROUND 1
// Intel GPU doesn't have full 32 bits precision in same cases, causes overflow
#define LUMA_FP64_HIGH_BITS_OVERFLOW_WORKAROUND 1
`;case"nvidia":return`#define NVIDIA_GPU
// Nvidia optimizes away the calculation necessary for emulated fp64
#define LUMA_FP64_CODE_ELIMINATION_WORKAROUND 1
`;case"intel":return`#define INTEL_GPU
// Intel optimizes away the calculation necessary for emulated fp64
#define LUMA_FP64_CODE_ELIMINATION_WORKAROUND 1
// Intel's built-in 'tan' function doesn't have acceptable precision
#define LUMA_FP32_TAN_PRECISION_WORKAROUND 1
// Intel GPU doesn't have full 32 bits precision in same cases, causes overflow
#define LUMA_FP64_HIGH_BITS_OVERFLOW_WORKAROUND 1
`;case"amd":return`#define AMD_GPU
`;default:return`#define DEFAULT_GPU
// Prevent driver from optimizing away the calculation necessary for emulated fp64
#define LUMA_FP64_CODE_ELIMINATION_WORKAROUND 1
// Headless Chrome's software shader 'tan' function doesn't have acceptable precision
#define LUMA_FP32_TAN_PRECISION_WORKAROUND 1
// If the GPU doesn't have full 32 bits precision, will causes overflow
#define LUMA_FP64_HIGH_BITS_OVERFLOW_WORKAROUND 1
`}}function $s(e,t){var s;if(Number(((s=e.match(/^#version[ \t]+(\d+)/m))==null?void 0:s[1])||100)!==300)throw new Error("luma.gl v9 only supports GLSL 3.00 shader sources");switch(t){case"vertex":return e=Ne(e,Bs),e;case"fragment":return e=Ne(e,zs),e;default:throw new Error(t)}}const An=[[/^(#version[ \t]+(100|300[ \t]+es))?[ \t]*\n/,`#version 300 es
`],[/\btexture(2D|2DProj|Cube)Lod(EXT)?\(/g,"textureLod("],[/\btexture(2D|2DProj|Cube)(EXT)?\(/g,"texture("]],Bs=[...An,[le("attribute"),"in $1"],[le("varying"),"out $1"]],zs=[...An,[le("varying"),"in $1"]];function Ne(e,t){for(const[n,s]of t)e=e.replace(n,s);return e}function le(e){return new RegExp(`\\b${e}[ \\t]+(\\w+[ \\t]+\\w+(\\[\\w+\\])?;)`,"g")}function Sn(e,t){let n="";for(const s in e){const r=e[s];if(n+=`void ${r.signature} {
`,r.header&&(n+=`  ${r.header}`),t[s]){const i=t[s];i.sort((o,c)=>o.order-c.order);for(const o of i)n+=`  ${o.injection}
`}r.footer&&(n+=`  ${r.footer}`),n+=`}
`}return n}function vn(e){const t={vertex:{},fragment:{}};for(const n of e){let s,r;typeof n!="string"?(s=n,r=s.hook):(s={},r=n),r=r.trim();const[i,o]=r.split(":"),c=r.replace(/\(.+/,""),a=Object.assign(s,{signature:o});switch(i){case"vs":t.vertex[c]=a;break;case"fs":t.fragment[c]=a;break;default:throw new Error(i)}}return t}function Fs(e,t){return{name:Ws(e,t),language:"glsl",version:Gs(e)}}function Ws(e,t="unnamed"){const s=/#define[^\S\r\n]*SHADER_NAME[^\S\r\n]*([A-Za-z0-9_-]+)\s*/.exec(e);return s?s[1]:t}function Gs(e){let t=100;const n=e.match(/[^\s]+/g);if(n&&n.length>=2&&n[0]==="#version"){const s=parseInt(n[1],10);Number.isFinite(s)&&(t=s)}if(t!==100&&t!==300)throw new Error(`Invalid GLSL version ${t}`);return t}const z="(?:var<\\s*(uniform|storage(?:\\s*,\\s*[A-Za-z_][A-Za-z0-9_]*)?)\\s*>|var)\\s+([A-Za-z_][A-Za-z0-9_]*)",F="\\s*",Et=[new RegExp(`@binding\\(\\s*(auto|\\d+)\\s*\\)${F}@group\\(\\s*(\\d+)\\s*\\)${F}${z}`,"g"),new RegExp(`@group\\(\\s*(\\d+)\\s*\\)${F}@binding\\(\\s*(auto|\\d+)\\s*\\)${F}${z}`,"g")],fe=[new RegExp(`@binding\\(\\s*(auto|\\d+)\\s*\\)${F}@group\\(\\s*(\\d+)\\s*\\)${F}${z}`,"g"),new RegExp(`@group\\(\\s*(\\d+)\\s*\\)${F}@binding\\(\\s*(auto|\\d+)\\s*\\)${F}${z}`,"g")],Hs=[new RegExp(`@binding\\(\\s*(\\d+)\\s*\\)${F}@group\\(\\s*(\\d+)\\s*\\)${F}${z}`,"g"),new RegExp(`@group\\(\\s*(\\d+)\\s*\\)${F}@binding\\(\\s*(\\d+)\\s*\\)${F}${z}`,"g")],Vs=[new RegExp(`@binding\\(\\s*(auto)\\s*\\)\\s*@group\\(\\s*(\\d+)\\s*\\)\\s*${z}`,"g"),new RegExp(`@group\\(\\s*(\\d+)\\s*\\)\\s*@binding\\(\\s*(auto)\\s*\\)\\s*${z}`,"g"),new RegExp(`@binding\\(\\s*(auto)\\s*\\)\\s*@group\\(\\s*(\\d+)\\s*\\)(?:[\\s\\n\\r]*@[A-Za-z_][^\\n\\r]*)*[\\s\\n\\r]*${z}`,"g"),new RegExp(`@group\\(\\s*(\\d+)\\s*\\)\\s*@binding\\(\\s*(auto)\\s*\\)(?:[\\s\\n\\r]*@[A-Za-z_][^\\n\\r]*)*[\\s\\n\\r]*${z}`,"g")];function ye(e){const t=e.split("");let n=0,s=0,r=!1,i=!1,o=!1;for(;n<e.length;){const c=e[n],a=e[n+1];if(i){o?o=!1:c==="\\"?o=!0:c==='"'&&(i=!1),n++;continue}if(r){c===`
`||c==="\r"?r=!1:t[n]=" ",n++;continue}if(s>0){if(c==="/"&&a==="*"){t[n]=" ",t[n+1]=" ",s++,n+=2;continue}if(c==="*"&&a==="/"){t[n]=" ",t[n+1]=" ",s--,n+=2;continue}c!==`
`&&c!=="\r"&&(t[n]=" "),n++;continue}if(c==='"'){i=!0,n++;continue}if(c==="/"&&a==="/"){t[n]=" ",t[n+1]=" ",r=!0,n+=2;continue}if(c==="/"&&a==="*"){t[n]=" ",t[n+1]=" ",s=1,n+=2;continue}n++}return t.join("")}function ht(e,t){var r;const n=ye(e),s=[];for(const i of t){i.lastIndex=0;let o;for(o=i.exec(n);o;){const c=i===t[0],a=o.index,l=o[0].length;s.push({match:e.slice(a,a+l),index:a,length:l,bindingToken:o[c?1:2],groupToken:o[c?2:1],accessDeclaration:(r=o[3])==null?void 0:r.trim(),name:o[4]}),o=i.exec(n)}}return s.sort((i,o)=>i.index-o.index)}function xn(e,t,n){const s=ht(e,t);if(!s.length)return e;let r="",i=0;for(const o of s)r+=e.slice(i,o.index),r+=n(o),i=o.index+o.length;return r+=e.slice(i),r}function wn(e){return/@binding\(\s*auto\s*\)/.test(ye(e))}function Ys(e,t){return ht(e,t===Et||t===fe?Vs:t).find(s=>s.bindingToken==="auto")}const Ie=[new RegExp(`@binding\\(\\s*(\\d+)\\s*\\)\\s*@group\\(\\s*(\\d+)\\s*\\)\\s*${z}\\s*:\\s*([^;]+);`,"g"),new RegExp(`@group\\(\\s*(\\d+)\\s*\\)\\s*@binding\\(\\s*(\\d+)\\s*\\)\\s*${z}\\s*:\\s*([^;]+);`,"g")];function On(e,t=[]){var i;const n=ye(e),s=new Map;for(const o of t)s.set(Ce(o.name,o.group,o.location),o.moduleName);const r=[];for(const o of Ie){o.lastIndex=0;let c;for(c=o.exec(n);c;){const a=o===Ie[0],l=Number(c[a?1:2]),f=Number(c[a?2:1]),h=(i=c[3])==null?void 0:i.trim(),u=c[4],d=c[5].trim(),g=s.get(Ce(u,f,l));r.push(Xs({name:u,group:f,binding:l,owner:g?"module":"application",moduleName:g,accessDeclaration:h,resourceType:d})),c=o.exec(n)}}return r.sort((o,c)=>o.group!==c.group?o.group-c.group:o.binding!==c.binding?o.binding-c.binding:o.name.localeCompare(c.name))}function Xs(e){const t={name:e.name,group:e.group,binding:e.binding,owner:e.owner,kind:"unknown",moduleName:e.moduleName,resourceType:e.resourceType};if(e.accessDeclaration){const n=e.accessDeclaration.split(",").map(s=>s.trim());if(n[0]==="uniform")return{...t,kind:"uniform",access:"uniform"};if(n[0]==="storage"){const s=n[1]||"read_write";return{...t,kind:s==="read"?"read-only-storage":"storage",access:s}}}return e.resourceType==="sampler"||e.resourceType==="sampler_comparison"?{...t,kind:"sampler",samplerKind:e.resourceType==="sampler_comparison"?"comparison":"filtering"}:e.resourceType.startsWith("texture_storage_")?{...t,kind:"storage-texture",access:Zs(e.resourceType),viewDimension:je(e.resourceType)}:e.resourceType.startsWith("texture_")?{...t,kind:"texture",viewDimension:je(e.resourceType),sampleType:qs(e.resourceType),multisampled:e.resourceType.startsWith("texture_multisampled_")}:t}function Ce(e,t,n){return`${t}:${n}:${e}`}function je(e){if(e.includes("cube_array"))return"cube-array";if(e.includes("2d_array"))return"2d-array";if(e.includes("cube"))return"cube";if(e.includes("3d"))return"3d";if(e.includes("2d"))return"2d";if(e.includes("1d"))return"1d"}function qs(e){if(e.startsWith("texture_depth_"))return"depth";if(e.includes("<i32>"))return"sint";if(e.includes("<u32>"))return"uint";if(e.includes("<f32>"))return"float"}function Zs(e){const t=/,\s*([A-Za-z_][A-Za-z0-9_]*)\s*>$/.exec(e);return t==null?void 0:t[1]}const Te=`

${Lt}
`,bt=100,Ks=`precision highp float;
`;function Js(e){const t=bn(e.modules||[]),{source:n,bindingAssignments:s}=tr(e.platformInfo,{...e,source:e.source,stage:"vertex",modules:t});return{source:n,getUniforms:Ln(t),bindingAssignments:s,bindingTable:On(n,s)}}function Qs(e){const{vs:t,fs:n}=e,s=bn(e.modules||[]);return{vs:De(e.platformInfo,{...e,source:t,stage:"vertex",modules:s}),fs:De(e.platformInfo,{...e,source:n,stage:"fragment",modules:s}),getUniforms:Ln(s)}}function tr(e,t){var E;const{source:n,stage:s,modules:r,hookFunctions:i=[],inject:o={},log:c}=t;yt(typeof n=="string","shader source must be a string");const a=n;let l="";const f=vn(i),h={},u={},d={};for(const _ in o){const y=typeof o[_]=="string"?{injection:o[_],order:0}:o[_],b=/^(v|f)s:(#)?([\w-]+)$/.exec(_);if(b){const A=b[2],x=b[3];A?x==="decl"?u[_]=[y]:d[_]=[y]:h[_]=[y]}else d[_]=[y]}const g=r,p=sr(a),m=nr(p.source),M=cr(g,t._bindingRegistry,m),v=[];for(const _ of g){c&&En(_,a,c);const y=rr(Rn(_,"wgsl",c),_,{usedBindingsByGroup:m,bindingRegistry:t._bindingRegistry,reservedBindingKeysByGroup:M});v.push(...y.bindingAssignments);const b=y.source;l+=b;const A=((E=_.injections)==null?void 0:E[s])||{};for(const x in A){const w=/^(v|f)s:#([\w-]+)$/.exec(x);if(w){const N=w[2]==="decl"?u:d;N[x]=N[x]||[],N[x].push(A[x])}else h[x]=h[x]||[],h[x].push(A[x])}}return l+=Te,l=It(l,s,u),l+=Sn(f[s],h),l+=ur(v),l+=p.source,l=It(l,s,d),hr(l),{source:l,bindingAssignments:v}}function De(e,t){var b;const{source:n,stage:s,language:r="glsl",modules:i,defines:o={},hookFunctions:c=[],inject:a={},prologue:l=!0,log:f}=t;yt(typeof n=="string","shader source must be a string");const h=r==="glsl"?Fs(n).version:-1,u=e.shaderLanguageVersion,d=h===100?"#version 100":"#version 300 es",p=n.split(`
`).slice(1).join(`
`),m={};i.forEach(A=>{Object.assign(m,A.defines)}),Object.assign(m,o);let M="";switch(r){case"wgsl":break;case"glsl":M=l?`${d}

// ----- PROLOGUE -------------------------
${`#define SHADER_TYPE_${s.toUpperCase()}`}

${Us(e)}
${s==="fragment"?Ks:""}

// ----- APPLICATION DEFINES -------------------------

${er(m)}

`:`${d}
`;break}const v=vn(c),E={},_={},y={};for(const A in a){const x=typeof a[A]=="string"?{injection:a[A],order:0}:a[A],w=/^(v|f)s:(#)?([\w-]+)$/.exec(A);if(w){const O=w[2],N=w[3];O?N==="decl"?_[A]=[x]:y[A]=[x]:E[A]=[x]}else y[A]=[x]}for(const A of i){f&&En(A,p,f);const x=Rn(A,s,f);M+=x;const w=((b=A.instance)==null?void 0:b.normalizedInjections[s])||{};for(const O in w){const N=/^(v|f)s:#([\w-]+)$/.exec(O);if(N){const k=N[2]==="decl"?_:y;k[O]=k[O]||[],k[O].push(w[O])}else E[O]=E[O]||[],E[O].push(w[O])}}return M+="// ----- MAIN SHADER SOURCE -------------------------",M+=Te,M=It(M,s,_),M+=Sn(v[s],E),M+=p,M=It(M,s,y),r==="glsl"&&h!==u&&(M=$s(M,s)),r==="glsl"&&Ls(M,s,f),M.trim()}function Ln(e){return function(n){var r;const s={};for(const i of e){const o=(r=i.getUniforms)==null?void 0:r.call(i,n,s);Object.assign(s,o)}return s}}function er(e={}){let t="";for(const n in e){const s=e[n];(s||Number.isFinite(s))&&(t+=`#define ${n.toUpperCase()} ${e[n]}
`)}return t}function Rn(e,t,n){let s;switch(t){case"vertex":s=e.vs||"";break;case"fragment":s=e.fs||"";break;case"wgsl":s=e.source||"";break;default:yt(!1)}if(!e.name)throw new Error("Shader module must have a name");Os(e,t,{log:n});const r=e.name.toUpperCase().replace(/[^0-9a-z]/gi,"_");let i=`// ----- MODULE ${e.name} ---------------

`;return t!=="wgsl"&&(i+=`#define MODULE_${r}
`),i+=`${s}
`,i}function nr(e){const t=new Map;for(const n of ht(e,Hs)){const s=Number(n.bindingToken),r=Number(n.groupToken);Me(r,s,n.name),ct(t,r,s,`application binding "${n.name}"`)}return t}function sr(e){const t=ht(e,fe),n=new Map;for(const i of t){if(i.bindingToken==="auto")continue;const o=Number(i.bindingToken),c=Number(i.groupToken);Me(c,o,i.name),ct(n,c,o,`application binding "${i.name}"`)}const s={sawSupportedBindingDeclaration:t.length>0},r=xn(e,fe,i=>or(i,n,s));if(wn(e)&&!s.sawSupportedBindingDeclaration)throw new Error('Unsupported @binding(auto) declaration form in application WGSL. Use adjacent "@group(N)" and "@binding(auto)" decorators followed by a bindable "var" declaration.');return{source:r}}function rr(e,t,n){const s=[],i={sawSupportedBindingDeclaration:ht(e,Et).length>0,nextHintedBindingLocation:typeof t.firstBindingSlot=="number"?t.firstBindingSlot:null},o=xn(e,Et,c=>ir(c,{module:t,context:n,bindingAssignments:s,relocationState:i}));if(wn(e)&&!i.sawSupportedBindingDeclaration)throw new Error(`Unsupported @binding(auto) declaration form in module "${t.name}". Use adjacent "@group(N)" and "@binding(auto)" decorators followed by a bindable "var" declaration.`);return{source:o,bindingAssignments:s}}function ir(e,t){var u,d;const{module:n,context:s,bindingAssignments:r,relocationState:i}=t,{match:o,bindingToken:c,groupToken:a,name:l}=e,f=Number(a);if(c==="auto"){const g=Pn(f,n.name,l),p=(u=s.bindingRegistry)==null?void 0:u.get(g),m=p!==void 0?p:i.nextHintedBindingLocation===null?Ue(f,s.usedBindingsByGroup):Ue(f,s.usedBindingsByGroup,i.nextHintedBindingLocation);return ke(n.name,f,m,l),p!==void 0&&ar(s.reservedBindingKeysByGroup,f,m,g)?(r.push({moduleName:n.name,name:l,group:f,location:m}),o.replace(/@binding\(\s*auto\s*\)/,`@binding(${m})`)):(ct(s.usedBindingsByGroup,f,m,`module "${n.name}" binding "${l}"`),(d=s.bindingRegistry)==null||d.set(g,m),r.push({moduleName:n.name,name:l,group:f,location:m}),i.nextHintedBindingLocation!==null&&p===void 0&&(i.nextHintedBindingLocation=m+1),o.replace(/@binding\(\s*auto\s*\)/,`@binding(${m})`))}const h=Number(c);return ke(n.name,f,h,l),ct(s.usedBindingsByGroup,f,h,`module "${n.name}" binding "${l}"`),r.push({moduleName:n.name,name:l,group:f,location:h}),o}function or(e,t,n){const{match:s,bindingToken:r,groupToken:i,name:o}=e,c=Number(i);if(r==="auto"){const a=fr(c,t);return Me(c,a,o),ct(t,c,a,`application binding "${o}"`),s.replace(/@binding\(\s*auto\s*\)/,`@binding(${a})`)}return n.sawSupportedBindingDeclaration=!0,s}function cr(e,t,n){const s=new Map;if(!t)return s;for(const r of e)for(const i of lr(r)){const o=Pn(i.group,r.name,i.name),c=t.get(o);if(c!==void 0){const a=s.get(i.group)||new Map,l=a.get(c);if(l&&l!==o)throw new Error(`Duplicate WGSL binding reservation for modules "${l}" and "${o}": group ${i.group}, binding ${c}.`);ct(n,i.group,c,`registered module binding "${o}"`),a.set(c,o),s.set(i.group,a)}}return s}function ar(e,t,n,s){const r=e.get(t);if(!r)return!1;const i=r.get(n);if(!i)return!1;if(i!==s)throw new Error(`Registered module binding "${s}" collided with "${i}": group ${t}, binding ${n}.`);return!0}function lr(e){const t=[],n=e.source||"";for(const s of ht(n,Et))t.push({name:s.name,group:Number(s.groupToken)});return t}function Me(e,t,n){if(e===0&&t>=bt)throw new Error(`Application binding "${n}" in group 0 uses reserved binding ${t}. Application-owned explicit group-0 bindings must stay below ${bt}.`)}function ke(e,t,n,s){if(t===0&&n<bt)throw new Error(`Module "${e}" binding "${s}" in group 0 uses reserved application binding ${n}. Module-owned explicit group-0 bindings must be ${bt} or higher.`)}function ct(e,t,n,s){const r=e.get(t)||new Set;if(r.has(n))throw new Error(`Duplicate WGSL binding assignment for ${s}: group ${t}, binding ${n}.`);r.add(n),e.set(t,r)}function Ue(e,t,n){const s=t.get(e)||new Set;let r=n??(e===0?bt:s.size>0?Math.max(...s)+1:0);for(;s.has(r);)r++;return r}function fr(e,t){const n=t.get(e)||new Set;let s=0;for(;n.has(s);)s++;return s}function hr(e){const t=Ys(e,Et);if(!t)return;const n=dr(e,t.index);throw n?new Error(`Unresolved @binding(auto) for module "${n}" binding "${t.name}" remained in assembled WGSL source.`):gr(e,t.index)?new Error(`Unresolved @binding(auto) for application binding "${t.name}" remained in assembled WGSL source.`):new Error(`Unresolved @binding(auto) remained in assembled WGSL source near "${pr(t.match)}".`)}function ur(e){if(e.length===0)return"";let t=`// ----- MODULE WGSL BINDING ASSIGNMENTS ---------------
`;for(const n of e)t+=`// ${n.moduleName}.${n.name} -> @group(${n.group}) @binding(${n.location})
`;return t+=`
`,t}function Pn(e,t,n){return`${e}:${t}:${n}`}function dr(e,t){const n=/^\/\/ ----- MODULE ([^\n]+) ---------------$/gm;let s,r;for(r=n.exec(e);r&&r.index<=t;)s=r[1],r=n.exec(e);return s}function gr(e,t){const n=e.indexOf(Te);return n>=0?t>n:!0}function pr(e){return e.replace(/\s+/g," ").trim()}const Ae="([a-zA-Z_][a-zA-Z0-9_]*)",mr=new RegExp(`^\\s*\\#\\s*ifdef\\s*${Ae}\\s*$`),_r=new RegExp(`^\\s*\\#\\s*ifndef\\s*${Ae}\\s*(?:\\/\\/.*)?$`),Er=/^\s*\#\s*else\s*(?:\/\/.*)?$/,br=/^\s*\#\s*endif\s*$/,yr=new RegExp(`^\\s*\\#\\s*ifdef\\s*${Ae}\\s*(?:\\/\\/.*)?$`),Tr=/^\s*\#\s*endif\s*(?:\/\/.*)?$/;function Mr(e,t){var o,c;const n=e.split(`
`),s=[],r=[];let i=!0;for(const a of n){const l=a.match(yr)||a.match(mr),f=a.match(_r),h=a.match(Er),u=a.match(Tr)||a.match(br);if(l||f){const d=(o=l||f)==null?void 0:o[1],g=!!((c=t==null?void 0:t.defines)!=null&&c[d]),p=l?g:!g,m=i&&p;r.push({parentActive:i,branchTaken:p,active:m}),i=m}else if(h){const d=r[r.length-1];if(!d)throw new Error("Encountered #else without matching #ifdef or #ifndef");d.active=d.parentActive&&!d.branchTaken,d.branchTaken=!0,i=d.active}else u?(r.pop(),i=r.length?r[r.length-1].active:!0):i&&s.push(a)}if(r.length>0)throw new Error("Unterminated conditional block in shader source");return s.join(`
`)}const K=class K{constructor(){T(this,"_hookFunctions",[]);T(this,"_defaultModules",[]);T(this,"_wgslBindingRegistry",new Map)}static getDefaultShaderAssembler(){return K.defaultShaderAssembler=K.defaultShaderAssembler||new K,K.defaultShaderAssembler}addDefaultModule(t){this._defaultModules.find(n=>n.name===(typeof t=="string"?t:t.name))||this._defaultModules.push(t)}removeDefaultModule(t){const n=typeof t=="string"?t:t.name;this._defaultModules=this._defaultModules.filter(s=>s.name!==n)}addShaderHook(t,n){n&&(t=Object.assign(n,{hook:t})),this._hookFunctions.push(t)}assembleWGSLShader(t){const n=this._getModuleList(t.modules),s=this._hookFunctions,{source:r,getUniforms:i,bindingAssignments:o}=Js({...t,source:t.source,_bindingRegistry:this._wgslBindingRegistry,modules:n,hookFunctions:s}),c={...n.reduce((l,f)=>(Object.assign(l,f.defines),l),{}),...t.defines},a=t.platformInfo.shaderLanguage==="wgsl"?Mr(r,{defines:c}):r;return{source:a,getUniforms:i,modules:n,bindingAssignments:o,bindingTable:On(a,o)}}assembleGLSLShaderPair(t){const n=this._getModuleList(t.modules),s=this._hookFunctions;return{...Qs({...t,vs:t.vs,fs:t.fs,modules:n,hookFunctions:s}),modules:n}}_getModuleList(t=[]){const n=new Array(this._defaultModules.length+t.length),s={};let r=0;for(let i=0,o=this._defaultModules.length;i<o;++i){const c=this._defaultModules[i],a=c.name;n[r++]=c,s[a]=!0}for(let i=0,o=t.length;i<o;++i){const c=t[i],a=c.name;s[a]||(n[r++]=c,s[a]=!0)}return n.length=r,Ct(n),n}};T(K,"defaultShaderAssembler");let $e=K;const Ar=1/Math.PI*180,Sr=1/180*Math.PI,vr={EPSILON:1e-12,debug:!1,precision:4,printTypes:!1,printDegrees:!1,printRowMajor:!0,_cartographicRadians:!1};globalThis.mathgl=globalThis.mathgl||{config:{...vr}};const $=globalThis.mathgl.config;function xr(e,{precision:t=$.precision}={}){return e=Rr(e),`${parseFloat(e.toPrecision(t))}`}function at(e){return Array.isArray(e)||ArrayBuffer.isView(e)&&!(e instanceof DataView)}function Mc(e){return wr(e)}function Ac(e){return Or(e)}function wr(e,t){return Se(e,n=>n*Sr,t)}function Or(e,t){return Se(e,n=>n*Ar,t)}function jt(e,t,n){return Se(e,s=>Math.max(t,Math.min(n,s)))}function Lr(e,t,n){return at(e)?e.map((s,r)=>Lr(s,t[r],n)):n*t+(1-n)*e}function Dt(e,t,n){const s=$.EPSILON;n&&($.EPSILON=n);try{if(e===t)return!0;if(at(e)&&at(t)){if(e.length!==t.length)return!1;for(let r=0;r<e.length;++r)if(!Dt(e[r],t[r]))return!1;return!0}return e&&e.equals?e.equals(t):t&&t.equals?t.equals(e):typeof e=="number"&&typeof t=="number"?Math.abs(e-t)<=$.EPSILON*Math.max(1,Math.abs(e),Math.abs(t)):!1}finally{$.EPSILON=s}}function Rr(e){return Math.round(e/$.EPSILON)*$.EPSILON}function Pr(e){return e.clone?e.clone():new Array(e.length)}function Se(e,t,n){if(at(e)){const s=e;n=n||Pr(s);for(let r=0;r<n.length&&r<s.length;++r){const i=typeof e=="number"?e:e[r];n[r]=t(i,r,n)}return n}return t(e)}class Nn extends Array{clone(){return new this.constructor().copy(this)}fromArray(t,n=0){for(let s=0;s<this.ELEMENTS;++s)this[s]=t[s+n];return this.check()}toArray(t=[],n=0){for(let s=0;s<this.ELEMENTS;++s)t[n+s]=this[s];return t}toObject(t){return t}from(t){return Array.isArray(t)?this.copy(t):this.fromObject(t)}to(t){return t===this?this:at(t)?this.toArray(t):this.toObject(t)}toTarget(t){return t?this.to(t):this}toFloat32Array(){return new Float32Array(this)}toString(){return this.formatString($)}formatString(t){let n="";for(let s=0;s<this.ELEMENTS;++s)n+=(s>0?", ":"")+xr(this[s],t);return`${t.printTypes?this.constructor.name:""}[${n}]`}equals(t){if(!t||this.length!==t.length)return!1;for(let n=0;n<this.ELEMENTS;++n)if(!Dt(this[n],t[n]))return!1;return!0}exactEquals(t){if(!t||this.length!==t.length)return!1;for(let n=0;n<this.ELEMENTS;++n)if(this[n]!==t[n])return!1;return!0}negate(){for(let t=0;t<this.ELEMENTS;++t)this[t]=-this[t];return this.check()}lerp(t,n,s){if(s===void 0)return this.lerp(this,t,n);for(let r=0;r<this.ELEMENTS;++r){const i=t[r],o=typeof n=="number"?n:n[r];this[r]=i+s*(o-i)}return this.check()}min(t){for(let n=0;n<this.ELEMENTS;++n)this[n]=Math.min(t[n],this[n]);return this.check()}max(t){for(let n=0;n<this.ELEMENTS;++n)this[n]=Math.max(t[n],this[n]);return this.check()}clamp(t,n){for(let s=0;s<this.ELEMENTS;++s)this[s]=Math.min(Math.max(this[s],t[s]),n[s]);return this.check()}add(...t){for(const n of t)for(let s=0;s<this.ELEMENTS;++s)this[s]+=n[s];return this.check()}subtract(...t){for(const n of t)for(let s=0;s<this.ELEMENTS;++s)this[s]-=n[s];return this.check()}scale(t){if(typeof t=="number")for(let n=0;n<this.ELEMENTS;++n)this[n]*=t;else for(let n=0;n<this.ELEMENTS&&n<t.length;++n)this[n]*=t[n];return this.check()}multiplyByScalar(t){for(let n=0;n<this.ELEMENTS;++n)this[n]*=t;return this.check()}check(){if($.debug&&!this.validate())throw new Error(`math.gl: ${this.constructor.name} some fields set to invalid numbers'`);return this}validate(){let t=this.length===this.ELEMENTS;for(let n=0;n<this.ELEMENTS;++n)t=t&&Number.isFinite(this[n]);return t}sub(t){return this.subtract(t)}setScalar(t){for(let n=0;n<this.ELEMENTS;++n)this[n]=t;return this.check()}addScalar(t){for(let n=0;n<this.ELEMENTS;++n)this[n]+=t;return this.check()}subScalar(t){return this.addScalar(-t)}multiplyScalar(t){for(let n=0;n<this.ELEMENTS;++n)this[n]*=t;return this.check()}divideScalar(t){return this.multiplyByScalar(1/t)}clampScalar(t,n){for(let s=0;s<this.ELEMENTS;++s)this[s]=Math.min(Math.max(this[s],t),n);return this.check()}get elements(){return this}}function Nr(e,t){if(e.length!==t)return!1;for(let n=0;n<e.length;++n)if(!Number.isFinite(e[n]))return!1;return!0}function U(e){if(!Number.isFinite(e))throw new Error(`Invalid number ${JSON.stringify(e)}`);return e}function qt(e,t,n=""){if($.debug&&!Nr(e,t))throw new Error(`math.gl: ${n} some fields set to invalid numbers'`);return e}function Be(e,t){if(!e)throw new Error(`math.gl assertion ${t}`)}class Ir extends Nn{get x(){return this[0]}set x(t){this[0]=U(t)}get y(){return this[1]}set y(t){this[1]=U(t)}len(){return Math.sqrt(this.lengthSquared())}magnitude(){return this.len()}lengthSquared(){let t=0;for(let n=0;n<this.ELEMENTS;++n)t+=this[n]*this[n];return t}magnitudeSquared(){return this.lengthSquared()}distance(t){return Math.sqrt(this.distanceSquared(t))}distanceSquared(t){let n=0;for(let s=0;s<this.ELEMENTS;++s){const r=this[s]-t[s];n+=r*r}return U(n)}dot(t){let n=0;for(let s=0;s<this.ELEMENTS;++s)n+=this[s]*t[s];return U(n)}normalize(){const t=this.magnitude();if(t!==0)for(let n=0;n<this.ELEMENTS;++n)this[n]/=t;return this.check()}multiply(...t){for(const n of t)for(let s=0;s<this.ELEMENTS;++s)this[s]*=n[s];return this.check()}divide(...t){for(const n of t)for(let s=0;s<this.ELEMENTS;++s)this[s]/=n[s];return this.check()}lengthSq(){return this.lengthSquared()}distanceTo(t){return this.distance(t)}distanceToSquared(t){return this.distanceSquared(t)}getComponent(t){return Be(t>=0&&t<this.ELEMENTS,"index is out of range"),U(this[t])}setComponent(t,n){return Be(t>=0&&t<this.ELEMENTS,"index is out of range"),this[t]=n,this.check()}addVectors(t,n){return this.copy(t).add(n)}subVectors(t,n){return this.copy(t).subtract(n)}multiplyVectors(t,n){return this.copy(t).multiply(n)}addScaledVector(t,n){return this.add(new this.constructor(t).multiplyScalar(n))}}const Rt=1e-6;let Q=typeof Float32Array<"u"?Float32Array:Array;function Cr(){const e=new Q(2);return Q!=Float32Array&&(e[0]=0,e[1]=0),e}function ze(e,t,n){return e[0]=t[0]+n[0],e[1]=t[1]+n[1],e}function jr(e,t,n){return e[0]=t[0]-n[0],e[1]=t[1]-n[1],e}function Dr(e,t){return e[0]=-t[0],e[1]=-t[1],e}function In(e,t,n,s){const r=t[0],i=t[1];return e[0]=r+s*(n[0]-r),e[1]=i+s*(n[1]-i),e}function Sc(e,t,n){const s=t[0],r=t[1];return e[0]=n[0]*s+n[2]*r,e[1]=n[1]*s+n[3]*r,e}function vc(e,t,n){const s=t[0],r=t[1];return e[0]=n[0]*s+n[2]*r+n[4],e[1]=n[1]*s+n[3]*r+n[5],e}function xc(e,t,n){const s=t[0],r=t[1];return e[0]=n[0]*s+n[3]*r+n[6],e[1]=n[1]*s+n[4]*r+n[7],e}function kr(e,t,n){const s=t[0],r=t[1];return e[0]=n[0]*s+n[4]*r+n[12],e[1]=n[1]*s+n[5]*r+n[13],e}const Ur=jr;(function(){const e=Cr();return function(t,n,s,r,i,o){let c,a;for(n||(n=2),s||(s=0),r?a=Math.min(r*n+s,t.length):a=t.length,c=s;c<a;c+=n)e[0]=t[c],e[1]=t[c+1],i(e,e,o),t[c]=e[0],t[c+1]=e[1];return t}})();function $r(e,t,n){const s=t[0],r=t[1],i=n[3]*s+n[7]*r||1;return e[0]=(n[0]*s+n[4]*r)/i,e[1]=(n[1]*s+n[5]*r)/i,e}function Cn(e,t,n){const s=t[0],r=t[1],i=t[2],o=n[3]*s+n[7]*r+n[11]*i||1;return e[0]=(n[0]*s+n[4]*r+n[8]*i)/o,e[1]=(n[1]*s+n[5]*r+n[9]*i)/o,e[2]=(n[2]*s+n[6]*r+n[10]*i)/o,e}function Br(e,t,n){const s=t[0],r=t[1];return e[0]=n[0]*s+n[2]*r,e[1]=n[1]*s+n[3]*r,e[2]=t[2],e}function wc(e,t,n){const s=t[0],r=t[1];return e[0]=n[0]*s+n[2]*r,e[1]=n[1]*s+n[3]*r,e[2]=t[2],e[3]=t[3],e}function Oc(e,t,n){const s=t[0],r=t[1],i=t[2];return e[0]=n[0]*s+n[3]*r+n[6]*i,e[1]=n[1]*s+n[4]*r+n[7]*i,e[2]=n[2]*s+n[5]*r+n[8]*i,e[3]=t[3],e}function zr(){const e=new Q(3);return Q!=Float32Array&&(e[0]=0,e[1]=0,e[2]=0),e}function Fr(e){const t=e[0],n=e[1],s=e[2];return Math.sqrt(t*t+n*n+s*s)}function Lc(e,t,n){const s=new Q(3);return s[0]=e,s[1]=t,s[2]=n,s}function Wr(e,t,n){return e[0]=t[0]-n[0],e[1]=t[1]-n[1],e[2]=t[2]-n[2],e}function Gr(e,t){const n=t[0]-e[0],s=t[1]-e[1],r=t[2]-e[2];return Math.sqrt(n*n+s*s+r*r)}function Hr(e){const t=e[0],n=e[1],s=e[2];return t*t+n*n+s*s}function Vr(e,t){return e[0]=-t[0],e[1]=-t[1],e[2]=-t[2],e}function Rc(e,t){const n=t[0],s=t[1],r=t[2];let i=n*n+s*s+r*r;return i>0&&(i=1/Math.sqrt(i)),e[0]=t[0]*i,e[1]=t[1]*i,e[2]=t[2]*i,e}function Yr(e,t){return e[0]*t[0]+e[1]*t[1]+e[2]*t[2]}function Xr(e,t,n){const s=t[0],r=t[1],i=t[2],o=n[0],c=n[1],a=n[2];return e[0]=r*a-i*c,e[1]=i*o-s*a,e[2]=s*c-r*o,e}function Pc(e,t,n,s){const r=t[0],i=t[1],o=t[2];return e[0]=r+s*(n[0]-r),e[1]=i+s*(n[1]-i),e[2]=o+s*(n[2]-o),e}function jn(e,t,n){const s=t[0],r=t[1],i=t[2];let o=n[3]*s+n[7]*r+n[11]*i+n[15];return o=o||1,e[0]=(n[0]*s+n[4]*r+n[8]*i+n[12])/o,e[1]=(n[1]*s+n[5]*r+n[9]*i+n[13])/o,e[2]=(n[2]*s+n[6]*r+n[10]*i+n[14])/o,e}function qr(e,t,n){const s=t[0],r=t[1],i=t[2];return e[0]=s*n[0]+r*n[3]+i*n[6],e[1]=s*n[1]+r*n[4]+i*n[7],e[2]=s*n[2]+r*n[5]+i*n[8],e}function Zr(e,t,n){const s=n[0],r=n[1],i=n[2],o=n[3],c=t[0],a=t[1],l=t[2];let f=r*l-i*a,h=i*c-s*l,u=s*a-r*c,d=r*u-i*h,g=i*f-s*u,p=s*h-r*f;const m=o*2;return f*=m,h*=m,u*=m,d*=2,g*=2,p*=2,e[0]=c+f+d,e[1]=a+h+g,e[2]=l+u+p,e}function Kr(e,t,n,s){const r=[],i=[];return r[0]=t[0]-n[0],r[1]=t[1]-n[1],r[2]=t[2]-n[2],i[0]=r[0],i[1]=r[1]*Math.cos(s)-r[2]*Math.sin(s),i[2]=r[1]*Math.sin(s)+r[2]*Math.cos(s),e[0]=i[0]+n[0],e[1]=i[1]+n[1],e[2]=i[2]+n[2],e}function Jr(e,t,n,s){const r=[],i=[];return r[0]=t[0]-n[0],r[1]=t[1]-n[1],r[2]=t[2]-n[2],i[0]=r[2]*Math.sin(s)+r[0]*Math.cos(s),i[1]=r[1],i[2]=r[2]*Math.cos(s)-r[0]*Math.sin(s),e[0]=i[0]+n[0],e[1]=i[1]+n[1],e[2]=i[2]+n[2],e}function Qr(e,t,n,s){const r=[],i=[];return r[0]=t[0]-n[0],r[1]=t[1]-n[1],r[2]=t[2]-n[2],i[0]=r[0]*Math.cos(s)-r[1]*Math.sin(s),i[1]=r[0]*Math.sin(s)+r[1]*Math.cos(s),i[2]=r[2],e[0]=i[0]+n[0],e[1]=i[1]+n[1],e[2]=i[2]+n[2],e}function ti(e,t){const n=e[0],s=e[1],r=e[2],i=t[0],o=t[1],c=t[2],a=Math.sqrt((n*n+s*s+r*r)*(i*i+o*o+c*c)),l=a&&Yr(e,t)/a;return Math.acos(Math.min(Math.max(l,-1),1))}const Nc=Wr,Ic=Gr,Cc=Fr,jc=Hr;(function(){const e=zr();return function(t,n,s,r,i,o){let c,a;for(n||(n=3),s||(s=0),r?a=Math.min(r*n+s,t.length):a=t.length,c=s;c<a;c+=n)e[0]=t[c],e[1]=t[c+1],e[2]=t[c+2],i(e,e,o),t[c]=e[0],t[c+1]=e[1],t[c+2]=e[2];return t}})();const Zt=[0,0,0];let Mt;class lt extends Ir{static get ZERO(){return Mt||(Mt=new lt(0,0,0),Object.freeze(Mt)),Mt}constructor(t=0,n=0,s=0){super(-0,-0,-0),arguments.length===1&&at(t)?this.copy(t):($.debug&&(U(t),U(n),U(s)),this[0]=t,this[1]=n,this[2]=s)}set(t,n,s){return this[0]=t,this[1]=n,this[2]=s,this.check()}copy(t){return this[0]=t[0],this[1]=t[1],this[2]=t[2],this.check()}fromObject(t){return $.debug&&(U(t.x),U(t.y),U(t.z)),this[0]=t.x,this[1]=t.y,this[2]=t.z,this.check()}toObject(t){return t.x=this[0],t.y=this[1],t.z=this[2],t}get ELEMENTS(){return 3}get z(){return this[2]}set z(t){this[2]=U(t)}angle(t){return ti(this,t)}cross(t){return Xr(this,this,t),this.check()}rotateX({radians:t,origin:n=Zt}){return Kr(this,this,n,t),this.check()}rotateY({radians:t,origin:n=Zt}){return Jr(this,this,n,t),this.check()}rotateZ({radians:t,origin:n=Zt}){return Qr(this,this,n,t),this.check()}transform(t){return this.transformAsPoint(t)}transformAsPoint(t){return jn(this,this,t),this.check()}transformAsVector(t){return Cn(this,this,t),this.check()}transformByMatrix3(t){return qr(this,this,t),this.check()}transformByMatrix2(t){return Br(this,this,t),this.check()}transformByQuaternion(t){return Zr(this,this,t),this.check()}}class ei extends Nn{toString(){let t="[";if($.printRowMajor){t+="row-major:";for(let n=0;n<this.RANK;++n)for(let s=0;s<this.RANK;++s)t+=` ${this[s*this.RANK+n]}`}else{t+="column-major:";for(let n=0;n<this.ELEMENTS;++n)t+=` ${this[n]}`}return t+="]",t}getElementIndex(t,n){return n*this.RANK+t}getElement(t,n){return this[n*this.RANK+t]}setElement(t,n,s){return this[n*this.RANK+t]=U(s),this}getColumn(t,n=new Array(this.RANK).fill(-0)){const s=t*this.RANK;for(let r=0;r<this.RANK;++r)n[r]=this[s+r];return n}setColumn(t,n){const s=t*this.RANK;for(let r=0;r<this.RANK;++r)this[s+r]=n[r];return this}}function ni(e){return e[0]=1,e[1]=0,e[2]=0,e[3]=0,e[4]=0,e[5]=1,e[6]=0,e[7]=0,e[8]=0,e[9]=0,e[10]=1,e[11]=0,e[12]=0,e[13]=0,e[14]=0,e[15]=1,e}function si(e,t){if(e===t){const n=t[1],s=t[2],r=t[3],i=t[6],o=t[7],c=t[11];e[1]=t[4],e[2]=t[8],e[3]=t[12],e[4]=n,e[6]=t[9],e[7]=t[13],e[8]=s,e[9]=i,e[11]=t[14],e[12]=r,e[13]=o,e[14]=c}else e[0]=t[0],e[1]=t[4],e[2]=t[8],e[3]=t[12],e[4]=t[1],e[5]=t[5],e[6]=t[9],e[7]=t[13],e[8]=t[2],e[9]=t[6],e[10]=t[10],e[11]=t[14],e[12]=t[3],e[13]=t[7],e[14]=t[11],e[15]=t[15];return e}function he(e,t){const n=t[0],s=t[1],r=t[2],i=t[3],o=t[4],c=t[5],a=t[6],l=t[7],f=t[8],h=t[9],u=t[10],d=t[11],g=t[12],p=t[13],m=t[14],M=t[15],v=n*c-s*o,E=n*a-r*o,_=n*l-i*o,y=s*a-r*c,b=s*l-i*c,A=r*l-i*a,x=f*p-h*g,w=f*m-u*g,O=f*M-d*g,N=h*m-u*p,B=h*M-d*p,k=u*M-d*m;let R=v*k-E*B+_*N+y*O-b*w+A*x;return R?(R=1/R,e[0]=(c*k-a*B+l*N)*R,e[1]=(r*B-s*k-i*N)*R,e[2]=(p*A-m*b+M*y)*R,e[3]=(u*b-h*A-d*y)*R,e[4]=(a*O-o*k-l*w)*R,e[5]=(n*k-r*O+i*w)*R,e[6]=(m*_-g*A-M*E)*R,e[7]=(f*A-u*_+d*E)*R,e[8]=(o*B-c*O+l*x)*R,e[9]=(s*O-n*B-i*x)*R,e[10]=(g*b-p*_+M*v)*R,e[11]=(h*_-f*b-d*v)*R,e[12]=(c*w-o*N-a*x)*R,e[13]=(n*N-s*w+r*x)*R,e[14]=(p*E-g*y-m*v)*R,e[15]=(f*y-h*E+u*v)*R,e):null}function ri(e){const t=e[0],n=e[1],s=e[2],r=e[3],i=e[4],o=e[5],c=e[6],a=e[7],l=e[8],f=e[9],h=e[10],u=e[11],d=e[12],g=e[13],p=e[14],m=e[15],M=t*o-n*i,v=t*c-s*i,E=n*c-s*o,_=l*g-f*d,y=l*p-h*d,b=f*p-h*g,A=t*b-n*y+s*_,x=i*b-o*y+c*_,w=l*E-f*v+h*M,O=d*E-g*v+p*M;return a*A-r*x+m*w-u*O}function J(e,t,n){const s=t[0],r=t[1],i=t[2],o=t[3],c=t[4],a=t[5],l=t[6],f=t[7],h=t[8],u=t[9],d=t[10],g=t[11],p=t[12],m=t[13],M=t[14],v=t[15];let E=n[0],_=n[1],y=n[2],b=n[3];return e[0]=E*s+_*c+y*h+b*p,e[1]=E*r+_*a+y*u+b*m,e[2]=E*i+_*l+y*d+b*M,e[3]=E*o+_*f+y*g+b*v,E=n[4],_=n[5],y=n[6],b=n[7],e[4]=E*s+_*c+y*h+b*p,e[5]=E*r+_*a+y*u+b*m,e[6]=E*i+_*l+y*d+b*M,e[7]=E*o+_*f+y*g+b*v,E=n[8],_=n[9],y=n[10],b=n[11],e[8]=E*s+_*c+y*h+b*p,e[9]=E*r+_*a+y*u+b*m,e[10]=E*i+_*l+y*d+b*M,e[11]=E*o+_*f+y*g+b*v,E=n[12],_=n[13],y=n[14],b=n[15],e[12]=E*s+_*c+y*h+b*p,e[13]=E*r+_*a+y*u+b*m,e[14]=E*i+_*l+y*d+b*M,e[15]=E*o+_*f+y*g+b*v,e}function kt(e,t,n){const s=n[0],r=n[1],i=n[2];let o,c,a,l,f,h,u,d,g,p,m,M;return t===e?(e[12]=t[0]*s+t[4]*r+t[8]*i+t[12],e[13]=t[1]*s+t[5]*r+t[9]*i+t[13],e[14]=t[2]*s+t[6]*r+t[10]*i+t[14],e[15]=t[3]*s+t[7]*r+t[11]*i+t[15]):(o=t[0],c=t[1],a=t[2],l=t[3],f=t[4],h=t[5],u=t[6],d=t[7],g=t[8],p=t[9],m=t[10],M=t[11],e[0]=o,e[1]=c,e[2]=a,e[3]=l,e[4]=f,e[5]=h,e[6]=u,e[7]=d,e[8]=g,e[9]=p,e[10]=m,e[11]=M,e[12]=o*s+f*r+g*i+t[12],e[13]=c*s+h*r+p*i+t[13],e[14]=a*s+u*r+m*i+t[14],e[15]=l*s+d*r+M*i+t[15]),e}function ve(e,t,n){const s=n[0],r=n[1],i=n[2];return e[0]=t[0]*s,e[1]=t[1]*s,e[2]=t[2]*s,e[3]=t[3]*s,e[4]=t[4]*r,e[5]=t[5]*r,e[6]=t[6]*r,e[7]=t[7]*r,e[8]=t[8]*i,e[9]=t[9]*i,e[10]=t[10]*i,e[11]=t[11]*i,e[12]=t[12],e[13]=t[13],e[14]=t[14],e[15]=t[15],e}function ii(e,t,n,s){let r=s[0],i=s[1],o=s[2],c=Math.sqrt(r*r+i*i+o*o),a,l,f,h,u,d,g,p,m,M,v,E,_,y,b,A,x,w,O,N,B,k,R,ut;return c<Rt?null:(c=1/c,r*=c,i*=c,o*=c,l=Math.sin(n),a=Math.cos(n),f=1-a,h=t[0],u=t[1],d=t[2],g=t[3],p=t[4],m=t[5],M=t[6],v=t[7],E=t[8],_=t[9],y=t[10],b=t[11],A=r*r*f+a,x=i*r*f+o*l,w=o*r*f-i*l,O=r*i*f-o*l,N=i*i*f+a,B=o*i*f+r*l,k=r*o*f+i*l,R=i*o*f-r*l,ut=o*o*f+a,e[0]=h*A+p*x+E*w,e[1]=u*A+m*x+_*w,e[2]=d*A+M*x+y*w,e[3]=g*A+v*x+b*w,e[4]=h*O+p*N+E*B,e[5]=u*O+m*N+_*B,e[6]=d*O+M*N+y*B,e[7]=g*O+v*N+b*B,e[8]=h*k+p*R+E*ut,e[9]=u*k+m*R+_*ut,e[10]=d*k+M*R+y*ut,e[11]=g*k+v*R+b*ut,t!==e&&(e[12]=t[12],e[13]=t[13],e[14]=t[14],e[15]=t[15]),e)}function Dn(e,t,n){const s=Math.sin(n),r=Math.cos(n),i=t[4],o=t[5],c=t[6],a=t[7],l=t[8],f=t[9],h=t[10],u=t[11];return t!==e&&(e[0]=t[0],e[1]=t[1],e[2]=t[2],e[3]=t[3],e[12]=t[12],e[13]=t[13],e[14]=t[14],e[15]=t[15]),e[4]=i*r+l*s,e[5]=o*r+f*s,e[6]=c*r+h*s,e[7]=a*r+u*s,e[8]=l*r-i*s,e[9]=f*r-o*s,e[10]=h*r-c*s,e[11]=u*r-a*s,e}function oi(e,t,n){const s=Math.sin(n),r=Math.cos(n),i=t[0],o=t[1],c=t[2],a=t[3],l=t[8],f=t[9],h=t[10],u=t[11];return t!==e&&(e[4]=t[4],e[5]=t[5],e[6]=t[6],e[7]=t[7],e[12]=t[12],e[13]=t[13],e[14]=t[14],e[15]=t[15]),e[0]=i*r-l*s,e[1]=o*r-f*s,e[2]=c*r-h*s,e[3]=a*r-u*s,e[8]=i*s+l*r,e[9]=o*s+f*r,e[10]=c*s+h*r,e[11]=a*s+u*r,e}function kn(e,t,n){const s=Math.sin(n),r=Math.cos(n),i=t[0],o=t[1],c=t[2],a=t[3],l=t[4],f=t[5],h=t[6],u=t[7];return t!==e&&(e[8]=t[8],e[9]=t[9],e[10]=t[10],e[11]=t[11],e[12]=t[12],e[13]=t[13],e[14]=t[14],e[15]=t[15]),e[0]=i*r+l*s,e[1]=o*r+f*s,e[2]=c*r+h*s,e[3]=a*r+u*s,e[4]=l*r-i*s,e[5]=f*r-o*s,e[6]=h*r-c*s,e[7]=u*r-a*s,e}function Dc(e,t){const n=t[0],s=t[1],r=t[2],i=t[4],o=t[5],c=t[6],a=t[8],l=t[9],f=t[10];return e[0]=Math.sqrt(n*n+s*s+r*r),e[1]=Math.sqrt(i*i+o*o+c*c),e[2]=Math.sqrt(a*a+l*l+f*f),e}function ci(e,t){const n=t[0],s=t[1],r=t[2],i=t[3],o=n+n,c=s+s,a=r+r,l=n*o,f=s*o,h=s*c,u=r*o,d=r*c,g=r*a,p=i*o,m=i*c,M=i*a;return e[0]=1-h-g,e[1]=f+M,e[2]=u-m,e[3]=0,e[4]=f-M,e[5]=1-l-g,e[6]=d+p,e[7]=0,e[8]=u+m,e[9]=d-p,e[10]=1-l-h,e[11]=0,e[12]=0,e[13]=0,e[14]=0,e[15]=1,e}function ai(e,t,n,s,r,i,o){const c=1/(n-t),a=1/(r-s),l=1/(i-o);return e[0]=i*2*c,e[1]=0,e[2]=0,e[3]=0,e[4]=0,e[5]=i*2*a,e[6]=0,e[7]=0,e[8]=(n+t)*c,e[9]=(r+s)*a,e[10]=(o+i)*l,e[11]=-1,e[12]=0,e[13]=0,e[14]=o*i*2*l,e[15]=0,e}function li(e,t,n,s,r){const i=1/Math.tan(t/2);if(e[0]=i/n,e[1]=0,e[2]=0,e[3]=0,e[4]=0,e[5]=i,e[6]=0,e[7]=0,e[8]=0,e[9]=0,e[11]=-1,e[12]=0,e[13]=0,e[15]=0,r!=null&&r!==1/0){const o=1/(s-r);e[10]=(r+s)*o,e[14]=2*r*s*o}else e[10]=-1,e[14]=-2*s;return e}const fi=li;function hi(e,t,n,s,r,i,o){const c=1/(t-n),a=1/(s-r),l=1/(i-o);return e[0]=-2*c,e[1]=0,e[2]=0,e[3]=0,e[4]=0,e[5]=-2*a,e[6]=0,e[7]=0,e[8]=0,e[9]=0,e[10]=2*l,e[11]=0,e[12]=(t+n)*c,e[13]=(r+s)*a,e[14]=(o+i)*l,e[15]=1,e}const ui=hi;function di(e,t,n,s){let r,i,o,c,a,l,f,h,u,d;const g=t[0],p=t[1],m=t[2],M=s[0],v=s[1],E=s[2],_=n[0],y=n[1],b=n[2];return Math.abs(g-_)<Rt&&Math.abs(p-y)<Rt&&Math.abs(m-b)<Rt?ni(e):(h=g-_,u=p-y,d=m-b,r=1/Math.sqrt(h*h+u*u+d*d),h*=r,u*=r,d*=r,i=v*d-E*u,o=E*h-M*d,c=M*u-v*h,r=Math.sqrt(i*i+o*o+c*c),r?(r=1/r,i*=r,o*=r,c*=r):(i=0,o=0,c=0),a=u*c-d*o,l=d*i-h*c,f=h*o-u*i,r=Math.sqrt(a*a+l*l+f*f),r?(r=1/r,a*=r,l*=r,f*=r):(a=0,l=0,f=0),e[0]=i,e[1]=a,e[2]=h,e[3]=0,e[4]=o,e[5]=l,e[6]=u,e[7]=0,e[8]=c,e[9]=f,e[10]=d,e[11]=0,e[12]=-(i*g+o*p+c*m),e[13]=-(a*g+l*p+f*m),e[14]=-(h*g+u*p+d*m),e[15]=1,e)}function gi(){const e=new Q(4);return Q!=Float32Array&&(e[0]=0,e[1]=0,e[2]=0,e[3]=0),e}function kc(e,t,n){return e[0]=t[0]+n[0],e[1]=t[1]+n[1],e[2]=t[2]+n[2],e[3]=t[3]+n[3],e}function pi(e,t,n){return e[0]=t[0]*n,e[1]=t[1]*n,e[2]=t[2]*n,e[3]=t[3]*n,e}function Uc(e){const t=e[0],n=e[1],s=e[2],r=e[3];return Math.sqrt(t*t+n*n+s*s+r*r)}function $c(e){const t=e[0],n=e[1],s=e[2],r=e[3];return t*t+n*n+s*s+r*r}function Bc(e,t){const n=t[0],s=t[1],r=t[2],i=t[3];let o=n*n+s*s+r*r+i*i;return o>0&&(o=1/Math.sqrt(o)),e[0]=n*o,e[1]=s*o,e[2]=r*o,e[3]=i*o,e}function zc(e,t){return e[0]*t[0]+e[1]*t[1]+e[2]*t[2]+e[3]*t[3]}function Fc(e,t,n,s){const r=t[0],i=t[1],o=t[2],c=t[3];return e[0]=r+s*(n[0]-r),e[1]=i+s*(n[1]-i),e[2]=o+s*(n[2]-o),e[3]=c+s*(n[3]-c),e}function Wt(e,t,n){const s=t[0],r=t[1],i=t[2],o=t[3];return e[0]=n[0]*s+n[4]*r+n[8]*i+n[12]*o,e[1]=n[1]*s+n[5]*r+n[9]*i+n[13]*o,e[2]=n[2]*s+n[6]*r+n[10]*i+n[14]*o,e[3]=n[3]*s+n[7]*r+n[11]*i+n[15]*o,e}function Wc(e,t,n){const s=t[0],r=t[1],i=t[2],o=n[0],c=n[1],a=n[2],l=n[3],f=l*s+c*i-a*r,h=l*r+a*s-o*i,u=l*i+o*r-c*s,d=-o*s-c*r-a*i;return e[0]=f*l+d*-o+h*-a-u*-c,e[1]=h*l+d*-c+u*-o-f*-a,e[2]=u*l+d*-a+f*-c-h*-o,e[3]=t[3],e}(function(){const e=gi();return function(t,n,s,r,i,o){let c,a;for(n||(n=4),s||(s=0),r?a=Math.min(r*n+s,t.length):a=t.length,c=s;c<a;c+=n)e[0]=t[c],e[1]=t[c+1],e[2]=t[c+2],e[3]=t[c+3],i(e,e,o),t[c]=e[0],t[c+1]=e[1],t[c+2]=e[2],t[c+3]=e[3];return t}})();var ue;(function(e){e[e.COL0ROW0=0]="COL0ROW0",e[e.COL0ROW1=1]="COL0ROW1",e[e.COL0ROW2=2]="COL0ROW2",e[e.COL0ROW3=3]="COL0ROW3",e[e.COL1ROW0=4]="COL1ROW0",e[e.COL1ROW1=5]="COL1ROW1",e[e.COL1ROW2=6]="COL1ROW2",e[e.COL1ROW3=7]="COL1ROW3",e[e.COL2ROW0=8]="COL2ROW0",e[e.COL2ROW1=9]="COL2ROW1",e[e.COL2ROW2=10]="COL2ROW2",e[e.COL2ROW3=11]="COL2ROW3",e[e.COL3ROW0=12]="COL3ROW0",e[e.COL3ROW1=13]="COL3ROW1",e[e.COL3ROW2=14]="COL3ROW2",e[e.COL3ROW3=15]="COL3ROW3"})(ue||(ue={}));const mi=45*Math.PI/180,_i=1,Kt=.1,Jt=500,Ei=Object.freeze([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]);class tt extends ei{static get IDENTITY(){return yi()}static get ZERO(){return bi()}get ELEMENTS(){return 16}get RANK(){return 4}get INDICES(){return ue}constructor(t){super(-0,-0,-0,-0,-0,-0,-0,-0,-0,-0,-0,-0,-0,-0,-0,-0),arguments.length===1&&Array.isArray(t)?this.copy(t):this.identity()}copy(t){return this[0]=t[0],this[1]=t[1],this[2]=t[2],this[3]=t[3],this[4]=t[4],this[5]=t[5],this[6]=t[6],this[7]=t[7],this[8]=t[8],this[9]=t[9],this[10]=t[10],this[11]=t[11],this[12]=t[12],this[13]=t[13],this[14]=t[14],this[15]=t[15],this.check()}set(t,n,s,r,i,o,c,a,l,f,h,u,d,g,p,m){return this[0]=t,this[1]=n,this[2]=s,this[3]=r,this[4]=i,this[5]=o,this[6]=c,this[7]=a,this[8]=l,this[9]=f,this[10]=h,this[11]=u,this[12]=d,this[13]=g,this[14]=p,this[15]=m,this.check()}setRowMajor(t,n,s,r,i,o,c,a,l,f,h,u,d,g,p,m){return this[0]=t,this[1]=i,this[2]=l,this[3]=d,this[4]=n,this[5]=o,this[6]=f,this[7]=g,this[8]=s,this[9]=c,this[10]=h,this[11]=p,this[12]=r,this[13]=a,this[14]=u,this[15]=m,this.check()}toRowMajor(t){return t[0]=this[0],t[1]=this[4],t[2]=this[8],t[3]=this[12],t[4]=this[1],t[5]=this[5],t[6]=this[9],t[7]=this[13],t[8]=this[2],t[9]=this[6],t[10]=this[10],t[11]=this[14],t[12]=this[3],t[13]=this[7],t[14]=this[11],t[15]=this[15],t}identity(){return this.copy(Ei)}fromObject(t){return this.check()}fromQuaternion(t){return ci(this,t),this.check()}frustum(t){const{left:n,right:s,bottom:r,top:i,near:o=Kt,far:c=Jt}=t;return c===1/0?Ti(this,n,s,r,i,o):ai(this,n,s,r,i,o,c),this.check()}lookAt(t){const{eye:n,center:s=[0,0,0],up:r=[0,1,0]}=t;return di(this,n,s,r),this.check()}ortho(t){const{left:n,right:s,bottom:r,top:i,near:o=Kt,far:c=Jt}=t;return ui(this,n,s,r,i,o,c),this.check()}orthographic(t){const{fovy:n=mi,aspect:s=_i,focalDistance:r=1,near:i=Kt,far:o=Jt}=t;Fe(n);const c=n/2,a=r*Math.tan(c),l=a*s;return this.ortho({left:-l,right:l,bottom:-a,top:a,near:i,far:o})}perspective(t){const{fovy:n=45*Math.PI/180,aspect:s=1,near:r=.1,far:i=500}=t;return Fe(n),fi(this,n,s,r,i),this.check()}determinant(){return ri(this)}getScale(t=[-0,-0,-0]){return t[0]=Math.sqrt(this[0]*this[0]+this[1]*this[1]+this[2]*this[2]),t[1]=Math.sqrt(this[4]*this[4]+this[5]*this[5]+this[6]*this[6]),t[2]=Math.sqrt(this[8]*this[8]+this[9]*this[9]+this[10]*this[10]),t}getTranslation(t=[-0,-0,-0]){return t[0]=this[12],t[1]=this[13],t[2]=this[14],t}getRotation(t,n){t=t||[-0,-0,-0,-0,-0,-0,-0,-0,-0,-0,-0,-0,-0,-0,-0,-0],n=n||[-0,-0,-0];const s=this.getScale(n),r=1/s[0],i=1/s[1],o=1/s[2];return t[0]=this[0]*r,t[1]=this[1]*i,t[2]=this[2]*o,t[3]=0,t[4]=this[4]*r,t[5]=this[5]*i,t[6]=this[6]*o,t[7]=0,t[8]=this[8]*r,t[9]=this[9]*i,t[10]=this[10]*o,t[11]=0,t[12]=0,t[13]=0,t[14]=0,t[15]=1,t}getRotationMatrix3(t,n){t=t||[-0,-0,-0,-0,-0,-0,-0,-0,-0],n=n||[-0,-0,-0];const s=this.getScale(n),r=1/s[0],i=1/s[1],o=1/s[2];return t[0]=this[0]*r,t[1]=this[1]*i,t[2]=this[2]*o,t[3]=this[4]*r,t[4]=this[5]*i,t[5]=this[6]*o,t[6]=this[8]*r,t[7]=this[9]*i,t[8]=this[10]*o,t}transpose(){return si(this,this),this.check()}invert(){return he(this,this),this.check()}multiplyLeft(t){return J(this,t,this),this.check()}multiplyRight(t){return J(this,this,t),this.check()}rotateX(t){return Dn(this,this,t),this.check()}rotateY(t){return oi(this,this,t),this.check()}rotateZ(t){return kn(this,this,t),this.check()}rotateXYZ(t){return this.rotateX(t[0]).rotateY(t[1]).rotateZ(t[2])}rotateAxis(t,n){return ii(this,this,t,n),this.check()}scale(t){return ve(this,this,Array.isArray(t)?t:[t,t,t]),this.check()}translate(t){return kt(this,this,t),this.check()}transform(t,n){return t.length===4?(n=Wt(n||[-0,-0,-0,-0],t,this),qt(n,4),n):this.transformAsPoint(t,n)}transformAsPoint(t,n){const{length:s}=t;let r;switch(s){case 2:r=kr(n||[-0,-0],t,this);break;case 3:r=jn(n||[-0,-0,-0],t,this);break;default:throw new Error("Illegal vector")}return qt(r,t.length),r}transformAsVector(t,n){let s;switch(t.length){case 2:s=$r(n||[-0,-0],t,this);break;case 3:s=Cn(n||[-0,-0,-0],t,this);break;default:throw new Error("Illegal vector")}return qt(s,t.length),s}transformPoint(t,n){return this.transformAsPoint(t,n)}transformVector(t,n){return this.transformAsPoint(t,n)}transformDirection(t,n){return this.transformAsVector(t,n)}makeRotationX(t){return this.identity().rotateX(t)}makeTranslation(t,n,s){return this.identity().translate([t,n,s])}}let At,St;function bi(){return At||(At=new tt([0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]),Object.freeze(At)),At}function yi(){return St||(St=new tt,Object.freeze(St)),St}function Fe(e){if(e>Math.PI*2)throw Error("expected radians")}function Ti(e,t,n,s,r,i){const o=2*i/(n-t),c=2*i/(r-s),a=(n+t)/(n-t),l=(r+s)/(r-s),f=-1,h=-1,u=-2*i;return e[0]=o,e[1]=0,e[2]=0,e[3]=0,e[4]=0,e[5]=c,e[6]=0,e[7]=0,e[8]=a,e[9]=l,e[10]=f,e[11]=h,e[12]=0,e[13]=0,e[14]=u,e[15]=0,e}const Mi=`#ifdef LUMA_FP32_TAN_PRECISION_WORKAROUND

// All these functions are for substituting tan() function from Intel GPU only
const float TWO_PI = 6.2831854820251465;
const float PI_2 = 1.5707963705062866;
const float PI_16 = 0.1963495463132858;

const float SIN_TABLE_0 = 0.19509032368659973;
const float SIN_TABLE_1 = 0.3826834261417389;
const float SIN_TABLE_2 = 0.5555702447891235;
const float SIN_TABLE_3 = 0.7071067690849304;

const float COS_TABLE_0 = 0.9807852506637573;
const float COS_TABLE_1 = 0.9238795042037964;
const float COS_TABLE_2 = 0.8314695954322815;
const float COS_TABLE_3 = 0.7071067690849304;

const float INVERSE_FACTORIAL_3 = 1.666666716337204e-01; // 1/3!
const float INVERSE_FACTORIAL_5 = 8.333333767950535e-03; // 1/5!
const float INVERSE_FACTORIAL_7 = 1.9841270113829523e-04; // 1/7!
const float INVERSE_FACTORIAL_9 = 2.75573188446287533e-06; // 1/9!

float sin_taylor_fp32(float a) {
  float r, s, t, x;

  if (a == 0.0) {
    return 0.0;
  }

  x = -a * a;
  s = a;
  r = a;

  r = r * x;
  t = r * INVERSE_FACTORIAL_3;
  s = s + t;

  r = r * x;
  t = r * INVERSE_FACTORIAL_5;
  s = s + t;

  r = r * x;
  t = r * INVERSE_FACTORIAL_7;
  s = s + t;

  r = r * x;
  t = r * INVERSE_FACTORIAL_9;
  s = s + t;

  return s;
}

void sincos_taylor_fp32(float a, out float sin_t, out float cos_t) {
  if (a == 0.0) {
    sin_t = 0.0;
    cos_t = 1.0;
  }
  sin_t = sin_taylor_fp32(a);
  cos_t = sqrt(1.0 - sin_t * sin_t);
}

float tan_taylor_fp32(float a) {
    float sin_a;
    float cos_a;

    if (a == 0.0) {
        return 0.0;
    }

    // 2pi range reduction
    float z = floor(a / TWO_PI);
    float r = a - TWO_PI * z;

    float t;
    float q = floor(r / PI_2 + 0.5);
    int j = int(q);

    if (j < -2 || j > 2) {
        return 1.0 / 0.0;
    }

    t = r - PI_2 * q;

    q = floor(t / PI_16 + 0.5);
    int k = int(q);
    int abs_k = int(abs(float(k)));

    if (abs_k > 4) {
        return 1.0 / 0.0;
    } else {
        t = t - PI_16 * q;
    }

    float u = 0.0;
    float v = 0.0;

    float sin_t, cos_t;
    float s, c;
    sincos_taylor_fp32(t, sin_t, cos_t);

    if (k == 0) {
        s = sin_t;
        c = cos_t;
    } else {
        if (abs(float(abs_k) - 1.0) < 0.5) {
            u = COS_TABLE_0;
            v = SIN_TABLE_0;
        } else if (abs(float(abs_k) - 2.0) < 0.5) {
            u = COS_TABLE_1;
            v = SIN_TABLE_1;
        } else if (abs(float(abs_k) - 3.0) < 0.5) {
            u = COS_TABLE_2;
            v = SIN_TABLE_2;
        } else if (abs(float(abs_k) - 4.0) < 0.5) {
            u = COS_TABLE_3;
            v = SIN_TABLE_3;
        }
        if (k > 0) {
            s = u * sin_t + v * cos_t;
            c = u * cos_t - v * sin_t;
        } else {
            s = u * sin_t - v * cos_t;
            c = u * cos_t + v * sin_t;
        }
    }

    if (j == 0) {
        sin_a = s;
        cos_a = c;
    } else if (j == 1) {
        sin_a = c;
        cos_a = -s;
    } else if (j == -1) {
        sin_a = -c;
        cos_a = s;
    } else {
        sin_a = -s;
        cos_a = -c;
    }
    return sin_a / cos_a;
}
#endif

float tan_fp32(float a) {
#ifdef LUMA_FP32_TAN_PRECISION_WORKAROUND
  return tan_taylor_fp32(a);
#else
  return tan(a);
#endif
}
`,Ai={name:"fp32",vs:Mi},Si=new be({id:"luma.gl"}),Qt={};function vi(e="id"){Qt[e]=Qt[e]||1;const t=Qt[e]++;return`${e}-${t}`}const xi="cpu-hotspot-profiler",We="GPU Resource Counts",Ge="Resource Counts",He="GPU Time and Memory",wi=["Resources","Buffers","Textures","Samplers","TextureViews","Framebuffers","QuerySets","Shaders","RenderPipelines","ComputePipelines","PipelineLayouts","VertexArrays","RenderPasss","ComputePasss","CommandEncoders","CommandBuffers"],Oi=["Resources","Buffers","Textures","Samplers","TextureViews","Framebuffers","QuerySets","Shaders","RenderPipelines","SharedRenderPipelines","ComputePipelines","PipelineLayouts","VertexArrays","RenderPasss","ComputePasss","CommandEncoders","CommandBuffers"],Li=wi.flatMap(e=>[`${e} Created`,`${e} Active`]),Ri=Oi.flatMap(e=>[`${e} Created`,`${e} Active`]),Ve=new WeakMap,Ye=new WeakMap;class Z{constructor(t,n,s){T(this,"id");T(this,"props");T(this,"userData",{});T(this,"_device");T(this,"destroyed",!1);T(this,"allocatedBytes",0);T(this,"allocatedBytesName",null);T(this,"_attachedResources",new Set);if(!t)throw new Error("no device");this._device=t,this.props=Pi(n,s);const r=this.props.id!=="undefined"?this.props.id:vi(this[Symbol.toStringTag]);this.props.id=r,this.id=r,this.userData=this.props.userData||{},this.addStats()}toString(){return`${this[Symbol.toStringTag]||this.constructor.name}:"${this.id}"`}destroy(){this.destroyed||this.destroyResource()}delete(){return this.destroy(),this}getProps(){return this.props}attachResource(t){this._attachedResources.add(t)}detachResource(t){this._attachedResources.delete(t)}destroyAttachedResource(t){this._attachedResources.delete(t)&&t.destroy()}destroyAttachedResources(){for(const t of this._attachedResources)t.destroy();this._attachedResources=new Set}destroyResource(){this.destroyed||(this.destroyAttachedResources(),this.removeStats(),this.destroyed=!0)}removeStats(){const t=pt(this._device),n=t?X():0,s=[this._device.statsManager.getStats(We),this._device.statsManager.getStats(Ge)],r=qe(this._device);for(const o of s)Xe(o,r);const i=this.getStatsName();for(const o of s)o.get("Resources Active").decrementCount(),o.get(`${i}s Active`).decrementCount();t&&(t.statsBookkeepingCalls=(t.statsBookkeepingCalls||0)+1,t.statsBookkeepingTimeMs=(t.statsBookkeepingTimeMs||0)+(X()-n))}trackAllocatedMemory(t,n=this.getStatsName()){const s=pt(this._device),r=s?X():0,i=this._device.statsManager.getStats(He);this.allocatedBytes>0&&this.allocatedBytesName&&(i.get("GPU Memory").subtractCount(this.allocatedBytes),i.get(`${this.allocatedBytesName} Memory`).subtractCount(this.allocatedBytes)),i.get("GPU Memory").addCount(t),i.get(`${n} Memory`).addCount(t),s&&(s.statsBookkeepingCalls=(s.statsBookkeepingCalls||0)+1,s.statsBookkeepingTimeMs=(s.statsBookkeepingTimeMs||0)+(X()-r)),this.allocatedBytes=t,this.allocatedBytesName=n}trackReferencedMemory(t,n=this.getStatsName()){this.trackAllocatedMemory(t,`Referenced ${n}`)}trackDeallocatedMemory(t=this.getStatsName()){if(this.allocatedBytes===0){this.allocatedBytesName=null;return}const n=pt(this._device),s=n?X():0,r=this._device.statsManager.getStats(He);r.get("GPU Memory").subtractCount(this.allocatedBytes),r.get(`${this.allocatedBytesName||t} Memory`).subtractCount(this.allocatedBytes),n&&(n.statsBookkeepingCalls=(n.statsBookkeepingCalls||0)+1,n.statsBookkeepingTimeMs=(n.statsBookkeepingTimeMs||0)+(X()-s)),this.allocatedBytes=0,this.allocatedBytesName=null}trackDeallocatedReferencedMemory(t=this.getStatsName()){this.trackDeallocatedMemory(`Referenced ${t}`)}addStats(){const t=this.getStatsName(),n=pt(this._device),s=n?X():0,r=[this._device.statsManager.getStats(We),this._device.statsManager.getStats(Ge)],i=qe(this._device);for(const o of r)Xe(o,i);for(const o of r)o.get("Resources Created").incrementCount(),o.get("Resources Active").incrementCount(),o.get(`${t}s Created`).incrementCount(),o.get(`${t}s Active`).incrementCount();n&&(n.statsBookkeepingCalls=(n.statsBookkeepingCalls||0)+1,n.statsBookkeepingTimeMs=(n.statsBookkeepingTimeMs||0)+(X()-s)),Ni(this._device,t)}getStatsName(){return Ii(this)}}T(Z,"defaultProps",{id:"undefined",handle:void 0,userData:void 0});function Pi(e,t){const n={...t};for(const s in e)e[s]!==void 0&&(n[s]=e[s]);return n}function Xe(e,t){const n=e.stats;let s=!1;for(const a of t)n[a]||(e.get(a),s=!0);const r=Object.keys(n).length,i=Ve.get(e);if(!s&&(i==null?void 0:i.orderedStatNames)===t&&i.statCount===r)return;const o={};let c=Ye.get(t);c||(c=new Set(t),Ye.set(t,c));for(const a of t)n[a]&&(o[a]=n[a]);for(const[a,l]of Object.entries(n))c.has(a)||(o[a]=l);for(const a of Object.keys(n))delete n[a];Object.assign(n,o),Ve.set(e,{orderedStatNames:t,statCount:r})}function qe(e){return e.type==="webgl"?Ri:Li}function pt(e){const t=e.userData[xi];return t!=null&&t.enabled?t:null}function X(){var e,t;return((t=(e=globalThis.performance)==null?void 0:e.now)==null?void 0:t.call(e))??Date.now()}function Ni(e,t){const n=pt(e);if(!(!n||!n.activeDefaultFramebufferAcquireDepth))switch(n.transientCanvasResourceCreates=(n.transientCanvasResourceCreates||0)+1,t){case"Texture":n.transientCanvasTextureCreates=(n.transientCanvasTextureCreates||0)+1;break;case"TextureView":n.transientCanvasTextureViewCreates=(n.transientCanvasTextureViewCreates||0)+1;break;case"Sampler":n.transientCanvasSamplerCreates=(n.transientCanvasSamplerCreates||0)+1;break;case"Framebuffer":n.transientCanvasFramebufferCreates=(n.transientCanvasFramebufferCreates||0)+1;break}}function Ii(e){let t=Object.getPrototypeOf(e);for(;t;){const n=Object.getPrototypeOf(t);if(!n||n===Z.prototype)return Ci(t)||e[Symbol.toStringTag]||e.constructor.name;t=n}return e[Symbol.toStringTag]||e.constructor.name}function Ci(e){const t=Object.getOwnPropertyDescriptor(e,Symbol.toStringTag);return typeof(t==null?void 0:t.get)=="function"?t.get.call(e):typeof(t==null?void 0:t.value)=="string"?t.value:null}const j=class j extends Z{constructor(n,s){const r={...s};(s.usage||0)&j.INDEX&&!s.indexType&&(s.data instanceof Uint32Array?r.indexType="uint32":s.data instanceof Uint16Array?r.indexType="uint16":s.data instanceof Uint8Array&&(r.indexType="uint8")),delete r.data;super(n,r,j.defaultProps);T(this,"usage");T(this,"indexType");T(this,"updateTimestamp");T(this,"debugData",new ArrayBuffer(0));this.usage=r.usage||0,this.indexType=r.indexType,this.updateTimestamp=n.incrementTimestamp()}get[Symbol.toStringTag](){return"Buffer"}clone(n){return this.device.createBuffer({...this.props,...n})}_setDebugData(n,s,r){let i=null,o;ArrayBuffer.isView(n)?(i=n,o=n.buffer):o=n;const c=Math.min(n?n.byteLength:r,j.DEBUG_DATA_MAX_LENGTH);if(o===null)this.debugData=new ArrayBuffer(c);else{const a=Math.min((i==null?void 0:i.byteOffset)||0,o.byteLength),l=Math.max(0,o.byteLength-a),f=Math.min(c,l);this.debugData=new Uint8Array(o,a,f).slice().buffer}}};T(j,"INDEX",16),T(j,"VERTEX",32),T(j,"UNIFORM",64),T(j,"STORAGE",128),T(j,"INDIRECT",256),T(j,"QUERY_RESOLVE",512),T(j,"MAP_READ",1),T(j,"MAP_WRITE",2),T(j,"COPY_SRC",4),T(j,"COPY_DST",8),T(j,"DEBUG_DATA_MAX_LENGTH",32),T(j,"defaultProps",{...Z.defaultProps,usage:0,byteLength:0,byteOffset:0,data:null,indexType:"uint16",onMapped:void 0});let Ze=j;class ji{getDataTypeInfo(t){const[n,s,r]=te[t],i=t.includes("norm"),o=!i&&!t.startsWith("float"),c=t.startsWith("s");return{signedType:n,primitiveType:s,byteLength:r,normalized:i,integer:o,signed:c}}getNormalizedDataType(t){const n=t;switch(n){case"uint8":return"unorm8";case"sint8":return"snorm8";case"uint16":return"unorm16";case"sint16":return"snorm16";default:return n}}alignTo(t,n){switch(n){case 1:return t;case 2:return t+t%2;default:return t+(4-t%4)%4}}getDataType(t){const n=ArrayBuffer.isView(t)?t.constructor:t;if(n===Uint8ClampedArray)return"uint8";const s=Object.values(te).find(r=>n===r[4]);if(!s)throw new Error(n.name);return s[0]}getTypedArrayConstructor(t){const[,,,,n]=te[t];return n}}const Pt=new ji,te={uint8:["uint8","u32",1,!1,Uint8Array],sint8:["sint8","i32",1,!1,Int8Array],unorm8:["uint8","f32",1,!0,Uint8Array],snorm8:["sint8","f32",1,!0,Int8Array],uint16:["uint16","u32",2,!1,Uint16Array],sint16:["sint16","i32",2,!1,Int16Array],unorm16:["uint16","u32",2,!0,Uint16Array],snorm16:["sint16","i32",2,!0,Int16Array],float16:["float16","f16",2,!1,Uint16Array],float32:["float32","f32",4,!1,Float32Array],uint32:["uint32","u32",4,!1,Uint32Array],sint32:["sint32","i32",4,!1,Int32Array]};class Di{getVertexFormatInfo(t){let n;t.endsWith("-webgl")&&(t.replace("-webgl",""),n=!0);const[s,r]=t.split("x"),i=s,o=r?parseInt(r):1,c=Pt.getDataTypeInfo(i),a={type:i,components:o,byteLength:c.byteLength*o,integer:c.integer,signed:c.signed,normalized:c.normalized};return n&&(a.webglOnly=!0),a}makeVertexFormat(t,n,s){const r=s?Pt.getNormalizedDataType(t):t;switch(r){case"unorm8":return n===1?"unorm8":n===3?"unorm8x3-webgl":`${r}x${n}`;case"snorm8":return n===1?"snorm8":n===3?"snorm8x3-webgl":`${r}x${n}`;case"uint8":case"sint8":if(n===1||n===3)throw new Error(`size: ${n}`);return`${r}x${n}`;case"uint16":return n===1?"uint16":n===3?"uint16x3-webgl":`${r}x${n}`;case"sint16":return n===1?"sint16":n===3?"sint16x3-webgl":`${r}x${n}`;case"unorm16":return n===1?"unorm16":n===3?"unorm16x3-webgl":`${r}x${n}`;case"snorm16":return n===1?"snorm16":n===3?"snorm16x3-webgl":`${r}x${n}`;case"float16":if(n===1||n===3)throw new Error(`size: ${n}`);return`${r}x${n}`;default:return n===1?r:`${r}x${n}`}}getVertexFormatFromAttribute(t,n,s){if(!n||n>4)throw new Error(`size ${n}`);const r=n,i=Pt.getDataType(t);return this.makeVertexFormat(i,r,s)}getCompatibleVertexFormat(t){let n;switch(t.primitiveType){case"f32":n="float32";break;case"i32":n="sint32";break;case"u32":n="uint32";break;case"f16":return t.components<=2?"float16x2":"float16x4"}return t.components===1?n:`${n}x${t.components}`}}const Gc=new Di,D="texture-compression-bc",L="texture-compression-astc",V="texture-compression-etc2",ki="texture-compression-etc1-webgl",vt="texture-compression-pvrtc-webgl",ee="texture-compression-atc-webgl",xt="float32-renderable-webgl",ne="float16-renderable-webgl",Ui="rgb9e5ufloat-renderable-webgl",se="snorm8-renderable-webgl",q="norm16-webgl",re="norm16-renderable-webgl",ie="snorm16-renderable-webgl",wt="float32-filterable",Ke="float16-filterable-webgl";function Un(e){const t=$n[e];if(!t)throw new Error(`Unsupported texture format ${e}`);return t}function Hc(){return $n}const $i={r8unorm:{},rg8unorm:{},"rgb8unorm-webgl":{},rgba8unorm:{},"rgba8unorm-srgb":{},r8snorm:{render:se},rg8snorm:{render:se},"rgb8snorm-webgl":{},rgba8snorm:{render:se},r8uint:{},rg8uint:{},rgba8uint:{},r8sint:{},rg8sint:{},rgba8sint:{},bgra8unorm:{},"bgra8unorm-srgb":{},r16unorm:{f:q,render:re},rg16unorm:{f:q,render:re},"rgb16unorm-webgl":{f:q,render:!1},rgba16unorm:{f:q,render:re},r16snorm:{f:q,render:ie},rg16snorm:{f:q,render:ie},"rgb16snorm-webgl":{f:q,render:!1},rgba16snorm:{f:q,render:ie},r16uint:{},rg16uint:{},rgba16uint:{},r16sint:{},rg16sint:{},rgba16sint:{},r16float:{render:ne,filter:"float16-filterable-webgl"},rg16float:{render:ne,filter:Ke},rgba16float:{render:ne,filter:Ke},r32uint:{},rg32uint:{},rgba32uint:{},r32sint:{},rg32sint:{},rgba32sint:{},r32float:{render:xt,filter:wt},rg32float:{render:!1,filter:wt},"rgb32float-webgl":{render:xt,filter:wt},rgba32float:{render:xt,filter:wt},"rgba4unorm-webgl":{channels:"rgba",bitsPerChannel:[4,4,4,4],packed:!0},"rgb565unorm-webgl":{channels:"rgb",bitsPerChannel:[5,6,5,0],packed:!0},"rgb5a1unorm-webgl":{channels:"rgba",bitsPerChannel:[5,5,5,1],packed:!0},rgb9e5ufloat:{channels:"rgb",packed:!0,render:Ui},rg11b10ufloat:{channels:"rgb",bitsPerChannel:[11,11,10,0],packed:!0,p:1,render:xt},rgb10a2unorm:{channels:"rgba",bitsPerChannel:[10,10,10,2],packed:!0,p:1},rgb10a2uint:{channels:"rgba",bitsPerChannel:[10,10,10,2],packed:!0,p:1},stencil8:{attachment:"stencil",bitsPerChannel:[8,0,0,0],dataType:"uint8"},depth16unorm:{attachment:"depth",bitsPerChannel:[16,0,0,0],dataType:"uint16"},depth24plus:{attachment:"depth",bitsPerChannel:[24,0,0,0],dataType:"uint32"},depth32float:{attachment:"depth",bitsPerChannel:[32,0,0,0],dataType:"float32"},"depth24plus-stencil8":{attachment:"depth-stencil",bitsPerChannel:[24,8,0,0],packed:!0},"depth32float-stencil8":{attachment:"depth-stencil",bitsPerChannel:[32,8,0,0],packed:!0}},Bi={"bc1-rgb-unorm-webgl":{f:D},"bc1-rgb-unorm-srgb-webgl":{f:D},"bc1-rgba-unorm":{f:D},"bc1-rgba-unorm-srgb":{f:D},"bc2-rgba-unorm":{f:D},"bc2-rgba-unorm-srgb":{f:D},"bc3-rgba-unorm":{f:D},"bc3-rgba-unorm-srgb":{f:D},"bc4-r-unorm":{f:D},"bc4-r-snorm":{f:D},"bc5-rg-unorm":{f:D},"bc5-rg-snorm":{f:D},"bc6h-rgb-ufloat":{f:D},"bc6h-rgb-float":{f:D},"bc7-rgba-unorm":{f:D},"bc7-rgba-unorm-srgb":{f:D},"etc2-rgb8unorm":{f:V},"etc2-rgb8unorm-srgb":{f:V},"etc2-rgb8a1unorm":{f:V},"etc2-rgb8a1unorm-srgb":{f:V},"etc2-rgba8unorm":{f:V},"etc2-rgba8unorm-srgb":{f:V},"eac-r11unorm":{f:V},"eac-r11snorm":{f:V},"eac-rg11unorm":{f:V},"eac-rg11snorm":{f:V},"astc-4x4-unorm":{f:L},"astc-4x4-unorm-srgb":{f:L},"astc-5x4-unorm":{f:L},"astc-5x4-unorm-srgb":{f:L},"astc-5x5-unorm":{f:L},"astc-5x5-unorm-srgb":{f:L},"astc-6x5-unorm":{f:L},"astc-6x5-unorm-srgb":{f:L},"astc-6x6-unorm":{f:L},"astc-6x6-unorm-srgb":{f:L},"astc-8x5-unorm":{f:L},"astc-8x5-unorm-srgb":{f:L},"astc-8x6-unorm":{f:L},"astc-8x6-unorm-srgb":{f:L},"astc-8x8-unorm":{f:L},"astc-8x8-unorm-srgb":{f:L},"astc-10x5-unorm":{f:L},"astc-10x5-unorm-srgb":{f:L},"astc-10x6-unorm":{f:L},"astc-10x6-unorm-srgb":{f:L},"astc-10x8-unorm":{f:L},"astc-10x8-unorm-srgb":{f:L},"astc-10x10-unorm":{f:L},"astc-10x10-unorm-srgb":{f:L},"astc-12x10-unorm":{f:L},"astc-12x10-unorm-srgb":{f:L},"astc-12x12-unorm":{f:L},"astc-12x12-unorm-srgb":{f:L},"pvrtc-rgb4unorm-webgl":{f:vt},"pvrtc-rgba4unorm-webgl":{f:vt},"pvrtc-rgb2unorm-webgl":{f:vt},"pvrtc-rgba2unorm-webgl":{f:vt},"etc1-rbg-unorm-webgl":{f:ki},"atc-rgb-unorm-webgl":{f:ee},"atc-rgba-unorm-webgl":{f:ee},"atc-rgbai-unorm-webgl":{f:ee}},$n={...$i,...Bi},zi=/^(r|rg|rgb|rgba|bgra)([0-9]*)([a-z]*)(-srgb)?(-webgl)?$/,Fi=["rgb","rgba","bgra"],Wi=["depth","stencil"],Gi=["bc1","bc2","bc3","bc4","bc5","bc6","bc7","etc1","etc2","eac","atc","astc","pvrtc"];class Hi{isColor(t){return Fi.some(n=>t.startsWith(n))}isDepthStencil(t){return Wi.some(n=>t.startsWith(n))}isCompressed(t){return Gi.some(n=>t.startsWith(n))}getInfo(t){return Bn(t)}getCapabilities(t){return Yi(t)}computeMemoryLayout(t){return Vi(t)}}const it=new Hi;function Vi({format:e,width:t,height:n,depth:s,byteAlignment:r}){const i=it.getInfo(e),{bytesPerPixel:o,bytesPerBlock:c=o,blockWidth:a=1,blockHeight:l=1,compressed:f=!1}=i,h=f?Math.ceil(t/a):t,u=f?Math.ceil(n/l):n,d=h*c,g=Math.ceil(d/r)*r,p=u,m=g*p*s;return{bytesPerPixel:o,bytesPerRow:g,rowsPerImage:p,depthOrArrayLayers:s,bytesPerImage:g*p,byteLength:m}}function Yi(e){const t=Un(e),n={format:e,create:t.f??!0,render:t.render??!0,filter:t.filter??!0,blend:t.blend??!0,store:t.store??!0},s=Bn(e),r=e.startsWith("depth")||e.startsWith("stencil"),i=s==null?void 0:s.signed,o=s==null?void 0:s.integer,c=s==null?void 0:s.webgl,a=!!(s!=null&&s.compressed);return n.render&&(n.render=!r&&!a),n.filter&&(n.filter=!r&&!i&&!o&&!c),n}function Bn(e){let t=Xi(e);if(it.isCompressed(e)){t.channels="rgb",t.components=3,t.bytesPerPixel=1,t.srgb=!1,t.compressed=!0,t.bytesPerBlock=Zi(e);const s=qi(e);s&&(t.blockWidth=s.blockWidth,t.blockHeight=s.blockHeight)}const n=t.packed?null:zi.exec(e);if(n){const[,s,r,i,o,c]=n,a=`${i}${r}`,l=Pt.getDataTypeInfo(a),f=l.byteLength*8,h=(s==null?void 0:s.length)??1,u=[f,h>=2?f:0,h>=3?f:0,h>=4?f:0];t={format:e,attachment:t.attachment,dataType:l.signedType,components:h,channels:s,integer:l.integer,signed:l.signed,normalized:l.normalized,bitsPerChannel:u,bytesPerPixel:l.byteLength*h,packed:t.packed,srgb:t.srgb},c==="-webgl"&&(t.webgl=!0),o==="-srgb"&&(t.srgb=!0)}return e.endsWith("-webgl")&&(t.webgl=!0),e.endsWith("-srgb")&&(t.srgb=!0),t}function Xi(e){var i;const t=Un(e),n=t.bytesPerPixel||1,s=t.bitsPerChannel||[8,8,8,8];return delete t.bitsPerChannel,delete t.bytesPerPixel,delete t.f,delete t.render,delete t.filter,delete t.blend,delete t.store,{...t,format:e,attachment:t.attachment||"color",channels:t.channels||"r",components:t.components||((i=t.channels)==null?void 0:i.length)||1,bytesPerPixel:n,bitsPerChannel:s,dataType:t.dataType||"uint8",srgb:t.srgb??!1,packed:t.packed??!1,webgl:t.webgl??!1,integer:t.integer??!1,signed:t.signed??!1,normalized:t.normalized??!1,compressed:t.compressed??!1}}function qi(e){const n=/.*-(\d+)x(\d+)-.*/.exec(e);if(n){const[,s,r]=n;return{blockWidth:Number(s),blockHeight:Number(r)}}return e.startsWith("bc")||e.startsWith("etc1")||e.startsWith("etc2")||e.startsWith("eac")||e.startsWith("atc")?{blockWidth:4,blockHeight:4}:e.startsWith("pvrtc-rgb4")||e.startsWith("pvrtc-rgba4")?{blockWidth:4,blockHeight:4}:e.startsWith("pvrtc-rgb2")||e.startsWith("pvrtc-rgba2")?{blockWidth:8,blockHeight:4}:null}function Zi(e){return e.startsWith("bc1")||e.startsWith("bc4")||e.startsWith("etc1")||e.startsWith("etc2-rgb8")||e.startsWith("etc2-rgb8a1")||e.startsWith("eac-r11")||e==="atc-rgb-unorm-webgl"?8:e.startsWith("bc2")||e.startsWith("bc3")||e.startsWith("bc5")||e.startsWith("bc6h")||e.startsWith("bc7")||e.startsWith("etc2-rgba8")||e.startsWith("eac-rg11")||e.startsWith("astc")||e==="atc-rgba-unorm-webgl"||e==="atc-rgbai-unorm-webgl"?16:e.startsWith("pvrtc")?8:16}function Vc(e){return typeof ImageData<"u"&&e instanceof ImageData||typeof ImageBitmap<"u"&&e instanceof ImageBitmap||typeof HTMLImageElement<"u"&&e instanceof HTMLImageElement||typeof HTMLVideoElement<"u"&&e instanceof HTMLVideoElement||typeof VideoFrame<"u"&&e instanceof VideoFrame||typeof HTMLCanvasElement<"u"&&e instanceof HTMLCanvasElement||typeof OffscreenCanvas<"u"&&e instanceof OffscreenCanvas}function Yc(e){if(typeof ImageData<"u"&&e instanceof ImageData||typeof ImageBitmap<"u"&&e instanceof ImageBitmap||typeof HTMLCanvasElement<"u"&&e instanceof HTMLCanvasElement||typeof OffscreenCanvas<"u"&&e instanceof OffscreenCanvas)return{width:e.width,height:e.height};if(typeof HTMLImageElement<"u"&&e instanceof HTMLImageElement)return{width:e.naturalWidth,height:e.naturalHeight};if(typeof HTMLVideoElement<"u"&&e instanceof HTMLVideoElement)return{width:e.videoWidth,height:e.videoHeight};if(typeof VideoFrame<"u"&&e instanceof VideoFrame)return{width:e.displayWidth,height:e.displayHeight};throw new Error("Unknown image type")}const _t=class _t extends Z{get[Symbol.toStringTag](){return"Sampler"}constructor(t,n){n=_t.normalizeProps(t,n),super(t,n,_t.defaultProps)}static normalizeProps(t,n){return n}};T(_t,"defaultProps",{...Z.defaultProps,type:"color-sampler",addressModeU:"clamp-to-edge",addressModeV:"clamp-to-edge",addressModeW:"clamp-to-edge",magFilter:"nearest",minFilter:"nearest",mipmapFilter:"none",lodMinClamp:0,lodMaxClamp:32,compare:"less-equal",maxAnisotropy:1});let de=_t;const Ki={"1d":"1d","2d":"2d","2d-array":"2d",cube:"2d","cube-array":"2d","3d":"3d"},P=class P extends Z{constructor(n,s,r){s=P.normalizeProps(n,s);super(n,s,P.defaultProps);T(this,"dimension");T(this,"baseDimension");T(this,"format");T(this,"width");T(this,"height");T(this,"depth");T(this,"mipLevels");T(this,"samples");T(this,"byteAlignment");T(this,"ready",Promise.resolve(this));T(this,"isReady",!0);T(this,"updateTimestamp");if(this.dimension=this.props.dimension,this.baseDimension=Ki[this.dimension],this.format=this.props.format,this.width=this.props.width,this.height=this.props.height,this.depth=this.props.depth,this.mipLevels=this.props.mipLevels,this.samples=this.props.samples||1,this.dimension==="cube"&&(this.depth=6),this.props.width===void 0||this.props.height===void 0)if(n.isExternalImage(s.data)){const i=n.getExternalImageSize(s.data);this.width=(i==null?void 0:i.width)||1,this.height=(i==null?void 0:i.height)||1}else this.width=1,this.height=1,(this.props.width===void 0||this.props.height===void 0)&&Si.warn(`${this} created with undefined width or height. This is deprecated. Use DynamicTexture instead.`)();this.byteAlignment=(r==null?void 0:r.byteAlignment)||1,this.updateTimestamp=n.incrementTimestamp()}get[Symbol.toStringTag](){return"Texture"}toString(){return`Texture(${this.id},${this.format},${this.width}x${this.height})`}clone(n){return this.device.createTexture({...this.props,...n})}setSampler(n){this.sampler=n instanceof de?n:this.device.createSampler(n)}copyImageData(n){const{data:s,depth:r,...i}=n;this.writeData(s,{...i,depthOrArrayLayers:i.depthOrArrayLayers??r})}computeMemoryLayout(n={}){const s=this._normalizeTextureReadOptions(n),{width:r=this.width,height:i=this.height,depthOrArrayLayers:o=this.depth}=s,{format:c,byteAlignment:a}=this;return it.computeMemoryLayout({format:c,width:r,height:i,depth:o,byteAlignment:a})}readBuffer(n,s){throw new Error("readBuffer not implemented")}readDataAsync(n){throw new Error("readBuffer not implemented")}writeBuffer(n,s){throw new Error("readBuffer not implemented")}writeData(n,s){throw new Error("readBuffer not implemented")}readDataSyncWebGL(n){throw new Error("readDataSyncWebGL not available")}generateMipmapsWebGL(){throw new Error("generateMipmapsWebGL not available")}static normalizeProps(n,s){const r={...s},{width:i,height:o}=r;return typeof i=="number"&&(r.width=Math.max(1,Math.ceil(i))),typeof o=="number"&&(r.height=Math.max(1,Math.ceil(o))),r}_initializeData(n){this.device.isExternalImage(n)?this.copyExternalImage({image:n,width:this.width,height:this.height,depth:this.depth,mipLevel:0,x:0,y:0,z:0,aspect:"all",colorSpace:"srgb",premultipliedAlpha:!1,flipY:!1}):n&&this.copyImageData({data:n,mipLevel:0,x:0,y:0,z:0,aspect:"all"})}_normalizeCopyImageDataOptions(n){const{data:s,depth:r,...i}=n,o=this._normalizeTextureWriteOptions({...i,depthOrArrayLayers:i.depthOrArrayLayers??r});return{data:s,depth:o.depthOrArrayLayers,...o}}_normalizeCopyExternalImageOptions(n){const s=P._omitUndefined(n),r=s.mipLevel??0,i=this._getMipLevelSize(r),o=this.device.getExternalImageSize(n.image),c={...P.defaultCopyExternalImageOptions,...i,...o,...s};return c.width=Math.min(c.width,i.width-c.x),c.height=Math.min(c.height,i.height-c.y),c.depth=Math.min(c.depth,i.depthOrArrayLayers-c.z),c}_normalizeTextureReadOptions(n){const s=P._omitUndefined(n),r=s.mipLevel??0,i=this._getMipLevelSize(r),o={...P.defaultTextureReadOptions,...i,...s};return o.width=Math.min(o.width,i.width-o.x),o.height=Math.min(o.height,i.height-o.y),o.depthOrArrayLayers=Math.min(o.depthOrArrayLayers,i.depthOrArrayLayers-o.z),o}_getSupportedColorReadOptions(n){const s=this._normalizeTextureReadOptions(n),r=it.getInfo(this.format);switch(this._validateColorReadAspect(s),this._validateColorReadFormat(r),this.dimension){case"2d":case"cube":case"cube-array":case"2d-array":case"3d":return s;default:throw new Error(`${this} color readback does not support ${this.dimension} textures`)}}_validateColorReadAspect(n){if(n.aspect!=="all")throw new Error(`${this} color readback only supports aspect 'all'`)}_validateColorReadFormat(n){if(n.compressed)throw new Error(`${this} color readback does not support compressed formats (${this.format})`);switch(n.attachment){case"color":return;case"depth":throw new Error(`${this} color readback does not support depth formats (${this.format})`);case"stencil":throw new Error(`${this} color readback does not support stencil formats (${this.format})`);case"depth-stencil":throw new Error(`${this} color readback does not support depth-stencil formats (${this.format})`);default:throw new Error(`${this} color readback does not support format ${this.format}`)}}_normalizeTextureWriteOptions(n){const s=P._omitUndefined(n),r=s.mipLevel??0,i=this._getMipLevelSize(r),o={...P.defaultTextureWriteOptions,...i,...s};o.width=Math.min(o.width,i.width-o.x),o.height=Math.min(o.height,i.height-o.y),o.depthOrArrayLayers=Math.min(o.depthOrArrayLayers,i.depthOrArrayLayers-o.z);const c=it.computeMemoryLayout({format:this.format,width:o.width,height:o.height,depth:o.depthOrArrayLayers,byteAlignment:this.byteAlignment}),a=c.bytesPerPixel*o.width;if(o.bytesPerRow=s.bytesPerRow??c.bytesPerRow,o.rowsPerImage=s.rowsPerImage??o.height,o.bytesPerRow<a)throw new Error(`bytesPerRow (${o.bytesPerRow}) must be at least ${a} for ${this.format}`);if(o.rowsPerImage<o.height)throw new Error(`rowsPerImage (${o.rowsPerImage}) must be at least ${o.height} for ${this.format}`);const l=this.device.getTextureFormatInfo(this.format).bytesPerPixel;if(l&&o.bytesPerRow%l!==0)throw new Error(`bytesPerRow (${o.bytesPerRow}) must be a multiple of bytesPerPixel (${l}) for ${this.format}`);return o}_getMipLevelSize(n){const s=Math.max(1,this.width>>n),r=this.baseDimension==="1d"?1:Math.max(1,this.height>>n),i=this.dimension==="3d"?Math.max(1,this.depth>>n):this.depth;return{width:s,height:r,depthOrArrayLayers:i}}getAllocatedByteLength(){let n=0;for(let s=0;s<this.mipLevels;s++){const{width:r,height:i,depthOrArrayLayers:o}=this._getMipLevelSize(s);n+=it.computeMemoryLayout({format:this.format,width:r,height:i,depth:o,byteAlignment:1}).byteLength}return n*this.samples}static _omitUndefined(n){return Object.fromEntries(Object.entries(n).filter(([,s])=>s!==void 0))}};T(P,"SAMPLE",4),T(P,"STORAGE",8),T(P,"RENDER",16),T(P,"COPY_SRC",1),T(P,"COPY_DST",2),T(P,"TEXTURE",4),T(P,"RENDER_ATTACHMENT",16),T(P,"defaultProps",{...Z.defaultProps,data:null,dimension:"2d",format:"rgba8unorm",usage:P.SAMPLE|P.RENDER|P.COPY_DST,width:void 0,height:void 0,depth:1,mipLevels:1,samples:void 0,sampler:{},view:void 0}),T(P,"defaultCopyDataOptions",{data:void 0,byteOffset:0,bytesPerRow:void 0,rowsPerImage:void 0,width:void 0,height:void 0,depthOrArrayLayers:void 0,depth:1,mipLevel:0,x:0,y:0,z:0,aspect:"all"}),T(P,"defaultCopyExternalImageOptions",{image:void 0,sourceX:0,sourceY:0,width:void 0,height:void 0,depth:1,mipLevel:0,x:0,y:0,z:0,aspect:"all",colorSpace:"srgb",premultipliedAlpha:!1,flipY:!1}),T(P,"defaultTextureReadOptions",{x:0,y:0,z:0,width:void 0,height:void 0,depthOrArrayLayers:1,mipLevel:0,aspect:"all"}),T(P,"defaultTextureWriteOptions",{byteOffset:0,bytesPerRow:void 0,rowsPerImage:void 0,x:0,y:0,z:0,width:void 0,height:void 0,depthOrArrayLayers:1,mipLevel:0,aspect:"all"});let Je=P;const Ji=`const SMOOTH_EDGE_RADIUS: f32 = 0.5;

struct VertexGeometry {
  position: vec4<f32>,
  worldPosition: vec3<f32>,
  worldPositionAlt: vec3<f32>,
  normal: vec3<f32>,
  uv: vec2<f32>,
  pickingColor: vec3<f32>,
};

var<private> geometry_: VertexGeometry = VertexGeometry(
  vec4<f32>(0.0, 0.0, 1.0, 0.0),
  vec3<f32>(0.0, 0.0, 0.0),
  vec3<f32>(0.0, 0.0, 0.0),
  vec3<f32>(0.0, 0.0, 0.0),
  vec2<f32>(0.0, 0.0),
  vec3<f32>(0.0, 0.0, 0.0)
);

struct FragmentGeometry {
  uv: vec2<f32>,
};

var<private> fragmentGeometry: FragmentGeometry;

fn smoothedge(edge: f32, x: f32) -> f32 {
  return smoothstep(edge - SMOOTH_EDGE_RADIUS, edge + SMOOTH_EDGE_RADIUS, x);
}
`,zn="#define SMOOTH_EDGE_RADIUS 0.5",Qi=`${zn}

struct VertexGeometry {
  vec4 position;
  vec3 worldPosition;
  vec3 worldPositionAlt;
  vec3 normal;
  vec2 uv;
  vec3 pickingColor;
} geometry = VertexGeometry(
  vec4(0.0, 0.0, 1.0, 0.0),
  vec3(0.0),
  vec3(0.0),
  vec3(0.0),
  vec2(0.0),
  vec3(0.0)
);
`,to=`${zn}

struct FragmentGeometry {
  vec2 uv;
} geometry;

float smoothedge(float edge, float x) {
  return smoothstep(edge - SMOOTH_EDGE_RADIUS, edge + SMOOTH_EDGE_RADIUS, x);
}
`,eo={name:"geometry",source:Ji,vs:Qi,fs:to},no=25;var I;(function(e){e[e.Start=1]="Start",e[e.Move=2]="Move",e[e.End=4]="End",e[e.Cancel=8]="Cancel"})(I||(I={}));var C;(function(e){e[e.None=0]="None",e[e.Left=1]="Left",e[e.Right=2]="Right",e[e.Up=4]="Up",e[e.Down=8]="Down",e[e.Horizontal=3]="Horizontal",e[e.Vertical=12]="Vertical",e[e.All=15]="All"})(C||(C={}));var S;(function(e){e[e.Possible=1]="Possible",e[e.Began=2]="Began",e[e.Changed=4]="Changed",e[e.Ended=8]="Ended",e[e.Recognized=8]="Recognized",e[e.Cancelled=16]="Cancelled",e[e.Failed=32]="Failed"})(S||(S={}));const Xc="compute",qc="auto",so="manipulation",ro="none",io="pan-x",oo="pan-y";function Fn(e){return e.trim().split(/\s+/g)}function oe(e,t,n){if(e)for(const s of Fn(t))e.addEventListener(s,n,!1)}function ce(e,t,n){if(e)for(const s of Fn(t))e.removeEventListener(s,n,!1)}function Qe(e){return(e.ownerDocument||e).defaultView}function co(e,t){let n=e;for(;n;){if(n===t)return!0;n=n.parentNode}return!1}function Wn(e){const t=e.length;if(t===1)return{x:Math.round(e[0].clientX),y:Math.round(e[0].clientY)};let n=0,s=0,r=0;for(;r<t;)n+=e[r].clientX,s+=e[r].clientY,r++;return{x:Math.round(n/t),y:Math.round(s/t)}}function tn(e){const t=[];let n=0;for(;n<e.pointers.length;)t[n]={clientX:Math.round(e.pointers[n].clientX),clientY:Math.round(e.pointers[n].clientY)},n++;return{timeStamp:Date.now(),pointers:t,center:Wn(t),deltaX:e.deltaX,deltaY:e.deltaY}}function Gn(e,t){const n=t.x-e.x,s=t.y-e.y;return Math.sqrt(n*n+s*s)}function en(e,t){const n=t.clientX-e.clientX,s=t.clientY-e.clientY;return Math.sqrt(n*n+s*s)}function ao(e,t){const n=t.x-e.x,s=t.y-e.y;return Math.atan2(s,n)*180/Math.PI}function nn(e,t){const n=t.clientX-e.clientX,s=t.clientY-e.clientY;return Math.atan2(s,n)*180/Math.PI}function Hn(e,t){return e===t?C.None:Math.abs(e)>=Math.abs(t)?e<0?C.Left:C.Right:t<0?C.Up:C.Down}function lo(e,t){const n=t.center;let s=e.offsetDelta,r=e.prevDelta;const i=e.prevInput;return(t.eventType===I.Start||(i==null?void 0:i.eventType)===I.End)&&(r=e.prevDelta={x:(i==null?void 0:i.deltaX)||0,y:(i==null?void 0:i.deltaY)||0},s=e.offsetDelta={x:n.x,y:n.y}),{deltaX:r.x+(n.x-s.x),deltaY:r.y+(n.y-s.y)}}function Vn(e,t,n){return{x:t/e||0,y:n/e||0}}function fo(e,t){return en(t[0],t[1])/en(e[0],e[1])}function ho(e,t){return nn(t[1],t[0])-nn(e[1],e[0])}function uo(e,t){const n=e.lastInterval||t,s=t.timeStamp-n.timeStamp;let r,i,o,c;if(t.eventType!==I.Cancel&&(s>no||n.velocity===void 0)){const a=t.deltaX-n.deltaX,l=t.deltaY-n.deltaY,f=Vn(s,a,l);i=f.x,o=f.y,r=Math.abs(f.x)>Math.abs(f.y)?f.x:f.y,c=Hn(a,l),e.lastInterval=t}else r=n.velocity,i=n.velocityX,o=n.velocityY,c=n.direction;t.velocity=r,t.velocityX=i,t.velocityY=o,t.direction=c}function go(e,t){const{session:n}=e,{pointers:s}=t,{length:r}=s;n.firstInput||(n.firstInput=tn(t)),r>1&&!n.firstMultiple?n.firstMultiple=tn(t):r===1&&(n.firstMultiple=!1);const{firstInput:i,firstMultiple:o}=n,c=o?o.center:i.center,a=t.center=Wn(s);t.timeStamp=Date.now(),t.deltaTime=t.timeStamp-i.timeStamp,t.angle=ao(c,a),t.distance=Gn(c,a);const{deltaX:l,deltaY:f}=lo(n,t);t.deltaX=l,t.deltaY=f,t.offsetDirection=Hn(t.deltaX,t.deltaY);const h=Vn(t.deltaTime,t.deltaX,t.deltaY);t.overallVelocityX=h.x,t.overallVelocityY=h.y,t.overallVelocity=Math.abs(h.x)>Math.abs(h.y)?h.x:h.y,t.scale=o?fo(o.pointers,s):1,t.rotation=o?ho(o.pointers,s):0,t.maxPointers=n.prevInput?t.pointers.length>n.prevInput.maxPointers?t.pointers.length:n.prevInput.maxPointers:t.pointers.length;let u=e.element;return co(t.srcEvent.target,u)&&(u=t.srcEvent.target),t.target=u,uo(n,t),t}function po(e,t,n){const s=n.pointers.length,r=n.changedPointers.length,i=t&I.Start&&s-r===0,o=t&(I.End|I.Cancel)&&s-r===0;n.isFirst=!!i,n.isFinal=!!o,i&&(e.session={}),n.eventType=t;const c=go(e,n);e.emit("hammer.input",c),e.recognize(c),e.session.prevInput=c}let mo=class{constructor(t){this.evEl="",this.evWin="",this.evTarget="",this.domHandler=n=>{this.manager.options.enable&&this.handler(n)},this.manager=t,this.element=t.element,this.target=t.options.inputTarget||t.element}callback(t,n){po(this.manager,t,n)}init(){oe(this.element,this.evEl,this.domHandler),oe(this.target,this.evTarget,this.domHandler),oe(Qe(this.element),this.evWin,this.domHandler)}destroy(){ce(this.element,this.evEl,this.domHandler),ce(this.target,this.evTarget,this.domHandler),ce(Qe(this.element),this.evWin,this.domHandler)}};const _o={pointerdown:I.Start,pointermove:I.Move,pointerup:I.End,pointercancel:I.Cancel,pointerout:I.Cancel},Eo="pointerdown",bo="pointermove pointerup pointercancel";class Kc extends mo{constructor(t){super(t),this.evEl=Eo,this.evWin=bo,this.store=this.manager.session.pointerEvents=[],this.init()}handler(t){const{store:n}=this;let s=!1;const r=_o[t.type],i=t.pointerType,o=i==="touch";let c=n.findIndex(a=>a.pointerId===t.pointerId);r&I.Start&&(t.buttons||o)?c<0&&(n.push(t),c=n.length-1):r&(I.End|I.Cancel)&&(s=!0),!(c<0)&&(n[c]=t,this.callback(r,{pointers:n,changedPointers:[t],eventType:r,pointerType:i,srcEvent:t}),s&&n.splice(c,1))}}let yo=1;function To(){return yo++}function sn(e){return e&S.Cancelled?"cancel":e&S.Ended?"end":e&S.Changed?"move":e&S.Began?"start":""}class Yn{constructor(t){this.options=t,this.id=To(),this.state=S.Possible,this.simultaneous={},this.requireFail=[]}set(t){return Object.assign(this.options,t),this.manager.touchAction.update(),this}recognizeWith(t){if(Array.isArray(t)){for(const r of t)this.recognizeWith(r);return this}let n;if(typeof t=="string"){if(n=this.manager.get(t),!n)throw new Error(`Cannot find recognizer ${t}`)}else n=t;const{simultaneous:s}=this;return s[n.id]||(s[n.id]=n,n.recognizeWith(this)),this}dropRecognizeWith(t){if(Array.isArray(t)){for(const s of t)this.dropRecognizeWith(s);return this}let n;return typeof t=="string"?n=this.manager.get(t):n=t,n&&delete this.simultaneous[n.id],this}requireFailure(t){if(Array.isArray(t)){for(const r of t)this.requireFailure(r);return this}let n;if(typeof t=="string"){if(n=this.manager.get(t),!n)throw new Error(`Cannot find recognizer ${t}`)}else n=t;const{requireFail:s}=this;return s.indexOf(n)===-1&&(s.push(n),n.requireFailure(this)),this}dropRequireFailure(t){if(Array.isArray(t)){for(const s of t)this.dropRequireFailure(s);return this}let n;if(typeof t=="string"?n=this.manager.get(t):n=t,n){const s=this.requireFail.indexOf(n);s>-1&&this.requireFail.splice(s,1)}return this}hasRequireFailures(){return!!this.requireFail.find(t=>t.options.enable)}canRecognizeWith(t){return!!this.simultaneous[t.id]}emit(t){if(!t)return;const{state:n}=this;n<S.Ended&&this.manager.emit(this.options.event+sn(n),t),this.manager.emit(this.options.event,t),t.additionalEvent&&this.manager.emit(t.additionalEvent,t),n>=S.Ended&&this.manager.emit(this.options.event+sn(n),t)}tryEmit(t){this.canEmit()?this.emit(t):this.state=S.Failed}canEmit(){let t=0;for(;t<this.requireFail.length;){if(!(this.requireFail[t].state&(S.Failed|S.Possible)))return!1;t++}return!0}recognize(t){const n={...t};if(!this.options.enable){this.reset(),this.state=S.Failed;return}this.state&(S.Recognized|S.Cancelled|S.Failed)&&(this.state=S.Possible),this.state=this.process(n),this.state&(S.Began|S.Changed|S.Ended|S.Cancelled)&&this.tryEmit(n)}getEventNames(){return[this.options.event]}reset(){}}class Xn extends Yn{attrTest(t){const n=this.options.pointers;return n===0||t.pointers.length===n}process(t){const{state:n}=this,{eventType:s}=t,r=n&(S.Began|S.Changed),i=this.attrTest(t);return r&&(s&I.Cancel||!i)?n|S.Cancelled:r||i?s&I.End?n|S.Ended:n&S.Began?n|S.Changed:S.Began:S.Failed}}class rn extends Yn{constructor(t={}){super({enable:!0,event:"tap",pointers:1,taps:1,interval:300,time:250,threshold:9,posThreshold:10,...t}),this.pTime=null,this.pCenter=null,this._timer=null,this._input=null,this.count=0}getTouchAction(){return[so]}process(t){const{options:n}=this,s=t.pointers.length===n.pointers,r=t.distance<n.threshold,i=t.deltaTime<n.time;if(this.reset(),t.eventType&I.Start&&this.count===0)return this.failTimeout();if(r&&i&&s){if(t.eventType!==I.End)return this.failTimeout();const o=this.pTime?t.timeStamp-this.pTime<n.interval:!0,c=!this.pCenter||Gn(this.pCenter,t.center)<n.posThreshold;if(this.pTime=t.timeStamp,this.pCenter=t.center,!c||!o?this.count=1:this.count+=1,this._input=t,this.count%n.taps===0)return this.hasRequireFailures()?(this._timer=setTimeout(()=>{this.state=S.Recognized,this.tryEmit(this._input)},n.interval),S.Began):S.Recognized}return S.Failed}failTimeout(){return this._timer=setTimeout(()=>{this.state=S.Failed},this.options.interval),S.Failed}reset(){clearTimeout(this._timer)}emit(t){this.state===S.Recognized&&(t.tapCount=this.count,this.manager.emit(this.options.event,t))}}const Mo=["","start","move","end","cancel","up","down","left","right"];class on extends Xn{constructor(t={}){super({enable:!0,pointers:1,event:"pan",threshold:10,direction:C.All,...t}),this.pX=null,this.pY=null}getTouchAction(){const{options:{direction:t}}=this,n=[];return t&C.Horizontal&&n.push(oo),t&C.Vertical&&n.push(io),n}getEventNames(){return Mo.map(t=>this.options.event+t)}directionTest(t){const{options:n}=this;let s=!0,{distance:r}=t,{direction:i}=t;const o=t.deltaX,c=t.deltaY;return i&n.direction||(n.direction&C.Horizontal?(i=o===0?C.None:o<0?C.Left:C.Right,s=o!==this.pX,r=Math.abs(t.deltaX)):(i=c===0?C.None:c<0?C.Up:C.Down,s=c!==this.pY,r=Math.abs(t.deltaY))),t.direction=i,s&&r>n.threshold&&!!(i&n.direction)}attrTest(t){return super.attrTest(t)&&(!!(this.state&S.Began)||!(this.state&S.Began)&&this.directionTest(t))}emit(t){this.pX=t.deltaX,this.pY=t.deltaY;const n=C[t.direction].toLowerCase();n&&(t.additionalEvent=this.options.event+n),super.emit(t)}}const Ao=["","start","move","end","cancel","in","out"];class So extends Xn{constructor(t={}){super({enable:!0,event:"pinch",threshold:0,pointers:2,...t})}getTouchAction(){return[ro]}getEventNames(){return Ao.map(t=>this.options.event+t)}attrTest(t){return super.attrTest(t)&&(Math.abs(t.scale-1)>this.options.threshold||!!(this.state&S.Began))}emit(t){if(t.scale!==1){const n=t.scale<1?"in":"out";t.additionalEvent=this.options.event+n}super.emit(t)}}class vo{constructor(t,n,s){this.element=t,this.callback=n,this.options=s}}const xo=typeof navigator<"u"&&navigator.userAgent?navigator.userAgent.toLowerCase():"",wo=xo.indexOf("firefox")!==-1,cn=4.000244140625,Oo=40,Lo=.25;class Jc extends vo{constructor(t,n,s){super(t,n,{enable:!0,...s}),this.handleEvent=r=>{if(!this.options.enable)return;let i=r.deltaY;globalThis.WheelEvent&&(wo&&r.deltaMode===globalThis.WheelEvent.DOM_DELTA_PIXEL&&(i/=globalThis.devicePixelRatio),r.deltaMode===globalThis.WheelEvent.DOM_DELTA_LINE&&(i*=Oo)),i!==0&&i%cn===0&&(i=Math.floor(i/cn)),r.shiftKey&&i&&(i=i*Lo),this.callback({type:"wheel",center:{x:r.clientX,y:r.clientY},delta:-i,srcEvent:r,pointerType:"mouse",target:r.target})},t.addEventListener("wheel",this.handleEvent,{passive:!1})}destroy(){this.element.removeEventListener("wheel",this.handleEvent)}enableEventType(t,n){t==="wheel"&&(this.options.enable=n)}}const an={DEFAULT:"default",LNGLAT:"lnglat",METER_OFFSETS:"meter-offsets",LNGLAT_OFFSETS:"lnglat-offsets",CARTESIAN:"cartesian"};Object.defineProperty(an,"IDENTITY",{get:()=>(_n.deprecated("COORDINATE_SYSTEM.IDENTITY","COORDINATE_SYSTEM.CARTESIAN")(),an.CARTESIAN)});const G={WEB_MERCATOR:1,GLOBE:2,WEB_MERCATOR_AUTO_OFFSET:4,IDENTITY:0},Ut={common:0,meters:1,pixels:2},Qc={click:"onClick",dblclick:"onClick",panstart:"onDragStart",panmove:"onDrag",panend:"onDragEnd"},ta={multipan:[on,{threshold:10,direction:C.Vertical,pointers:2}],pinch:[So,{},null,["multipan"]],pan:[on,{threshold:1},["pinch"],["multipan"]],dblclick:[rn,{event:"dblclick",taps:2}],click:[rn,{event:"click"},null,["dblclick"]]};function Ro(e,t){if(e===t)return!0;if(Array.isArray(e)){const n=e.length;if(!t||t.length!==n)return!1;for(let s=0;s<n;s++)if(e[s]!==t[s])return!1;return!0}return!1}function Po(e){let t={},n;return s=>{for(const r in s)if(!Ro(s[r],t[r])){n=e(s),t=s;break}return n}}const ln=[0,0,0,0],No=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,0],qn=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],Io=[0,0,0],Zn=[0,0,0],Co={default:-1,cartesian:0,lnglat:1,"meter-offsets":2,"lnglat-offsets":3};function xe(e){const t=Co[e];if(t===void 0)throw new Error(`Invalid coordinateSystem: ${e}`);return t}const jo=Po($o);function Do(e,t,n=Zn){n.length<3&&(n=[n[0],n[1],0]);let s=n,r,i=!0;switch(t==="lnglat-offsets"||t==="meter-offsets"?r=n:r=e.isGeospatial?[Math.fround(e.longitude),Math.fround(e.latitude),0]:null,e.projectionMode){case G.WEB_MERCATOR:(t==="lnglat"||t==="cartesian")&&(r=[0,0,0],i=!1);break;case G.WEB_MERCATOR_AUTO_OFFSET:t==="lnglat"?s=r:t==="cartesian"&&(s=[Math.fround(e.center[0]),Math.fround(e.center[1]),0],r=e.unprojectPosition(s),s[0]-=n[0],s[1]-=n[1],s[2]-=n[2]);break;case G.IDENTITY:s=e.position.map(Math.fround),s[2]=s[2]||0;break;case G.GLOBE:i=!1,r=null;break;default:i=!1}return{geospatialOrigin:r,shaderCoordinateOrigin:s,offsetMode:i}}function ko(e,t,n){const{viewMatrixUncentered:s,projectionMatrix:r}=e;let{viewMatrix:i,viewProjectionMatrix:o}=e,c=ln,a=ln,l=e.cameraPosition;const{geospatialOrigin:f,shaderCoordinateOrigin:h,offsetMode:u}=Do(e,t,n);return u&&(a=e.projectPosition(f||h),l=[l[0]-a[0],l[1]-a[1],l[2]-a[2]],a[3]=1,c=Wt([],a,o),i=s||i,o=J([],r,i),o=J([],o,No)),{viewMatrix:i,viewProjectionMatrix:o,projectionCenter:c,originCommon:a,cameraPosCommon:l,shaderCoordinateOrigin:h,geospatialOrigin:f}}function Uo({viewport:e,devicePixelRatio:t=1,modelMatrix:n=null,coordinateSystem:s="default",coordinateOrigin:r=Zn,autoWrapLongitude:i=!1}){s==="default"&&(s=e.isGeospatial?"lnglat":"cartesian");const o=jo({viewport:e,devicePixelRatio:t,coordinateSystem:s,coordinateOrigin:r});return o.wrapLongitude=i,o.modelMatrix=n||qn,o}function $o({viewport:e,devicePixelRatio:t,coordinateSystem:n,coordinateOrigin:s}){const{projectionCenter:r,viewProjectionMatrix:i,originCommon:o,cameraPosCommon:c,shaderCoordinateOrigin:a,geospatialOrigin:l}=ko(e,n,s),f=e.getDistanceScales(),h=[e.width*t,e.height*t],u=Wt([],[0,0,-e.focalDistance,1],e.projectionMatrix)[3]||1,d={coordinateSystem:xe(n),projectionMode:e.projectionMode,coordinateOrigin:a,commonOrigin:o.slice(0,3),center:r,pseudoMeters:!!e._pseudoMeters,viewportSize:h,devicePixelRatio:t,focalDistance:u,commonUnitsPerMeter:f.unitsPerMeter,commonUnitsPerWorldUnit:f.unitsPerMeter,commonUnitsPerWorldUnit2:Io,scale:e.scale,wrapLongitude:!1,viewProjectionMatrix:i,modelMatrix:qn,cameraPosition:c};if(l){const g=e.getDistanceScales(l);switch(n){case"meter-offsets":d.commonUnitsPerWorldUnit=g.unitsPerMeter,d.commonUnitsPerWorldUnit2=g.unitsPerMeter2;break;case"lnglat":case"lnglat-offsets":e._pseudoMeters||(d.commonUnitsPerMeter=g.unitsPerMeter),d.commonUnitsPerWorldUnit=g.unitsPerDegree,d.commonUnitsPerWorldUnit2=g.unitsPerDegree2;break;case"cartesian":d.commonUnitsPerWorldUnit=[1,1,g.unitsPerMeter[2]],d.commonUnitsPerWorldUnit2=[0,0,g.unitsPerMeter2[2]];break}}return d}const Bo=["default","lnglat","meter-offsets","lnglat-offsets","cartesian"],zo=Bo.map(e=>`const COORDINATE_SYSTEM_${e.toUpperCase().replaceAll("-","_")}: i32 = ${xe(e)};`).join(""),Fo=Object.keys(G).map(e=>`const PROJECTION_MODE_${e}: i32 = ${G[e]};`).join(""),Wo=Object.keys(Ut).map(e=>`const UNIT_${e.toUpperCase()}: i32 = ${Ut[e]};`).join(""),Go=`${zo}
${Fo}
${Wo}

const TILE_SIZE: f32 = 512.0;
const PI: f32 = 3.1415926536;
const WORLD_SCALE: f32 = TILE_SIZE / (PI * 2.0);
const ZERO_64_LOW: vec3<f32> = vec3<f32>(0.0, 0.0, 0.0);
const EARTH_RADIUS: f32 = 6370972.0; // meters
const GLOBE_RADIUS: f32 = 256.0;

// -----------------------------------------------------------------------------
// Uniform block (converted from GLSL uniform block)
// -----------------------------------------------------------------------------
struct ProjectUniforms {
  wrapLongitude: i32,
  coordinateSystem: i32,
  commonUnitsPerMeter: vec3<f32>,
  projectionMode: i32,
  scale: f32,
  commonUnitsPerWorldUnit: vec3<f32>,
  commonUnitsPerWorldUnit2: vec3<f32>,
  center: vec4<f32>,
  modelMatrix: mat4x4<f32>,
  viewProjectionMatrix: mat4x4<f32>,
  viewportSize: vec2<f32>,
  devicePixelRatio: f32,
  focalDistance: f32,
  cameraPosition: vec3<f32>,
  coordinateOrigin: vec3<f32>,
  commonOrigin: vec3<f32>,
  pseudoMeters: i32,
};

@group(0) @binding(auto)
var<uniform> project: ProjectUniforms;

// -----------------------------------------------------------------------------
// Geometry data shared across the project helpers.
// The active layer shader is responsible for populating this private module
// state before calling the project functions below.
// -----------------------------------------------------------------------------

// Structure to carry additional geometry data used by deck.gl filters.
struct Geometry {
  worldPosition: vec3<f32>,
  worldPositionAlt: vec3<f32>,
  position: vec4<f32>,
  normal: vec3<f32>,
  uv: vec2<f32>,
  pickingColor: vec3<f32>,
};

var<private> geometry: Geometry;
`,Ho=`${Go}

// -----------------------------------------------------------------------------
// Functions
// -----------------------------------------------------------------------------

// Returns an adjustment factor for commonUnitsPerMeter
fn _project_size_at_latitude(lat: f32) -> f32 {
  let y = clamp(lat, -89.9, 89.9);
  return 1.0 / cos(radians(y));
}

// Overloaded version: scales a value in meters at a given latitude.
fn _project_size_at_latitude_m(meters: f32, lat: f32) -> f32 {
  return meters * project.commonUnitsPerMeter.z * _project_size_at_latitude(lat);
}

// Computes a non-linear scale factor based on geometry.
// (Note: This function relies on "geometry" being provided.)
fn project_size() -> f32 {
  if (project.projectionMode == PROJECTION_MODE_WEB_MERCATOR &&
      project.coordinateSystem == COORDINATE_SYSTEM_LNGLAT &&
      project.pseudoMeters == 0) {
    if (geometry.position.w == 0.0) {
      return _project_size_at_latitude(geometry.worldPosition.y);
    }
    let y: f32 = geometry.position.y / TILE_SIZE * 2.0 - 1.0;
    let y2 = y * y;
    let y4 = y2 * y2;
    let y6 = y4 * y2;
    return 1.0 + 4.9348 * y2 + 4.0587 * y4 + 1.5642 * y6;
  }
  return 1.0;
}

// Overloads to scale offsets (meters to world units)
fn project_size_float(meters: f32) -> f32 {
  return meters * project.commonUnitsPerMeter.z * project_size();
}

fn project_size_vec2(meters: vec2<f32>) -> vec2<f32> {
  return meters * project.commonUnitsPerMeter.xy * project_size();
}

fn project_size_vec3(meters: vec3<f32>) -> vec3<f32> {
  return meters * project.commonUnitsPerMeter * project_size();
}

fn project_size_vec4(meters: vec4<f32>) -> vec4<f32> {
  return vec4<f32>(meters.xyz * project.commonUnitsPerMeter, meters.w);
}

// Returns a rotation matrix aligning the z‑axis with the given up vector.
fn project_get_orientation_matrix(up: vec3<f32>) -> mat3x3<f32> {
  let uz = normalize(up);
  let ux = select(
    vec3<f32>(1.0, 0.0, 0.0),
    normalize(vec3<f32>(uz.y, -uz.x, 0.0)),
    abs(uz.z) == 1.0
  );
  let uy = cross(uz, ux);
  return mat3x3<f32>(ux, uy, uz);
}

// Since WGSL does not support "out" parameters, we return a struct.
struct RotationResult {
  needsRotation: bool,
  transform: mat3x3<f32>,
};

fn project_needs_rotation(commonPosition: vec3<f32>) -> RotationResult {
  if (project.projectionMode == PROJECTION_MODE_GLOBE) {
    return RotationResult(true, project_get_orientation_matrix(commonPosition));
  } else {
    return RotationResult(false, mat3x3<f32>());  // identity alternative if needed
  };
}

// Projects a normal vector from the current coordinate system to world space.
fn project_normal(vector: vec3<f32>) -> vec3<f32> {
  let normal_modelspace = project.modelMatrix * vec4<f32>(vector, 0.0);
  var n = normalize(normal_modelspace.xyz * project.commonUnitsPerMeter);
  let rotResult = project_needs_rotation(geometry.position.xyz);
  if (rotResult.needsRotation) {
    n = rotResult.transform * n;
  }
  return n;
}

// Applies a scale offset based on y-offset (dy)
fn project_offset_(offset: vec4<f32>) -> vec4<f32> {
  let dy: f32 = offset.y;
  let commonUnitsPerWorldUnit = project.commonUnitsPerWorldUnit + project.commonUnitsPerWorldUnit2 * dy;
  return vec4<f32>(offset.xyz * commonUnitsPerWorldUnit, offset.w);
}

// Projects lng/lat coordinates to a unit tile [0,1]
fn project_mercator_(lnglat: vec2<f32>) -> vec2<f32> {
  var x = lnglat.x;
  if (project.wrapLongitude != 0) {
    x = ((x + 180.0) % 360.0) - 180.0;
  }
  let y = clamp(lnglat.y, -89.9, 89.9);
  return vec2<f32>(
    radians(x) + PI,
    PI + log(tan(PI * 0.25 + radians(y) * 0.5))
  ) * WORLD_SCALE;
}

// Projects lng/lat/z coordinates for a globe projection.
fn project_globe_(lnglatz: vec3<f32>) -> vec3<f32> {
  let lambda = radians(lnglatz.x);
  let phi = radians(lnglatz.y);
  let cosPhi = cos(phi);
  let D = (lnglatz.z / EARTH_RADIUS + 1.0) * GLOBE_RADIUS;
  return vec3<f32>(
    sin(lambda) * cosPhi,
    -cos(lambda) * cosPhi,
    sin(phi)
  ) * D;
}

// Projects positions (with an optional 64-bit low part) from the input
// coordinate system to the common space.
fn project_position_vec4_f64(position: vec4<f32>, position64Low: vec3<f32>) -> vec4<f32> {
  var position_world = project.modelMatrix * position;

  // Work around for a Mac+NVIDIA bug:
  if (project.projectionMode == PROJECTION_MODE_WEB_MERCATOR) {
    if (project.coordinateSystem == COORDINATE_SYSTEM_LNGLAT) {
      return vec4<f32>(
        project_mercator_(position_world.xy),
        _project_size_at_latitude_m(position_world.z, position_world.y),
        position_world.w
      );
    }
    if (project.coordinateSystem == COORDINATE_SYSTEM_CARTESIAN) {
      position_world = vec4f(position_world.xyz + project.coordinateOrigin, position_world.w);
    }
  }
  if (project.projectionMode == PROJECTION_MODE_GLOBE) {
    if (project.coordinateSystem == COORDINATE_SYSTEM_LNGLAT) {
      return vec4<f32>(
        project_globe_(position_world.xyz),
        position_world.w
      );
    }
  }
  if (project.projectionMode == PROJECTION_MODE_WEB_MERCATOR_AUTO_OFFSET) {
    if (project.coordinateSystem == COORDINATE_SYSTEM_LNGLAT) {
      if (abs(position_world.y - project.coordinateOrigin.y) > 0.25) {
        return vec4<f32>(
          project_mercator_(position_world.xy) - project.commonOrigin.xy,
          project_size_float(position_world.z),
          position_world.w
        );
      }
    }
  }
  if (project.projectionMode == PROJECTION_MODE_IDENTITY ||
      (project.projectionMode == PROJECTION_MODE_WEB_MERCATOR_AUTO_OFFSET &&
       (project.coordinateSystem == COORDINATE_SYSTEM_LNGLAT ||
        project.coordinateSystem == COORDINATE_SYSTEM_CARTESIAN))) {
    position_world = vec4f(position_world.xyz - project.coordinateOrigin, position_world.w);
  }

  return project_offset_(position_world) +
         project_offset_(project.modelMatrix * vec4<f32>(position64Low, 0.0));
}

// Overloaded versions for different input types.
fn project_position_vec4_f32(position: vec4<f32>) -> vec4<f32> {
  return project_position_vec4_f64(position, ZERO_64_LOW);
}

fn project_position_vec3_f64(position: vec3<f32>, position64Low: vec3<f32>) -> vec3<f32> {
  let projected_position = project_position_vec4_f64(vec4<f32>(position, 1.0), position64Low);
  return projected_position.xyz;
}

fn project_position_vec3_f32(position: vec3<f32>) -> vec3<f32> {
  let projected_position = project_position_vec4_f64(vec4<f32>(position, 1.0), ZERO_64_LOW);
  return projected_position.xyz;
}

fn project_position_vec2_f32(position: vec2<f32>) -> vec2<f32> {
  let projected_position = project_position_vec4_f64(vec4<f32>(position, 0.0, 1.0), ZERO_64_LOW);
  return projected_position.xy;
}

// Transforms a common space position to clip space.
fn project_common_position_to_clipspace_with_projection(position: vec4<f32>, viewProjectionMatrix: mat4x4<f32>, center: vec4<f32>) -> vec4<f32> {
  return viewProjectionMatrix * position + center;
}

// Uses the project viewProjectionMatrix and center.
fn project_common_position_to_clipspace(position: vec4<f32>) -> vec4<f32> {
  return project_common_position_to_clipspace_with_projection(position, project.viewProjectionMatrix, project.center);
}

// Returns a clip space offset corresponding to a given number of screen pixels.
fn project_pixel_size_to_clipspace(pixels: vec2<f32>) -> vec2<f32> {
  let offset = pixels / project.viewportSize * project.devicePixelRatio * 2.0;
  return offset * project.focalDistance;
}

fn project_meter_size_to_pixel(meters: f32) -> f32 {
  return project_size_float(meters) * project.scale;
}

fn project_unit_size_to_pixel(size: f32, unit: i32) -> f32 {
  if (unit == UNIT_METERS) {
    return project_meter_size_to_pixel(size);
  } else if (unit == UNIT_COMMON) {
    return size * project.scale;
  }
  // UNIT_PIXELS: no scaling applied.
  return size;
}

fn project_pixel_size_float(pixels: f32) -> f32 {
  return pixels / project.scale;
}

fn project_pixel_size_vec2(pixels: vec2<f32>) -> vec2<f32> {
  return pixels / project.scale;
}
`,Vo=["default","lnglat","meter-offsets","lnglat-offsets","cartesian"],Yo=Vo.map(e=>`const int COORDINATE_SYSTEM_${e.toUpperCase().replaceAll("-","_")} = ${xe(e)};`).join(""),Xo=Object.keys(G).map(e=>`const int PROJECTION_MODE_${e} = ${G[e]};`).join(""),qo=Object.keys(Ut).map(e=>`const int UNIT_${e.toUpperCase()} = ${Ut[e]};`).join(""),Zo=`${Yo}
${Xo}
${qo}
layout(std140) uniform projectUniforms {
bool wrapLongitude;
int coordinateSystem;
vec3 commonUnitsPerMeter;
int projectionMode;
float scale;
vec3 commonUnitsPerWorldUnit;
vec3 commonUnitsPerWorldUnit2;
vec4 center;
mat4 modelMatrix;
mat4 viewProjectionMatrix;
vec2 viewportSize;
float devicePixelRatio;
float focalDistance;
vec3 cameraPosition;
vec3 coordinateOrigin;
vec3 commonOrigin;
bool pseudoMeters;
} project;
const float TILE_SIZE = 512.0;
const float PI = 3.1415926536;
const float WORLD_SCALE = TILE_SIZE / (PI * 2.0);
const vec3 ZERO_64_LOW = vec3(0.0);
const float EARTH_RADIUS = 6370972.0;
const float GLOBE_RADIUS = 256.0;
float project_size_at_latitude(float lat) {
float y = clamp(lat, -89.9, 89.9);
return 1.0 / cos(radians(y));
}
float project_size() {
if (project.projectionMode == PROJECTION_MODE_WEB_MERCATOR &&
project.coordinateSystem == COORDINATE_SYSTEM_LNGLAT &&
project.pseudoMeters == false) {
if (geometry.position.w == 0.0) {
return project_size_at_latitude(geometry.worldPosition.y);
}
float y = geometry.position.y / TILE_SIZE * 2.0 - 1.0;
float y2 = y * y;
float y4 = y2 * y2;
float y6 = y4 * y2;
return 1.0 + 4.9348 * y2 + 4.0587 * y4 + 1.5642 * y6;
}
return 1.0;
}
float project_size_at_latitude(float meters, float lat) {
return meters * project.commonUnitsPerMeter.z * project_size_at_latitude(lat);
}
float project_size(float meters) {
return meters * project.commonUnitsPerMeter.z * project_size();
}
vec2 project_size(vec2 meters) {
return meters * project.commonUnitsPerMeter.xy * project_size();
}
vec3 project_size(vec3 meters) {
return meters * project.commonUnitsPerMeter * project_size();
}
vec4 project_size(vec4 meters) {
return vec4(meters.xyz * project.commonUnitsPerMeter, meters.w);
}
mat3 project_get_orientation_matrix(vec3 up) {
vec3 uz = normalize(up);
vec3 ux = abs(uz.z) == 1.0 ? vec3(1.0, 0.0, 0.0) : normalize(vec3(uz.y, -uz.x, 0));
vec3 uy = cross(uz, ux);
return mat3(ux, uy, uz);
}
bool project_needs_rotation(vec3 commonPosition, out mat3 transform) {
if (project.projectionMode == PROJECTION_MODE_GLOBE) {
transform = project_get_orientation_matrix(commonPosition);
return true;
}
return false;
}
vec3 project_normal(vec3 vector) {
vec4 normal_modelspace = project.modelMatrix * vec4(vector, 0.0);
vec3 n = normalize(normal_modelspace.xyz * project.commonUnitsPerMeter);
mat3 rotation;
if (project_needs_rotation(geometry.position.xyz, rotation)) {
n = rotation * n;
}
return n;
}
vec4 project_offset_(vec4 offset) {
float dy = offset.y;
vec3 commonUnitsPerWorldUnit = project.commonUnitsPerWorldUnit + project.commonUnitsPerWorldUnit2 * dy;
return vec4(offset.xyz * commonUnitsPerWorldUnit, offset.w);
}
vec2 project_mercator_(vec2 lnglat) {
float x = lnglat.x;
if (project.wrapLongitude) {
x = mod(x + 180., 360.0) - 180.;
}
float y = clamp(lnglat.y, -89.9, 89.9);
return vec2(
radians(x) + PI,
PI + log(tan_fp32(PI * 0.25 + radians(y) * 0.5))
) * WORLD_SCALE;
}
vec3 project_globe_(vec3 lnglatz) {
float lambda = radians(lnglatz.x);
float phi = radians(lnglatz.y);
float cosPhi = cos(phi);
float D = (lnglatz.z / EARTH_RADIUS + 1.0) * GLOBE_RADIUS;
return vec3(
sin(lambda) * cosPhi,
-cos(lambda) * cosPhi,
sin(phi)
) * D;
}
vec4 project_position(vec4 position, vec3 position64Low) {
vec4 position_world = project.modelMatrix * position;
if (project.projectionMode == PROJECTION_MODE_WEB_MERCATOR) {
if (project.coordinateSystem == COORDINATE_SYSTEM_LNGLAT) {
return vec4(
project_mercator_(position_world.xy),
project_size_at_latitude(position_world.z, position_world.y),
position_world.w
);
}
if (project.coordinateSystem == COORDINATE_SYSTEM_CARTESIAN) {
position_world.xyz += project.coordinateOrigin;
}
}
if (project.projectionMode == PROJECTION_MODE_GLOBE) {
if (project.coordinateSystem == COORDINATE_SYSTEM_LNGLAT) {
return vec4(
project_globe_(position_world.xyz),
position_world.w
);
}
}
if (project.projectionMode == PROJECTION_MODE_WEB_MERCATOR_AUTO_OFFSET) {
if (project.coordinateSystem == COORDINATE_SYSTEM_LNGLAT) {
if (abs(position_world.y - project.coordinateOrigin.y) > 0.25) {
return vec4(
project_mercator_(position_world.xy) - project.commonOrigin.xy,
project_size(position_world.z),
position_world.w
);
}
}
}
if (project.projectionMode == PROJECTION_MODE_IDENTITY ||
(project.projectionMode == PROJECTION_MODE_WEB_MERCATOR_AUTO_OFFSET &&
(project.coordinateSystem == COORDINATE_SYSTEM_LNGLAT ||
project.coordinateSystem == COORDINATE_SYSTEM_CARTESIAN))) {
position_world.xyz -= project.coordinateOrigin;
}
return project_offset_(position_world) + project_offset_(project.modelMatrix * vec4(position64Low, 0.0));
}
vec4 project_position(vec4 position) {
return project_position(position, ZERO_64_LOW);
}
vec3 project_position(vec3 position, vec3 position64Low) {
vec4 projected_position = project_position(vec4(position, 1.0), position64Low);
return projected_position.xyz;
}
vec3 project_position(vec3 position) {
vec4 projected_position = project_position(vec4(position, 1.0), ZERO_64_LOW);
return projected_position.xyz;
}
vec2 project_position(vec2 position) {
vec4 projected_position = project_position(vec4(position, 0.0, 1.0), ZERO_64_LOW);
return projected_position.xy;
}
vec4 project_common_position_to_clipspace(vec4 position, mat4 viewProjectionMatrix, vec4 center) {
return viewProjectionMatrix * position + center;
}
vec4 project_common_position_to_clipspace(vec4 position) {
return project_common_position_to_clipspace(position, project.viewProjectionMatrix, project.center);
}
vec2 project_pixel_size_to_clipspace(vec2 pixels) {
vec2 offset = pixels / project.viewportSize * project.devicePixelRatio * 2.0;
return offset * project.focalDistance;
}
float project_size_to_pixel(float meters) {
return project_size(meters) * project.scale;
}
vec2 project_size_to_pixel(vec2 meters) {
return project_size(meters) * project.scale;
}
float project_size_to_pixel(float size, int unit) {
if (unit == UNIT_METERS) return project_size_to_pixel(size);
if (unit == UNIT_COMMON) return size * project.scale;
return size;
}
float project_pixel_size(float pixels) {
return pixels / project.scale;
}
vec2 project_pixel_size(vec2 pixels) {
return pixels / project.scale;
}
`,Ko={};function Jo(e=Ko){return"viewport"in e?Uo(e):{}}const ea={name:"project",dependencies:[Ai,eo],source:Ho,vs:Zo,getUniforms:Jo,uniformTypes:{wrapLongitude:"f32",coordinateSystem:"i32",commonUnitsPerMeter:"vec3<f32>",projectionMode:"i32",scale:"f32",commonUnitsPerWorldUnit:"vec3<f32>",commonUnitsPerWorldUnit2:"vec3<f32>",center:"vec4<f32>",modelMatrix:"mat4x4<f32>",viewProjectionMatrix:"mat4x4<f32>",viewportSize:"vec2<f32>",devicePixelRatio:"f32",focalDistance:"f32",cameraPosition:"vec3<f32>",coordinateOrigin:"vec3<f32>",commonOrigin:"vec3<f32>",pseudoMeters:"f32"}};function Qo(){return[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]}function ot(e,t){const n=Wt([],t,e);return pi(n,n,1/n[3]),n}function ge(e,t,n){return e<t?t:e>n?n:e}function tc(e){return Math.log(e)*Math.LOG2E}const Kn=Math.log2||tc;function Y(e,t){if(!e)throw new Error(t||"@math.gl/web-mercator: assertion failed.")}const H=Math.PI,Jn=H/4,W=H/180,pe=180/H,ft=512,$t=4003e4,Ot=85.051129,ec=1.5;function nc(e){return Kn(e)}function Bt(e){const[t,n]=e;Y(Number.isFinite(t)),Y(Number.isFinite(n)&&n>=-90&&n<=90,"invalid latitude");const s=t*W,r=n*W,i=ft*(s+H)/(2*H),o=ft*(H+Math.log(Math.tan(Jn+r*.5)))/(2*H);return[i,o]}function Gt(e){const[t,n]=e,s=t/ft*(2*H)-H,r=2*(Math.atan(Math.exp(n/ft*(2*H)-H))-Jn);return[s*pe,r*pe]}function sc(e){const{latitude:t}=e;Y(Number.isFinite(t));const n=Math.cos(t*W);return nc($t*n)-9}function ae(e){const t=Math.cos(e*W);return ft/$t/t}function me(e){const{latitude:t,longitude:n,highPrecision:s=!1}=e;Y(Number.isFinite(t)&&Number.isFinite(n));const r=ft,i=Math.cos(t*W),o=r/360,c=o/i,a=r/$t/i,l={unitsPerMeter:[a,a,a],metersPerUnit:[1/a,1/a,1/a],unitsPerDegree:[o,c,a],degreesPerUnit:[1/o,1/c,1/a]};if(s){const f=W*Math.tan(t*W)/i,h=o*f/2,u=r/$t*f,d=u/c*a;l.unitsPerDegree2=[0,h,u],l.unitsPerMeter2=[d,0,d]}return l}function rc(e,t){const[n,s,r]=e,[i,o,c]=t,{unitsPerMeter:a,unitsPerMeter2:l}=me({longitude:n,latitude:s,highPrecision:!0}),f=Bt(e);f[0]+=i*(a[0]+l[0]*o),f[1]+=o*(a[1]+l[1]*o);const h=Gt(f),u=(r||0)+(c||0);return Number.isFinite(r)||Number.isFinite(c)?[h[0],h[1],u]:h}function ic(e){const{height:t,pitch:n,bearing:s,altitude:r,scale:i,center:o}=e,c=Qo();kt(c,c,[0,0,-r]),Dn(c,c,-n*W),kn(c,c,s*W);const a=i/t;return ve(c,c,[a,a,a]),o&&kt(c,c,Vr([],o)),c}function oc(e){const{width:t,height:n,altitude:s,pitch:r=0,offset:i,center:o,scale:c,nearZMultiplier:a=1,farZMultiplier:l=1}=e;let{fovy:f=zt(ec)}=e;s!==void 0&&(f=zt(s));const h=f*W,u=r*W,d=Qn(f);let g=d;o&&(g+=o[2]*c/Math.cos(u)/n);const p=h*(.5+(i?i[1]:0)/n),m=Math.sin(p)*g/Math.sin(ge(Math.PI/2-u-p,.01,Math.PI-.01)),M=Math.sin(u)*m+g,v=g*10,E=Math.min(M*l,v);return{fov:h,aspect:t/n,focalDistance:d,near:a,far:E}}function zt(e){return 2*Math.atan(.5/e)*pe}function Qn(e){return .5/Math.tan(.5*e*W)}function cc(e,t){const[n,s,r=0]=e;return Y(Number.isFinite(n)&&Number.isFinite(s)&&Number.isFinite(r)),ot(t,[n,s,r,1])}function ts(e,t,n=0){const[s,r,i]=e;if(Y(Number.isFinite(s)&&Number.isFinite(r),"invalid pixel coordinate"),Number.isFinite(i))return ot(t,[s,r,i,1]);const o=ot(t,[s,r,0,1]),c=ot(t,[s,r,1,1]),a=o[2],l=c[2],f=a===l?0:((n||0)-a)/(l-a);return In([],o,c,f)}function ac(e){const{width:t,height:n,bounds:s,minExtent:r=0,maxZoom:i=24,offset:o=[0,0]}=e,[[c,a],[l,f]]=s,h=lc(e.padding),u=Bt([c,ge(f,-Ot,Ot)]),d=Bt([l,ge(a,-Ot,Ot)]),g=[Math.max(Math.abs(d[0]-u[0]),r),Math.max(Math.abs(d[1]-u[1]),r)],p=[t-h.left-h.right-Math.abs(o[0])*2,n-h.top-h.bottom-Math.abs(o[1])*2];Y(p[0]>0&&p[1]>0);const m=p[0]/g[0],M=p[1]/g[1],v=(h.right-h.left)/2/m,E=(h.top-h.bottom)/2/M,_=[(d[0]+u[0])/2+v,(d[1]+u[1])/2+E],y=Gt(_),b=Math.min(i,Kn(Math.abs(Math.min(m,M))));return Y(Number.isFinite(b)),{longitude:y[0],latitude:y[1],zoom:b}}function lc(e=0){return typeof e=="number"?{top:e,bottom:e,left:e,right:e}:(Y(Number.isFinite(e.top)&&Number.isFinite(e.bottom)&&Number.isFinite(e.left)&&Number.isFinite(e.right)),e)}const fn=Math.PI/180;function fc(e,t=0){const{width:n,height:s,unproject:r}=e,i={targetZ:t},o=r([0,s],i),c=r([n,s],i);let a,l;const f=e.fovy?.5*e.fovy*fn:Math.atan(.5/e.altitude),h=(90-e.pitch)*fn;return f>h-.01?(a=hn(e,0,t),l=hn(e,n,t)):(a=r([0,0],i),l=r([n,0],i)),[o,c,l,a]}function hn(e,t,n){const{pixelUnprojectionMatrix:s}=e,r=ot(s,[t,0,1,1]),i=ot(s,[t,e.height,1,1]),c=(n*e.distanceScales.unitsPerMeter[2]-r[2])/(i[2]-r[2]),a=In([],r,i,c),l=Gt(a);return l.push(n),l}class hc{constructor(t={}){this._pool=[],this.opts={overAlloc:2,poolSize:100},this.setOptions(t)}setOptions(t){Object.assign(this.opts,t)}allocate(t,n,{size:s=1,type:r,padding:i=0,copy:o=!1,initialize:c=!1,maxCount:a}){const l=r||t&&t.constructor||Float32Array,f=n*s+i;if(ArrayBuffer.isView(t)){if(f<=t.length)return t;if(f*t.BYTES_PER_ELEMENT<=t.buffer.byteLength)return new l(t.buffer,0,f)}let h=1/0;a&&(h=a*s+i);const u=this._allocate(l,f,c,h);return t&&o?u.set(t):c||u.fill(0,0,4),this._release(t),u}release(t){this._release(t)}_allocate(t,n,s,r){let i=Math.max(Math.ceil(n*this.opts.overAlloc),1);i>r&&(i=r);const o=this._pool,c=t.BYTES_PER_ELEMENT*i,a=o.findIndex(l=>l.byteLength>=c);if(a>=0){const l=new t(o.splice(a,1)[0],0,i);return s&&l.fill(0),l}return new t(i)}_release(t){if(!ArrayBuffer.isView(t))return;const n=this._pool,{buffer:s}=t,{byteLength:r}=s,i=n.findIndex(o=>o.byteLength>=r);i<0?n.push(s):(i>0||n.length<this.opts.poolSize)&&n.splice(i,0,s),n.length>this.opts.poolSize&&n.shift()}}const uc=new hc;function mt(){return[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]}function na(e,t){const n=e%t;return n<0?t+n:n}function dc(e){return[e[12],e[13],e[14]]}function gc(e){return{left:st(e[3]+e[0],e[7]+e[4],e[11]+e[8],e[15]+e[12]),right:st(e[3]-e[0],e[7]-e[4],e[11]-e[8],e[15]-e[12]),bottom:st(e[3]+e[1],e[7]+e[5],e[11]+e[9],e[15]+e[13]),top:st(e[3]-e[1],e[7]-e[5],e[11]-e[9],e[15]-e[13]),near:st(e[3]+e[2],e[7]+e[6],e[11]+e[10],e[15]+e[14]),far:st(e[3]-e[2],e[7]-e[6],e[11]-e[10],e[15]-e[14])}}const un=new lt;function st(e,t,n,s){un.set(e,t,n);const r=un.len();return{distance:s/r,normal:new lt(-e/r,-t/r,-n/r)}}function pc(e){return e-Math.fround(e)}let gt;function sa(e,t){const{size:n=1,startIndex:s=0}=t,r=t.endIndex!==void 0?t.endIndex:e.length,i=(r-s)/n;gt=uc.allocate(gt,i,{type:Float32Array,size:n*2});let o=s,c=0;for(;o<r;){for(let a=0;a<n;a++){const l=e[o++];gt[c+a]=l,gt[c+a+n]=pc(l)}c+=n*2}return gt.subarray(0,i*n*2)}function ra(e){let t=null,n=!1;for(const s of e)s&&(t?(n||(t=[[t[0][0],t[0][1]],[t[1][0],t[1][1]]],n=!0),t[0][0]=Math.min(t[0][0],s[0][0]),t[0][1]=Math.min(t[0][1],s[0][1]),t[1][0]=Math.max(t[1][0],s[1][0]),t[1][1]=Math.max(t[1][1],s[1][1])):t=s);return t}const mc=Math.PI/180,_c=mt(),dn=[0,0,0],Ec={unitsPerMeter:[1,1,1],metersPerUnit:[1,1,1]};function bc({width:e,height:t,orthographic:n,fovyRadians:s,focalDistance:r,padding:i,near:o,far:c}){const a=e/t,l=n?new tt().orthographic({fovy:s,aspect:a,focalDistance:r,near:o,far:c}):new tt().perspective({fovy:s,aspect:a,near:o,far:c});if(i){const{left:f=0,right:h=0,top:u=0,bottom:d=0}=i,g=jt((f+e-h)/2,0,e)-e/2,p=jt((u+t-d)/2,0,t)-t/2;l[8]-=g*2/e,l[9]+=p*2/t}return l}class Ht{constructor(t={}){this._frustumPlanes={},this.id=t.id||this.constructor.displayName||"viewport",this.x=t.x||0,this.y=t.y||0,this.width=t.width||1,this.height=t.height||1,this.zoom=t.zoom||0,this.padding=t.padding,this.distanceScales=t.distanceScales||Ec,this.focalDistance=t.focalDistance||1,this.position=t.position||dn,this.modelMatrix=t.modelMatrix||null;const{longitude:n,latitude:s}=t;this.isGeospatial=Number.isFinite(s)&&Number.isFinite(n),this._initProps(t),this._initMatrices(t),this.equals=this.equals.bind(this),this.project=this.project.bind(this),this.unproject=this.unproject.bind(this),this.projectPosition=this.projectPosition.bind(this),this.unprojectPosition=this.unprojectPosition.bind(this),this.projectFlat=this.projectFlat.bind(this),this.unprojectFlat=this.unprojectFlat.bind(this)}get subViewports(){return null}get metersPerPixel(){return this.distanceScales.metersPerUnit[2]/this.scale}get projectionMode(){return this.isGeospatial?this.zoom<12?G.WEB_MERCATOR:G.WEB_MERCATOR_AUTO_OFFSET:G.IDENTITY}equals(t){return t instanceof Ht?this===t?!0:t.width===this.width&&t.height===this.height&&t.scale===this.scale&&Dt(t.projectionMatrix,this.projectionMatrix)&&Dt(t.viewMatrix,this.viewMatrix):!1}project(t,{topLeft:n=!0}={}){const s=this.projectPosition(t),r=cc(s,this.pixelProjectionMatrix),[i,o]=r,c=n?o:this.height-o;return t.length===2?[i,c]:[i,c,r[2]]}unproject(t,{topLeft:n=!0,targetZ:s}={}){const[r,i,o]=t,c=n?i:this.height-i,a=s&&s*this.distanceScales.unitsPerMeter[2],l=ts([r,c,o],this.pixelUnprojectionMatrix,a),[f,h,u]=this.unprojectPosition(l);return Number.isFinite(o)?[f,h,u]:Number.isFinite(s)?[f,h,s]:[f,h]}projectPosition(t){const[n,s]=this.projectFlat(t),r=(t[2]||0)*this.distanceScales.unitsPerMeter[2];return[n,s,r]}unprojectPosition(t){const[n,s]=this.unprojectFlat(t),r=(t[2]||0)*this.distanceScales.metersPerUnit[2];return[n,s,r]}projectFlat(t){if(this.isGeospatial){const n=Bt(t);return n[1]=jt(n[1],-318,830),n}return t}unprojectFlat(t){return this.isGeospatial?Gt(t):t}getBounds(t={}){const n={targetZ:t.z||0},s=this.unproject([0,0],n),r=this.unproject([this.width,0],n),i=this.unproject([0,this.height],n),o=this.unproject([this.width,this.height],n);return[Math.min(s[0],r[0],i[0],o[0]),Math.min(s[1],r[1],i[1],o[1]),Math.max(s[0],r[0],i[0],o[0]),Math.max(s[1],r[1],i[1],o[1])]}getDistanceScales(t){return t&&this.isGeospatial?me({longitude:t[0],latitude:t[1],highPrecision:!0}):this.distanceScales}containsPixel({x:t,y:n,width:s=1,height:r=1}){return t<this.x+this.width&&this.x<t+s&&n<this.y+this.height&&this.y<n+r}getFrustumPlanes(){return this._frustumPlanes.near?this._frustumPlanes:(Object.assign(this._frustumPlanes,gc(this.viewProjectionMatrix)),this._frustumPlanes)}panByPosition(t,n,s){return null}_initProps(t){const n=t.longitude,s=t.latitude;this.isGeospatial&&(Number.isFinite(t.zoom)||(this.zoom=sc({latitude:s})+Math.log2(this.focalDistance)),this.distanceScales=t.distanceScales||me({latitude:s,longitude:n}));const r=Math.pow(2,this.zoom);this.scale=r;const{position:i,modelMatrix:o}=t;let c=dn;if(i&&(c=o?new tt(o).transformAsVector(i,[]):i),this.isGeospatial){const a=this.projectPosition([n,s,0]);this.center=new lt(c).scale(this.distanceScales.unitsPerMeter).add(a)}else this.center=this.projectPosition(c)}_initMatrices(t){const{viewMatrix:n=_c,projectionMatrix:s=null,orthographic:r=!1,fovyRadians:i,fovy:o=75,near:c=.1,far:a=1e3,padding:l=null,focalDistance:f=1}=t;this.viewMatrixUncentered=n,this.viewMatrix=new tt().multiplyRight(n).translate(new lt(this.center).negate()),this.projectionMatrix=s||bc({width:this.width,height:this.height,orthographic:r,fovyRadians:i||o*mc,focalDistance:f,padding:l,near:c,far:a});const h=mt();J(h,h,this.projectionMatrix),J(h,h,this.viewMatrix),this.viewProjectionMatrix=h,this.viewMatrixInverse=he([],this.viewMatrix)||this.viewMatrix,this.cameraPosition=dc(this.viewMatrixInverse);const u=mt(),d=mt();ve(u,u,[this.width/2,-this.height/2,1]),kt(u,u,[1,-1,0]),J(d,u,this.viewProjectionMatrix),this.pixelProjectionMatrix=d,this.pixelUnprojectionMatrix=he(mt(),this.pixelProjectionMatrix),this.pixelUnprojectionMatrix||_n.warn("Pixel project matrix not invertible")()}}Ht.displayName="Viewport";class Ft extends Ht{constructor(t={}){const{latitude:n=0,longitude:s=0,zoom:r=0,pitch:i=0,bearing:o=0,nearZMultiplier:c=.1,farZMultiplier:a=1.01,nearZ:l,farZ:f,orthographic:h=!1,projectionMatrix:u,repeat:d=!1,worldOffset:g=0,position:p,padding:m,legacyMeterSizes:M=!1}=t;let{width:v,height:E,altitude:_=1.5}=t;const y=Math.pow(2,r);v=v||1,E=E||1;let b,A=null;if(u)_=u[5]/2,b=zt(_);else{t.fovy?(b=t.fovy,_=Qn(b)):b=zt(_);let w;if(m){const{top:O=0,bottom:N=0}=m;w=[0,jt((O+E-N)/2,0,E)-E/2]}A=oc({width:v,height:E,scale:y,center:p&&[0,0,p[2]*ae(n)],offset:w,pitch:i,fovy:b,nearZMultiplier:c,farZMultiplier:a}),Number.isFinite(l)&&(A.near=l),Number.isFinite(f)&&(A.far=f)}let x=ic({height:E,pitch:i,bearing:o,scale:y,altitude:_});g&&(x=new tt().translate([512*g,0,0]).multiplyLeft(x)),super({...t,width:v,height:E,viewMatrix:x,longitude:s,latitude:n,zoom:r,...A,fovy:b,focalDistance:_}),this.latitude=n,this.longitude=s,this.zoom=r,this.pitch=i,this.bearing=o,this.altitude=_,this.fovy=b,this.orthographic=h,this._subViewports=d?[]:null,this._pseudoMeters=M,Object.freeze(this)}get subViewports(){if(this._subViewports&&!this._subViewports.length){const t=this.getBounds(),n=Math.floor((t[0]+180)/360),s=Math.ceil((t[2]-180)/360);for(let r=n;r<=s;r++){const i=r?new Ft({...this,worldOffset:r}):this;this._subViewports.push(i)}}return this._subViewports}projectPosition(t){if(this._pseudoMeters)return super.projectPosition(t);const[n,s]=this.projectFlat(t),r=(t[2]||0)*ae(t[1]);return[n,s,r]}unprojectPosition(t){if(this._pseudoMeters)return super.unprojectPosition(t);const[n,s]=this.unprojectFlat(t),r=(t[2]||0)/ae(s);return[n,s,r]}addMetersToLngLat(t,n){return rc(t,n)}panByPosition(t,n,s){const r=ts(n,this.pixelUnprojectionMatrix),i=this.projectFlat(t),o=ze([],i,Dr([],r)),c=ze([],this.center,o),[a,l]=this.unprojectFlat(c);return{longitude:a,latitude:l}}panByPosition3D(t,n){const s=t[2]||0,r=Ur([],t,this.unproject(n,{targetZ:s}));return{longitude:this.longitude+r[0],latitude:this.latitude+r[1]}}getBounds(t={}){const n=fc(this,t.z||0);return[Math.min(n[0][0],n[1][0],n[2][0],n[3][0]),Math.min(n[0][1],n[1][1],n[2][1],n[3][1]),Math.max(n[0][0],n[1][0],n[2][0],n[3][0]),Math.max(n[0][1],n[1][1],n[2][1],n[3][1])]}fitBounds(t,n={}){const{width:s,height:r}=this,{longitude:i,latitude:o,zoom:c}=ac({width:s,height:r,bounds:t,...n});return new Ft({width:s,height:r,longitude:i,latitude:o,zoom:c})}}Ft.displayName="WebMercatorViewport";function gn(e,t,n){if(e===t)return!0;if(!n||!e||!t)return!1;if(Array.isArray(e)){if(!Array.isArray(t)||e.length!==t.length)return!1;for(let s=0;s<e.length;s++)if(!gn(e[s],t[s],n-1))return!1;return!0}if(Array.isArray(t))return!1;if(typeof e=="object"&&typeof t=="object"){const s=Object.keys(e),r=Object.keys(t);if(s.length!==r.length)return!1;for(const i of s)if(!t.hasOwnProperty(i)||!gn(e[i],t[i],n-1))return!1;return!0}return!1}export{Q as $,ta as A,Ze as B,Ot as C,ae as D,Qc as E,be as F,Ir as G,at as H,vo as I,$ as J,U as K,kr as L,tt as M,$r as N,xc as O,Kc as P,vc as Q,S as R,$e as S,ro as T,Sc as U,lt as V,Jc as W,jn as X,Oc as Y,wc as Z,Zr as _,io as a,ei as a0,qr as a1,qt as a2,Uc as a3,$c as a4,zc as a5,zr as a6,Lc as a7,Yr as a8,Xr as a9,Do as aA,Pt as aB,sa as aC,ra as aD,cc as aE,vi as aF,Gc as aG,Vc as aH,Yc as aI,Hc as aJ,ze as aK,Dr as aL,Ic as aM,pc as aN,Z as aO,bn as aP,ss as aQ,Tc as aR,Cc as aa,Rc as ab,kc as ac,Fc as ad,pi as ae,Bc as af,Rt as ag,Nn as ah,Wc as ai,de as aj,an as ak,Dc as al,Be as am,it as an,Ac as ao,Mc as ap,Fr as aq,Or as ar,Qn as as,zt as at,jc as au,Nc as av,Pc as aw,Wt as ax,Ut as ay,rc as az,oo as b,so as c,_n as d,qc as e,Xc as f,xe as g,G as h,_e as i,ts as j,eo as k,Si as l,Po as m,Ht as n,gn as o,ea as p,Dt as q,Lr as r,Fn as s,na as t,jt as u,Bt as v,Gt as w,Ft as x,Je as y,uc as z};
//# sourceMappingURL=deep-equal-Dwhz1A9B.js.map
