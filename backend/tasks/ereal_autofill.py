"""
eReal sweep + transfer-event detector — the KC assessor tap, turned on.

Why (2026-10-23): the death-x-trust validation showed trust-titled sales
carry death signals at 2.8x base even on a starved obit feed, and the
recorder portal (the obvious feed) CAPTCHA-gates every search lane. But
sales_history_v3 — populated by the eReal harvester we already run —
carries instrument + sale_reason per transfer ('Estate Settlement',
'Divorce', 'Trustee Deed'...): recorder-grade intelligence, pre-joined
to the parcel, free. What was missing was only cadence (the April
backfill was partial and nothing kept it fresh) and a detector.

This task:
  1. Sweeps KC ZIPs on a rotation via ereal_property.run_batch
     (TTL-gated, 1.2s/parcel politeness inherited), with a priority
     tier — trust-held and signal-matched parcels — refreshed on a
     tighter TTL via run_pins.
  2. After each batch, detects transfer events in the fresh sales rows
     and writes signals + matches DIRECTLY (parcel identity — no name
     matching, matched_at set so the rematch task never touches them):
       sale_reason ~ ESTATE            -> estate_transfer      (strict)
       sale_reason ~ DIVORCE           -> divorce_transfer     (strict)
       seller ~ TRUST, non-arms-length -> trust_distribution   (strict)
       buyer  ~ TRUST, non-arms-length -> trust_retitle        (strict)
     document_ref = "<recording_number>/<pin>" (multi-parcel deeds
     share recording numbers; the per-pin suffix keeps the
     (source_type, document_ref) dedup key unique and re-runs
     idempotent).
  3. Retires leads whose parcel's NEWEST transfer in the window is a
     recent arms-length sale (status 'retired_sold_assessor') — the KC
     leg of lead retirement, from the same sweep.

CAVEAT (documented, not hypothetical): a destructive full /rematch
deletes all matches and NULLs matched_at; the name-matcher has no
dispatcher for these signal types and would re-mark them with 0
matches. After any full /rematch, hit POST /api/harvest/transfer-detect
to re-derive them from sales_history_v3 — idempotent by design.

Memory: bounded — pin lists are strings, sales queried in chunks;
nothing county-wide is held (lesson of the 2026-10-23 OOM loop).
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta, date
from typing import Optional

log = logging.getLogger(__name__)

# ── Configuration (env-tunable) ───────────────────────────────────────
TICK_INTERVAL   = int(os.environ.get("EREAL_AUTOFILL_TICK_SECONDS", "180"))
IDLE_INTERVAL   = int(os.environ.get("EREAL_AUTOFILL_IDLE_SECONDS", "3600"))
BATCH_PARCELS   = int(os.environ.get("EREAL_AUTOFILL_BATCH", "60"))
GENERAL_TTL_D   = int(os.environ.get("EREAL_AUTOFILL_TTL_DAYS", "30"))
PRIORITY_TTL_D  = int(os.environ.get("EREAL_AUTOFILL_PRIORITY_TTL_DAYS", "7"))
STARTUP_DELAY   = int(os.environ.get("EREAL_AUTOFILL_STARTUP_DELAY", "120"))
# How far back a transfer still counts as an event (overlay decays
# CALL NOW urgency past 365d anyway — see harvester_overlay._STALE_DAYS).
EVENT_WINDOW_D  = int(os.environ.get("EREAL_TRANSFER_WINDOW_DAYS", "365"))

ENABLED_AT_BOOT = os.environ.get(
    "EREAL_AUTOFILL_ENABLED", "1"
).strip().lower() not in {"0", "false", "no", "off"}

MAX_BACKOFF_SECS = 1800

SOURCE_TYPE = "kc_assessor"   # documented in schema/006 as 'KC Assessor deed transfers'

state: dict = {
    "enabled":              ENABLED_AT_BOOT,
    "started_at":           None,
    "last_tick_at":         None,
    "last_tick_result":     None,
    "consecutive_errors":   0,
    "backoff_until":        None,
    "total_ticks":          0,
    "total_fetched":        0,
    "total_sales_upserted": 0,
    "total_signals":        0,
    "total_retired":        0,
    "total_errors":         0,
    "last_error":           None,
    "last_error_at":        None,
    "zip_rotation":         [],     # KC zips, refreshed each full cycle
    "zip_cursor":           0,
    "phase":                None,   # 'priority' | 'general'
    "wake_requested":       False,
    "config": {
        "tick_interval":    TICK_INTERVAL,
        "batch_parcels":    BATCH_PARCELS,
        "general_ttl_days": GENERAL_TTL_D,
        "priority_ttl_days": PRIORITY_TTL_D,
        "event_window_days": EVENT_WINDOW_D,
    },
}


# ── Transfer classification ───────────────────────────────────────────

def _classify_transfer(sale: dict) -> Optional[str]:
    """Map a sales_history_v3 row to a transfer signal type, or None.

    Vocabulary mirrors ereal_property_parser._classify_arms_length —
    real observed values ('Estate Settlement', 'Statutory Warranty
    Deed', trustee/quit-claim instruments), never guessed codes.
    """
    reason = (sale.get("sale_reason") or "").strip().upper()
    instr  = (sale.get("instrument") or "").strip().upper()
    seller = (sale.get("seller_name") or "").upper()
    buyer  = (sale.get("buyer_name") or "").upper()
    arms   = sale.get("is_arms_length")

    if "ESTATE" in reason:
        return "estate_transfer"
    if "DIVORCE" in reason:
        return "divorce_transfer"
    trust_sell = ("TRUST" in seller) or ("TTEE" in seller)
    trust_buy  = ("TRUST" in buyer) or ("TTEE" in buyer)
    trusty_instr = ("TRUSTEE" in instr) or ("TRUST" in reason)
    if arms is False or trusty_instr:
        # Direction decides the meaning: OUT of a trust is a
        # distribution (post-death administration — the quiet-estate
        # catch); INTO a trust is a retitle (planning event, the
        # trust_young precursor). Both-sides-trust = trustee swap; skip.
        if trust_sell and not trust_buy:
            return "trust_distribution"
        if trust_buy and not trust_sell:
            return "trust_retitle"
    return None


def _event_cutoff() -> str:
    return (date.today() - timedelta(days=EVENT_WINDOW_D)).isoformat()


def detect_transfers(supa, pins: list[str]) -> dict:
    """Derive signals/matches/retirements from sales_history_v3 for the
    given pins. Idempotent (dedup on (source_type, document_ref) and
    (raw_signal_id, pin)). Returns counters. Callable standalone from
    the admin resync endpoint."""
    out = {"pins": len(pins), "sales_seen": 0, "signals": 0,
           "retired_pins": 0, "by_type": {}, "errors": 0}
    if not pins:
        return out
    cutoff = _event_cutoff()
    CHUNK = 300
    now_iso = datetime.now(timezone.utc).isoformat()
    for i in range(0, len(pins), CHUNK):
        chunk = pins[i:i + CHUNK]
        try:
            rows = (supa.table("sales_history_v3")
                    .select("pin, recording_number, sale_date, sale_price, "
                            "seller_name, buyer_name, instrument, "
                            "sale_reason, is_arms_length")
                    .in_("pin", chunk)
                    .gte("sale_date", cutoff)
                    .execute()).data or []
        except Exception as e:
            log.warning(f"ereal_detect: sales query failed: {e}")
            out["errors"] += 1
            continue
        out["sales_seen"] += len(rows)
        by_pin: dict[str, list] = {}
        for r in rows:
            by_pin.setdefault(r["pin"], []).append(r)
        for pin, sales in by_pin.items():
            sales.sort(key=lambda s: s.get("sale_date") or "", reverse=True)
            newest = sales[0]
            # Retirement: the parcel's newest in-window transfer is a
            # genuine open-market sale -> every live lead on it is dead.
            if newest.get("is_arms_length") is True:
                try:
                    res = (supa.table("raw_signal_matches_v3")
                           .update({"match_review_status": "retired_sold_assessor",
                                    "match_review_reason":
                                        f"arms-length sale {newest.get('sale_date')} "
                                        f"rec {newest.get('recording_number')} "
                                        f"(eReal sweep)"})
                           .eq("pin", pin)
                           .is_("match_review_status", "null")
                           .execute())
                    if res.data:
                        out["retired_pins"] += 1
                except Exception as e:
                    log.warning(f"ereal_detect: retire {pin} failed: {e}")
                    out["errors"] += 1
                continue   # a sold home needs no new transfer signals
            for s in sales:
                stype = _classify_transfer(s)
                if not stype:
                    continue
                doc_ref = f"{s.get('recording_number')}/{pin}"
                parties = []
                if s.get("seller_name"):
                    parties.append({"raw": s["seller_name"], "role": "grantor"})
                if s.get("buyer_name"):
                    parties.append({"raw": s["buyer_name"], "role": "grantee"})
                sig_row = {
                    "source_type":  SOURCE_TYPE,
                    "signal_type":  stype,
                    "trust_level":  "high",     # authoritative county record
                    "party_names":  parties,
                    "event_date":   s.get("sale_date"),
                    "jurisdiction": "WA_KING",
                    "property_hint": {"parcel_id": pin},
                    "document_ref": doc_ref,
                    "raw_data":     {"sale": s, "detector": "ereal_sweep_v1"},
                    "matched_at":   now_iso,    # parcel identity — the
                    "match_count":  1,          # name-matcher never runs
                }
                try:
                    ins = (supa.table("raw_signals_v3")
                           .upsert(sig_row,
                                   on_conflict="source_type,document_ref")
                           .execute())
                    sid = (ins.data or [{}])[0].get("id")
                    if sid is None:
                        out["errors"] += 1
                        continue
                    (supa.table("raw_signal_matches_v3")
                     .upsert({"raw_signal_id": sid,
                              "pin":            pin,
                              "match_strength": "strict",
                              "match_method":   "assessor_transfer",
                              "matched_at":     now_iso},
                             on_conflict="raw_signal_id,pin")
                     .execute())
                    out["signals"] += 1
                    out["by_type"][stype] = out["by_type"].get(stype, 0) + 1
                except Exception as e:
                    log.warning(f"ereal_detect: signal write {doc_ref} failed: {e}")
                    out["errors"] += 1
    return out


# ── Priority-pin selection ────────────────────────────────────────────

def _priority_pins(supa, zip_code: str, limit: int) -> list[str]:
    """Trust-held parcels in the ZIP whose eReal snapshot is older than
    the priority TTL (or never fetched). Signal-matched parcels ride the
    general sweep; trusts are the tier that catches quiet estates."""
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=PRIORITY_TTL_D)).isoformat()
    pins: list[str] = []
    page = 0
    while True:
        res = (supa.table("parcels_v3")
               .select("pin")
               .eq("zip_code", zip_code)
               .eq("owner_type", "trust")
               .range(page * 1000, page * 1000 + 999)
               .execute()).data or []
        pins.extend(r["pin"] for r in res)
        if len(res) < 1000 or page > 40:
            break
        page += 1
    if not pins:
        return []
    stale: list[str] = []
    for i in range(0, len(pins), 500):
        chunk = pins[i:i + 500]
        meta = (supa.table("parcel_ereal_meta_v3")
                .select("pin, fetched_at")
                .in_("pin", chunk)
                .execute()).data or []
        seen = {m["pin"]: m.get("fetched_at") for m in meta}
        for p in chunk:
            f = seen.get(p)
            if not f or f < cutoff:
                stale.append(p)
            if len(stale) >= limit:
                return stale
    return stale


def _kc_zips(supa) -> list[str]:
    rows = (supa.table("zip_coverage_v3")
            .select("zip_code")
            .eq("market_key", "WA_KING")
            .execute()).data or []
    return sorted(r["zip_code"] for r in rows)


# ── Main loop ─────────────────────────────────────────────────────────

async def ereal_autofill_loop() -> None:
    from backend.api.db import get_supabase_client
    from backend.harvesters import ereal_property as E

    state["started_at"] = datetime.now(timezone.utc).isoformat()
    log.info(
        f"ereal_autofill: tick {TICK_INTERVAL}s, batch {BATCH_PARCELS}, "
        f"ttl general {GENERAL_TTL_D}d / priority(trust) {PRIORITY_TTL_D}d, "
        f"enabled={state['enabled']}, first tick in {STARTUP_DELAY}s"
    )
    await asyncio.sleep(STARTUP_DELAY)

    while True:
        try:
            if not state["enabled"]:
                await asyncio.sleep(30)
                continue
            if state["backoff_until"]:
                now = datetime.now(timezone.utc)
                try:
                    until = datetime.fromisoformat(state["backoff_until"])
                except Exception:
                    until = now
                if now < until:
                    await asyncio.sleep(30)
                    continue
                state["backoff_until"] = None

            supa = get_supabase_client()
            if supa is None:
                await asyncio.sleep(60)
                continue

            if not state["zip_rotation"] or state["zip_cursor"] >= len(state["zip_rotation"]):
                state["zip_rotation"] = await asyncio.to_thread(_kc_zips, supa)
                state["zip_cursor"] = 0
                if not state["zip_rotation"]:
                    await asyncio.sleep(IDLE_INTERVAL)
                    continue

            zip_code = state["zip_rotation"][state["zip_cursor"]]

            # Phase 1: priority (trust-held, tighter TTL) via run_pins;
            # phase 2: the general TTL sweep for the same ZIP.
            pr_pins = await asyncio.to_thread(
                _priority_pins, supa, zip_code, BATCH_PARCELS)
            if pr_pins:
                state["phase"] = "priority"
                batch = await asyncio.to_thread(
                    E.run_pins, supa, pr_pins)
            else:
                state["phase"] = "general"
                batch = await asyncio.to_thread(
                    E.run_batch, supa, zip_code, BATCH_PARCELS, GENERAL_TTL_D)
                if batch.get("candidates_found", 0) == 0:
                    # ZIP fully fresh — move the rotation along.
                    state["zip_cursor"] += 1

            fetched_pins = batch.get("fetched_pins") or []
            det = await asyncio.to_thread(detect_transfers, supa, fetched_pins)

            state["last_tick_at"] = datetime.now(timezone.utc).isoformat()
            state["last_tick_result"] = {
                "zip": zip_code, "phase": state["phase"],
                "fetched": batch.get("fetched", 0),
                "parsed_ok": batch.get("parsed_ok", 0),
                "http_errors": batch.get("http_errors", 0),
                "sales_upserted": batch.get("sales_upserted", 0),
                "detect": det,
            }
            state["total_ticks"]         += 1
            state["total_fetched"]       += batch.get("fetched", 0)
            state["total_sales_upserted"] += batch.get("sales_upserted", 0)
            state["total_signals"]       += det.get("signals", 0)
            state["total_retired"]       += det.get("retired_pins", 0)
            state["consecutive_errors"]   = 0
            log.info(f"ereal_autofill tick #{state['total_ticks']}: "
                     f"{zip_code} {state['phase']} fetched={batch.get('fetched')} "
                     f"signals={det.get('signals')} retired={det.get('retired_pins')}")

            import gc
            gc.collect()
            try:
                import ctypes
                ctypes.CDLL("libc.so.6").malloc_trim(0)
            except Exception:
                pass

            # Idle when nothing anywhere needed work this pass.
            nothing = (batch.get("fetched", 0) == 0)
            slept = 0
            target = IDLE_INTERVAL if nothing else TICK_INTERVAL
            while slept < target:
                if state.get("wake_requested"):
                    state["wake_requested"] = False
                    break
                await asyncio.sleep(min(20, target - slept))
                slept += 20

        except asyncio.CancelledError:
            log.info("ereal_autofill: loop cancelled (shutdown)")
            raise
        except Exception as e:
            state["consecutive_errors"] += 1
            state["total_errors"]       += 1
            state["last_error"]          = f"{type(e).__name__}: {str(e)[:300]}"
            state["last_error_at"]       = datetime.now(timezone.utc).isoformat()
            log.exception(f"ereal_autofill tick failed: {e}")
            backoff = min(MAX_BACKOFF_SECS,
                          60 * (2 ** min(state["consecutive_errors"], 5)))
            state["backoff_until"] = (
                datetime.now(timezone.utc) + timedelta(seconds=backoff)
            ).isoformat()
            await asyncio.sleep(60)
