"""
SellerSignal v3 — FastAPI application entry point.

Clean rewrite. No additive scoring. No LLM-delegated decisions.
Pressure-scored decision layer from verified facts only.
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from backend.api import (
    briefings,
    parcels,
    investigations,
    playbook,
    map_data,
    health,
    coverage,
    admin,
    deep_signal,
    harvest,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup + shutdown hooks. Validates env config at boot."""
    required_env = ['SUPABASE_URL', 'SUPABASE_SERVICE_KEY']
    missing = [e for e in required_env if not os.environ.get(e)]
    if missing and os.environ.get('ENVIRONMENT') == 'production':
        raise RuntimeError(f'Missing required env vars in production: {missing}')
    elif missing:
        print(f'[warn] Missing env vars (dev mode, may still work): {missing}')

    # Start the autofill background task. It runs until the app shuts down.
    # Disabled automatically if ADMIN_KEY env var is not set.
    # Can be paused/resumed at runtime via /api/harvest/autofill-{pause,resume}.
    import asyncio
    from backend.tasks.autofill import autofill_loop
    autofill_task = asyncio.create_task(autofill_loop())

    # Also start the obit harvester on its own cadence (default 12h). New
    # obits auto-appear in /matches without manual /harvest/run calls.
    from backend.tasks.obit_autofill import obit_autofill_loop
    obit_autofill_task = asyncio.create_task(obit_autofill_loop())

    # KC Treasury tax-foreclosure harvester on a daily cadence. The feed
    # is a snapshot (not a time-series), so once/day is the right cadence
    # — parcels enter/exit foreclosure as tax debts are filed or paid.
    from backend.tasks.treasury_autofill import treasury_autofill_loop
    treasury_autofill_task = asyncio.create_task(treasury_autofill_loop())

    yield

    # Shutdown: cancel background tasks cleanly
    autofill_task.cancel()
    obit_autofill_task.cancel()
    treasury_autofill_task.cancel()
    try:
        await autofill_task
    except asyncio.CancelledError:
        pass
    try:
        await obit_autofill_task
    except asyncio.CancelledError:
        pass
    try:
        await treasury_autofill_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="SellerSignal v3",
    description="Pressure-scored real-estate prospect intelligence",
    version="3.0.0",
    lifespan=lifespan,
)

# CORS — frontend runs on a different port in dev, same-origin in prod
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://sellersignal.co",
        "https://*.sellersignal.co",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── ROUTES ─────────────────────────────────────────────────────────────
app.include_router(health.router,         prefix="/api",             tags=["health"])
app.include_router(coverage.router,       prefix="/api/coverage",    tags=["coverage"])
app.include_router(briefings.router,      prefix="/api/briefings",   tags=["briefings"])
app.include_router(parcels.router,        prefix="/api/parcels",     tags=["parcels"])
app.include_router(investigations.router, prefix="/api/investigations", tags=["investigations"])
app.include_router(playbook.router,       prefix="/api/playbook",    tags=["playbook"])
app.include_router(map_data.router,       prefix="/api/map",         tags=["map"])
app.include_router(admin.router,          prefix="/api/admin",       tags=["admin"])
app.include_router(deep_signal.router,    prefix="/api/deep-signal", tags=["deep-signal"])
app.include_router(harvest.router,        prefix="/api/harvest",     tags=["harvest"])


# ── FRONTEND ───────────────────────────────────────────────────────────
# In production, serve the built React frontend from frontend/dist.
# In dev, frontend runs separately on :5173 (Vite default).
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend', 'dist')
if os.path.isdir(FRONTEND_DIST):
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    # Serve actual build artifacts (JS, CSS, images, etc.) from /assets/*.
    # React Router paths like /coverage, /zip/98004 don't map to real files —
    # they're handled client-side — so the catch-all below returns index.html
    # for any GET that isn't /api/* or /assets/* and doesn't have an extension.
    app.mount("/assets",
              StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")),
              name="assets")

    _INDEX_HTML = os.path.join(FRONTEND_DIST, "index.html")

    @app.get("/")
    async def serve_root():
        return FileResponse(_INDEX_HTML)

    # SPA catch-all: anything that isn't /api/*, /docs, /redoc, /openapi.json,
    # or a static asset falls through to here and gets the React entry point.
    # React Router reads the URL client-side and mounts the right page.
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # API routes are handled by their own routers registered above; if we
        # get here with an /api/ prefix it means the route genuinely doesn't
        # exist — return JSON 404 instead of the React shell.
        if full_path.startswith("api/") or full_path.startswith("docs") \
                or full_path == "openapi.json" or full_path.startswith("redoc"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        # For everything else (SPA routes like /zip/98004, /coverage, etc.)
        # serve the React app and let client-side routing take over.
        return FileResponse(_INDEX_HTML)
else:
    @app.get("/")
    async def root():
        return JSONResponse({
            "service": "sellersignal-v3-backend",
            "status": "running",
            "frontend": "not_built",
            "message": "Frontend not built yet. API available at /api/*.",
            "docs": "/docs",
        })


# ── ERROR HANDLERS ─────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    # In production, don't leak stack traces
    if os.environ.get('ENVIRONMENT') == 'production':
        return JSONResponse(
            status_code=500,
            content={"error": "internal_server_error", "detail": "An error occurred"}
        )
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "detail": str(exc)}
    )
