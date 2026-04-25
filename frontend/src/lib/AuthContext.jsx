import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { supabase, signOut as supabaseSignOut, getAccessToken } from './supabase.js';

// AuthContext — single source of truth for the signed-in agent and
// their profile, exposed to every page through useAuth().
//
// Lifecycle:
//   1. On mount, AuthProvider checks for an existing Supabase
//      session (session restored from localStorage or fresh from
//      the magic-link redirect URL hash).
//   2. If a session exists, fetch the matching agent_profiles_v3 row
//      from /api/profile and store it on the context.
//   3. Listen for onAuthStateChange so sign-in / sign-out events
//      from anywhere in the app propagate to all consumers.
//
// Three loading states a consumer can render:
//   loading       — true on mount until auth check completes
//   session       — Supabase session object or null
//   profile       — agent_profiles_v3 row or null
//
// Note: a user can be signed in (session exists) but profile fetch
// can fail (backend down). Pages should treat session+!profile as
// 'sign-in worked but data is offline' and degrade gracefully.

const AuthContext = createContext({
  loading: true,
  session: null,
  profile: null,
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

  // Fetch agent profile from the backend. Wrapped so we can call
  // it after sign-in or when the user updates their profile and
  // wants the context to refresh.
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
    if (!supabase) {
      // Auth not configured. Treat as signed-out and stop loading
      // so the UI can render public pages with a notice.
      setLoading(false);
      return;
    }

    let mounted = true;

    // Initial session check on mount. Handles both 'restored from
    // localStorage' and 'extracted from magic-link redirect URL'.
    supabase.auth.getSession().then(({ data }) => {
      if (!mounted) return;
      setSession(data.session || null);
      setLoading(false);
    });

    // Subscribe to future auth state changes.
    const { data: sub } = supabase.auth.onAuthStateChange((_event, newSession) => {
      if (!mounted) return;
      setSession(newSession || null);
    });

    return () => {
      mounted = false;
      sub?.subscription?.unsubscribe?.();
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
