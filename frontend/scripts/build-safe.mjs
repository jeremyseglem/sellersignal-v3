#!/usr/bin/env node
//
// build-safe.mjs — wraps `vite build` with a post-build verification
// step that confirms the Supabase config was actually inlined.
//
// The problem this exists to prevent:
//
//   When VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY are not set in
//   the build environment, Vite silently inlines `undefined` into
//   the bundle. The build succeeds with no error or warning. The
//   resulting JS ships supabase=null, and every auth call (both
//   magic-link and password) fails in production with an
//   "Authentication isn't configured" banner. There is no signal
//   from npm/vite that anything went wrong until users try to sign
//   in. This has shipped to production twice in one day.
//
// What this script does:
//
//   1. Runs `vite build` as normal.
//   2. Reads the built index-*.js bundle from dist/assets.
//   3. Greps for two markers:
//        - the Supabase project ref ("eeqsbvizgpuehphiaslo") proves
//          VITE_SUPABASE_URL was inlined.
//        - the canonical Supabase JWT header+iss prefix proves
//          VITE_SUPABASE_ANON_KEY was inlined and is a Supabase JWT.
//   4. If either marker is missing, exits non-zero with a clear
//      explanation of what's wrong and how to fix it. The dist/
//      output is left on disk so the developer can inspect it.
//   5. If both markers are present, prints a confirmation line and
//      exits zero.
//
// How to use:
//
//   npm run build:safe
//
// The standard `npm run build` still works (raw vite, no check).
// Use this script whenever the output will end up in git or
// production — i.e., basically always.

import { execSync } from 'node:child_process';
import { readdirSync, readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const FRONTEND_ROOT = join(__dirname, '..');
const DIST_ASSETS = join(FRONTEND_ROOT, 'dist', 'assets');

// Markers we expect to find in a correctly-built bundle.
//
// The project ref is hardcoded because there is only one Supabase
// project for SellerSignal. If a staging project is ever added,
// extend this to accept multiple refs (e.g., via env var override).
const EXPECTED_PROJECT_REF = 'eeqsbvizgpuehphiaslo';

// Any Supabase-issued JWT (anon or service_role) starts with these
// 76 characters because base64-decoding them yields
//   {"alg":"HS256","typ":"JWT"}.{"iss":"supabase",...
// This is a structural check, not a value check — it proves a
// Supabase JWT was inlined without pinning to a specific key.
const SUPABASE_JWT_PREFIX =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSI';

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
  // vite already printed its errors to stderr. Just exit with the
  // same kind of code so callers can tell build failed.
  process.exit(1);
}

// ── Step 2: locate the bundle ───────────────────────────────────
console.log('');
console.log('→ Verifying bundle has Supabase config baked in...');

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

// ── Step 3: verify markers ──────────────────────────────────────
const hasUrl = contents.includes(EXPECTED_PROJECT_REF);
const hasAnonKey = contents.includes(SUPABASE_JWT_PREFIX);

if (!hasUrl || !hasAnonKey) {
  const missing = [];
  if (!hasUrl) missing.push(`Supabase project ref ("${EXPECTED_PROJECT_REF}")`);
  if (!hasAnonKey) missing.push('Supabase JWT (the anon key)');

  fail(
    `Bundle ${bundleFile} is missing: ${missing.join(' AND ')}.\n` +
      `\n` +
      `This means VITE_SUPABASE_URL and/or VITE_SUPABASE_ANON_KEY were\n` +
      `not set when vite built. The bundle would ship with supabase=null\n` +
      `and break all auth in production.\n` +
      `\n` +
      `Fix:\n` +
      `  export VITE_SUPABASE_URL="https://${EXPECTED_PROJECT_REF}.supabase.co"\n` +
      `  export VITE_SUPABASE_ANON_KEY="<anon key from Supabase or Railway>"\n` +
      `  npm run build:safe\n` +
      `\n` +
      `Aborting before this broken bundle gets committed.`,
    3,
  );
}

ok(`${bundleFile} has Supabase config baked in — safe to commit.`);
