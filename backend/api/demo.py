"""Demo mode — public, unauthenticated, fixture-only.

Serves a fixed set of FABRICATED briefing/map/dossier payloads for the
marketing video and Zoom pitches. Every response is a static JSON file
committed under backend/data/demo/. There is deliberately NO code path
from these endpoints to parcels_v3, case_parties_v3, or any live table —
so this router can never leak a real owner, PR, or case.

The identities in the fixtures are invented (Eleanor R Winslow et al.);
addresses and case numbers are synthetic. See scripts that generated
them for the sanitization audit. Do not wire a real-ZIP passthrough here.
"""
import json
import os
from functools import lru_cache

from fastapi import APIRouter, HTTPException

router = APIRouter()

_DEMO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "demo")
_ALLOWED = {"briefing", "map", "lot_polygons", "parcel"}


@lru_cache(maxsize=8)
def _fixture(name: str) -> str:
    if name not in _ALLOWED:
        raise HTTPException(status_code=404, detail="No such demo fixture")
    path = os.path.join(_DEMO_DIR, f"{name}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Demo fixture missing")
    with open(path, "r") as f:
        return f.read()


def _json_response(name: str):
    from fastapi.responses import Response
    return Response(content=_fixture(name), media_type="application/json")


@router.get("/briefing")
async def demo_briefing():
    """Fabricated 98008 briefing (call_now/build_now/holds)."""
    return _json_response("briefing")


@router.get("/map")
async def demo_map():
    """Fabricated parcel map for the demo ZIP."""
    return _json_response("map")


@router.get("/lot-polygons")
async def demo_lot_polygons():
    """Real lot geometry (non-identifying) for the demo ZIP's fabricated pins."""
    return _json_response("lot_polygons")


@router.get("/parcel/{pin}")
async def demo_parcel(pin: str):
    """Fabricated dossier for the single demo lead. Pin is ignored —
    only one demo parcel exists — but accepted so the frontend can call
    the same shape it uses for real parcels."""
    return _json_response("parcel")
