"""
Lead retirement — the sold/listed scrub.

Problem (Gallatin MLS hindcast, 2026-10-16): 4 of the 108 live CALL NOW
leads in the Gallatin ZIPs had ALREADY closed a sale, and nothing in the
pipeline noticed. An agent working the briefing would be cold-calling the
new owner about the previous owner's probate — the worst possible first
impression the product can make.

Fix: re-fetch the CURRENT owner of record for every parcel that carries a
non-retired signal match, compare against the owner the fabric knows, and
when the surname has clearly changed hands:

  1. Retire the parcel's signal matches — match_review_status =
     'retired_ownership_change' (reusing the schema/013 review columns;
     no migration needed). The briefing match fetch skips retired rows,
     so the lead drops out of CALL NOW/Contact Now on the next build.
  2. Heal the parcel row — new owner_name, tenure reset, deterministic
     re-classify (why_not_selling) + re-band (banding_v3), so the parcel
     re-enters the fabric as what it now is: a recent purchase.

Surname test is deliberately conservative: a transfer WITHIN a family
(probate → heir, "SMITH JOHN" → "SMITH FAMILY TRUST") shares a surname
token and is NOT retired — the lead is still live in that case. Only a
clean break (no shared name token) retires, which is what an arm's-length
sale looks like in owner-of-record data.

Owner re-fetch adapters are per-state. MT ships first (DNRC statewide
cadastral FeatureServer — the same source the seeds came from, monthly
refresh). States without an adapter are reported as unsupported, not
silently skipped.

Usage (admin API):
    POST /api/admin/scrub-leads/{zip_code}            — dry run (report only)
    POST /api/admin/scrub-leads/{zip_code}?write=1    — apply
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional

MT_CADASTRAL_URL = (
    "https://gis.dnrc.mt.gov/arcgis/rest/services/DNRALL/Cadastral/FeatureServer/0"
)
_UA = {"User-Agent": "Mozilla/5.0 SellerSignal-Scrub/1.0"}

# Match strengths worth scrubbing — the ones that drive briefing urgency.
_SCRUB_STRENGTHS = ("strict", "llc_exact", "trust_name")

_RETIRED_STATUS = "retired_ownership_change"

# Tokens that carry no identity (entity suffixes, conjunctions, initials
# fall out via the length filter).
_NOISE_TOKENS = {
    "TRUST", "TRUSTEE", "TRUSTEES", "LIVING", "FAMILY", "REVOCABLE",
    "IRREVOCABLE", "LLC", "INC", "CORP", "LTD", "LLP", "LP", "CO",
    "HOLDINGS", "PARTNERS", "PARTNERSHIP", "GROUP", "ENTERPRISES",
    "ESTATE", "HEIRS", "ETAL", "ET", "AL", "THE", "OF", "AND", "JR",
    "SR", "II", "III", "IV", "DECEASED", "SURVIVOR", "SURVIVORS",
    "PROPERTIES", "INVESTMENTS", "RENTALS", "DBA",
}


def _name_tokens(name: str) -> set:
    """Identity-bearing tokens of an owner name (3+ letters, not noise)."""
    toks = re.findall(r"[A-Z]{3,}", (name or "").upper())
    return {t for t in toks if t not in _NOISE_TOKENS}


def ownership_changed(old_name: str, new_name: str) -> bool:
    """True when the owner of record shows a clean break from the fabric's
    owner — no shared identity token. Family transfers (shared surname)
    and formatting drift return False."""
    old_t, new_t = _name_tokens(old_name), _name_tokens(new_name)
    if not old_t or not new_t:
        return False          # can't judge — never retire on missing data
    return not (old_t & new_t)


# ─────────────────────────────────────────────────────────────────────
# Per-state current-owner adapters: {pin: current_owner_name}
# ─────────────────────────────────────────────────────────────────────

def _fetch_mt_owners(pins: list) -> dict:
    """Current OwnerName per PARCELID from the MT DNRC cadastral layer."""
    out = {}
    CHUNK = 80
    for i in range(0, len(pins), CHUNK):
        chunk = pins[i:i + CHUNK]
        where = "PARCELID IN ({})".format(
            ",".join("'" + p.replace("'", "") + "'" for p in chunk))
        params = urllib.parse.urlencode({
            "where": where,
            "outFields": "PARCELID,OwnerName",
            "returnGeometry": "false",
            "f": "json",
        })
        req = urllib.request.Request(
            f"{MT_CADASTRAL_URL}/query?{params}", headers=_UA)
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode())
        for feat in data.get("features") or []:
            a = feat.get("attributes") or {}
            if a.get("PARCELID"):
                out[a["PARCELID"]] = a.get("OwnerName") or ""
    return out


_OWNER_FETCHERS = {
    "MT": _fetch_mt_owners,
}


# ─────────────────────────────────────────────────────────────────────
# The scrub
# ─────────────────────────────────────────────────────────────────────

def scrub_zip(zip_code: str, write: bool = False) -> dict:
    """Check every signal-matched parcel in a ZIP for an ownership change;
    retire matches and heal parcels where one is found.

    Returns a report dict. write=False (default) reports without touching
    the database.
    """
    from backend.api.db import get_supabase_client
    supa = get_supabase_client()
    if not supa:
        raise RuntimeError("Supabase not configured")

    cov = (supa.table("zip_coverage_v3")
           .select("state, market_key")
           .eq("zip_code", zip_code)
           .maybe_single().execute())
    state = (cov.data or {}).get("state") if cov else None
    fetcher = _OWNER_FETCHERS.get(state or "")
    if fetcher is None:
        return {"zip": zip_code, "state": state, "supported": False,
                "detail": f"no current-owner adapter for state {state!r} — "
                          f"supported: {sorted(_OWNER_FETCHERS)}"}

    # Parcels in the ZIP (paginated), keyed by pin
    parcels = {}
    offset, page = 0, 1000
    while True:
        res = (supa.table("parcels_v3")
               .select("pin, owner_name, owner_name_raw, owner_type, "
                       "tenure_years, total_value, prop_type, address, "
                       "is_vacant_land, is_absentee, is_out_of_state, "
                       "signal_family, band")
               .eq("zip_code", zip_code)
               .range(offset, offset + page - 1).execute())
        rows = res.data or []
        for r in rows:
            parcels[r["pin"]] = r
        if len(rows) < page:
            break
        offset += page

    if not parcels:
        return {"zip": zip_code, "state": state, "supported": True,
                "matched_pins": 0, "checked": 0, "changed": [],
                "detail": "no parcels"}

    # Non-retired matches on those pins
    pins = list(parcels)
    matches_by_pin = {}
    CHUNK = 200
    for i in range(0, len(pins), CHUNK):
        chunk = pins[i:i + CHUNK]
        res = (supa.table("raw_signal_matches_v3")
               .select("id, raw_signal_id, pin, match_strength, "
                       "match_review_status")
               .in_("pin", chunk)
               .in_("match_strength", list(_SCRUB_STRENGTHS))
               .limit(5000).execute())
        for m in res.data or []:
            status = m.get("match_review_status") or ""
            if status.startswith("retired"):
                continue
            matches_by_pin.setdefault(m["pin"], []).append(m)

    matched_pins = sorted(matches_by_pin)
    if not matched_pins:
        return {"zip": zip_code, "state": state, "supported": True,
                "matched_pins": 0, "checked": 0, "changed": []}

    current = fetcher(matched_pins)

    from backend.scoring.why_not_selling import classify_archetype
    from backend.scoring.banding_v3 import determine_band

    today = datetime.now(timezone.utc).date().isoformat()
    changed, healed, retired_match_ids = [], 0, []
    for pin in matched_pins:
        new_owner = current.get(pin)
        if not new_owner:
            continue              # parcel gone from layer / no data — skip
        old_owner = (parcels[pin].get("owner_name_raw")
                     or parcels[pin].get("owner_name") or "")
        if not ownership_changed(old_owner, new_owner):
            continue

        match_ids = [m["id"] for m in matches_by_pin[pin]]
        retired_match_ids.extend(match_ids)
        changed.append({"pin": pin, "old_owner": old_owner,
                        "new_owner": new_owner,
                        "retired_matches": len(match_ids)})

        if not write:
            continue

        # 1. Retire the matches
        reason = (f"ownership changed: {old_owner!r} -> {new_owner!r} "
                  f"(cadastral {today})")
        (supa.table("raw_signal_matches_v3")
         .update({"match_review_status": _RETIRED_STATUS,
                  "match_review_reason": reason[:500]})
         .in_("id", match_ids).execute())

        # 2. Heal the parcel: new owner, tenure reset, deterministic
        #    re-classify + re-band so it re-enters the fabric truthfully.
        p = dict(parcels[pin])
        p["owner_name"] = new_owner
        p["owner_name_raw"] = new_owner
        p["tenure_years"] = 0.1
        new_arch = classify_archetype(p)
        p["signal_family"] = new_arch
        new_band = determine_band(p, state=state)
        (supa.table("parcels_v3")
         .update({"owner_name": new_owner,
                  "owner_name_raw": new_owner,
                  "tenure_years": 0.1,
                  "signal_family": new_arch,
                  "band": new_band})
         .eq("pin", pin).execute())
        healed += 1

    return {
        "zip": zip_code, "state": state, "supported": True,
        "matched_pins": len(matched_pins),
        "checked": len(current),
        "changed": changed,
        "retired_match_rows": len(retired_match_ids) if write else 0,
        "healed_parcels": healed,
        "write": write,
    }
