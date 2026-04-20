/*
 * api/client.js — thin fetch wrapper for the SellerSignal v3 backend.
 *
 * In development, Vite's proxy sends /api/* to http://localhost:8000.
 * In production, frontend is served from the same origin as the backend.
 */

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

// ── Health ─────────────────────────────────────────────────────────

export const health = {
  check: () => request('/health'),
  status: () => request('/status'),
};
