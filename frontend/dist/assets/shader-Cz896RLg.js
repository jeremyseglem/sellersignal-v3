var Re=Object.defineProperty;var Be=(i,e,t)=>e in i?Re(i,e,{enumerable:!0,configurable:!0,writable:!0,value:t}):i[e]=t;var u=(i,e,t)=>Be(i,typeof e!="symbol"?e+"":e,t);import{aO as ie,aF as Ce,l as d,B as y,aG as $e,aP as De,aH as _e,aI as ke,y as b,aj as me,S as Ue,aB as Me}from"./deep-equal-Dwhz1A9B.js";import{R as F,S as ze,a as x,b as je,r as We,c as Ve,n as Ge,T as He,d as qe}from"./array-utils-flat-Bshre25B.js";function Ke(i){return ArrayBuffer.isView(i)&&!(i instanceof DataView)}function Ye(i){return Array.isArray(i)?i.length===0||typeof i[0]=="number":!1}function Xe(i){return Ke(i)||Ye(i)}function Q(i,e=[],t=0){const r=Math.fround(i),s=i-r;return e[t]=r,e[t+1]=s,e}function ve(i){return i-Math.fround(i)}function be(i){const e=new Float32Array(32);for(let t=0;t<4;++t)for(let r=0;r<4;++r){const s=t*4+r;Q(i[r*4+t],e,s*2)}return e}const se=`
layout(std140) uniform fp64arithmeticUniforms {
  uniform float ONE;
  uniform float SPLIT;
} fp64;

/*
About LUMA_FP64_CODE_ELIMINATION_WORKAROUND

The purpose of this workaround is to prevent shader compilers from
optimizing away necessary arithmetic operations by swapping their sequences
or transform the equation to some 'equivalent' form.

These helpers implement Dekker/Veltkamp-style error tracking. If the compiler
folds constants or reassociates the arithmetic, the high/low split can stop
tracking the rounding error correctly. That failure mode tends to look fine in
simple coordinate setup, but then breaks down inside iterative arithmetic such
as fp64 Mandelbrot loops.

The method is to multiply an artifical variable, ONE, which will be known to
the compiler to be 1 only at runtime. The whole expression is then represented
as a polynomial with respective to ONE. In the coefficients of all terms, only one a
and one b should appear

err = (a + b) * ONE^6 - a * ONE^5 - (a + b) * ONE^4 + a * ONE^3 - b - (a + b) * ONE^2 + a * ONE
*/

float prevent_fp64_optimization(float value) {
#if defined(LUMA_FP64_CODE_ELIMINATION_WORKAROUND)
  return value + fp64.ONE * 0.0;
#else
  return value;
#endif
}

// Divide float number to high and low floats to extend fraction bits
vec2 split(float a) {
  // Keep SPLIT as a runtime uniform so the compiler cannot fold the Dekker
  // split into a constant expression and reassociate the recovery steps.
  float split = prevent_fp64_optimization(fp64.SPLIT);
  float t = prevent_fp64_optimization(a * split);
  float temp = t - a;
  float a_hi = t - temp;
  float a_lo = a - a_hi;
  return vec2(a_hi, a_lo);
}

// Divide float number again when high float uses too many fraction bits
vec2 split2(vec2 a) {
  vec2 b = split(a.x);
  b.y += a.y;
  return b;
}

// Special sum operation when a > b
vec2 quickTwoSum(float a, float b) {
#if defined(LUMA_FP64_CODE_ELIMINATION_WORKAROUND)
  float sum = (a + b) * fp64.ONE;
  float err = b - (sum - a) * fp64.ONE;
#else
  float sum = a + b;
  float err = b - (sum - a);
#endif
  return vec2(sum, err);
}

// General sum operation
vec2 twoSum(float a, float b) {
  float s = (a + b);
#if defined(LUMA_FP64_CODE_ELIMINATION_WORKAROUND)
  float v = (s * fp64.ONE - a) * fp64.ONE;
  float err = (a - (s - v) * fp64.ONE) * fp64.ONE * fp64.ONE * fp64.ONE + (b - v);
#else
  float v = s - a;
  float err = (a - (s - v)) + (b - v);
#endif
  return vec2(s, err);
}

vec2 twoSub(float a, float b) {
  float s = (a - b);
#if defined(LUMA_FP64_CODE_ELIMINATION_WORKAROUND)
  float v = (s * fp64.ONE - a) * fp64.ONE;
  float err = (a - (s - v) * fp64.ONE) * fp64.ONE * fp64.ONE * fp64.ONE - (b + v);
#else
  float v = s - a;
  float err = (a - (s - v)) - (b + v);
#endif
  return vec2(s, err);
}

vec2 twoSqr(float a) {
  float prod = a * a;
  vec2 a_fp64 = split(a);
#if defined(LUMA_FP64_CODE_ELIMINATION_WORKAROUND)
  float err = ((a_fp64.x * a_fp64.x - prod) * fp64.ONE + 2.0 * a_fp64.x *
    a_fp64.y * fp64.ONE * fp64.ONE) + a_fp64.y * a_fp64.y * fp64.ONE * fp64.ONE * fp64.ONE;
#else
  float err = ((a_fp64.x * a_fp64.x - prod) + 2.0 * a_fp64.x * a_fp64.y) + a_fp64.y * a_fp64.y;
#endif
  return vec2(prod, err);
}

vec2 twoProd(float a, float b) {
  float prod = a * b;
  vec2 a_fp64 = split(a);
  vec2 b_fp64 = split(b);
  // twoProd is especially sensitive because mul_fp64 and div_fp64 both depend
  // on the split terms and cross terms staying in the original evaluation
  // order. If the compiler folds or reassociates them, the low part tends to
  // collapse to zero or NaN on some drivers.
  float highProduct = prevent_fp64_optimization(a_fp64.x * b_fp64.x);
  float crossProduct1 = prevent_fp64_optimization(a_fp64.x * b_fp64.y);
  float crossProduct2 = prevent_fp64_optimization(a_fp64.y * b_fp64.x);
  float lowProduct = prevent_fp64_optimization(a_fp64.y * b_fp64.y);
#if defined(LUMA_FP64_CODE_ELIMINATION_WORKAROUND)
  float err1 = (highProduct - prod) * fp64.ONE;
  float err2 = crossProduct1 * fp64.ONE * fp64.ONE;
  float err3 = crossProduct2 * fp64.ONE * fp64.ONE * fp64.ONE;
  float err4 = lowProduct * fp64.ONE * fp64.ONE * fp64.ONE * fp64.ONE;
#else
  float err1 = highProduct - prod;
  float err2 = crossProduct1;
  float err3 = crossProduct2;
  float err4 = lowProduct;
#endif
  float err = ((err1 + err2) + err3) + err4;
  return vec2(prod, err);
}

vec2 sum_fp64(vec2 a, vec2 b) {
  vec2 s, t;
  s = twoSum(a.x, b.x);
  t = twoSum(a.y, b.y);
  s.y += t.x;
  s = quickTwoSum(s.x, s.y);
  s.y += t.y;
  s = quickTwoSum(s.x, s.y);
  return s;
}

vec2 sub_fp64(vec2 a, vec2 b) {
  vec2 s, t;
  s = twoSub(a.x, b.x);
  t = twoSub(a.y, b.y);
  s.y += t.x;
  s = quickTwoSum(s.x, s.y);
  s.y += t.y;
  s = quickTwoSum(s.x, s.y);
  return s;
}

vec2 mul_fp64(vec2 a, vec2 b) {
  vec2 prod = twoProd(a.x, b.x);
  // y component is for the error
  prod.y += a.x * b.y;
#if defined(LUMA_FP64_HIGH_BITS_OVERFLOW_WORKAROUND)
  prod = split2(prod);
#endif
  prod = quickTwoSum(prod.x, prod.y);
  prod.y += a.y * b.x;
#if defined(LUMA_FP64_HIGH_BITS_OVERFLOW_WORKAROUND)
  prod = split2(prod);
#endif
  prod = quickTwoSum(prod.x, prod.y);
  return prod;
}

vec2 div_fp64(vec2 a, vec2 b) {
  float xn = 1.0 / b.x;
#if defined(LUMA_FP64_HIGH_BITS_OVERFLOW_WORKAROUND)
  vec2 yn = mul_fp64(a, vec2(xn, 0));
#else
  vec2 yn = a * xn;
#endif
  float diff = (sub_fp64(a, mul_fp64(b, yn))).x;
  vec2 prod = twoProd(xn, diff);
  return sum_fp64(yn, prod);
}

vec2 sqrt_fp64(vec2 a) {
  if (a.x == 0.0 && a.y == 0.0) return vec2(0.0, 0.0);
  if (a.x < 0.0) return vec2(0.0 / 0.0, 0.0 / 0.0);

  float x = 1.0 / sqrt(a.x);
  float yn = a.x * x;
#if defined(LUMA_FP64_CODE_ELIMINATION_WORKAROUND)
  vec2 yn_sqr = twoSqr(yn) * fp64.ONE;
#else
  vec2 yn_sqr = twoSqr(yn);
#endif
  float diff = sub_fp64(a, yn_sqr).x;
  vec2 prod = twoProd(x * 0.5, diff);
#if defined(LUMA_FP64_HIGH_BITS_OVERFLOW_WORKAROUND)
  return sum_fp64(split(yn), prod);
#else
  return sum_fp64(vec2(yn, 0.0), prod);
#endif
}
`,Je=`struct Fp64ArithmeticUniforms {
  ONE: f32,
  SPLIT: f32,
};

@group(0) @binding(auto) var<uniform> fp64arithmetic : Fp64ArithmeticUniforms;

fn fp64_nan(seed: f32) -> f32 {
  let nanBits = 0x7fc00000u | select(0u, 1u, seed < 0.0);
  return bitcast<f32>(nanBits);
}

fn fp64_runtime_zero() -> f32 {
  return fp64arithmetic.ONE * 0.0;
}

fn prevent_fp64_optimization(value: f32) -> f32 {
#ifdef LUMA_FP64_CODE_ELIMINATION_WORKAROUND
  return value + fp64_runtime_zero();
#else
  return value;
#endif
}

fn split(a: f32) -> vec2f {
  let splitValue = prevent_fp64_optimization(fp64arithmetic.SPLIT + fp64_runtime_zero());
  let t = prevent_fp64_optimization(a * splitValue);
  let temp = prevent_fp64_optimization(t - a);
  let aHi = prevent_fp64_optimization(t - temp);
  let aLo = prevent_fp64_optimization(a - aHi);
  return vec2f(aHi, aLo);
}

fn split2(a: vec2f) -> vec2f {
  var b = split(a.x);
  b.y = b.y + a.y;
  return b;
}

fn quickTwoSum(a: f32, b: f32) -> vec2f {
#ifdef LUMA_FP64_CODE_ELIMINATION_WORKAROUND
  let sum = prevent_fp64_optimization((a + b) * fp64arithmetic.ONE);
  let err = prevent_fp64_optimization(b - (sum - a) * fp64arithmetic.ONE);
#else
  let sum = prevent_fp64_optimization(a + b);
  let err = prevent_fp64_optimization(b - (sum - a));
#endif
  return vec2f(sum, err);
}

fn twoSum(a: f32, b: f32) -> vec2f {
  let s = prevent_fp64_optimization(a + b);
#ifdef LUMA_FP64_CODE_ELIMINATION_WORKAROUND
  let v = prevent_fp64_optimization((s * fp64arithmetic.ONE - a) * fp64arithmetic.ONE);
  let err =
    prevent_fp64_optimization((a - (s - v) * fp64arithmetic.ONE) *
      fp64arithmetic.ONE *
      fp64arithmetic.ONE *
      fp64arithmetic.ONE) +
    prevent_fp64_optimization(b - v);
#else
  let v = prevent_fp64_optimization(s - a);
  let err = prevent_fp64_optimization(a - (s - v)) + prevent_fp64_optimization(b - v);
#endif
  return vec2f(s, err);
}

fn twoSub(a: f32, b: f32) -> vec2f {
  let s = prevent_fp64_optimization(a - b);
#ifdef LUMA_FP64_CODE_ELIMINATION_WORKAROUND
  let v = prevent_fp64_optimization((s * fp64arithmetic.ONE - a) * fp64arithmetic.ONE);
  let err =
    prevent_fp64_optimization((a - (s - v) * fp64arithmetic.ONE) *
      fp64arithmetic.ONE *
      fp64arithmetic.ONE *
      fp64arithmetic.ONE) -
    prevent_fp64_optimization(b + v);
#else
  let v = prevent_fp64_optimization(s - a);
  let err = prevent_fp64_optimization(a - (s - v)) - prevent_fp64_optimization(b + v);
#endif
  return vec2f(s, err);
}

fn twoSqr(a: f32) -> vec2f {
  let prod = prevent_fp64_optimization(a * a);
  let aFp64 = split(a);
  let highProduct = prevent_fp64_optimization(aFp64.x * aFp64.x);
  let crossProduct = prevent_fp64_optimization(2.0 * aFp64.x * aFp64.y);
  let lowProduct = prevent_fp64_optimization(aFp64.y * aFp64.y);
#ifdef LUMA_FP64_CODE_ELIMINATION_WORKAROUND
  let err =
    (prevent_fp64_optimization(highProduct - prod) * fp64arithmetic.ONE +
      crossProduct * fp64arithmetic.ONE * fp64arithmetic.ONE) +
    lowProduct * fp64arithmetic.ONE * fp64arithmetic.ONE * fp64arithmetic.ONE;
#else
  let err = ((prevent_fp64_optimization(highProduct - prod) + crossProduct) + lowProduct);
#endif
  return vec2f(prod, err);
}

fn twoProd(a: f32, b: f32) -> vec2f {
  let prod = prevent_fp64_optimization(a * b);
  let aFp64 = split(a);
  let bFp64 = split(b);
  let highProduct = prevent_fp64_optimization(aFp64.x * bFp64.x);
  let crossProduct1 = prevent_fp64_optimization(aFp64.x * bFp64.y);
  let crossProduct2 = prevent_fp64_optimization(aFp64.y * bFp64.x);
  let lowProduct = prevent_fp64_optimization(aFp64.y * bFp64.y);
#ifdef LUMA_FP64_CODE_ELIMINATION_WORKAROUND
  let err1 = (highProduct - prod) * fp64arithmetic.ONE;
  let err2 = crossProduct1 * fp64arithmetic.ONE * fp64arithmetic.ONE;
  let err3 = crossProduct2 * fp64arithmetic.ONE * fp64arithmetic.ONE * fp64arithmetic.ONE;
  let err4 =
    lowProduct *
    fp64arithmetic.ONE *
    fp64arithmetic.ONE *
    fp64arithmetic.ONE *
    fp64arithmetic.ONE;
#else
  let err1 = highProduct - prod;
  let err2 = crossProduct1;
  let err3 = crossProduct2;
  let err4 = lowProduct;
#endif
  let err12InputA = prevent_fp64_optimization(err1);
  let err12InputB = prevent_fp64_optimization(err2);
  let err12 = prevent_fp64_optimization(err12InputA + err12InputB);
  let err123InputA = prevent_fp64_optimization(err12);
  let err123InputB = prevent_fp64_optimization(err3);
  let err123 = prevent_fp64_optimization(err123InputA + err123InputB);
  let err1234InputA = prevent_fp64_optimization(err123);
  let err1234InputB = prevent_fp64_optimization(err4);
  let err = prevent_fp64_optimization(err1234InputA + err1234InputB);
  return vec2f(prod, err);
}

fn sum_fp64(a: vec2f, b: vec2f) -> vec2f {
  var s = twoSum(a.x, b.x);
  let t = twoSum(a.y, b.y);
  s.y = prevent_fp64_optimization(s.y + t.x);
  s = quickTwoSum(s.x, s.y);
  s.y = prevent_fp64_optimization(s.y + t.y);
  s = quickTwoSum(s.x, s.y);
  return s;
}

fn sub_fp64(a: vec2f, b: vec2f) -> vec2f {
  var s = twoSub(a.x, b.x);
  let t = twoSub(a.y, b.y);
  s.y = prevent_fp64_optimization(s.y + t.x);
  s = quickTwoSum(s.x, s.y);
  s.y = prevent_fp64_optimization(s.y + t.y);
  s = quickTwoSum(s.x, s.y);
  return s;
}

fn mul_fp64(a: vec2f, b: vec2f) -> vec2f {
  var prod = twoProd(a.x, b.x);
  let crossProduct1 = prevent_fp64_optimization(a.x * b.y);
  prod.y = prevent_fp64_optimization(prod.y + crossProduct1);
#ifdef LUMA_FP64_HIGH_BITS_OVERFLOW_WORKAROUND
  prod = split2(prod);
#endif
  prod = quickTwoSum(prod.x, prod.y);
  let crossProduct2 = prevent_fp64_optimization(a.y * b.x);
  prod.y = prevent_fp64_optimization(prod.y + crossProduct2);
#ifdef LUMA_FP64_HIGH_BITS_OVERFLOW_WORKAROUND
  prod = split2(prod);
#endif
  prod = quickTwoSum(prod.x, prod.y);
  return prod;
}

fn div_fp64(a: vec2f, b: vec2f) -> vec2f {
  let xn = prevent_fp64_optimization(1.0 / b.x);
  let yn = mul_fp64(a, vec2f(xn, fp64_runtime_zero()));
  let diff = prevent_fp64_optimization(sub_fp64(a, mul_fp64(b, yn)).x);
  let prod = twoProd(xn, diff);
  return sum_fp64(yn, prod);
}

fn sqrt_fp64(a: vec2f) -> vec2f {
  if (a.x == 0.0 && a.y == 0.0) {
    return vec2f(0.0, 0.0);
  }
  if (a.x < 0.0) {
    let nanValue = fp64_nan(a.x);
    return vec2f(nanValue, nanValue);
  }

  let x = prevent_fp64_optimization(1.0 / sqrt(a.x));
  let yn = prevent_fp64_optimization(a.x * x);
#ifdef LUMA_FP64_CODE_ELIMINATION_WORKAROUND
  let ynSqr = twoSqr(yn) * fp64arithmetic.ONE;
#else
  let ynSqr = twoSqr(yn);
#endif
  let diff = prevent_fp64_optimization(sub_fp64(a, ynSqr).x);
  let prod = twoProd(prevent_fp64_optimization(x * 0.5), diff);
#ifdef LUMA_FP64_HIGH_BITS_OVERFLOW_WORKAROUND
  return sum_fp64(split(yn), prod);
#else
  return sum_fp64(vec2f(yn, 0.0), prod);
#endif
}
`,Ze=`const vec2 E_FP64 = vec2(2.7182817459106445e+00, 8.254840366817007e-08);
const vec2 LOG2_FP64 = vec2(0.6931471824645996e+00, -1.9046542121259336e-09);
const vec2 PI_FP64 = vec2(3.1415927410125732, -8.742278012618954e-8);
const vec2 TWO_PI_FP64 = vec2(6.2831854820251465, -1.7484556025237907e-7);
const vec2 PI_2_FP64 = vec2(1.5707963705062866, -4.371139006309477e-8);
const vec2 PI_4_FP64 = vec2(0.7853981852531433, -2.1855695031547384e-8);
const vec2 PI_16_FP64 = vec2(0.19634954631328583, -5.463923757886846e-9);
const vec2 PI_16_2_FP64 = vec2(0.39269909262657166, -1.0927847515773692e-8);
const vec2 PI_16_3_FP64 = vec2(0.5890486240386963, -1.4906100798128818e-9);
const vec2 PI_180_FP64 = vec2(0.01745329238474369, 1.3519960498364902e-10);

const vec2 SIN_TABLE_0_FP64 = vec2(0.19509032368659973, -1.6704714833615242e-9);
const vec2 SIN_TABLE_1_FP64 = vec2(0.3826834261417389, 6.22335089017767e-9);
const vec2 SIN_TABLE_2_FP64 = vec2(0.5555702447891235, -1.1769521357507529e-8);
const vec2 SIN_TABLE_3_FP64 = vec2(0.7071067690849304, 1.2101617041793133e-8);

const vec2 COS_TABLE_0_FP64 = vec2(0.9807852506637573, 2.9739473106360492e-8);
const vec2 COS_TABLE_1_FP64 = vec2(0.9238795042037964, 2.8307490351764386e-8);
const vec2 COS_TABLE_2_FP64 = vec2(0.8314695954322815, 1.6870263741530778e-8);
const vec2 COS_TABLE_3_FP64 = vec2(0.7071067690849304, 1.2101617152815436e-8);

const vec2 INVERSE_FACTORIAL_3_FP64 = vec2(1.666666716337204e-01, -4.967053879312289e-09); // 1/3!
const vec2 INVERSE_FACTORIAL_4_FP64 = vec2(4.16666679084301e-02, -1.2417634698280722e-09); // 1/4!
const vec2 INVERSE_FACTORIAL_5_FP64 = vec2(8.333333767950535e-03, -4.34617203337595e-10); // 1/5!
const vec2 INVERSE_FACTORIAL_6_FP64 = vec2(1.3888889225199819e-03, -3.3631094437103215e-11); // 1/6!
const vec2 INVERSE_FACTORIAL_7_FP64 = vec2(1.9841270113829523e-04,  -2.725596874933456e-12); // 1/7!
const vec2 INVERSE_FACTORIAL_8_FP64 = vec2(2.4801587642286904e-05, -3.406996025904184e-13); // 1/8!
const vec2 INVERSE_FACTORIAL_9_FP64 = vec2(2.75573188446287533e-06, 3.7935713937038186e-14); // 1/9!
const vec2 INVERSE_FACTORIAL_10_FP64 = vec2(2.755731998149713e-07, -7.575112367869873e-15); // 1/10!

float nint(float d) {
    if (d == floor(d)) return d;
    return floor(d + 0.5);
}

vec2 nint_fp64(vec2 a) {
    float hi = nint(a.x);
    float lo;
    vec2 tmp;
    if (hi == a.x) {
        lo = nint(a.y);
        tmp = quickTwoSum(hi, lo);
    } else {
        lo = 0.0;
        if (abs(hi - a.x) == 0.5 && a.y < 0.0) {
            hi -= 1.0;
        }
        tmp = vec2(hi, lo);
    }
    return tmp;
}

/* k_power controls how much range reduction we would like to have
Range reduction uses the following method:
assume a = k_power * r + m * log(2), k and m being integers.
Set k_power = 4 (we can choose other k to trade accuracy with performance.
we only need to calculate exp(r) and using exp(a) = 2^m * exp(r)^k_power;
*/

vec2 exp_fp64(vec2 a) {
  // We need to make sure these two numbers match
  // as bit-wise shift is not available in GLSL 1.0
  const int k_power = 4;
  const float k = 16.0;

  const float inv_k = 1.0 / k;

  if (a.x <= -88.0) return vec2(0.0, 0.0);
  if (a.x >= 88.0) return vec2(1.0 / 0.0, 1.0 / 0.0);
  if (a.x == 0.0 && a.y == 0.0) return vec2(1.0, 0.0);
  if (a.x == 1.0 && a.y == 0.0) return E_FP64;

  float m = floor(a.x / LOG2_FP64.x + 0.5);
  vec2 r = sub_fp64(a, mul_fp64(LOG2_FP64, vec2(m, 0.0))) * inv_k;
  vec2 s, t, p;

  p = mul_fp64(r, r);
  s = sum_fp64(r, p * 0.5);
  p = mul_fp64(p, r);
  t = mul_fp64(p, INVERSE_FACTORIAL_3_FP64);

  s = sum_fp64(s, t);
  p = mul_fp64(p, r);
  t = mul_fp64(p, INVERSE_FACTORIAL_4_FP64);

  s = sum_fp64(s, t);
  p = mul_fp64(p, r);
  t = mul_fp64(p, INVERSE_FACTORIAL_5_FP64);

  // s = sum_fp64(s, t);
  // p = mul_fp64(p, r);
  // t = mul_fp64(p, INVERSE_FACTORIAL_6_FP64);

  // s = sum_fp64(s, t);
  // p = mul_fp64(p, r);
  // t = mul_fp64(p, INVERSE_FACTORIAL_7_FP64);

  s = sum_fp64(s, t);


  // At this point, s = exp(r) - 1; but after following 4 recursions, we will get exp(r) ^ 512 - 1.
  for (int i = 0; i < k_power; i++) {
    s = sum_fp64(s * 2.0, mul_fp64(s, s));
  }

#if defined(NVIDIA_FP64_WORKAROUND) || defined(INTEL_FP64_WORKAROUND)
  s = sum_fp64(s, vec2(fp64.ONE, 0.0));
#else
  s = sum_fp64(s, vec2(1.0, 0.0));
#endif

  return s * pow(2.0, m);
//   return r;
}

vec2 log_fp64(vec2 a)
{
  if (a.x == 1.0 && a.y == 0.0) return vec2(0.0, 0.0);
  if (a.x <= 0.0) return vec2(0.0 / 0.0, 0.0 / 0.0);
  vec2 x = vec2(log(a.x), 0.0);
  vec2 s;
#if defined(NVIDIA_FP64_WORKAROUND) || defined(INTEL_FP64_WORKAROUND)
  s = vec2(fp64.ONE, 0.0);
#else
  s = vec2(1.0, 0.0);
#endif

  x = sub_fp64(sum_fp64(x, mul_fp64(a, exp_fp64(-x))), s);
  return x;
}

vec2 sin_taylor_fp64(vec2 a) {
  vec2 r, s, t, x;

  if (a.x == 0.0 && a.y == 0.0) {
    return vec2(0.0, 0.0);
  }

  x = -mul_fp64(a, a);
  s = a;
  r = a;

  r = mul_fp64(r, x);
  t = mul_fp64(r, INVERSE_FACTORIAL_3_FP64);
  s = sum_fp64(s, t);

  r = mul_fp64(r, x);
  t = mul_fp64(r, INVERSE_FACTORIAL_5_FP64);
  s = sum_fp64(s, t);

  /* keep the following commented code in case we need them
  for extra accuracy from the Taylor expansion*/

  // r = mul_fp64(r, x);
  // t = mul_fp64(r, INVERSE_FACTORIAL_7_FP64);
  // s = sum_fp64(s, t);

  // r = mul_fp64(r, x);
  // t = mul_fp64(r, INVERSE_FACTORIAL_9_FP64);
  // s = sum_fp64(s, t);

  return s;
}

vec2 cos_taylor_fp64(vec2 a) {
  vec2 r, s, t, x;

  if (a.x == 0.0 && a.y == 0.0) {
    return vec2(1.0, 0.0);
  }

  x = -mul_fp64(a, a);
  r = x;
  s = sum_fp64(vec2(1.0, 0.0), r * 0.5);

  r = mul_fp64(r, x);
  t = mul_fp64(r, INVERSE_FACTORIAL_4_FP64);
  s = sum_fp64(s, t);

  r = mul_fp64(r, x);
  t = mul_fp64(r, INVERSE_FACTORIAL_6_FP64);
  s = sum_fp64(s, t);

  /* keep the following commented code in case we need them
  for extra accuracy from the Taylor expansion*/

  // r = mul_fp64(r, x);
  // t = mul_fp64(r, INVERSE_FACTORIAL_8_FP64);
  // s = sum_fp64(s, t);

  // r = mul_fp64(r, x);
  // t = mul_fp64(r, INVERSE_FACTORIAL_10_FP64);
  // s = sum_fp64(s, t);

  return s;
}

void sincos_taylor_fp64(vec2 a, out vec2 sin_t, out vec2 cos_t) {
  if (a.x == 0.0 && a.y == 0.0) {
    sin_t = vec2(0.0, 0.0);
    cos_t = vec2(1.0, 0.0);
  }

  sin_t = sin_taylor_fp64(a);
  cos_t = sqrt_fp64(sub_fp64(vec2(1.0, 0.0), mul_fp64(sin_t, sin_t)));
}

vec2 sin_fp64(vec2 a) {
    if (a.x == 0.0 && a.y == 0.0) {
        return vec2(0.0, 0.0);
    }

    // 2pi range reduction
    vec2 z = nint_fp64(div_fp64(a, TWO_PI_FP64));
    vec2 r = sub_fp64(a, mul_fp64(TWO_PI_FP64, z));

    vec2 t;
    float q = floor(r.x / PI_2_FP64.x + 0.5);
    int j = int(q);

    if (j < -2 || j > 2) {
        return vec2(0.0 / 0.0, 0.0 / 0.0);
    }

    t = sub_fp64(r, mul_fp64(PI_2_FP64, vec2(q, 0.0)));

    q = floor(t.x / PI_16_FP64.x + 0.5);
    int k = int(q);

    if (k == 0) {
        if (j == 0) {
            return sin_taylor_fp64(t);
        } else if (j == 1) {
            return cos_taylor_fp64(t);
        } else if (j == -1) {
            return -cos_taylor_fp64(t);
        } else {
            return -sin_taylor_fp64(t);
        }
    }

    int abs_k = int(abs(float(k)));

    if (abs_k > 4) {
        return vec2(0.0 / 0.0, 0.0 / 0.0);
    } else {
        t = sub_fp64(t, mul_fp64(PI_16_FP64, vec2(q, 0.0)));
    }

    vec2 u = vec2(0.0, 0.0);
    vec2 v = vec2(0.0, 0.0);

#if defined(NVIDIA_FP64_WORKAROUND) || defined(INTEL_FP64_WORKAROUND)
    if (abs(float(abs_k) - 1.0) < 0.5) {
        u = COS_TABLE_0_FP64;
        v = SIN_TABLE_0_FP64;
    } else if (abs(float(abs_k) - 2.0) < 0.5) {
        u = COS_TABLE_1_FP64;
        v = SIN_TABLE_1_FP64;
    } else if (abs(float(abs_k) - 3.0) < 0.5) {
        u = COS_TABLE_2_FP64;
        v = SIN_TABLE_2_FP64;
    } else if (abs(float(abs_k) - 4.0) < 0.5) {
        u = COS_TABLE_3_FP64;
        v = SIN_TABLE_3_FP64;
    }
#else
    if (abs_k == 1) {
        u = COS_TABLE_0_FP64;
        v = SIN_TABLE_0_FP64;
    } else if (abs_k == 2) {
        u = COS_TABLE_1_FP64;
        v = SIN_TABLE_1_FP64;
    } else if (abs_k == 3) {
        u = COS_TABLE_2_FP64;
        v = SIN_TABLE_2_FP64;
    } else if (abs_k == 4) {
        u = COS_TABLE_3_FP64;
        v = SIN_TABLE_3_FP64;
    }
#endif

    vec2 sin_t, cos_t;
    sincos_taylor_fp64(t, sin_t, cos_t);



    vec2 result = vec2(0.0, 0.0);
    if (j == 0) {
        if (k > 0) {
            result = sum_fp64(mul_fp64(u, sin_t), mul_fp64(v, cos_t));
        } else {
            result = sub_fp64(mul_fp64(u, sin_t), mul_fp64(v, cos_t));
        }
    } else if (j == 1) {
        if (k > 0) {
            result = sub_fp64(mul_fp64(u, cos_t), mul_fp64(v, sin_t));
        } else {
            result = sum_fp64(mul_fp64(u, cos_t), mul_fp64(v, sin_t));
        }
    } else if (j == -1) {
        if (k > 0) {
            result = sub_fp64(mul_fp64(v, sin_t), mul_fp64(u, cos_t));
        } else {
            result = -sum_fp64(mul_fp64(v, sin_t), mul_fp64(u, cos_t));
        }
    } else {
        if (k > 0) {
            result = -sum_fp64(mul_fp64(u, sin_t), mul_fp64(v, cos_t));
        } else {
            result = sub_fp64(mul_fp64(v, cos_t), mul_fp64(u, sin_t));
        }
    }

    return result;
}

vec2 cos_fp64(vec2 a) {
    if (a.x == 0.0 && a.y == 0.0) {
        return vec2(1.0, 0.0);
    }

    // 2pi range reduction
    vec2 z = nint_fp64(div_fp64(a, TWO_PI_FP64));
    vec2 r = sub_fp64(a, mul_fp64(TWO_PI_FP64, z));

    vec2 t;
    float q = floor(r.x / PI_2_FP64.x + 0.5);
    int j = int(q);

    if (j < -2 || j > 2) {
        return vec2(0.0 / 0.0, 0.0 / 0.0);
    }

    t = sub_fp64(r, mul_fp64(PI_2_FP64, vec2(q, 0.0)));

    q = floor(t.x / PI_16_FP64.x + 0.5);
    int k = int(q);

    if (k == 0) {
        if (j == 0) {
            return cos_taylor_fp64(t);
        } else if (j == 1) {
            return -sin_taylor_fp64(t);
        } else if (j == -1) {
            return sin_taylor_fp64(t);
        } else {
            return -cos_taylor_fp64(t);
        }
    }

    int abs_k = int(abs(float(k)));

    if (abs_k > 4) {
        return vec2(0.0 / 0.0, 0.0 / 0.0);
    } else {
        t = sub_fp64(t, mul_fp64(PI_16_FP64, vec2(q, 0.0)));
    }

    vec2 u = vec2(0.0, 0.0);
    vec2 v = vec2(0.0, 0.0);

#if defined(NVIDIA_FP64_WORKAROUND) || defined(INTEL_FP64_WORKAROUND)
    if (abs(float(abs_k) - 1.0) < 0.5) {
        u = COS_TABLE_0_FP64;
        v = SIN_TABLE_0_FP64;
    } else if (abs(float(abs_k) - 2.0) < 0.5) {
        u = COS_TABLE_1_FP64;
        v = SIN_TABLE_1_FP64;
    } else if (abs(float(abs_k) - 3.0) < 0.5) {
        u = COS_TABLE_2_FP64;
        v = SIN_TABLE_2_FP64;
    } else if (abs(float(abs_k) - 4.0) < 0.5) {
        u = COS_TABLE_3_FP64;
        v = SIN_TABLE_3_FP64;
    }
#else
    if (abs_k == 1) {
        u = COS_TABLE_0_FP64;
        v = SIN_TABLE_0_FP64;
    } else if (abs_k == 2) {
        u = COS_TABLE_1_FP64;
        v = SIN_TABLE_1_FP64;
    } else if (abs_k == 3) {
        u = COS_TABLE_2_FP64;
        v = SIN_TABLE_2_FP64;
    } else if (abs_k == 4) {
        u = COS_TABLE_3_FP64;
        v = SIN_TABLE_3_FP64;
    }
#endif

    vec2 sin_t, cos_t;
    sincos_taylor_fp64(t, sin_t, cos_t);

    vec2 result = vec2(0.0, 0.0);
    if (j == 0) {
        if (k > 0) {
            result = sub_fp64(mul_fp64(u, cos_t), mul_fp64(v, sin_t));
        } else {
            result = sum_fp64(mul_fp64(u, cos_t), mul_fp64(v, sin_t));
        }
    } else if (j == 1) {
        if (k > 0) {
            result = -sum_fp64(mul_fp64(u, sin_t), mul_fp64(v, cos_t));
        } else {
            result = sub_fp64(mul_fp64(v, cos_t), mul_fp64(u, sin_t));
        }
    } else if (j == -1) {
        if (k > 0) {
            result = sum_fp64(mul_fp64(u, sin_t), mul_fp64(v, cos_t));
        } else {
            result = sub_fp64(mul_fp64(u, sin_t), mul_fp64(v, cos_t));
        }
    } else {
        if (k > 0) {
            result = sub_fp64(mul_fp64(v, sin_t), mul_fp64(u, cos_t));
        } else {
            result = -sum_fp64(mul_fp64(u, cos_t), mul_fp64(v, sin_t));
        }
    }

    return result;
}

vec2 tan_fp64(vec2 a) {
    vec2 sin_a;
    vec2 cos_a;

    if (a.x == 0.0 && a.y == 0.0) {
        return vec2(0.0, 0.0);
    }

    // 2pi range reduction
    vec2 z = nint_fp64(div_fp64(a, TWO_PI_FP64));
    vec2 r = sub_fp64(a, mul_fp64(TWO_PI_FP64, z));

    vec2 t;
    float q = floor(r.x / PI_2_FP64.x + 0.5);
    int j = int(q);


    if (j < -2 || j > 2) {
        return vec2(0.0 / 0.0, 0.0 / 0.0);
    }

    t = sub_fp64(r, mul_fp64(PI_2_FP64, vec2(q, 0.0)));

    q = floor(t.x / PI_16_FP64.x + 0.5);
    int k = int(q);
    int abs_k = int(abs(float(k)));

    // We just can't get PI/16 * 3.0 very accurately.
    // so let's just store it
    if (abs_k > 4) {
        return vec2(0.0 / 0.0, 0.0 / 0.0);
    } else {
        t = sub_fp64(t, mul_fp64(PI_16_FP64, vec2(q, 0.0)));
    }


    vec2 u = vec2(0.0, 0.0);
    vec2 v = vec2(0.0, 0.0);

    vec2 sin_t, cos_t;
    vec2 s, c;
    sincos_taylor_fp64(t, sin_t, cos_t);

    if (k == 0) {
        s = sin_t;
        c = cos_t;
    } else {
#if defined(NVIDIA_FP64_WORKAROUND) || defined(INTEL_FP64_WORKAROUND)
        if (abs(float(abs_k) - 1.0) < 0.5) {
            u = COS_TABLE_0_FP64;
            v = SIN_TABLE_0_FP64;
        } else if (abs(float(abs_k) - 2.0) < 0.5) {
            u = COS_TABLE_1_FP64;
            v = SIN_TABLE_1_FP64;
        } else if (abs(float(abs_k) - 3.0) < 0.5) {
            u = COS_TABLE_2_FP64;
            v = SIN_TABLE_2_FP64;
        } else if (abs(float(abs_k) - 4.0) < 0.5) {
            u = COS_TABLE_3_FP64;
            v = SIN_TABLE_3_FP64;
        }
#else
        if (abs_k == 1) {
            u = COS_TABLE_0_FP64;
            v = SIN_TABLE_0_FP64;
        } else if (abs_k == 2) {
            u = COS_TABLE_1_FP64;
            v = SIN_TABLE_1_FP64;
        } else if (abs_k == 3) {
            u = COS_TABLE_2_FP64;
            v = SIN_TABLE_2_FP64;
        } else if (abs_k == 4) {
            u = COS_TABLE_3_FP64;
            v = SIN_TABLE_3_FP64;
        }
#endif
        if (k > 0) {
            s = sum_fp64(mul_fp64(u, sin_t), mul_fp64(v, cos_t));
            c = sub_fp64(mul_fp64(u, cos_t), mul_fp64(v, sin_t));
        } else {
            s = sub_fp64(mul_fp64(u, sin_t), mul_fp64(v, cos_t));
            c = sum_fp64(mul_fp64(u, cos_t), mul_fp64(v, sin_t));
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
    return div_fp64(sin_a, cos_a);
}

vec2 radians_fp64(vec2 degree) {
  return mul_fp64(degree, PI_180_FP64);
}

vec2 mix_fp64(vec2 a, vec2 b, float x) {
  vec2 range = sub_fp64(b, a);
  return sum_fp64(a, mul_fp64(range, vec2(x, 0.0)));
}

// Vector functions
// vec2 functions
void vec2_sum_fp64(vec2 a[2], vec2 b[2], out vec2 out_val[2]) {
    out_val[0] = sum_fp64(a[0], b[0]);
    out_val[1] = sum_fp64(a[1], b[1]);
}

void vec2_sub_fp64(vec2 a[2], vec2 b[2], out vec2 out_val[2]) {
    out_val[0] = sub_fp64(a[0], b[0]);
    out_val[1] = sub_fp64(a[1], b[1]);
}

void vec2_mul_fp64(vec2 a[2], vec2 b[2], out vec2 out_val[2]) {
    out_val[0] = mul_fp64(a[0], b[0]);
    out_val[1] = mul_fp64(a[1], b[1]);
}

void vec2_div_fp64(vec2 a[2], vec2 b[2], out vec2 out_val[2]) {
    out_val[0] = div_fp64(a[0], b[0]);
    out_val[1] = div_fp64(a[1], b[1]);
}

void vec2_mix_fp64(vec2 x[2], vec2 y[2], float a, out vec2 out_val[2]) {
  vec2 range[2];
  vec2_sub_fp64(y, x, range);
  vec2 portion[2];
  portion[0] = range[0] * a;
  portion[1] = range[1] * a;
  vec2_sum_fp64(x, portion, out_val);
}

vec2 vec2_length_fp64(vec2 x[2]) {
  return sqrt_fp64(sum_fp64(mul_fp64(x[0], x[0]), mul_fp64(x[1], x[1])));
}

void vec2_normalize_fp64(vec2 x[2], out vec2 out_val[2]) {
  vec2 length = vec2_length_fp64(x);
  vec2 length_vec2[2];
  length_vec2[0] = length;
  length_vec2[1] = length;

  vec2_div_fp64(x, length_vec2, out_val);
}

vec2 vec2_distance_fp64(vec2 x[2], vec2 y[2]) {
  vec2 diff[2];
  vec2_sub_fp64(x, y, diff);
  return vec2_length_fp64(diff);
}

vec2 vec2_dot_fp64(vec2 a[2], vec2 b[2]) {
  vec2 v[2];

  v[0] = mul_fp64(a[0], b[0]);
  v[1] = mul_fp64(a[1], b[1]);

  return sum_fp64(v[0], v[1]);
}

// vec3 functions
void vec3_sub_fp64(vec2 a[3], vec2 b[3], out vec2 out_val[3]) {
  for (int i = 0; i < 3; i++) {
    out_val[i] = sum_fp64(a[i], b[i]);
  }
}

void vec3_sum_fp64(vec2 a[3], vec2 b[3], out vec2 out_val[3]) {
  for (int i = 0; i < 3; i++) {
    out_val[i] = sum_fp64(a[i], b[i]);
  }
}

vec2 vec3_length_fp64(vec2 x[3]) {
  return sqrt_fp64(sum_fp64(sum_fp64(mul_fp64(x[0], x[0]), mul_fp64(x[1], x[1])),
    mul_fp64(x[2], x[2])));
}

vec2 vec3_distance_fp64(vec2 x[3], vec2 y[3]) {
  vec2 diff[3];
  vec3_sub_fp64(x, y, diff);
  return vec3_length_fp64(diff);
}

// vec4 functions
void vec4_fp64(vec4 a, out vec2 out_val[4]) {
  out_val[0].x = a[0];
  out_val[0].y = 0.0;

  out_val[1].x = a[1];
  out_val[1].y = 0.0;

  out_val[2].x = a[2];
  out_val[2].y = 0.0;

  out_val[3].x = a[3];
  out_val[3].y = 0.0;
}

void vec4_scalar_mul_fp64(vec2 a[4], vec2 b, out vec2 out_val[4]) {
  out_val[0] = mul_fp64(a[0], b);
  out_val[1] = mul_fp64(a[1], b);
  out_val[2] = mul_fp64(a[2], b);
  out_val[3] = mul_fp64(a[3], b);
}

void vec4_sum_fp64(vec2 a[4], vec2 b[4], out vec2 out_val[4]) {
  for (int i = 0; i < 4; i++) {
    out_val[i] = sum_fp64(a[i], b[i]);
  }
}

void vec4_dot_fp64(vec2 a[4], vec2 b[4], out vec2 out_val) {
  vec2 v[4];

  v[0] = mul_fp64(a[0], b[0]);
  v[1] = mul_fp64(a[1], b[1]);
  v[2] = mul_fp64(a[2], b[2]);
  v[3] = mul_fp64(a[3], b[3]);

  out_val = sum_fp64(sum_fp64(v[0], v[1]), sum_fp64(v[2], v[3]));
}

void mat4_vec4_mul_fp64(vec2 b[16], vec2 a[4], out vec2 out_val[4]) {
  vec2 tmp[4];

  for (int i = 0; i < 4; i++)
  {
    for (int j = 0; j < 4; j++)
    {
      tmp[j] = b[j + i * 4];
    }
    vec4_dot_fp64(a, tmp, out_val[i]);
  }
}
`,Qe={ONE:1,SPLIT:4097},et={name:"fp64arithmetic",source:Je,fs:se,vs:se,defaultUniforms:Qe,uniformTypes:{ONE:"f32",SPLIT:"f32"},fp64ify:Q,fp64LowPart:ve,fp64ifyMatrix4:be},qt={name:"fp64",vs:Ze,dependencies:[et],fp64ify:Q,fp64LowPart:ve,fp64ifyMatrix4:be},C=class C extends ie{constructor(t,r){super(t,r,C.defaultProps);u(this,"hash","");u(this,"shaderLayout");this.shaderLayout=r.shaderLayout}get[Symbol.toStringTag](){return"ComputePipeline"}};u(C,"defaultProps",{...ie.defaultProps,shader:void 0,entryPoint:void 0,constants:{},shaderLayout:void 0});let R=C;const $=class ${constructor(e){u(this,"device");u(this,"_hashCounter",0);u(this,"_hashes",{});u(this,"_renderPipelineCache",{});u(this,"_computePipelineCache",{});u(this,"_sharedRenderPipelineCache",{});this.device=e}static getDefaultPipelineFactory(e){const t=e.getModuleData("@luma.gl/core");return t.defaultPipelineFactory||(t.defaultPipelineFactory=new $(e)),t.defaultPipelineFactory}get[Symbol.toStringTag](){return"PipelineFactory"}toString(){return`PipelineFactory(${this.device.id})`}createRenderPipeline(e){var o;if(!this.device.props._cachePipelines)return this.device.createRenderPipeline(e);const t={...F.defaultProps,...e},r=this._renderPipelineCache,s=this._hashRenderPipeline(t);let n=(o=r[s])==null?void 0:o.resource;if(n)r[s].useCount++,this.device.props.debugFactories&&d.log(3,`${this}: ${r[s].resource} reused, count=${r[s].useCount}, (id=${e.id})`)();else{const a=this.device.type==="webgl"&&this.device.props._sharePipelines?this.createSharedRenderPipeline(t):void 0;n=this.device.createRenderPipeline({...t,id:t.id?`${t.id}-cached`:Ce("unnamed-cached"),_sharedRenderPipeline:a}),n.hash=s,r[s]={resource:n,useCount:1},this.device.props.debugFactories&&d.log(3,`${this}: ${n} created, count=${r[s].useCount}`)()}return n}createComputePipeline(e){var o;if(!this.device.props._cachePipelines)return this.device.createComputePipeline(e);const t={...R.defaultProps,...e},r=this._computePipelineCache,s=this._hashComputePipeline(t);let n=(o=r[s])==null?void 0:o.resource;return n?(r[s].useCount++,this.device.props.debugFactories&&d.log(3,`${this}: ${r[s].resource} reused, count=${r[s].useCount}, (id=${e.id})`)()):(n=this.device.createComputePipeline({...t,id:t.id?`${t.id}-cached`:void 0}),n.hash=s,r[s]={resource:n,useCount:1},this.device.props.debugFactories&&d.log(3,`${this}: ${n} created, count=${r[s].useCount}`)()),n}release(e){if(!this.device.props._cachePipelines){e.destroy();return}const t=this._getCache(e),r=e.hash;t[r].useCount--,t[r].useCount===0?(this._destroyPipeline(e),this.device.props.debugFactories&&d.log(3,`${this}: ${e} released and destroyed`)()):t[r].useCount<0?(d.error(`${this}: ${e} released, useCount < 0, resetting`)(),t[r].useCount=0):this.device.props.debugFactories&&d.log(3,`${this}: ${e} released, count=${t[r].useCount}`)()}createSharedRenderPipeline(e){const t=this._hashSharedRenderPipeline(e);let r=this._sharedRenderPipelineCache[t];return r||(r={resource:this.device._createSharedRenderPipelineWebGL(e),useCount:0},this._sharedRenderPipelineCache[t]=r),r.useCount++,r.resource}releaseSharedRenderPipeline(e){if(!e.sharedRenderPipeline)return;const t=this._hashSharedRenderPipeline(e.sharedRenderPipeline.props),r=this._sharedRenderPipelineCache[t];r&&(r.useCount--,r.useCount===0&&(r.resource.destroy(),delete this._sharedRenderPipelineCache[t]))}_destroyPipeline(e){const t=this._getCache(e);return this.device.props._destroyPipelines?(delete t[e.hash],e.destroy(),e instanceof F&&this.releaseSharedRenderPipeline(e),!0):!1}_getCache(e){let t;if(e instanceof R&&(t=this._computePipelineCache),e instanceof F&&(t=this._renderPipelineCache),!t)throw new Error(`${this}`);if(!t[e.hash])throw new Error(`${this}: ${e} matched incorrect entry`);return t}_hashComputePipeline(e){const{type:t}=this.device,r=this._getHash(e.shader.source),s=this._getHash(JSON.stringify(e.shaderLayout));return`${t}/C/${r}SL${s}`}_hashRenderPipeline(e){const t=e.vs?this._getHash(e.vs.source):0,r=e.fs?this._getHash(e.fs.source):0,s=this._getWebGLVaryingHash(e),n=this._getHash(JSON.stringify(e.shaderLayout)),o=this._getHash(JSON.stringify(e.bufferLayout)),{type:a}=this.device;switch(a){case"webgl":const f=this._getHash(JSON.stringify(e.parameters));return`${a}/R/${t}/${r}V${s}T${e.topology}P${f}SL${n}BL${o}`;case"webgpu":default:const c=this._getHash(JSON.stringify({vertexEntryPoint:e.vertexEntryPoint,fragmentEntryPoint:e.fragmentEntryPoint})),l=this._getHash(JSON.stringify(e.parameters)),h=this._getWebGPUAttachmentHash(e);return`${a}/R/${t}/${r}V${s}T${e.topology}EP${c}P${l}SL${n}BL${o}A${h}`}}_hashSharedRenderPipeline(e){const t=e.vs?this._getHash(e.vs.source):0,r=e.fs?this._getHash(e.fs.source):0,s=this._getWebGLVaryingHash(e);return`webgl/S/${t}/${r}V${s}`}_getHash(e){return this._hashes[e]===void 0&&(this._hashes[e]=this._hashCounter++),this._hashes[e]}_getWebGLVaryingHash(e){const{varyings:t=[],bufferMode:r=null}=e;return this._getHash(JSON.stringify({varyings:t,bufferMode:r}))}_getWebGPUAttachmentHash(e){var s;const t=e.colorAttachmentFormats??[this.device.preferredColorFormat],r=(s=e.parameters)!=null&&s.depthWriteEnabled?e.depthStencilAttachmentFormat||this.device.preferredDepthFormat:null;return this._getHash(JSON.stringify({colorAttachmentFormats:t,depthStencilAttachmentFormat:r}))}};u($,"defaultProps",{...F.defaultProps});let G=$;const D=class D{constructor(e){u(this,"device");u(this,"_cache",{});this.device=e}static getDefaultShaderFactory(e){const t=e.getModuleData("@luma.gl/core");return t.defaultShaderFactory||(t.defaultShaderFactory=new D(e)),t.defaultShaderFactory}get[Symbol.toStringTag](){return"ShaderFactory"}toString(){return`${this[Symbol.toStringTag]}(${this.device.id})`}createShader(e){if(!this.device.props._cacheShaders)return this.device.createShader(e);const t=this._hashShader(e);let r=this._cache[t];if(r)r.useCount++,this.device.props.debugFactories&&d.log(3,`${this}: Reusing shader ${r.resource.id} count=${r.useCount}`)();else{const s=this.device.createShader({...e,id:e.id?`${e.id}-cached`:void 0});this._cache[t]=r={resource:s,useCount:1},this.device.props.debugFactories&&d.log(3,`${this}: Created new shader ${s.id}`)()}return r.resource}release(e){if(!this.device.props._cacheShaders){e.destroy();return}const t=this._hashShader(e),r=this._cache[t];if(r)if(r.useCount--,r.useCount===0)this.device.props._destroyShaders&&(delete this._cache[t],r.resource.destroy(),this.device.props.debugFactories&&d.log(3,`${this}: Releasing shader ${e.id}, destroyed`)());else{if(r.useCount<0)throw new Error(`ShaderFactory: Shader ${e.id} released too many times`);this.device.props.debugFactories&&d.log(3,`${this}: Releasing shader ${e.id} count=${r.useCount}`)()}}_hashShader(e){return`${e.stage}:${e.source}`}};u(D,"defaultProps",{...ze.defaultProps});let H=D;function tt(i,e={}){const t={...i},r=e.layout??"std140",s={};let n=0;for(const[o,a]of Object.entries(t))n=q(s,o,a,n,r);return n=x(n,w(t,r)),{layout:r,byteLength:n*4,uniformTypes:t,fields:s}}function M(i,e){const t=We(i),r=je(t),s=/^mat(\d)x(\d)<.+>$/.exec(t);if(s){const o=Number(s[1]),a=Number(s[2]),f=ne(a,t,r.type),c=it(f.size,f.alignment,e);return{alignment:f.alignment,size:o*c,components:o*a,columns:o,rows:a,columnStride:c,shaderType:t,type:r.type}}const n=/^vec(\d)<.+>$/.exec(t);return n?ne(Number(n[1]),t,r.type):{alignment:1,size:1,components:1,columns:1,rows:1,columnStride:1,shaderType:t,type:r.type}}function ye(i){return!!i&&typeof i=="object"&&!Array.isArray(i)}function q(i,e,t,r,s){if(typeof t=="string"){const n=M(t,s),o=x(r,n.alignment);return i[e]={offset:o,...n},o+n.size}if(Array.isArray(t)){if(Array.isArray(t[0]))throw new Error(`Nested arrays are not supported for ${e}`);const n=t[0],o=t[1],a=xe(n,s),f=x(r,w(t,s));for(let c=0;c<o;c++)q(i,`${e}[${c}]`,n,f+c*a,s);return f+a*o}if(ye(t)){const n=w(t,s);let o=x(r,n);for(const[a,f]of Object.entries(t))o=q(i,`${e}.${a}`,f,o,s);return x(o,n)}throw new Error(`Unsupported CompositeShaderType for ${e}`)}function ge(i,e){if(typeof i=="string")return M(i,e).size;if(Array.isArray(i)){const r=i[0],s=i[1];if(Array.isArray(r))throw new Error("Nested arrays are not supported");return xe(r,e)*s}let t=0;for(const r of Object.values(i)){const s=r;t=x(t,w(s,e)),t+=ge(s,e)}return x(t,w(i,e))}function w(i,e){if(typeof i=="string")return M(i,e).alignment;if(Array.isArray(i)){const r=i[0],s=w(r,e);return Ae(e)?Math.max(s,4):s}let t=1;for(const r of Object.values(i)){const s=w(r,e);t=Math.max(t,s)}return st(e)?Math.max(t,4):t}function ne(i,e,t,r){return{alignment:i===2?2:4,size:i===3?3:i,components:i,columns:1,rows:i,columnStride:i===3?3:i,shaderType:e,type:t}}function xe(i,e){const t=ge(i,e),r=w(i,e);return rt(t,r,e)}function rt(i,e,t){return x(i,Ae(t)?4:e)}function it(i,e,t){return t==="std140"?4:x(i,e)}function Ae(i){return i==="std140"||i==="wgsl-uniform"}function st(i){return i==="std140"||i==="wgsl-uniform"}function nt(i){return ArrayBuffer.isView(i)&&!(i instanceof DataView)}function B(i){return Array.isArray(i)?i.length===0||typeof i[0]=="number":nt(i)}class ot{constructor(e){u(this,"layout");this.layout=e}has(e){return!!this.layout.fields[e]}get(e){const t=this.layout.fields[e];return t?{offset:t.offset,size:t.size}:void 0}getFlatUniformValues(e){const t={};for(const[r,s]of Object.entries(e)){const n=this.layout.uniformTypes[r];n?this._flattenCompositeValue(t,r,n,s):this.layout.fields[r]&&(t[r]=s)}return t}getData(e){const t=Ve(this.layout.byteLength);new Uint8Array(t,0,this.layout.byteLength).fill(0);const r={i32:new Int32Array(t),u32:new Uint32Array(t),f32:new Float32Array(t),f16:new Uint16Array(t)},s=this.getFlatUniformValues(e);for(const[n,o]of Object.entries(s))this._writeLeafValue(r,n,o);return new Uint8Array(t,0,this.layout.byteLength)}_flattenCompositeValue(e,t,r,s){if(s!==void 0){if(typeof r=="string"||this.layout.fields[t]){e[t]=s;return}if(Array.isArray(r)){const n=r[0],o=r[1];if(Array.isArray(n))throw new Error(`Nested arrays are not supported for ${t}`);if(typeof n=="string"&&B(s)){this._flattenPackedArray(e,t,n,o,s);return}if(!Array.isArray(s)){d.warn(`Unsupported uniform array value for ${t}:`,s)();return}for(let a=0;a<Math.min(s.length,o);a++){const f=s[a];f!==void 0&&this._flattenCompositeValue(e,`${t}[${a}]`,n,f)}return}if(ye(r)&&at(s)){for(const[n,o]of Object.entries(s)){if(o===void 0)continue;const a=`${t}.${n}`;this._flattenCompositeValue(e,a,r[n],o)}return}d.warn(`Unsupported uniform value for ${t}:`,s)()}}_flattenPackedArray(e,t,r,s,n){const o=n,f=M(r,this.layout.layout).components;for(let c=0;c<s;c++){const l=c*f;if(l>=o.length)break;f===1?e[`${t}[${c}]`]=Number(o[l]):e[`${t}[${c}]`]=ut(n,l,l+f)}}_writeLeafValue(e,t,r){const s=this.layout.fields[t];if(!s){d.warn(`Uniform ${t} not found in layout`)();return}const{type:n,components:o,columns:a,rows:f,offset:c,columnStride:l}=s,h=e[n];if(o===1){h[c]=Number(r);return}const _=r;if(a===1){for(let p=0;p<o;p++)h[c+p]=Number(_[p]??0);return}let m=0;for(let p=0;p<a;p++){const v=c+p*l;for(let O=0;O<f;O++)h[v+O]=Number(_[m++]??0)}}}function at(i){return!!i&&typeof i=="object"&&!Array.isArray(i)&&!ArrayBuffer.isView(i)}function ut(i,e,t){return Array.prototype.slice.call(i,e,t)}const ft=128;function ct(i,e,t=16){if(i===e)return!0;const r=i,s=e;if(!B(r)||!B(s)||r.length!==s.length)return!1;const n=Math.min(t,ft);if(r.length>n)return!1;for(let o=0;o<r.length;++o)if(s[o]!==r[o])return!1;return!0}function lt(i){return B(i)?i.slice():i}class dt{constructor(e){u(this,"name");u(this,"uniforms",{});u(this,"modifiedUniforms",{});u(this,"modified",!0);u(this,"bindingLayout",{});u(this,"needsRedraw","initialized");var t;if(this.name=(e==null?void 0:e.name)||"unnamed",e!=null&&e.name&&(e!=null&&e.shaderLayout)){const r=(t=e==null?void 0:e.shaderLayout.bindings)==null?void 0:t.find(n=>n.type==="uniform"&&n.name===(e==null?void 0:e.name));if(!r)throw new Error(e==null?void 0:e.name);const s=r;for(const n of s.uniforms||[])this.bindingLayout[n.name]=n}}setUniforms(e){for(const[t,r]of Object.entries(e))this._setUniform(t,r),this.needsRedraw||this.setNeedsRedraw(`${this.name}.${t}=${r}`)}setNeedsRedraw(e){this.needsRedraw=this.needsRedraw||e}getAllUniforms(){return this.modifiedUniforms={},this.needsRedraw=!1,this.uniforms||{}}_setUniform(e,t){ct(this.uniforms[e],t)||(this.uniforms[e]=lt(t),this.modifiedUniforms[e]=!0,this.modified=!0)}}const ht=1024;class pt{constructor(e,t){u(this,"device");u(this,"uniformBlocks",new Map);u(this,"shaderBlockLayouts",new Map);u(this,"shaderBlockWriters",new Map);u(this,"uniformBuffers",new Map);this.device=e;for(const[r,s]of Object.entries(t)){const n=r,o=tt(s.uniformTypes??{},{layout:s.layout??_t(e)}),a=new ot(o);this.shaderBlockLayouts.set(n,o),this.shaderBlockWriters.set(n,a);const f=new dt({name:r});f.setUniforms(a.getFlatUniformValues(s.defaultUniforms||{})),this.uniformBlocks.set(n,f)}}destroy(){for(const e of this.uniformBuffers.values())e.destroy()}setUniforms(e){var t;for(const[r,s]of Object.entries(e)){const n=r,o=this.shaderBlockWriters.get(n),a=o==null?void 0:o.getFlatUniformValues(s||{});(t=this.uniformBlocks.get(n))==null||t.setUniforms(a||{})}this.updateUniformBuffers()}getUniformBufferByteLength(e){var r;const t=((r=this.shaderBlockLayouts.get(e))==null?void 0:r.byteLength)||0;return Math.max(t,ht)}getUniformBufferData(e){var s;const t=((s=this.uniformBlocks.get(e))==null?void 0:s.getAllUniforms())||{},r=this.shaderBlockWriters.get(e);return(r==null?void 0:r.getData(t))||new Uint8Array(0)}createUniformBuffer(e,t){t&&this.setUniforms(t);const r=this.getUniformBufferByteLength(e),s=this.device.createBuffer({usage:y.UNIFORM|y.COPY_DST,byteLength:r}),n=this.getUniformBufferData(e);return s.write(n),s}getManagedUniformBuffer(e){if(!this.uniformBuffers.get(e)){const t=this.getUniformBufferByteLength(e),r=this.device.createBuffer({usage:y.UNIFORM|y.COPY_DST,byteLength:t});this.uniformBuffers.set(e,r)}return this.uniformBuffers.get(e)}updateUniformBuffers(){let e=!1;for(const t of this.uniformBlocks.keys()){const r=this.updateUniformBuffer(t);e||(e=r)}return e&&d.log(3,`UniformStore.updateUniformBuffers(): ${e}`)(),e}updateUniformBuffer(e){var n;const t=this.uniformBlocks.get(e);let r=this.uniformBuffers.get(e),s=!1;if(r&&(t!=null&&t.needsRedraw)){s||(s=t.needsRedraw);const o=this.getUniformBufferData(e);r=this.uniformBuffers.get(e),r==null||r.write(o);const a=(n=this.uniformBlocks.get(e))==null?void 0:n.getAllUniforms();d.log(4,`Writing to uniform buffer ${String(e)}`,o,a)()}return s}}function _t(i){return i.type==="webgpu"?"wgsl-uniform":"std140"}const j={};function ee(i="id"){j[i]=j[i]||1;const e=j[i]++;return`${i}-${e}`}class oe{constructor(e){u(this,"id");u(this,"userData",{});u(this,"topology");u(this,"bufferLayout",[]);u(this,"vertexCount");u(this,"indices");u(this,"attributes");if(this.id=e.id||ee("geometry"),this.topology=e.topology,this.indices=e.indices||null,this.attributes=e.attributes,this.vertexCount=e.vertexCount,this.bufferLayout=e.bufferLayout||[],this.indices&&!(this.indices.usage&y.INDEX))throw new Error("Index buffer must have INDEX usage")}destroy(){var e;(e=this.indices)==null||e.destroy();for(const t of Object.values(this.attributes))t.destroy()}getVertexCount(){return this.vertexCount}getAttributes(){return this.attributes}getIndexes(){return this.indices||null}_calculateVertexCount(e){return e.byteLength/12}}function mt(i,e){if(e instanceof oe)return e;const t=vt(i,e),{attributes:r,bufferLayout:s}=bt(i,e);return new oe({topology:e.topology||"triangle-list",bufferLayout:s,vertexCount:e.vertexCount,indices:t,attributes:r})}function vt(i,e){if(!e.indices)return;const t=e.indices.value;return i.createBuffer({usage:y.INDEX,data:t})}function bt(i,e){const t=[],r={};for(const[n,o]of Object.entries(e.attributes)){let a=n;switch(n){case"POSITION":a="positions";break;case"NORMAL":a="normals";break;case"TEXCOORD_0":a="texCoords";break;case"TEXCOORD_1":a="texCoords1";break;case"COLOR_0":a="colors";break}if(o){r[a]=i.createBuffer({data:o.value,id:`${n}-buffer`});const{value:f,size:c,normalized:l}=o;if(c===void 0)throw new Error(`Attribute ${n} is missing a size`);t.push({name:a,format:$e.getVertexFormatFromAttribute(f,c,l)})}}const s=e._calculateVertexCount(e.attributes,e.indices);return{attributes:r,bufferLayout:t,vertexCount:s}}function yt(i,e){var s;const t={},r="Values";if(i.attributes.length===0&&!((s=i.varyings)!=null&&s.length))return{"No attributes or varyings":{[r]:"N/A"}};for(const n of i.attributes)if(n){const o=`${n.location} ${n.name}: ${n.type}`;t[`in ${o}`]={[r]:n.stepMode||"vertex"}}for(const n of i.varyings||[]){const o=`${n.location} ${n.name}`;t[`out ${o}`]={[r]:JSON.stringify(n)}}return t}const T="__debugFramebufferState",W=8;function gt(i,e,t){if(i.device.type!=="webgl")return;const r=wt(i.device);if(!r.flushing){if(Pt(i)){xt(i,t,r);return}e&&Ot(e)&&e.handle!==null&&(r.queuedFramebuffers.includes(e)||r.queuedFramebuffers.push(e))}}function xt(i,e,t){if(t.queuedFramebuffers.length===0)return;const r=i.device,{gl:s}=r,n=s.getParameter(36010),o=s.getParameter(36006),[a,f]=i.device.getDefaultCanvasContext().getDrawingBufferSize();let c=ae(e.top,W);const l=ae(e.left,W);t.flushing=!0;try{for(const h of t.queuedFramebuffers){const[_,m,p,v,O]=At({framebuffer:h,targetWidth:a,targetHeight:f,topPx:c,leftPx:l,minimap:e.minimap});s.bindFramebuffer(36008,h.handle),s.bindFramebuffer(36009,null),s.blitFramebuffer(0,0,h.width,h.height,_,m,p,v,16384,9728),c+=O+W}}finally{s.bindFramebuffer(36008,n),s.bindFramebuffer(36009,o),t.flushing=!1}}function At(i){const{framebuffer:e,targetWidth:t,targetHeight:r,topPx:s,leftPx:n}=i,o=Math.max(Math.floor(t/4),1),a=Math.max(Math.floor(r/4),1),f=Math.min(o/e.width,a/e.height),c=Math.max(Math.floor(e.width*f),1),l=Math.max(Math.floor(e.height*f),1),h=n,_=Math.max(r-s-l,0),m=h+c,p=_+l;return[h,_,m,p,l]}function wt(i){var e;return(e=i.userData)[T]||(e[T]={flushing:!1,queuedFramebuffers:[]}),i.userData[T]}function Ot(i){return"colorAttachments"in i}function Pt(i){const e=i.props.framebuffer;return!e||e.handle===null}function ae(i,e){if(!i)return e;const t=Number.parseInt(i,10);return Number.isFinite(t)?t:e}function K(i,e,t){if(i===e)return!0;if(!t||!i||!e)return!1;if(Array.isArray(i)){if(!Array.isArray(e)||i.length!==e.length)return!1;for(let r=0;r<i.length;r++)if(!K(i[r],e[r],t-1))return!1;return!0}if(Array.isArray(e))return!1;if(typeof i=="object"&&typeof e=="object"){const r=Object.keys(i),s=Object.keys(e);if(r.length!==s.length)return!1;for(const n of r)if(!e.hasOwnProperty(n)||!K(i[n],e[n],t-1))return!1;return!0}return!1}class V{constructor(e){u(this,"bufferLayouts");this.bufferLayouts=e}getBufferLayout(e){return this.bufferLayouts.find(t=>t.name===e)||null}getAttributeNamesForBuffer(e){var t;return e.attributes?(t=e.attributes)==null?void 0:t.map(r=>r.attribute):[e.name]}mergeBufferLayouts(e,t){const r=[...e];for(const s of t){const n=r.findIndex(o=>o.name===s.name);n<0?r.push(s):r[n]=s}return r}getBufferIndex(e){const t=this.bufferLayouts.findIndex(r=>r.name===e);return t===-1&&d.warn(`BufferLayout: Missing buffer for "${e}".`)(),t}}function ue(i,e){let t=1/0;for(const r of i){const s=e[r];s!==void 0&&(t=Math.min(t,s))}return t}function Lt(i,e){const t=Object.fromEntries(i.attributes.map(s=>[s.name,s.location])),r=e.slice();return r.sort((s,n)=>{const o=s.attributes?s.attributes.map(l=>l.attribute):[s.name],a=n.attributes?n.attributes.map(l=>l.attribute):[n.name],f=ue(o,t),c=ue(a,t);return f-c}),r}function fe(i,e){if(!i||!e.some(r=>{var s;return(s=r.bindingLayout)==null?void 0:s.length}))return i;const t={...i,bindings:i.bindings.map(r=>({...r}))};"attributes"in(i||{})&&(t.attributes=(i==null?void 0:i.attributes)||[]);for(const r of e)for(const s of r.bindingLayout||[])for(const n of It(s.name)){const o=t.bindings.find(a=>a.name===n);(o==null?void 0:o.group)===0&&(o.group=s.group)}return t}function Et(i){return!!(i.uniformTypes&&!St(i.uniformTypes))}function It(i){const e=new Set([i,`${i}Uniforms`]);return i.endsWith("Uniforms")||e.add(`${i}Sampler`),[...e]}function St(i){for(const e in i)return!1;return!0}function Ft(i){return Xe(i)||typeof i=="number"||typeof i=="boolean"}function Nt(i,e={}){const t={bindings:{},uniforms:{}};return Object.keys(i).forEach(r=>{const s=i[r];Object.prototype.hasOwnProperty.call(e,r)||Ft(s)?t.uniforms[r]=s:t.bindings[r]=s}),t}class Tt{constructor(e,t){u(this,"options",{disableWarnings:!1});u(this,"modules");u(this,"moduleUniforms");u(this,"moduleBindings");Object.assign(this.options,t);const r=De(Object.values(e).filter(Rt));for(const s of r)e[s.name]=s;d.log(1,"Creating ShaderInputs with modules",Object.keys(e))(),this.modules=e,this.moduleUniforms={},this.moduleBindings={};for(const[s,n]of Object.entries(e))n&&(this._addModule(n),n.name&&s!==n.name&&!this.options.disableWarnings&&d.warn(`Module name: ${s} vs ${n.name}`)())}destroy(){}setProps(e){var t;for(const r of Object.keys(e)){const s=r,n=e[s]||{},o=this.modules[s];if(!o)this.options.disableWarnings||d.warn(`Module ${r} not found`)();else{const a=this.moduleUniforms[s],f=this.moduleBindings[s],c=((t=o.getUniforms)==null?void 0:t.call(o,n,a))||n,{uniforms:l,bindings:h}=Nt(c,o.uniformTypes);this.moduleUniforms[s]=ce(a,l,o.uniformTypes),this.moduleBindings[s]={...f,...h}}}}getModules(){return Object.values(this.modules)}getUniformValues(){return this.moduleUniforms}getBindingValues(){const e={};for(const t of Object.values(this.moduleBindings))Object.assign(e,t);return e}getDebugTable(){var t;const e={};for(const[r,s]of Object.entries(this.moduleUniforms))for(const[n,o]of Object.entries(s))e[`${r}.${n}`]={type:(t=this.modules[r].uniformTypes)==null?void 0:t[n],value:String(o)};return e}_addModule(e){const t=e.name;this.moduleUniforms[t]=ce({},e.defaultUniforms||{},e.uniformTypes),this.moduleBindings[t]={}}}function ce(i={},e={},t={}){const r={...i};for(const[s,n]of Object.entries(e))n!==void 0&&(r[s]=Y(i[s],n,t[s]));return r}function Y(i,e,t){if(!t||typeof t=="string")return N(e);if(Array.isArray(t)){if(X(e)||!Array.isArray(e))return N(e);const o=Array.isArray(i)&&!X(i)?[...i]:[],a=o.slice();for(let f=0;f<e.length;f++){const c=e[f];c!==void 0&&(a[f]=Y(o[f],c,t[0]))}return a}if(!J(e))return N(e);const r=t,s=J(i)?i:{},n={...s};for(const[o,a]of Object.entries(e))a!==void 0&&(n[o]=Y(s[o],a,r[o]));return n}function N(i){return ArrayBuffer.isView(i)?Array.prototype.slice.call(i):Array.isArray(i)?X(i)?i.slice():i.map(t=>t===void 0?void 0:N(t)):J(i)?Object.fromEntries(Object.entries(i).map(([e,t])=>[e,t===void 0?void 0:N(t)])):i}function X(i){return ArrayBuffer.isView(i)||Array.isArray(i)&&(i.length===0||typeof i[0]=="number")}function J(i){return!!i&&typeof i=="object"&&!Array.isArray(i)&&!ArrayBuffer.isView(i)}function Rt(i){return!!(i!=null&&i.dependencies)}const we={"+X":0,"-X":1,"+Y":2,"-Y":3,"+Z":4,"-Z":5};function I(i){return i?Array.isArray(i)?i[0]??null:i:null}function Bt(i){const{dimension:e,data:t}=i;if(!t)return null;switch(e){case"1d":{const r=I(t);if(!r)return null;const{width:s}=S(r);return{width:s,height:1}}case"2d":{const r=I(t);return r?S(r):null}case"3d":case"2d-array":{if(!Array.isArray(t)||t.length===0)return null;const r=I(t[0]);return r?S(r):null}case"cube":{const r=Object.keys(t)[0]??null;if(!r)return null;const s=t[r],n=I(s);return n?S(n):null}case"cube-array":{if(!Array.isArray(t)||t.length===0)return null;const r=t[0],s=Object.keys(r)[0]??null;if(!s)return null;const n=I(r[s]);return n?S(n):null}default:return null}}function S(i){if(_e(i))return ke(i);if(typeof i=="object"&&"width"in i&&"height"in i)return{width:i.width,height:i.height};throw new Error("Unsupported mip-level data")}function Ct(i){return typeof i=="object"&&i!==null&&"data"in i&&"width"in i&&"height"in i}function $t(i){return ArrayBuffer.isView(i)}function Oe(i){const{textureFormat:e,format:t}=i;if(e&&t&&e!==t)throw new Error(`Conflicting texture formats "${e}" and "${t}" provided for the same mip level`);return e??t}function Pe(i){const e=we[i];if(e===void 0)throw new Error(`Invalid cube face: ${i}`);return e}function Dt(i,e){return 6*i+Pe(e)}function Le(i){throw new Error("setTexture1DData not supported in WebGL.")}function kt(i){return Array.isArray(i)?i:[i]}function E(i,e,t,r){const s=kt(e),n=i,o=[];for(let a=0;a<s.length;a++){const f=s[a];if(_e(f))o.push({type:"external-image",image:f,z:n,mipLevel:a});else if(Ct(f))o.push({type:"texture-data",data:f,textureFormat:Oe(f),z:n,mipLevel:a});else if($t(f)&&t)o.push({type:"texture-data",data:{data:f,width:Math.max(1,t.width>>a),height:Math.max(1,t.height>>a),...r?{format:r}:{}},textureFormat:r,z:n,mipLevel:a});else throw new Error("Unsupported 2D mip-level payload")}return o}function Ee(i){const e=[];for(let t=0;t<i.length;t++)e.push(...E(t,i[t]));return e}function Ie(i){const e=[];for(let t=0;t<i.length;t++)e.push(...E(t,i[t]));return e}function Se(i){const e=[];for(const[t,r]of Object.entries(i)){const s=Pe(t);e.push(...E(s,r))}return e}function Fe(i){const e=[];return i.forEach((t,r)=>{for(const[s,n]of Object.entries(t)){const o=Dt(r,s);e.push(...E(o,n))}}),e}const k=class k{constructor(e,t){u(this,"device");u(this,"id");u(this,"props");u(this,"_texture",null);u(this,"_sampler",null);u(this,"_view",null);u(this,"ready");u(this,"isReady",!1);u(this,"destroyed",!1);u(this,"resolveReady",()=>{});u(this,"rejectReady",()=>{});this.device=e;const r=ee("dynamic-texture"),s=t;this.props={...k.defaultProps,id:r,...t,data:null},this.id=this.props.id,this.ready=new Promise((n,o)=>{this.resolveReady=n,this.rejectReady=o}),this.initAsync(s)}get texture(){if(!this._texture)throw new Error("Texture not initialized yet");return this._texture}get sampler(){if(!this._sampler)throw new Error("Sampler not initialized yet");return this._sampler}get view(){if(!this._view)throw new Error("View not initialized yet");return this._view}get[Symbol.toStringTag](){return"DynamicTexture"}toString(){var r,s;const e=((r=this._texture)==null?void 0:r.width)??this.props.width??"?",t=((s=this._texture)==null?void 0:s.height)??this.props.height??"?";return`DynamicTexture:"${this.id}":${e}x${t}px:(${this.isReady?"ready":"loading..."})`}async initAsync(e){try{const t=await this._loadAllData(e);this._checkNotDestroyed();const r=t.data?Ut({...t,width:e.width,height:e.height,format:e.format}):[],s="format"in e&&e.format!==void 0,n="usage"in e&&e.usage!==void 0,a=(()=>{if(this.props.width&&this.props.height)return{width:this.props.width,height:this.props.height};const v=Bt(t);return v||{width:this.props.width||1,height:this.props.height||1}})();if(!a||a.width<=0||a.height<=0)throw new Error(`${this} size could not be determined or was zero`);const f=Mt(this.device,r,a,{format:s?e.format:void 0}),c=f.format??this.props.format,l={...this.props,...a,format:c,mipLevels:1,data:void 0};this.device.isTextureFormatCompressed(c)&&!n&&(l.usage=b.SAMPLE|b.COPY_DST);const h=this.props.mipmaps&&!f.hasExplicitMipChain&&!this.device.isTextureFormatCompressed(c);if(this.device.type==="webgpu"&&h){const v=this.props.dimension==="3d"?b.SAMPLE|b.STORAGE|b.COPY_DST|b.COPY_SRC:b.SAMPLE|b.RENDER|b.COPY_DST|b.COPY_SRC;l.usage|=v}const _=this.device.getMipLevelCount(l.width,l.height),m=f.hasExplicitMipChain?f.mipLevels:this.props.mipLevels==="auto"?_:Math.max(1,Math.min(_,this.props.mipLevels??1)),p={...l,mipLevels:m};this._texture=this.device.createTexture(p),this._sampler=this.texture.sampler,this._view=this.texture.view,f.subresources.length&&this._setTextureSubresources(f.subresources),this.props.mipmaps&&!f.hasExplicitMipChain&&!h&&d.warn(`${this} skipping auto-generated mipmaps for compressed texture format`)(),h&&this.generateMipmaps(),this.isReady=!0,this.resolveReady(this.texture),d.info(0,`${this} created`)()}catch(t){const r=t instanceof Error?t:new Error(String(t));this.rejectReady(r)}}destroy(){this._texture&&(this._texture.destroy(),this._texture=null,this._sampler=null,this._view=null),this.destroyed=!0}generateMipmaps(){this.device.type==="webgl"?this.texture.generateMipmapsWebGL():this.device.type==="webgpu"?this.device.generateMipmapsWebGPU(this.texture):d.warn(`${this} mipmaps not supported on ${this.device.type}`)}setSampler(e={}){this._checkReady();const t=e instanceof me?e:this.device.createSampler(e);this.texture.setSampler(t),this._sampler=t}async readBuffer(e={}){this.isReady||await this.ready;const t=e.width??this.texture.width,r=e.height??this.texture.height,s=e.depthOrArrayLayers??this.texture.depth,n=this.texture.computeMemoryLayout({width:t,height:r,depthOrArrayLayers:s}),o=this.device.createBuffer({byteLength:n.byteLength,usage:y.COPY_DST|y.MAP_READ});this.texture.readBuffer({...e,width:t,height:r,depthOrArrayLayers:s},o);const a=this.device.createFence();return await a.signaled,a.destroy(),o}async readAsync(e={}){this.isReady||await this.ready;const t=e.width??this.texture.width,r=e.height??this.texture.height,s=e.depthOrArrayLayers??this.texture.depth,n=this.texture.computeMemoryLayout({width:t,height:r,depthOrArrayLayers:s}),o=await this.readBuffer(e),a=await o.readAsync(0,n.byteLength);return o.destroy(),a.buffer}resize(e){if(this._checkReady(),e.width===this.texture.width&&e.height===this.texture.height)return!1;const t=this.texture;return this._texture=t.clone(e),this._sampler=this.texture.sampler,this._view=this.texture.view,t.destroy(),d.info(`${this} resized`),!0}getCubeFaceIndex(e){const t=we[e];if(t===void 0)throw new Error(`Invalid cube face: ${e}`);return t}getCubeArrayFaceIndex(e,t){return 6*e+this.getCubeFaceIndex(t)}setTexture1DData(e){if(this._checkReady(),this.texture.props.dimension!=="1d")throw new Error(`${this} is not 1d`);const t=Le();this._setTextureSubresources(t)}setTexture2DData(e,t=0){if(this._checkReady(),this.texture.props.dimension!=="2d")throw new Error(`${this} is not 2d`);const r=E(t,e);this._setTextureSubresources(r)}setTexture3DData(e){if(this.texture.props.dimension!=="3d")throw new Error(`${this} is not 3d`);const t=Ee(e);this._setTextureSubresources(t)}setTextureArrayData(e){if(this.texture.props.dimension!=="2d-array")throw new Error(`${this} is not 2d-array`);const t=Ie(e);this._setTextureSubresources(t)}setTextureCubeData(e){if(this.texture.props.dimension!=="cube")throw new Error(`${this} is not cube`);const t=Se(e);this._setTextureSubresources(t)}setTextureCubeArrayData(e){if(this.texture.props.dimension!=="cube-array")throw new Error(`${this} is not cube-array`);const t=Fe(e);this._setTextureSubresources(t)}_setTextureSubresources(e){for(const t of e){const{z:r,mipLevel:s}=t;switch(t.type){case"external-image":const{image:n,flipY:o}=t;this.texture.copyExternalImage({image:n,z:r,mipLevel:s,flipY:o});break;case"texture-data":const{data:a,textureFormat:f}=t;if(f&&f!==this.texture.format)throw new Error(`${this} mip level ${s} uses format "${f}" but texture format is "${this.texture.format}"`);this.texture.writeData(a.data,{x:0,y:0,z:r,width:a.width,height:a.height,depthOrArrayLayers:1,mipLevel:s});break;default:throw new Error("Unsupported 2D mip-level payload")}}}async _loadAllData(e){const t=await Z(e.data);return{dimension:e.dimension??"2d",data:t??null}}_checkNotDestroyed(){this.destroyed&&d.warn(`${this} already destroyed`)}_checkReady(){this.isReady||d.warn(`${this} Cannot perform this operation before ready`)}};u(k,"defaultProps",{...b.defaultProps,dimension:"2d",data:null,mipmaps:!1});let L=k;function Ut(i){if(!i.data)return[];const e=i.width&&i.height?{width:i.width,height:i.height}:void 0,t="format"in i?i.format:void 0;switch(i.dimension){case"1d":return Le();case"2d":return E(0,i.data,e,t);case"3d":return Ee(i.data);case"2d-array":return Ie(i.data);case"cube":return Se(i.data);case"cube-array":return Fe(i.data);default:throw new Error(`Unhandled dimension ${i.dimension}`)}}function Mt(i,e,t,r){if(e.length===0)return{subresources:e,mipLevels:1,format:r.format,hasExplicitMipChain:!1};const s=new Map;for(const l of e){const h=s.get(l.z)??[];h.push(l),s.set(l.z,h)}const n=e.some(l=>l.mipLevel>0);let o=r.format,a=Number.POSITIVE_INFINITY;const f=[];for(const[l,h]of s){const _=[...h].sort((g,P)=>g.mipLevel-P.mipLevel),m=_[0];if(!m||m.mipLevel!==0)throw new Error(`DynamicTexture: slice ${l} is missing mip level 0`);const p=de(i,m);if(p.width!==t.width||p.height!==t.height)throw new Error(`DynamicTexture: slice ${l} base level dimensions ${p.width}x${p.height} do not match expected ${t.width}x${t.height}`);const v=le(m);if(v){if(o&&o!==v)throw new Error(`DynamicTexture: slice ${l} base level format "${v}" does not match texture format "${o}"`);o=v}const O=o&&i.isTextureFormatCompressed(o)?zt(i,p.width,p.height,o):i.getMipLevelCount(p.width,p.height);let te=0;for(let g=0;g<_.length;g++){const P=_[g];if(!P||P.mipLevel!==g||g>=O)break;const re=de(i,P),Ne=Math.max(1,p.width>>g),Te=Math.max(1,p.height>>g);if(re.width!==Ne||re.height!==Te)break;const z=le(P);if(z&&(o||(o=z),z!==o))break;te++,f.push(P)}a=Math.min(a,te)}const c=Number.isFinite(a)?Math.max(1,a):1;return{subresources:f.filter(l=>l.mipLevel<c),mipLevels:c,format:o,hasExplicitMipChain:n}}function le(i){if(i.type==="texture-data")return i.textureFormat??Oe(i.data)}function de(i,e){switch(e.type){case"external-image":return i.getExternalImageSize(e.image);case"texture-data":return{width:e.data.width,height:e.data.height};default:throw new Error("Unsupported texture subresource")}}function zt(i,e,t,r){const{blockWidth:s=1,blockHeight:n=1}=i.getTextureFormatInfo(r);let o=1;for(let a=1;;a++){const f=Math.max(1,e>>a),c=Math.max(1,t>>a);if(f<s||c<n)break;o++}return o}async function Z(i){if(i=await i,Array.isArray(i))return await Promise.all(i.map(Z));if(i&&typeof i=="object"&&i.constructor===Object){const e=i,t=await Promise.all(Object.values(e).map(Z)),r=Object.keys(e),s={};for(let n=0;n<r.length;n++)s[r[n]]=t[n];return s}return i}const A=2,jt=1e4,he="render pipeline initialization failed",U=class U{constructor(e,t){u(this,"device");u(this,"id");u(this,"source");u(this,"vs");u(this,"fs");u(this,"pipelineFactory");u(this,"shaderFactory");u(this,"userData",{});u(this,"parameters");u(this,"topology");u(this,"bufferLayout");u(this,"isInstanced");u(this,"instanceCount",0);u(this,"vertexCount");u(this,"indexBuffer",null);u(this,"bufferAttributes",{});u(this,"constantAttributes",{});u(this,"bindings",{});u(this,"vertexArray");u(this,"transformFeedback",null);u(this,"pipeline");u(this,"shaderInputs");u(this,"material",null);u(this,"_uniformStore");u(this,"_attributeInfos",{});u(this,"_gpuGeometry",null);u(this,"props");u(this,"_pipelineNeedsUpdate","newly created");u(this,"_needsRedraw","initializing");u(this,"_destroyed",!1);u(this,"_lastDrawTimestamp",-1);u(this,"_bindingTable",[]);u(this,"_lastLogTime",0);u(this,"_logOpen",!1);u(this,"_drawCount",0);var f,c,l,h;this.props={...U.defaultProps,...t},t=this.props,this.id=t.id||ee("model"),this.device=e,Object.assign(this.userData,t.userData),this.material=t.material||null;const r=Object.fromEntries(((f=this.props.modules)==null?void 0:f.map(_=>[_.name,_]))||[]),s=t.shaderInputs||new Tt(r,{disableWarnings:this.props.disableWarnings});this.setShaderInputs(s);const n=Wt(e),o=(((c=this.props.modules)==null?void 0:c.length)>0?this.props.modules:(l=this.shaderInputs)==null?void 0:l.getModules())||[];if(this.props.shaderLayout=fe(this.props.shaderLayout,o)||null,this.device.type==="webgpu"&&this.props.source){const{source:_,getUniforms:m,bindingTable:p}=this.props.shaderAssembler.assembleWGSLShader({platformInfo:n,...this.props,modules:o});this.source=_,this._getModuleUniforms=m,this._bindingTable=p;const v=(h=e.getShaderLayout)==null?void 0:h.call(e,this.source);this.props.shaderLayout=fe(this.props.shaderLayout||v||null,o)||null}else{const{vs:_,fs:m,getUniforms:p}=this.props.shaderAssembler.assembleGLSLShaderPair({platformInfo:n,...this.props,modules:o});this.vs=_,this.fs=m,this._getModuleUniforms=p,this._bindingTable=[]}this.vertexCount=this.props.vertexCount,this.instanceCount=this.props.instanceCount,this.topology=this.props.topology,this.bufferLayout=this.props.bufferLayout,this.parameters=this.props.parameters,t.geometry&&this.setGeometry(t.geometry),this.pipelineFactory=t.pipelineFactory||G.getDefaultPipelineFactory(this.device),this.shaderFactory=t.shaderFactory||H.getDefaultShaderFactory(this.device),this.pipeline=this._updatePipeline(),this.vertexArray=e.createVertexArray({shaderLayout:this.pipeline.shaderLayout,bufferLayout:this.pipeline.bufferLayout}),this._gpuGeometry&&this._setGeometryAttributes(this._gpuGeometry),"isInstanced"in t&&(this.isInstanced=t.isInstanced),t.instanceCount&&this.setInstanceCount(t.instanceCount),t.vertexCount&&this.setVertexCount(t.vertexCount),t.indexBuffer&&this.setIndexBuffer(t.indexBuffer),t.attributes&&this.setAttributes(t.attributes),t.constantAttributes&&this.setConstantAttributes(t.constantAttributes),t.bindings&&this.setBindings(t.bindings),t.transformFeedback&&(this.transformFeedback=t.transformFeedback)}get[Symbol.toStringTag](){return"Model"}toString(){return`Model(${this.id})`}destroy(){var e;this._destroyed||(this.pipelineFactory.release(this.pipeline),this.shaderFactory.release(this.pipeline.vs),this.pipeline.fs&&this.pipeline.fs!==this.pipeline.vs&&this.shaderFactory.release(this.pipeline.fs),this._uniformStore.destroy(),(e=this._gpuGeometry)==null||e.destroy(),this._destroyed=!0)}needsRedraw(){this._getBindingsUpdateTimestamp()>this._lastDrawTimestamp&&this.setNeedsRedraw("contents of bound textures or buffers updated");const e=this._needsRedraw;return this._needsRedraw=!1,e}setNeedsRedraw(e){this._needsRedraw||(this._needsRedraw=e)}getBindingDebugTable(){return this._bindingTable}predraw(){this.updateShaderInputs(),this.pipeline=this._updatePipeline()}draw(e){const t=this._areBindingsLoading();if(t)return d.info(A,`>>> DRAWING ABORTED ${this.id}: ${t} not loaded`)(),!1;try{e.pushDebugGroup(`${this}.predraw(${e})`),this.predraw()}finally{e.popDebugGroup()}let r,s=this.pipeline.isErrored;try{if(e.pushDebugGroup(`${this}.draw(${e})`),this._logDrawCallStart(),this.pipeline=this._updatePipeline(),s=this.pipeline.isErrored,s)d.info(A,`>>> DRAWING ABORTED ${this.id}: ${he}`)(),r=!1;else{const n=this._getBindings(),o=this._getBindGroups(),{indexBuffer:a}=this.vertexArray,f=a?a.byteLength/(a.indexType==="uint32"?4:2):void 0;r=this.pipeline.draw({renderPass:e,vertexArray:this.vertexArray,isInstanced:this.isInstanced,vertexCount:this.vertexCount,instanceCount:this.instanceCount,indexCount:f,transformFeedback:this.transformFeedback||void 0,bindings:n,bindGroups:o,_bindGroupCacheKeys:this._getBindGroupCacheKeys(),uniforms:this.props.uniforms,parameters:this.parameters,topology:this.topology})}}finally{e.popDebugGroup(),this._logDrawCallEnd()}return this._logFramebuffer(e),r?(this._lastDrawTimestamp=this.device.timestamp,this._needsRedraw=!1):s?this._needsRedraw=he:this._needsRedraw="waiting for resource initialization",r}setGeometry(e){var r;(r=this._gpuGeometry)==null||r.destroy();const t=e&&mt(this.device,e);if(t){this.setTopology(t.topology||"triangle-list");const s=new V(this.bufferLayout);this.bufferLayout=s.mergeBufferLayouts(t.bufferLayout,this.bufferLayout),this.vertexArray&&this._setGeometryAttributes(t)}this._gpuGeometry=t}setTopology(e){e!==this.topology&&(this.topology=e,this._setPipelineNeedsUpdate("topology"))}setBufferLayout(e){const t=new V(this.bufferLayout);this.bufferLayout=this._gpuGeometry?t.mergeBufferLayouts(e,this._gpuGeometry.bufferLayout):e,this._setPipelineNeedsUpdate("bufferLayout"),this.pipeline=this._updatePipeline(),this.vertexArray=this.device.createVertexArray({shaderLayout:this.pipeline.shaderLayout,bufferLayout:this.pipeline.bufferLayout}),this._gpuGeometry&&this._setGeometryAttributes(this._gpuGeometry)}setParameters(e){K(e,this.parameters,2)||(this.parameters=e,this._setPipelineNeedsUpdate("parameters"))}setInstanceCount(e){this.instanceCount=e,this.isInstanced===void 0&&e>0&&(this.isInstanced=!0),this.setNeedsRedraw("instanceCount")}setVertexCount(e){this.vertexCount=e,this.setNeedsRedraw("vertexCount")}setShaderInputs(e){var t;this.shaderInputs=e,this._uniformStore=new pt(this.device,this.shaderInputs.modules);for(const[r,s]of Object.entries(this.shaderInputs.modules))if(Et(s)&&!((t=this.material)!=null&&t.ownsModule(r))){const n=this._uniformStore.getManagedUniformBuffer(r);this.bindings[`${r}Uniforms`]=n}this.setNeedsRedraw("shaderInputs")}setMaterial(e){this.material=e,this.setNeedsRedraw("material")}updateShaderInputs(){this._uniformStore.setUniforms(this.shaderInputs.getUniformValues()),this.setBindings(this._getNonMaterialBindings(this.shaderInputs.getBindingValues())),this.setNeedsRedraw("shaderInputs")}setBindings(e){Object.assign(this.bindings,e),this.setNeedsRedraw("bindings")}setTransformFeedback(e){this.transformFeedback=e,this.setNeedsRedraw("transformFeedback")}setIndexBuffer(e){this.vertexArray.setIndexBuffer(e),this.setNeedsRedraw("indexBuffer")}setAttributes(e,t){const r=(t==null?void 0:t.disableWarnings)??this.props.disableWarnings;e.indices&&d.warn(`Model:${this.id} setAttributes() - indexBuffer should be set using setIndexBuffer()`)(),this.bufferLayout=Lt(this.pipeline.shaderLayout,this.bufferLayout);const s=new V(this.bufferLayout);for(const[n,o]of Object.entries(e)){const a=s.getBufferLayout(n);if(!a){r||d.warn(`Model(${this.id}): Missing layout for buffer "${n}".`)();continue}const f=s.getAttributeNamesForBuffer(a);let c=!1;for(const l of f){const h=this._attributeInfos[l];if(h){const _=this.device.type==="webgpu"?s.getBufferIndex(h.bufferName):h.location;this.vertexArray.setBuffer(_,o),c=!0}}!c&&!r&&d.warn(`Model(${this.id}): Ignoring buffer "${o.id}" for unknown attribute "${n}"`)()}this.setNeedsRedraw("attributes")}setConstantAttributes(e,t){for(const[r,s]of Object.entries(e)){const n=this._attributeInfos[r];n?this.vertexArray.setConstantWebGL(n.location,s):((t==null?void 0:t.disableWarnings)??this.props.disableWarnings)||d.warn(`Model "${this.id}: Ignoring constant supplied for unknown attribute "${r}"`)()}this.setNeedsRedraw("constants")}_areBindingsLoading(){var e;for(const t of Object.values(this.bindings))if(t instanceof L&&!t.isReady)return t.id;for(const t of Object.values(((e=this.material)==null?void 0:e.bindings)||{}))if(t instanceof L&&!t.isReady)return t.id;return!1}_getBindings(){const e={};for(const[t,r]of Object.entries(this.bindings))r instanceof L?r.isReady&&(e[t]=r.texture):e[t]=r;return e}_getBindGroups(){var r;const e=((r=this.pipeline)==null?void 0:r.shaderLayout)||this.props.shaderLayout||{bindings:[]},t=e.bindings.length?Ge(e,this._getBindings()):{0:this._getBindings()};if(!this.material)return t;for(const[s,n]of Object.entries(this.material.getBindingsByGroup())){const o=Number(s);t[o]={...t[o]||{},...n}}return t}_getBindGroupCacheKeys(){var t;const e=(t=this.material)==null?void 0:t.getBindGroupCacheKey(3);return e?{3:e}:{}}_getBindingsUpdateTimestamp(){var t;let e=0;for(const r of Object.values(this.bindings))r instanceof He?e=Math.max(e,r.texture.updateTimestamp):r instanceof y||r instanceof b?e=Math.max(e,r.updateTimestamp):r instanceof L?e=r.texture?Math.max(e,r.texture.updateTimestamp):1/0:r instanceof me||(e=Math.max(e,r.buffer.updateTimestamp));return Math.max(e,((t=this.material)==null?void 0:t.getBindingsUpdateTimestamp())||0)}_setGeometryAttributes(e){const t={...e.attributes};for(const[r]of Object.entries(t))!this.pipeline.shaderLayout.attributes.find(s=>s.name===r)&&r!=="positions"&&delete t[r];this.vertexCount=e.vertexCount,this.setIndexBuffer(e.indices||null),this.setAttributes(e.attributes,{disableWarnings:!0}),this.setAttributes(t,{disableWarnings:this.props.disableWarnings}),this.setNeedsRedraw("geometry attributes")}_setPipelineNeedsUpdate(e){this._pipelineNeedsUpdate||(this._pipelineNeedsUpdate=e),this.setNeedsRedraw(e)}_updatePipeline(){if(this._pipelineNeedsUpdate){let e=null,t=null;this.pipeline&&(d.log(1,`Model ${this.id}: Recreating pipeline because "${this._pipelineNeedsUpdate}".`)(),e=this.pipeline.vs,t=this.pipeline.fs),this._pipelineNeedsUpdate=!1;const r=this.shaderFactory.createShader({id:`${this.id}-vertex`,stage:"vertex",source:this.source||this.vs,debugShaders:this.props.debugShaders});let s=null;this.source?s=r:this.fs&&(s=this.shaderFactory.createShader({id:`${this.id}-fragment`,stage:"fragment",source:this.source||this.fs,debugShaders:this.props.debugShaders})),this.pipeline=this.pipelineFactory.createRenderPipeline({...this.props,bindings:void 0,bufferLayout:this.bufferLayout,topology:this.topology,parameters:this.parameters,bindGroups:this._getBindGroups(),vs:r,fs:s}),this._attributeInfos=qe(this.pipeline.shaderLayout,this.bufferLayout),e&&this.shaderFactory.release(e),t&&t!==e&&this.shaderFactory.release(t)}return this.pipeline}_logDrawCallStart(){const e=d.level>3?0:jt;d.level<2||Date.now()-this._lastLogTime<e||(this._lastLogTime=Date.now(),this._logOpen=!0,d.group(A,`>>> DRAWING MODEL ${this.id}`,{collapsed:d.level<=2})())}_logDrawCallEnd(){if(this._logOpen){const e=yt(this.pipeline.shaderLayout,this.id);d.table(A,e)();const t=this.shaderInputs.getDebugTable();d.table(A,t)();const r=this._getAttributeDebugTable();d.table(A,this._attributeInfos)(),d.table(A,r)(),d.groupEnd(A)(),this._logOpen=!1}}_logFramebuffer(e){const t=this.device.props.debugFramebuffers;if(this._drawCount++,!t)return;const r=e.props.framebuffer;gt(e,r,{id:(r==null?void 0:r.id)||`${this.id}-framebuffer`,minimap:!0})}_getAttributeDebugTable(){const e={};for(const[t,r]of Object.entries(this._attributeInfos)){const s=this.vertexArray.attributes[r.location];e[r.location]={name:t,type:r.shaderType,values:s?this._getBufferOrConstantValues(s,r.bufferDataType):"null"}}if(this.vertexArray.indexBuffer){const{indexBuffer:t}=this.vertexArray,r=t.indexType==="uint32"?new Uint32Array(t.debugData):new Uint16Array(t.debugData);e.indices={name:"indices",type:t.indexType,values:r.toString()}}return e}_getBufferOrConstantValues(e,t){const r=Me.getTypedArrayConstructor(t);return(e instanceof y?new r(e.debugData):e).toString()}_getNonMaterialBindings(e){if(!this.material)return e;const t={};for(const[r,s]of Object.entries(e))this.material.ownsBinding(r)||(t[r]=s);return t}};u(U,"defaultProps",{...F.defaultProps,source:void 0,vs:null,fs:null,id:"unnamed",handle:void 0,userData:{},defines:{},modules:[],geometry:null,indexBuffer:null,attributes:{},constantAttributes:{},bindings:{},uniforms:{},varyings:[],isInstanced:void 0,instanceCount:0,vertexCount:0,shaderInputs:void 0,material:void 0,pipelineFactory:void 0,shaderFactory:void 0,transformFeedback:void 0,shaderAssembler:Ue.getDefaultShaderAssembler(),debugShaders:void 0,disableWarnings:void 0});let pe=U;function Wt(i){return{type:i.type,shaderLanguage:i.info.shadingLanguage,shaderLanguageVersion:i.info.shadingLanguageVersion,gpu:i.info.gpu,features:i.features}}function Kt(i,e){if(!e)return i;const t={...i,...e};if("defines"in e&&(t.defines={...i.defines,...e.defines}),"modules"in e&&(t.modules=(i.modules||[]).concat(e.modules),e.modules.some(r=>r.name==="project64"))){const r=t.modules.findIndex(s=>s.name==="project32");r>=0&&t.modules.splice(r,1)}if("inject"in e)if(!i.inject)t.inject=e.inject;else{const r={...i.inject};for(const s in e.inject)r[s]=(r[s]||"")+e.inject[s];t.inject=r}return t}export{L as D,pe as M,Tt as S,pt as U,qt as a,et as f,Kt as m,Et as s,ee as u};
//# sourceMappingURL=shader-Cz896RLg.js.map
