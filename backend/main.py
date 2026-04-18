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
    yield
    # Shutdown hooks would go here (connection cleanup, etc.)


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


# ── FRONTEND ───────────────────────────────────────────────────────────
# In production, serve the built React frontend from frontend/dist.
# In dev, frontend runs separately on :5173 (Vite default).
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend', 'dist')
if os.path.isdir(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
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
