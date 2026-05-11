// Supabase client + auth helpers for the SellerSignal frontend.
//
// Two env vars must be present at build time:
//   VITE_SUPABASE_URL      — https://<project>.supabase.co
//   VITE_SUPABASE_ANON_KEY — public anon key (safe to ship in JS)
//
// These get set in Railway's environment for the frontend deploy
// step. When missing (e.g., a fresh dev clone without secrets), the
// client object is null and AuthProvider renders sign-in pages with
// a 'Auth not configured' notice rather than crashing.
//
// The anon key is intentionally public — it grants only the
// permissions defined by Row Level Security policies in the
// database. Sensitive operations (rescore, admin actions) require
// the service key, which lives only on the backend.

import { createClient } from '@supabase/supabase-js';

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const supabase =
  url && anonKey
    ? createClient(url, anonKey, {
        auth: {
          // Persist session in localStorage so the user stays signed in
          // across page reloads. Standard Supabase default but stated
          // explicitly here so the behavior is documented in code.
          persistSession: true,
          autoRefreshToken: true,
          // Magic-link emails redirect back to the SPA. Use the auth
          // callback path so the AuthProvider can extract the session
          // from the URL fragment.
          detectSessionInUrl: true,
        },
      })
    : null;

export const supabaseConfigured = supabase !== null;


// ── Auth API helpers ────────────────────────────────────────────
// Thin wrappers around the supabase-js methods so callers don't
// have to handle the null-supabase case everywhere.

export async function sendMagicLink(email, { redirectTo } = {}) {
  if (!supabase) {
    throw new Error('Authentication is not configured. Contact the SellerSignal team.');
  }
  const { error } = await supabase.auth.signInWithOtp({
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

export async function signOut() {
  if (!supabase) return;
  await supabase.auth.signOut();
}

export async function getCurrentSession() {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session || null;
}

// Expose the current user's access token so other API calls can
// attach it as a Bearer token to authenticate against the V3
// backend's /api/profile endpoints. Returns null when signed out.
export async function getAccessToken() {
  const session = await getCurrentSession();
  return session?.access_token || null;
}
