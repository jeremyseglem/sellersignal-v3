// Supabase client + auth helpers for the SellerSignal frontend.
//
// Config-loading model (changed 2026-05-20):
//
//   Previously the Supabase URL + anon key were read from Vite env
//   vars (`import.meta.env.VITE_SUPABASE_*`) and inlined into the JS
//   bundle at `vite build` time. This silently shipped auth-broken
//   bundles whenever a rebuild ran in an environment without those
//   env vars. The bundle would initialize supabase=null and every
//   auth call would hit a "not configured" fallback. Users only
//   noticed once their cached session expired.
//
//   Current model: fetch `/api/config` at runtime. The backend reads
//   SUPABASE_URL + SUPABASE_ANON_KEY from Railway env vars and
//   returns them. No build-time injection. Any environment can
//   rebuild the frontend and the result still works.
//
//   Both values are public by design — the anon key is a routing
//   token, not a credential. RLS policies in Postgres enforce real
//   permissions.
//
// Initialization flow:
//
//   Module load (sync) → triggers fetch('/api/config') in background.
//   Helper functions   → await initialization before calling supabase.
//   AuthContext        → awaits getSupabase() in its bootstrap effect.
//   isConfigured()     → sync boolean; true after successful init,
//                        false during init AND on failure. Pair with
//                        AuthContext.loading to distinguish.
//
// Caching: result cached in localStorage so subsequent page loads
// init instantly. Background refresh on every load handles the rare
// case where SUPABASE_URL or SUPABASE_ANON_KEY rotate.

import { createClient } from '@supabase/supabase-js';

const CONFIG_CACHE_KEY = 'sellersignal:supabase_config_v1';

let _client = null;
let _initPromise = null;


function _safeLocalStorageGet(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function _safeLocalStorageSet(key, value) {
  try { localStorage.setItem(key, value); } catch { /* ignore */ }
}

function _buildClient(url, anonKey) {
  if (!url || !anonKey) return null;
  return createClient(url, anonKey, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  });
}

async function _fetchConfig() {
  // 5s timeout — fail fast if backend is unreachable so the UI can
  // render a degraded state instead of blocking forever.
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 5000);
  try {
    const res = await fetch('/api/config', { signal: ctrl.signal });
    if (!res.ok) throw new Error(`/api/config returned ${res.status}`);
    const data = await res.json();
    if (!data.supabase_url || !data.supabase_anon_key) {
      throw new Error('/api/config returned empty credentials');
    }
    return data;
  } finally {
    clearTimeout(timer);
  }
}

async function _doInit() {
  // 1. Cached config path — instant init for repeat visits.
  const cached = _safeLocalStorageGet(CONFIG_CACHE_KEY);
  if (cached) {
    try {
      const { supabase_url, supabase_anon_key } = JSON.parse(cached);
      const client = _buildClient(supabase_url, supabase_anon_key);
      if (client) {
        _client = client;
        // Refresh in the background so rotated keys propagate by next
        // load. We don't hot-swap mid-session — supabase-js doesn't
        // support it cleanly and key rotation is rare.
        _fetchConfig().then((fresh) => {
          if (
            fresh.supabase_url !== supabase_url ||
            fresh.supabase_anon_key !== supabase_anon_key
          ) {
            _safeLocalStorageSet(CONFIG_CACHE_KEY, JSON.stringify(fresh));
          }
        }).catch(() => { /* background refresh, ignore */ });
        return client;
      }
    } catch { /* cache corrupted; fall through */ }
  }

  // 2. Fresh fetch path — first visit or cache cleared.
  try {
    const cfg = await _fetchConfig();
    _safeLocalStorageSet(CONFIG_CACHE_KEY, JSON.stringify(cfg));
    _client = _buildClient(cfg.supabase_url, cfg.supabase_anon_key);
    return _client;
  } catch (err) {
    console.error('Supabase init failed:', err);
    _client = null;
    return null;
  }
}

// Single-flight init: all concurrent callers share the same promise.
function _ensureInit() {
  if (!_initPromise) _initPromise = _doInit();
  return _initPromise;
}

// Kick off init at module load — most callers hit a resolved promise.
_ensureInit();


// ── Public API ──────────────────────────────────────────────────

/**
 * Resolve to the supabase client (or null if init failed). Use in any
 * async context — AuthContext effect, auth helpers below, etc.
 */
export async function getSupabase() {
  return _ensureInit();
}

/**
 * Sync getter — current client or null. Tolerates null on first paint;
 * for code paths that can't await.
 */
export function getSupabaseSync() {
  return _client;
}

/**
 * True iff supabase finished initializing successfully. Returns false
 * during init AND on failure — pair with AuthContext.loading to
 * distinguish the two.
 */
export function isConfigured() {
  return _client !== null;
}


// ── Auth API helpers ────────────────────────────────────────────

function _notConfiguredError() {
  return new Error(
    'Authentication is not configured. Contact the SellerSignal team.',
  );
}

export async function sendMagicLink(email, { redirectTo } = {}) {
  const sb = await _ensureInit();
  if (!sb) throw _notConfiguredError();
  const { error } = await sb.auth.signInWithOtp({
    email,
    options: {
      emailRedirectTo: redirectTo || `${window.location.origin}/territories`,
      // shouldCreateUser: true is the default — magic-link auth
      // creates the user on first sign-in. The
      // create_agent_profile_on_signup trigger then creates the
      // matching agent_profiles_v3 row.
    },
  });
  if (error) throw error;
}

// Password auth — sidesteps corporate email scanners (MS Defender Safe
// Links, etc.) that pre-fetch and consume one-time-use magic-link
// tokens before the user can click them. "Confirm email" MUST be
// DISABLED in the Supabase dashboard for signUpWithPassword to return
// a session immediately.

export async function signUpWithPassword(email, password) {
  const sb = await _ensureInit();
  if (!sb) throw _notConfiguredError();
  const { data, error } = await sb.auth.signUp({ email, password });
  if (error) throw error;
  return data;
}

export async function signInWithPassword(email, password) {
  const sb = await _ensureInit();
  if (!sb) throw _notConfiguredError();
  const { data, error } = await sb.auth.signInWithPassword({ email, password });
  if (error) throw error;
  return data;
}

export async function sendPasswordReset(email, { redirectTo } = {}) {
  const sb = await _ensureInit();
  if (!sb) throw _notConfiguredError();
  const { error } = await sb.auth.resetPasswordForEmail(email, {
    redirectTo: redirectTo || `${window.location.origin}/reset-password`,
  });
  if (error) throw error;
}

export async function updatePassword(newPassword) {
  const sb = await _ensureInit();
  if (!sb) throw _notConfiguredError();
  const { error } = await sb.auth.updateUser({ password: newPassword });
  if (error) throw error;
}

export async function signOut() {
  const sb = await _ensureInit();
  if (!sb) return;
  await sb.auth.signOut();
}

export async function getCurrentSession() {
  const sb = await _ensureInit();
  if (!sb) return null;
  const { data } = await sb.auth.getSession();
  return data.session || null;
}

// Bearer token for backend API calls. Returns null when signed out.
export async function getAccessToken() {
  const session = await getCurrentSession();
  return session?.access_token || null;
}
