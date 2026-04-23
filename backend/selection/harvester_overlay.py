"""
Harvester-to-investigation bridge for the briefing pipeline.

The briefing pipeline (api/briefings.py → selection/weekly_selector.py)
uses an 'investigation-shaped' dict on each lead to decide promotion:

    lead["investigation"] = {
        "mode":               "deep" | "screen",
        "has_blocker":        bool,
        "has_life_event":     bool,
        "has_financial":      bool,
        "recommended_action": {
            "category":  "call_now" | "build_now" | "hold",
            "tone":      "sensitive" | "direct" | ...,
            "pressure":  0 | 1 | 2 | 3,
            "reason":    "short human-readable explanation",
            "next_step": "outreach direction",
        },
    }

That shape originally came from SerpAPI investigations_v3 rows. The new
harvester pipeline produces its own signals (obituary, probate, divorce,
tax_foreclosure) that sit in raw_signals_v3 / raw_signal_matches_v3 and
currently don't feed the briefing at all.

This module bridges the two:
    build_investigation_overlay(pin, harvester_matches_for_pin,
                                signals_by_id)
        → investigation-shaped dict | None

The briefing endpoint merges this overlay with the existing SerpAPI-era
investigation (if any). Promotion semantics:
  - strict probate / obituary / divorce / tax_foreclosure → pressure=3
    → call_now (existing selector promotes Band 2 to CALL NOW if
    investigation pressure == 3)
  - weak matches → pressure=2 → stays build_now but ranks higher
  - multi-signal convergence (≥2 strict matches on same pin) → pressure=3
    with convergence flag; ranks at top of call_now

Design principles (from Session's Option B strawman):
  1. Stable structural band stays on parcels_v3.band; this overlay is
     computed at read time.
  2. Harvester match is ADDITIVE — never demotes a Band 3 to something
     lower.
  3. The `reason` string is human-readable so an agent sees exactly why
     a parcel moved up (e.g. "obituary: Tina Jean Fee Han, 2026-03-31;
     probate: 25-4-12345 KNT").

See backend/pipeline/signal_registry.py for the formal signal family
catalog this feeds into.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional


# ── Pressure table ────────────────────────────────────────────────────────
# Maps (signal_type, match_strength) → pressure 0..3. The existing
# weekly_selector reads pressure=3 as "promote to CALL NOW".
_PRESSURE_TABLE = {
    # Strict matches — court-verified or authoritative source
    ("probate",         "strict"): 3,
    ("obituary",        "strict"): 3,
    ("divorce",         "strict"): 3,
    ("tax_foreclosure", "strict"): 3,

    # Weak matches — surname-only, heir inference, common-surname
    # collisions. Still surface, but don't promote to call_now.
    ("probate",         "weak"): 2,
    ("obituary",        "weak"): 2,
    ("divorce",         "weak"): 2,
    ("tax_foreclosure", "weak"): 2,
}

# Signal families that are "life events" vs "financial". Feeds the
# has_life_event / has_financial flags on the investigation shape.
_LIFE_EVENT_SIGNALS = {"probate", "obituary", "divorce"}
_FINANCIAL_SIGNALS  = {"tax_foreclosure"}


def _match_to_display(signal: dict, match: dict) -> str:
    """
    Render a single harvester match as a one-line human-readable phrase.

    Examples:
      "obituary (strict): Tina Jean Fee Han, 2026-03-31"
      "probate (strict): 25-4-12345 KNT"
      "tax_foreclosure (strict): parcel 1802000050"
      "divorce (weak): 25-3-54321 KNT"
    """
    stype     = signal.get("signal_type", "unknown")
    strength  = match.get("match_strength", "weak")
    event_dt  = signal.get("event_date") or ""
    doc_ref   = signal.get("document_ref") or ""

    parties = signal.get("party_names") or []
    lead_party = None
    for p in parties:
        if not isinstance(p, dict):
            continue
        role = (p.get("role") or "").lower()
        # Prefer the decedent for obit/probate, petitioner for divorce
        if role in ("decedent", "petitioner", "party", "parcel_only"):
            lead_party = p.get("raw")
            break
    if not lead_party and parties and isinstance(parties[0], dict):
        lead_party = parties[0].get("raw")

    label = lead_party or doc_ref
    date_suffix = f", {event_dt}" if event_dt else ""
    return f"{stype} ({strength}): {label}{date_suffix}".strip()


def _highest_pressure(match_rows: list[dict], signals_by_id: dict) -> int:
    """
    Among all matches for a single pin, find the highest pressure.

    Convergence bonus: two or more STRICT matches on the same pin ⇒
    pressure stays 3 (it's already max), but we flag the convergence
    in the reason string so the agent can see why the lead is urgent.
    """
    best = 0
    for m in match_rows:
        sig = signals_by_id.get(m.get("raw_signal_id"))
        if not sig:
            continue
        key = (sig.get("signal_type"), m.get("match_strength"))
        best = max(best, _PRESSURE_TABLE.get(key, 0))
    return best


def build_investigation_overlay(
    pin: str,
    match_rows: list[dict],
    signals_by_id: dict,
) -> Optional[dict]:
    """
    Return an investigation-shaped dict built from harvester matches, or
    None if nothing matched this pin.

    match_rows: list of raw_signal_matches_v3 rows for THIS pin. Each row
                has {raw_signal_id, pin, match_strength, match_method,
                matched_at}.
    signals_by_id: map from raw_signal.id → full raw_signal row
                (signal_type, party_names, event_date, document_ref, …).

    The caller (briefing endpoint) merges this with any existing
    investigations_v3 row. Policy when both exist:
      - If harvester pressure is HIGHER → overlay wins (additive only,
        no demotion)
      - If harvester pressure is LOWER or equal → keep SerpAPI reason
        but add harvester details to a `harvester_matches` sidecar.
    """
    if not match_rows:
        return None

    # Resolve all matches, filter out any with missing signal rows
    resolved = []
    for m in match_rows:
        sig = signals_by_id.get(m.get("raw_signal_id"))
        if sig:
            resolved.append((sig, m))
    if not resolved:
        return None

    pressure = _highest_pressure(match_rows, signals_by_id)

    # Classify what kinds of signals fired
    has_life_event = any(
        sig.get("signal_type") in _LIFE_EVENT_SIGNALS
        for sig, _ in resolved
    )
    has_financial = any(
        sig.get("signal_type") in _FINANCIAL_SIGNALS
        for sig, _ in resolved
    )

    # Build human-readable reason: one phrase per match, joined with "; "
    # Sort for stability: strict-first then by signal_type alphabetic
    resolved.sort(key=lambda sm: (
        0 if sm[1].get("match_strength") == "strict" else 1,
        sm[0].get("signal_type") or "",
    ))
    phrases = [_match_to_display(sig, m) for sig, m in resolved]

    # Convergence detection: two or more STRICT matches
    strict_count = sum(
        1 for _sig, m in resolved if m.get("match_strength") == "strict"
    )
    converged = strict_count >= 2

    # Category + tone from pressure
    if pressure >= 3:
        category = "call_now"
        tone = "sensitive" if has_life_event else "direct"
        next_step = (
            "Strong converging signal — early outreach with sensitivity."
            if converged
            else "Early outreach with sensitivity — decision window has opened."
        )
    elif pressure == 2:
        category = "build_now"
        tone = "sensitive" if has_life_event else "direct"
        next_step = "Watch for second signal; no outreach yet."
    else:
        category = "hold"
        tone = "direct"
        next_step = "Monitor. No action required."

    reason_prefix = "converged: " if converged else ""
    reason = reason_prefix + "; ".join(phrases)

    return {
        "mode":              "deep",  # harvester is an authoritative source
        "has_blocker":       False,
        "has_life_event":    has_life_event,
        "has_financial":     has_financial,
        "recommended_action": {
            "category":  category,
            "tone":      tone,
            "pressure":  pressure,
            "reason":    reason,
            "next_step": next_step,
        },
        # Sidecar: the raw match list for UI to render per-signal cards
        "harvester_matches": [
            {
                "signal_type":    sig.get("signal_type"),
                "source_type":    sig.get("source_type"),
                "match_strength": m.get("match_strength"),
                "event_date":     sig.get("event_date"),
                "document_ref":   sig.get("document_ref"),
                "party_names":    sig.get("party_names"),
                "matched_at":     m.get("matched_at"),
            }
            for sig, m in resolved
        ],
        "convergence":       converged,
        "strict_match_count": strict_count,
    }


def merge_with_existing(
    existing_inv: Optional[dict],
    overlay: Optional[dict],
) -> Optional[dict]:
    """
    Combine an existing SerpAPI-era investigation (or None) with a
    harvester overlay (or None). Returns the merged dict, or None if
    both inputs are None.

    Merge rules:
      - If only one present, return that one.
      - If both present, keep the higher-pressure recommended_action.
      - has_life_event / has_financial are OR-ed.
      - harvester_matches sidecar is always attached if overlay had any.
    """
    if existing_inv is None and overlay is None:
        return None
    if existing_inv is None:
        return overlay
    if overlay is None:
        return existing_inv

    existing_rec = existing_inv.get("recommended_action") or {}
    overlay_rec  = overlay.get("recommended_action") or {}

    existing_pressure = existing_rec.get("pressure") or 0
    overlay_pressure  = overlay_rec.get("pressure") or 0

    merged: dict = dict(existing_inv)  # copy
    merged["has_life_event"] = bool(
        existing_inv.get("has_life_event") or overlay.get("has_life_event")
    )
    merged["has_financial"] = bool(
        existing_inv.get("has_financial") or overlay.get("has_financial")
    )

    # Promotion rule: whichever recommended_action has higher pressure
    # wins. Tie → harvester overlay wins (it's the newer authoritative
    # data source; SerpAPI data is v2 heritage and often stale).
    if overlay_pressure >= existing_pressure:
        merged["recommended_action"] = overlay_rec

    # Always attach harvester sidecar for UI rendering
    merged["harvester_matches"]  = overlay.get("harvester_matches", [])
    merged["convergence"]        = overlay.get("convergence", False)
    merged["strict_match_count"] = overlay.get("strict_match_count", 0)

    return merged
