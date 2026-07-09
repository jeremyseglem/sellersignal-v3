# SellerSignal V4 — UI Migration Plan

**Status:** Phase 0 in progress (started 2026-07-09)
**What V4 is:** A full visual redesign of the live V3 product — warm-dusk "ink & brass" design language, new typography stack, and a new mapping system (atlas / satellite / earth altitudes, parcel-polygon fabric). **V4 changes NO product logic, NO data, NO API contracts.** Same components, new skin, one new map component.
**Version lineage:** v1/v2 archived → V3 live today (all tables `*_v3`) → **V4 = this redesign.** Never call it v2.
**Design source of truth:** the approved demo files from the July 2026 design sessions (homepage v18, briefing real-data demo, territories atlas demo). Demos are the spec; production code is ported to match them — not the other way around.

---

## Non-negotiables (Jeremy's)

1. **Lose nothing.** Every piece of information, every tab, every button, every behavior on the live site exists in V4. The redesign changes mapping structure, page design, font, and color scheme — nothing else.
2. **Never break live.** V3 look remains the default until Jeremy flips the flag. Rollback is an env-var flip, not a redeploy.
3. **Mobile ships with V4, not after it.** Every phase has a mobile acceptance gate. No surface flips to V4 default until it passes on a real phone.
4. **One phase = one revertable commit series.** No half-skinned pages in production.
5. `npm run build:safe` only. Never raw `vite build`.

---

## Naming conventions

| Thing | Name |
|---|---|
| Feature flag (Railway env) | `UI_V4` (`"1"` = on by default; unset/`""` = off) |
| Config field | `ui_v4` in `GET /api/config` |
| Preview override | `?v4=1` query param → localStorage `ss:ui_v4_preview` (`?v4=0` clears) |
| Theme scope | `<html data-theme="v4">` |
| Token file | `frontend/src/styles/v4-tokens.css` |
| Activation util | `frontend/src/lib/uiVersion.js` |
| New map component | `frontend/src/components/MapPanelV4.jsx` (old `MapPanel.jsx` untouched) |
| This doc | `MIGRATION_V4.md` (repo root) |

## The V4 design language (from the approved demos)

- **Palette (warm dusk):** `--ink:#14110C` · `--ink-deep:#0D0B07` · `--panel:#1A1610` · `--line:#2A241A` · `--line-soft:#201B13` · brass `#C6A15B` / `#E9CD8F` · text `#F3EFE6` / `#C8C2B4` / `#7A7264`
- **Type:** Playfair Display (display serif) · DM Serif Display (wordmark) · Source Serif 4 (body serif) · IBM Plex Mono (machine voice) · Inter (UI sans)
- **Map system:** warm-dusk vector atlas → treated Esri satellite (zoom-revealed) → Google photoreal 3D tiles (Earth mode, territory owners only — "velvet rope"); WA-statewide parcel polygons as the clickable fabric; gold boundary arrival ritual.
- **Voice:** no probate/court/filing language on public marketing surfaces; clipped declaratives; scarcity by silence (no countdown theater).

---

## Phases

### Phase 0 — Groundwork (invisible; THIS PHASE)
- `v4-tokens.css`: full token set scoped to `[data-theme="v4"]` + breakpoint custom properties. Loading it changes nothing while the attribute is absent.
- `uiVersion.js`: reads `ui_v4` from `/api/config` (+ `?v4=1|0` preview override in localStorage), sets `data-theme="v4"` on `<html>`, and lazy-injects the V4 Google-font stylesheet only when active (zero weight for V3 users).
- `GET /api/config` gains `"ui_v4"` (string flag from Railway env `UI_V4`, default off).
- Wire `uiVersion.js` into `main.jsx`. **Default state after deploy: byte-identical UI for every user.**
- Verify: prod healthy, login works, `/api/config` returns `ui_v4:""`, `?v4=1` flips the html attribute (and nothing visibly changes yet — no V4 styles reference real components in Phase 0).

### Phase 1 — Leaf pages (lowest risk)
Terms, Privacy, Contact, Voice settings, Profile. Static or low-mutation pages. Port the approved demo skins. Inline-style purge → CSS Modules with v4 tokens. **Mobile gate:** all five pass at 390px; auth-adjacent pages (Profile) verified logged-in on phone.

### Phase 2 — Homepage (public, no auth logic)
Port homepage v18: hero build-video + terminal overlay, tagline "The future of listing generation.", founders section, ZIP checker (already live), territory tiles, warm palette. Mobile pass already designed in demo v13/v14 — port it. **Mobile gate:** hero video behavior on iOS Safari (autoplay/muted/playsinline), checker keyboard UX.

### Phase 3 — Territories atlas
Port the atlas demo onto `TerritoriesPage.jsx`: ZCTA polygon board (source: existing public `/api/zip-polygons` — extend to serve TIGERweb-cached geometry + `avg_home_value` aggregate), market chips, hover intel, dive + gold draw, claim sheet. **ClaimModal/claim-zip handlers unchanged.** New small backend: coverage avg-value aggregate (one column or computed endpoint; cached — NOT 90 map calls). **Mobile gate:** atlas = map-first with cards as swipe-up drawer; dive + claim flow completable on phone.

### Phase 4 — Briefing + dossier (biggest, last)
- `MapPanelV4.jsx`: MapLibre atlas/satellite + parcel-polygon fabric + PIP click; deck.gl + Earth mode as **dynamic imports** (zero bundle cost until used). Parcel polygons served by new backend proxy `GET /api/map/{zip}/lot-polygons` (WA statewide FeatureServer, cached in Supabase — county GIS uptime is not our uptime).
- Google Maps key for 3D tiles: server-held, exposed only via short-lived authorized session to territory owners (velvet rope = cost cap). Referrer-restricted + usage-capped in Cloud Console.
- Skin `BriefingPage` (header/oracle/bucket tabs/action list/pipeline), `ParcelDossierV2` (all five sections + tabs + letters modal + notes + skip trace + working section — behavior untouched), `LeadRow`, lists.
- **Mobile gate:** rail becomes bottom-sheet over full-bleed map; dossier is a full-screen takeover with thumb-reachable script tabs; tested with a real claimed territory.

### Phase 5 — Preview, flip, retire
- Week 1: `?v4=1` preview for Jeremy + Brian in their real territories (this is also mobile QA).
- Flip: set `UI_V4=1` in Railway (default on; `?v4=0` still available as escape hatch).
- Two weeks stable → remove flag plumbing + dead V3-only styles in a cleanup commit. `MapPanel.jsx` (Leaflet) retained until Jeremy explicitly approves deletion.

---

## Risk register

| Risk | Mitigation |
|---|---|
| Inline styles block theming | A page is fully converted or not shipped; no half-skinned states |
| Auth regressions (May 20 incident class) | Auth pages last in phase; every deploy ends with a real login test; `build:safe` guard |
| Bundle weight (deck.gl, fonts) | Dynamic imports; fonts injected only when v4 active |
| County GIS downtime (KC 503s, July 8) | Backend proxy + Supabase geometry cache; graceful dot-fallback when polygons missing |
| Google 3D tiles cost | Owners-only, server-gated key, Cloud Console caps |
| Existing customers surprised by dark UI | Preview toggle phase + announcement before default flip |

## Rollback procedure
Any phase: unset `UI_V4` in Railway → all users on V3 skin instantly (no redeploy). Code-level: each phase is a contiguous commit series on main; `git revert` the series. `MapPanel.jsx` and all V3 styles remain in-tree until Phase 5 cleanup.
