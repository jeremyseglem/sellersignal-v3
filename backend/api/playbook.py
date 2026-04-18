"""
Playbook PDF generation API.

  GET /api/playbook/:zip               — structured JSON playbook (also available via briefings endpoint)
  GET /api/playbook/:zip/pdf           — printable PDF weekly operator sheet
  GET /api/playbook/:zip/dossiers.zip  — bundle of per-lead dossier PDFs

PDFs use the Estate aesthetic: Playfair Display, ivory background,
gold accents. Generated server-side via ReportLab.
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from datetime import date, timedelta
import io
import json

from backend.api.db import get_supabase_client
from backend.api.zip_gate import require_live_zip

router = APIRouter()


def _build_picks_payload_for_renderer(zip_code: str) -> dict:
    """
    Build the picks JSON shape that render_playbook.py expects:
        {
          'week_of': '2026-04-13',
          'call_now': [{pin, address, zip, value, copy: {happening, why, action}}, ...],
          'build_now': [...],
          'strategic_holds': [...],
        }

    Selects same logic as briefings.py: 5 CALL NOW / 3 BUILD NOW / 2 HOLDS
    with slot reservations. Copy is composed from recommended_action fields.
    """
    supa = get_supabase_client()
    if not supa:
        raise HTTPException(503, "Database unavailable")

    # Pull parcels + investigations in two queries
    parcels_res = (supa.table('parcels_v3').select('*')
                   .eq('zip_code', zip_code).execute())
    parcels = parcels_res.data or []
    if not parcels:
        raise HTTPException(404, f"No parcels in {zip_code}")

    inv_res = (supa.table('investigations_v3').select('*')
               .eq('zip_code', zip_code).execute())
    inv_by_pin = {}
    for row in (inv_res.data or []):
        pin = row['pin']
        if pin not in inv_by_pin or row['mode'] == 'deep':
            inv_by_pin[pin] = row

    # Build pools
    filtered = [(p, inv_by_pin.get(p['pin']))
                for p in parcels
                if not (inv_by_pin.get(p['pin']) or {}).get('has_blocker')]

    call_now_pool, build_now_pool, hold_pool = [], [], []
    for p, inv in filtered:
        band = p.get('band')
        action_cat = (inv or {}).get('action_category')
        if band == 3 or action_cat == 'call_now':
            if action_cat == 'call_now' or action_cat is None:
                call_now_pool.append((p, inv))
        elif band in (2, 2.5) and action_cat == 'build_now':
            build_now_pool.append((p, inv))
        elif band in (2, 2.5) and p.get('signal_family') == 'trust_aging':
            hold_pool.append((p, inv))

    def _rank(t):
        p, inv = t
        val = p.get('total_value') or 0
        pressure = (inv or {}).get('action_pressure') or 0
        return (pressure, val)

    def _pick_format(p, inv):
        rec = inv or {}
        return {
            'pin':     p['pin'],
            'address': p.get('address'),
            'zip':     p.get('zip_code'),
            'value':   p.get('total_value'),
            'copy': {
                'happening': _derive_happening(p, rec),
                'why':       rec.get('action_reason') or _derive_why(p),
                'action':    rec.get('action_next_step') or 'Monitor; revisit next cycle.',
            },
        }

    # CALL NOW: 2 reserved for Band 3 financial_stress, 3 more from pool
    fs = sorted(
        [t for t in call_now_pool if t[0].get('signal_family') == 'financial_stress'],
        key=_rank, reverse=True,
    )
    used = set()
    call_now_picks = []
    for p, inv in fs[:2]:
        if p['pin'] not in used:
            call_now_picks.append(_pick_format(p, inv))
            used.add(p['pin'])
    remaining = sorted(
        [(p, inv) for p, inv in call_now_pool if p['pin'] not in used],
        key=_rank, reverse=True,
    )
    for p, inv in remaining:
        if len(call_now_picks) >= 5: break
        if p['pin'] not in used:
            call_now_picks.append(_pick_format(p, inv))
            used.add(p['pin'])

    build_now_sorted = sorted(build_now_pool, key=_rank, reverse=True)
    build_now_picks = [_pick_format(p, inv) for p, inv in build_now_sorted[:3]]

    holds_sorted = sorted(hold_pool, key=_rank, reverse=True)
    hold_picks = [_pick_format(p, inv) for p, inv in holds_sorted[:2]]

    today = date.today()
    week_monday = today - timedelta(days=today.weekday())

    return {
        'week_of':         week_monday.isoformat(),
        'call_now':        call_now_picks,
        'build_now':       build_now_picks,
        'strategic_holds': hold_picks,
    }


def _derive_happening(parcel: dict, inv: dict) -> str:
    """Short 'what's going on' line from investigation or structural features."""
    sf = parcel.get('signal_family')
    if sf == 'financial_stress':
        return "Financial pressure filing active. Time-sensitive."
    if sf == 'failed_sale_attempt':
        return "Listing expired after extended market time."
    if sf == 'investor_disposition':
        return "Investor holding past typical exit window."
    if sf == 'trust_aging':
        return "Trust-held asset, grantor in late-life stage."
    if sf == 'estate_heirs':
        return "Active estate settlement process."
    if sf == 'absentee_dormant':
        return "Dormant ownership pattern with long tenure."
    return "Structural transition signal observed."


def _derive_why(parcel: dict) -> str:
    """Fallback 'why' line."""
    sf = parcel.get('signal_family')
    if sf == 'financial_stress':
        return "Owner likely needs clean exit before auction."
    if sf == 'failed_sale_attempt':
        return "Seller didn't fail — timing and strategy did."
    if sf == 'trust_aging':
        return "Decision window is biological, not market-driven."
    return "Pattern matches historical pre-seller cohort."


@router.get("/{zip_code}")
async def get_playbook_json(zip_code: str = Depends(require_live_zip)):
    """
    Structured JSON playbook. Same data shape as briefings endpoint
    but without the full map_data payload — lighter-weight.
    """
    return _build_picks_payload_for_renderer(zip_code)


@router.get("/{zip_code}/pdf")
async def get_playbook_pdf(zip_code: str = Depends(require_live_zip)):
    """
    Printable 1-page PDF of the weekly playbook.
    Estate aesthetic — Playfair Display, ivory, gold accents.
    """
    try:
        picks = _build_picks_payload_for_renderer(zip_code)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error building playbook: {e}")

    try:
        from backend.rendering import render_playbook
    except ImportError:
        raise HTTPException(501, "Playbook renderer not available")

    # render_playbook expects file paths — write picks to tmp, render, read back
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as picks_f:
        json.dump(picks, picks_f, default=str)
        picks_path = picks_f.name

    pdf_path = picks_path.replace('.json', '.pdf')

    try:
        render_playbook.render(picks_path, pdf_path)
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
    except Exception as e:
        raise HTTPException(500, f"PDF render failed: {e}")
    finally:
        for p in (picks_path, pdf_path):
            try: os.remove(p)
            except OSError: pass

    week_of = picks.get('week_of', 'current')
    return Response(
        content=pdf_bytes,
        media_type='application/pdf',
        headers={
            'Content-Disposition':
                f'attachment; filename="sellersignal-playbook-{zip_code}-{week_of}.pdf"',
        },
    )


@router.get("/{zip_code}/dossiers.zip")
async def get_dossier_bundle(zip_code: str = Depends(require_live_zip)):
    """
    ZIP bundle of per-lead dossier PDFs (up to 10 — one per playbook lead).

    Not yet implemented — next session will wire to
    backend/rendering/dossier_compiler.py which exists in the repo.
    """
    raise HTTPException(
        501,
        detail={
            'error': 'not_implemented',
            'message': ('Dossier bundle generation is planned but not yet '
                        'wired. See docs/STATUS.md for timeline.'),
        },
    )
