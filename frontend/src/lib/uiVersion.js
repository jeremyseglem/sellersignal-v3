/*
 * uiVersion.js — V4 UI flag plumbing (see MIGRATION_V4.md).
 *
 * Decides whether this browser sees the V4 skin, in priority order:
 *   1. Per-browser preview override:
 *        ?v4=1  -> localStorage 'ss:ui_v4_preview' = '1'  (force ON)
 *        ?v4=0  -> removes the override                    (back to server flag)
 *   2. Server flag: `ui_v4` from GET /api/config (Railway env UI_V4).
 *
 * When active: sets <html data-theme="v4"> and lazily injects the V4
 * Google-font stylesheet. When inactive: does nothing — V3 users pay
 * zero bytes and see zero change. Rollback = unset UI_V4 (no redeploy).
 *
 * Fail-safe: any error resolves to V3. The V4 skin can never brick auth
 * or rendering because it is additive CSS scoped to the data attribute.
 */

const PREVIEW_KEY = 'ss:ui_v4_preview';
const FONTS_HREF =
  'https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,500;0,600;1,400;1,500&family=DM+Serif+Display&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@400;500;600&display=swap';

function readPreviewOverride() {
  try {
    const params = new URLSearchParams(window.location.search);
    if (params.get('v4') === '1') localStorage.setItem(PREVIEW_KEY, '1');
    if (params.get('v4') === '0') localStorage.removeItem(PREVIEW_KEY);
    return localStorage.getItem(PREVIEW_KEY) === '1';
  } catch (e) {
    return false;
  }
}

function injectFonts() {
  if (document.getElementById('v4-fonts')) return;
  const pre1 = document.createElement('link');
  pre1.rel = 'preconnect';
  pre1.href = 'https://fonts.googleapis.com';
  const pre2 = document.createElement('link');
  pre2.rel = 'preconnect';
  pre2.href = 'https://fonts.gstatic.com';
  pre2.crossOrigin = 'anonymous';
  const css = document.createElement('link');
  css.id = 'v4-fonts';
  css.rel = 'stylesheet';
  css.href = FONTS_HREF;
  document.head.append(pre1, pre2, css);
}

function activate() {
  document.documentElement.dataset.theme = 'v4';
  injectFonts();
  try {
    window.dispatchEvent(new Event('ss:ui-v4'));
  } catch (e) { /* older browsers: attribute alone still themes CSS */ }
}

/**
 * Initialize the UI version. Called once from main.jsx.
 * Preview override applies synchronously (no flash for previewers);
 * the server flag applies as soon as /api/config resolves.
 */
export function initUiVersion() {
  try {
    if (readPreviewOverride()) {
      activate();
      return;
    }
    // Same runtime-config endpoint the Supabase client uses (May 2026
    // refactor). A second fetch is cheap and cached by the browser.
    fetch('/api/config')
      .then((r) => (r.ok ? r.json() : null))
      .then((cfg) => {
        if (cfg && cfg.ui_v4 === '1') activate();
      })
      .catch(() => {});
  } catch (e) {
    /* V3 remains the default on any failure */
  }
}

/** True if the V4 skin is currently active (for per-phase component checks). */
export function isV4() {
  return document.documentElement.dataset.theme === 'v4';
}
