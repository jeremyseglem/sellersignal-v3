/*
 * api/client.js — thin fetch wrapper for the SellerSignal v3 backend.
 *
 * In development, Vite's proxy sends /api/* to http://localhost:8000.
 * In production, frontend is served from the same origin as the backend.
 */

import { getAccessToken } from '../lib/supabase.js';

const API_BASE = '/api';

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const resp = await fetch(url, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!resp.ok) {
    const text = await resp.text();
    let detail;
    try { detail = JSON.parse(text); } catch { detail = text; }
    const err = new Error(`API error ${resp.status}: ${resp.statusText}`);
    err.status = resp.status;
    err.detail = detail;
    throw err;
  }

  return resp.json();
}

/**
 * authedRequest — same as request() but auto-attaches the Supabase
 * access token as a Bearer header. Used for endpoints that require
 * authentication (lead interactions, profile, etc.). If the user
 * isn't signed in, throws an error with status=401 BEFORE making
 * the fetch call so the caller can handle "needs auth" cleanly
 * (e.g., open the conversion modal in cold-visitor mode).
 */
async function authedRequest(path, options = {}) {
  const token = await getAccessToken();
  if (!token) {
    const err = new Error('Not signed in');
    err.status = 401;
    err.detail = { message: 'Authentication required' };
    throw err;
  }
  return request(path, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.headers || {}),
    },
  });
}

// ── Coverage ───────────────────────────────────────────────────────

export const coverage = {
  list: () => request('/coverage'),
  detail: (zip) => request(`/coverage/${zip}`),
  stats:  (zip) => request(`/coverage/${zip}/stats`),
};

// ── Briefings ──────────────────────────────────────────────────────

export const briefings = {
  get: (zip, includeMap = true) =>
    request(`/briefings/${zip}?include_map=${includeMap}`),
  summary: (zip) => request(`/briefings/${zip}/summary`),
  history: (zip, limit = 12) => request(`/briefings/${zip}/history?limit=${limit}`),
};

// ── Map data ───────────────────────────────────────────────────────

export const map = {
  get: (zip, includeUninvestigated = true) =>
    request(`/map/${zip}?include_uninvestigated=${includeUninvestigated}`),
  bounds: (zip) => request(`/map/${zip}/bounds`),
  streetView: (pin, size = '640x400') =>
    request(`/map/streetview/${pin}?size=${size}`),
};

// ── Parcels ────────────────────────────────────────────────────────

export const parcels = {
  get: (pin) => request(`/parcels/${pin}`),
  why: (pin) => request(`/parcels/${pin}/why`),
};

// ── Investigations ─────────────────────────────────────────────────

export const investigations = {
  run: (zip, dryRun = true, maxFinalists = 15) =>
    request('/investigations/run', {
      method: 'POST',
      body: JSON.stringify({ zip_code: zip, dry_run: dryRun, max_finalists: maxFinalists }),
    }),
  budget: () => request('/investigations/budget'),
  deep: (pin) => request(`/investigations/parcel/${pin}/deep`, { method: 'POST' }),
};

// ── Playbook ───────────────────────────────────────────────────────

export const playbook = {
  get: (zip) => request(`/playbook/${zip}`),
  pdfUrl: (zip) => `${API_BASE}/playbook/${zip}/pdf`,  // direct <a href> target
};

// ── Deep Signal ────────────────────────────────────────────────────
// GET returns cached Deep Signal or 404 — use to check existence.
// POST generates on demand (cache-first; pass force=true to bypass cache).

export const deepSignal = {
  get:       (pin) => request(`/deep-signal/${pin}`),
  generate:  (pin, force = false) =>
    request(`/deep-signal/${pin}${force ? '?force=true' : ''}`, { method: 'POST' }),
};

// ── Health ─────────────────────────────────────────────────────────

export const health = {
  check: () => request('/health'),
  status: () => request('/status'),
};

// ── Lead Interactions (Lead Memory) ────────────────────────────────
// Per-agent event log: working / not_relevant / sent_to_crm + outcomes.
// All endpoints require auth — calls throw 401 in cold-visitor mode
// before the fetch fires, which the dossier handles by routing to
// the conversion modal.

export const leadInteractions = {
  /**
   * Log a new event for the current agent.
   * @param {{pin: string, zip_code: string, event_type: string, event_data?: object}} body
   */
  log: (body) => authedRequest('/lead-interactions', {
    method: 'POST',
    body: JSON.stringify(body),
  }),

  /**
   * Full event history for one parcel from the current agent.
   * Returns {pin, events: [{event_type, event_data, created_at, ...}, ...]}
   * — newest first.
   */
  byPin: (pin) => authedRequest(`/lead-interactions/by-pin/${pin}`),

  /**
   * Per-pin current status map for a whole ZIP. Returns
   * {zip_code, statuses: {pin: {status, status_at, event_data}}}.
   * Reads from lead_status_v3 view — only includes pins with at
   * least one status-changing event from this agent.
   */
  byZip: (zip) => authedRequest(`/lead-interactions/by-zip/${zip}`),
};
