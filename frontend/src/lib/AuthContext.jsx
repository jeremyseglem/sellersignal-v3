import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import {
  getSupabase,
  signOut as supabaseSignOut,
  getAccessToken,
  isConfigured as supabaseIsConfigured,
} from './supabase.js';

// AuthContext — single source of truth for the signed-in agent and
// their profile, exposed to every page through useAuth().
//
// Lifecycle (post 2026-05-20 refactor):
//   1. On mount, AuthProvider awaits getSupabase() — which itself
//      awaits the runtime config fetch from /api/config.
//   2. If init succeeds, check for an existing Supabase session
//      (restored from localStorage or fresh from magic-link redirect).
//   3. If a session exists, fetch the matching agent_profiles_v3 row
//      from /api/profile and store on context.
//   4. Subscribe to onAuthStateChange so sign-in / sign-out events
//      propagate to all consumers.
//
// Three loading states exposed:
//   loading       — true on mount until auth init + session check
//                   complete (typically <300ms with cached config)
//   session       — Supabase session object or null
//   profile       — agent_profiles_v3 row or null
//   isConfigured  — true if supabase init succeeded; false if the
//                   /api/config fetch failed (backend down, etc).
//                   Use AS WELL AS loading: pages that show the
//                   "auth not configured" banner should check
//                   `!loading && !isConfigured`.
//
// Note: a user can be signed in (session exists) but profile fetch
// can fail (backend down). Pages should treat session+!profile as
// 'sign-in worked but data is offline' and degrade gracefully.

const AuthContext = createContext({
  loading: true,
  session: null,
  profile: null,
  isConfigured: false,
  signOut: async () => {},
  refreshProfile: async () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}


export function AuthProvider({ children }) {
  const [loading, setLoading] = useState(true);
  const [session, setSession] = useState(null);
  const [profile, setProfile] = useState(null);
  const [isConfigured, setIsConfigured] = useState(false);

  // Fetch agent profile from the backend. Wrapped so we can call it
  // after sign-in or when the user updates their profile.
  const refreshProfile = useCallback(async () => {
    const token = await getAccessToken();
    if (!token) {
      setProfile(null);
      return;
    }
    try {
      const res = await fetch('/api/profile', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        setProfile(null);
        return;
      }
      const data = await res.json();
      setProfile(data);
    } catch {
      setProfile(null);
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    let unsub = null;

    (async () => {
      // Await runtime config fetch + Supabase client init.
      const supabase = await getSupabase();

      if (!mounted) return;

      if (!supabase) {
        // /api/config fetch failed OR returned empty creds. Render
        // public pages with the "not configured" banner.
        setIsConfigured(false);
        setLoading(false);
        return;
      }

      setIsConfigured(true);

      // Initial session check — handles both 'restored from
      // localStorage' and 'extracted from magic-link redirect URL'.
      const { data } = await supabase.auth.getSession();
      if (!mounted) return;
      setSession(data.session || null);
      setLoading(false);

      // Subscribe to future auth state changes.
      const { data: sub } = supabase.auth.onAuthStateChange(
        (_event, newSession) => {
          if (!mounted) return;
          setSession(newSession || null);
        },
      );
      unsub = () => sub?.subscription?.unsubscribe?.();
    })();

    return () => {
      mounted = false;
      unsub?.();
    };
  }, []);

  // Whenever the session changes, refresh the profile.
  useEffect(() => {
    if (session) {
      refreshProfile();
    } else {
      setProfile(null);
    }
  }, [session, refreshProfile]);

  const value = {
    loading,
    session,
    profile,
    isConfigured,
    signOut: async () => {
      await supabaseSignOut();
      setProfile(null);
      // session goes null via onAuthStateChange
    },
    refreshProfile,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}
