/*
 * api/client.js — thin fetch wrapper for the SellerSignal v3 backend.
 *
 * In development, Vite's proxy sends /api/* to http://localhost:8000.
 * In production, frontend is served from the same origin as the backend.
 */

import { getAccessToken } from '../lib/supabase.js';

const API_BASE = '/api';

async function request(path, options = {}) {
  const { headers: optHeaders, ...rest } = options;
  const url = `${API_BASE}${path}`;
  const resp = await fetch(url, {
    credentials: 'include',
    ...rest,
    headers: {
      'Content-Type': 'application/json',
      ...(optHeaders || {}),
    },
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
 * safeErrorMessage — coerce an arbitrary error (especially the
 * structured detail blob FastAPI returns on 422 validation errors)
 * into a string suitable for rendering as a React child.
 *
 * FastAPI 422 shape is: {"detail": [{"type", "loc", "msg", "input"}]}
 * Rendering that array directly causes React error #31. This helper
 * extracts the first .msg from the array, or falls through to the
 * usual string-detail / err.message paths.
 */
export function safeErrorMessage(err, fallback = 'Something went wrong') {
  const detail = err?.detail?.detail ?? err?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail[0]?.msg) {
    // Surface the first validation error in human form
    const loc = Array.isArray(detail[0].loc) ? detail[0].loc.join('.') : '';
    return loc ? `${detail[0].msg} (${loc})` : detail[0].msg;
  }
  if (typeof detail === 'object' && detail?.message) return detail.message;
  return err?.message || fallback;
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

// ── ZIP polygons (for the territories map) ─────────────────────────

export const zipPolygons = {
  // Returns a GeoJSON FeatureCollection — one polygon per live ZIP
  // in our coverage. The frontend caches this aggressively; the
  // browser also honors the server's Cache-Control: max-age=3600.
  list: () => request('/zip-polygons'),
};

// ── Notify-me when a territory releases ────────────────────────────

export const notifications = {
  subscribe: (zip_code, email) =>
    request('/notifications/subscribe', {
      method: 'POST',
      body: JSON.stringify({ zip_code, email }),
    }),
  queueSize: (zip) => request(`/notifications/zip/${zip}/queue-size`),
};

// ── Briefings ──────────────────────────────────────────────────────

export const briefings = {
  get: (zip, includeMap = true) =>
    authedRequest(`/briefings/${zip}?include_map=${includeMap}`),
  summary: (zip) => authedRequest(`/briefings/${zip}/summary`),
  history: (zip, limit = 12) => authedRequest(`/briefings/${zip}/history?limit=${limit}`),
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


// ── Lead notes ────────────────────────────────────────────────────
// Mutable free-text notes per (agent, parcel). Multiple notes per
// parcel allowed; each has its own id, body, and created/updated
// timestamps. Backed by lead_notes_v3 (migration 019).

export const leadNotes = {
  /**
   * Create a new note. Returns the inserted row.
   * @param {{pin: string, zip_code: string, body: string}} body
   */
  create: (body) => authedRequest('/lead-notes', {
    method: 'POST',
    body: JSON.stringify(body),
  }),

  /**
   * Update an existing note's body. Server auto-bumps updated_at.
   * @param {string} id
   * @param {string} body
   */
  update: (id, body) => authedRequest(`/lead-notes/${id}`, {
    method: 'PUT',
    body: JSON.stringify({ body }),
  }),

  /**
   * Delete a note. Returns {deleted: true, id}. RLS scoped to caller.
   */
  remove: (id) => authedRequest(`/lead-notes/${id}`, {
    method: 'DELETE',
  }),

  /**
   * List all this agent's notes on one parcel, newest first.
   * Returns {pin, notes: [{id, body, created_at, updated_at, ...}, ...]}
   */
  byPin: (pin) => authedRequest(`/lead-notes/by-pin/${pin}`),
};


// ── Lead tags ─────────────────────────────────────────────────────
// Flat (agent, pin, zip, tag) assignments. Agent's distinct tag
// strings form their own private taxonomy — no shared taxonomy
// table. Backed by lead_tags_v3 (migration 019).

export const leadTags = {
  /**
   * Assign a tag to a parcel. Idempotent: re-adding an existing
   * (pin, tag) returns the existing row rather than erroring.
   * @param {{pin: string, zip_code: string, tag: string}} body
   */
  create: (body) => authedRequest('/lead-tags', {
    method: 'POST',
    body: JSON.stringify(body),
  }),

  /**
   * Remove a tag assignment by id.
   */
  remove: (id) => authedRequest(`/lead-tags/${id}`, {
    method: 'DELETE',
  }),

  /**
   * List this agent's distinct tags with usage counts.
   * Optionally filter by zip_code. Returns
   * {tags: [{tag, count}, ...]} sorted by count desc, then alpha.
   * Powers the briefing-page tag filter chip row.
   */
  list: (zip_code) => {
    const qs = zip_code ? `?zip_code=${encodeURIComponent(zip_code)}` : '';
    return authedRequest(`/lead-tags${qs}`);
  },

  /**
   * All tags this agent has on one parcel.
   * Returns {pin, tags: [{id, tag, created_at, ...}, ...]}.
   */
  byPin: (pin) => authedRequest(`/lead-tags/by-pin/${pin}`),

  /**
   * All pins this agent has assigned a given tag to.
   * Optionally filter by zip_code. Returns
   * {tag, zip_code, assignments: [{pin, zip_code, created_at, ...}, ...]}.
   * Powers "search by tag" in the briefing UI.
   */
  byTag: (tag, zip_code) => {
    const qs = zip_code ? `?zip_code=${encodeURIComponent(zip_code)}` : '';
    return authedRequest(`/lead-tags/by-tag/${encodeURIComponent(tag)}${qs}`);
  },
};


/**
 * agentVoice — agent voice product API.
 *
 * generateScripts() runs the 6-archetype LLM generation against the
 * agent's profile (voice_sample, stance, bio). Server-side: ~30-90
 * seconds, runs all 6 in parallel. Returns the full result with
 * scripts, errors per archetype if any, token usage, and the
 * voice_onboarding_completed_at timestamp.
 *
 * editScript({archetype, script}) saves an agent-edited version of
 * one archetype's full script object back to the profile.
 */
export const agentVoice = {
  generateScripts: () => authedRequest('/agent/generate-scripts', {
    method: 'POST',
    body: JSON.stringify({}),
  }),

  editScript: ({ archetype, script }) => authedRequest('/agent/edit-script', {
    method: 'PUT',
    body: JSON.stringify({ archetype, script }),
  }),
};


/**
 * territory — territory claim & gating API.
 *
 * status() returns the territory grid annotated for the authenticated
 * user: their role, their assigned ZIP (if any), and every live ZIP
 * with a status — 'mine' | 'available' | 'claimed_by_other'.
 *
 * claim({zip_code}) attempts to claim a ZIP. Validates server-side:
 * agent role required, no prior claim, ZIP must be live and unclaimed.
 * Returns 409 on conflicts (already claimed, ZIP taken, etc.).
 */
export const territory = {
  status: () => authedRequest('/agent/territory-status'),

  claim: (zip_code) => authedRequest('/agent/claim-zip', {
    method: 'POST',
    body: JSON.stringify({ zip_code }),
  }),
};
