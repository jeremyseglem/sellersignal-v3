#!/usr/bin/env node
//
// build-safe.mjs — wraps `vite build` with a post-build verification
// step that confirms the bundle uses runtime config fetch (not
// build-time injection) for Supabase credentials.
//
// Background:
//
//   Originally this script verified the OPPOSITE — it checked that
//   VITE_SUPABASE_URL + VITE_SUPABASE_ANON_KEY were inlined into the
//   bundle, because the frontend relied on Vite env-var injection.
//   That model shipped auth-broken bundles whenever a rebuild ran
//   without those env vars set (e.g., a Claude container with only
//   backend env vars). The auth-broken bundle would init supabase=null
//   and users would hit a "not configured" fallback once their cached
//   session expired.
//
//   On 2026-05-20 the frontend was refactored to fetch credentials at
//   runtime from `/api/config` (which reads SUPABASE_URL +
//   SUPABASE_ANON_KEY from Railway env vars and returns them). The
//   build no longer needs any VITE_SUPABASE_* env vars. Any environment
//   can rebuild the frontend and the result will work in production.
//
// What this script verifies now:
//
//   1. Runs `vite build` as normal.
//   2. Reads the built index-*.js bundle from dist/assets.
//   3. Confirms the bundle references `/api/config` (proves the
//      runtime fetch code path is present).
//   4. Confirms the bundle does NOT contain a hardcoded Supabase JWT
//      anon key (proves we didn't accidentally re-introduce build-time
//      injection by, e.g., importing `import.meta.env.VITE_*` somewhere).
//   5. Exits zero if both invariants hold.
//
// How to use:
//
//   npm run build:safe
//
// Raw `npm run build` still works for development. Use build:safe
// whenever the output will be committed.

import { execSync } from 'node:child_process';
import { readdirSync, readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const FRONTEND_ROOT = join(__dirname, '..');
const DIST_ASSETS = join(FRONTEND_ROOT, 'dist', 'assets');

// Any Supabase-issued JWT (anon or service_role) starts with these
// 76 characters because base64-decoding them yields
//   {"alg":"HS256","typ":"JWT"}.{"iss":"supabase",...
// Presence in the bundle means we accidentally inlined a credential.
const SUPABASE_JWT_PREFIX =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSI';

// The runtime-config endpoint path. Presence in the bundle confirms
// the runtime fetch code path is wired up.
const RUNTIME_CONFIG_PATH = '/api/config';

function fail(message, code) {
  console.error('');
  console.error('  ╳ BUILD VERIFICATION FAILED');
  console.error('');
  for (const line of message.split('\n')) {
    console.error(`    ${line}`);
  }
  console.error('');
  process.exit(code);
}

function ok(message) {
  console.log('');
  console.log(`  ✓ ${message}`);
  console.log('');
}

// ── Step 1: run vite build ──────────────────────────────────────
console.log('→ Running vite build...');
try {
  execSync('vite build', { cwd: FRONTEND_ROOT, stdio: 'inherit' });
} catch {
  // vite already printed errors to stderr; exit non-zero so callers
  // can tell build failed.
  process.exit(1);
}

// ── Step 2: locate the bundle ───────────────────────────────────
console.log('');
console.log('→ Verifying bundle uses runtime config fetch...');

if (!existsSync(DIST_ASSETS)) {
  fail(
    `dist/assets does not exist after build.\n` +
      `This shouldn't happen — vite build appeared to succeed but produced\n` +
      `no output directory. Investigate manually.`,
    2,
  );
}

const jsFiles = readdirSync(DIST_ASSETS).filter(
  (f) => f.startsWith('index-') && f.endsWith('.js') && !f.endsWith('.map'),
);

if (jsFiles.length === 0) {
  fail(
    `No index-*.js file in dist/assets after build.\n` +
      `Expected exactly one. Got: ${readdirSync(DIST_ASSETS).join(', ') || '(empty)'}`,
    2,
  );
}

if (jsFiles.length > 1) {
  fail(
    `Multiple index-*.js files in dist/assets. Expected exactly one.\n` +
      `Found: ${jsFiles.join(', ')}\n` +
      `Stale builds from a previous run may need to be cleaned.`,
    2,
  );
}

const bundleFile = jsFiles[0];
const bundlePath = join(DIST_ASSETS, bundleFile);
const contents = readFileSync(bundlePath, 'utf-8');

// ── Step 3: positive invariant — /api/config must be referenced ──
const hasRuntimeFetch = contents.includes(RUNTIME_CONFIG_PATH);
if (!hasRuntimeFetch) {
  fail(
    `Bundle ${bundleFile} does not reference '${RUNTIME_CONFIG_PATH}'.\n` +
      `\n` +
      `The frontend is supposed to fetch Supabase config from the backend\n` +
      `at runtime. If that string isn't in the bundle, either:\n` +
      `  (a) frontend/src/lib/supabase.js was modified to not fetch config\n` +
      `      at runtime — verify it still calls fetch('/api/config'), or\n` +
      `  (b) Vite tree-shook the fetch call because nothing imports the\n` +
      `      supabase module — investigate why supabase.js is unreferenced.\n` +
      `\n` +
      `Aborting before this broken bundle gets committed.`,
    3,
  );
}

// ── Step 4: negative invariant — no Supabase JWT in the bundle ──
const hasInlinedJwt = contents.includes(SUPABASE_JWT_PREFIX);
if (hasInlinedJwt) {
  fail(
    `Bundle ${bundleFile} contains an inlined Supabase JWT.\n` +
      `\n` +
      `Since the 2026-05-20 refactor, no Supabase credentials should be\n` +
      `inlined into the JS bundle. The frontend fetches them from\n` +
      `/api/config at runtime. If a JWT made it into the bundle, someone\n` +
      `accidentally reintroduced build-time injection — likely by:\n` +
      `  (a) referencing import.meta.env.VITE_SUPABASE_* somewhere, or\n` +
      `  (b) hardcoding a key in a .js or .jsx file.\n` +
      `\n` +
      `Grep the source for 'eyJhbGc' to find it.\n` +
      `\n` +
      `Aborting before this leaked-credential bundle gets committed.`,
    4,
  );
}

ok(`${bundleFile} uses runtime config fetch — safe to commit.`);
