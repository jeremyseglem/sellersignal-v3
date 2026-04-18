"""
Playbook PDF generation API.

  GET /api/playbook/:zip         — HTML version (for in-app display)
  GET /api/playbook/:zip/pdf     — PDF download (the printable 1-page operator sheet)
  GET /api/playbook/:zip/dossiers.zip — full dossier bundle (10-page forensic reads)
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

router = APIRouter()


@router.get("/{zip_code}")
async def get_playbook_html(zip_code: str):
    """
    Returns the weekly playbook as structured JSON for the frontend to render.
    The frontend renders this in the Estate aesthetic in-browser rather than
    serving pre-rendered HTML.
    """
    return {
        "zip": zip_code,
        "status": "scaffold_only",
        "playbook": {"call_now": [], "build_now": [], "strategic_holds": []},
    }


@router.get("/{zip_code}/pdf")
async def get_playbook_pdf(zip_code: str):
    """
    Printable 1-page PDF version of the weekly playbook.
    Generated via ReportLab from backend.rendering.render_playbook.
    """
    raise HTTPException(501, "Not implemented yet — wire to rendering.render_playbook")


@router.get("/{zip_code}/dossiers.zip")
async def get_dossiers_bundle(zip_code: str):
    """
    Bundle of dossier PDFs — one per lead on the weekly playbook.
    Each dossier is a 1-page forensic read with evidence citations.
    """
    raise HTTPException(501, "Not implemented yet — wire to rendering.dossier_compiler")
