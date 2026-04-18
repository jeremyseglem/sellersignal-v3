# SellerSignal v3 Frontend

Merged map + briefing interface. One screen, not two pages.

## Stack

- Vite + React 18
- react-leaflet for the map (CartoDB Positron tiles — warm, muted match for Estate aesthetic)
- Plain CSS with design tokens (no Tailwind, no CSS-in-JS framework)
- Typography: Playfair Display (display), Source Serif 4 (body), Inter (UI)

## Layout

```
┌─────────────┬──────────────────────────────────────┐
│  PLAYBOOK   │                                      │
│             │                                      │
│  CALL NOW   │           TERRITORY MAP              │
│   · lead 1  │                                      │
│   · lead 2  │         (pins colored by             │
│   · lead 3  │          pressure category)          │
│   · ...     │                                      │
│             │                                      │
│  BUILD NOW  │   [on pin click: dossier slides      │
│   · lead 6  │    in from the right, covering       │
│   · ...     │    part of the map]                  │
│             │                                      │
│  HOLDS      │                                      │
│   · lead 9  │                                      │
│   · lead 10 │                                      │
└─────────────┴──────────────────────────────────────┘
```

## Running in dev

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on http://localhost:5173. Vite proxies `/api/*` to the
FastAPI backend at http://localhost:8000.

So to see the full stack working locally, run the backend first:

```bash
# Terminal 1
uvicorn backend.main:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev
```

Then visit http://localhost:5173.

## Build for production

```bash
cd frontend
npm run build
```

Output goes to `frontend/dist/`. The FastAPI app in `backend/main.py`
automatically serves from this directory when it exists — so production
deploys just need one service.

## Structure

```
frontend/
├── index.html              # HTML entrypoint, font imports, Leaflet CSS
├── package.json
├── vite.config.js          # Vite config with /api → backend proxy
└── src/
    ├── main.jsx            # React root + BrowserRouter
    ├── App.jsx             # Route table
    ├── api/
    │   └── client.js       # Thin fetch wrapper for all /api/* calls
    ├── pages/
    │   ├── CoveragePage.jsx    # Landing — lists live ZIPs
    │   └── BriefingPage.jsx    # Map + playbook for a ZIP
    ├── components/
    │   ├── PlaybookList.jsx    # Left panel: CALL NOW / BUILD NOW / HOLDS
    │   ├── MapPanel.jsx        # Leaflet map with category-colored pins
    │   └── ParcelDossier.jsx   # Slide-in dossier with Street View + signals
    └── styles/
        └── tokens.css      # Design tokens — use these, not raw hex
```

## Design tokens

Always use CSS vars from `src/styles/tokens.css`. The key ones:

- `--bg` — ivory background (#F5F0EB)
- `--text` — deep warm brown (#2C2418)
- `--accent` — gold (#8B6914)
- `--call-now` — muted red (#9E4B3C)
- `--build-now` — gold (same as accent)
- `--hold` — sage (#5A7247)
- `--font-display` — Playfair Display
- `--font-serif` — Source Serif 4 (for body)
- `--font-sans` — Inter (for UI chrome)

## Pin color scheme

- CALL NOW leads:    **red**, radius 8
- BUILD NOW leads:   **gold**, radius 7
- Strategic holds:   **sage**, radius 6
- Hold leads:        neutral tan, radius 5
- Avoid:             slate, radius 5
- Uninvestigated:    pale tan, radius 3 (visible but muted)

The frontend reads `category` from `GET /api/map/:zip` responses. That
field is populated server-side from `investigations_v3.action_category`.
For uninvestigated parcels it's the string `'uninvestigated'`.

## What's NOT built yet

- Authentication flow — backend has Supabase Auth hooks, frontend hasn't
  wired them up yet. Currently assumes anonymous access (RLS is permissive
  on live ZIPs).
- Outcomes tracking — "I called this lead, here's what happened" form.
- Email/Slack alert integration for new CALL NOW entries each week.
- Downloadable PDF playbook button (backend endpoint exists — just needs
  UI button wired to `/api/playbook/:zip/pdf`).
- Street View cache — currently every pin click hits Google. Should cache
  URLs client-side.

These are next-session items. Everything currently built is enough to
validate the UX with 98004 once its build completes.
