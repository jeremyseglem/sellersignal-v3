#!/usr/bin/env bash
# ============================================================================
# Onboard 10 King County ZIPs to SellerSignal V3.
#
# Runs each ZIP through the build pipeline:
#   register -> ingest -> geocode -> classify -> band -> publish
#
# Skips the optional `investigate` step (SerpAPI). Confirmed via audit
# that nothing agent-visible in the dossier today depends on SerpAPI
# data — the harvester pipeline (KC Superior Court, KC Treasurer,
# obit RSS) is the operative source. `cmd_publish --force` bypasses
# the SerpAPI prerequisite gate.
#
# Each ZIP onboarding takes ~1-3 minutes depending on parcel count.
# 10 ZIPs total: budget ~30 minutes.
#
# How to run on Railway:
#   1. Open the V3 project's web service in Railway
#   2. Click the three-dot menu on any deployment -> 'Run Command'
#      (or use `railway run` from a local checkout)
#   3. Paste this script's contents, OR run:
#        bash scripts/onboard_kc_zips.sh
#
# How to run locally (against production Supabase):
#   Set SUPABASE_URL + SUPABASE_SERVICE_KEY env vars, then:
#     bash scripts/onboard_kc_zips.sh
#
# Idempotent: rerunning is safe. `register` skips already-registered
# ZIPs. `ingest` is upsert-based. Subsequent stages skip when their
# prior stage timestamp is unchanged.
# ============================================================================

set -e  # fail fast on any error
set -u  # fail on undefined vars

# ── ZIP roster ──────────────────────────────────────────────────────
# Tier 1: Eastside luxury (4 ZIPs) — highest signal density,
# matches the luxury beta-agent profile.
# Tier 2: Eastside extension (3 ZIPs) — broader Eastside coverage
# with mid-tier price points.
# Tier 3: Seattle SFH pockets (3 ZIPs) — high-end Seattle
# neighborhoods that match the product's signal model (avoiding
# condo-tower / U-District / downtown noise).

declare -a ZIPS=(
    # Tier 1 — Eastside luxury
    "98039:Medina"
    "98040:Mercer Island"
    "98033:Kirkland"
    "98006:Bellevue"
    # Tier 2 — Eastside extension
    "98052:Redmond"
    "98005:Bellevue"
    "98007:Bellevue"
    # Tier 3 — Seattle SFH pockets
    "98112:Seattle"
    "98199:Seattle"
    "98105:Seattle"
)

MARKET="WA_KING"
STATE="WA"

# ── Helpers ────────────────────────────────────────────────────────
log()   { echo "[$(date '+%H:%M:%S')] $*"; }
hdr()   { echo; echo "════════════════════════════════════════════════"; echo "  $*"; echo "════════════════════════════════════════════════"; }

run_stage() {
    local stage=$1
    local zip=$2
    shift 2
    log "→ $stage $zip"
    if python -m backend.ingest.zip_builder "$stage" "$zip" "$@"; then
        log "✓ $stage $zip complete"
    else
        log "✗ $stage $zip FAILED"
        return 1
    fi
}

# ── Pre-flight ─────────────────────────────────────────────────────
hdr "Pre-flight check"
log "Roster: ${#ZIPS[@]} ZIPs"
for entry in "${ZIPS[@]}"; do
    zip=${entry%%:*}
    city=${entry#*:}
    log "  $zip · $city"
done

if [[ -z "${SUPABASE_URL:-}" ]] || [[ -z "${SUPABASE_SERVICE_KEY:-}" ]]; then
    log "ERROR: SUPABASE_URL or SUPABASE_SERVICE_KEY not set"
    log "These are required to write to zip_coverage_v3 / parcels_v3"
    exit 1
fi
log "✓ Supabase env vars present"

# ── Per-ZIP pipeline ────────────────────────────────────────────────
START_TIME=$SECONDS
SUCCESS=0
FAILED=()

for entry in "${ZIPS[@]}"; do
    zip=${entry%%:*}
    city=${entry#*:}

    hdr "Onboarding $zip · $city"
    ZIP_START=$SECONDS

    # Stage 1: register — adds row to zip_coverage_v3 with status=in_development
    # (idempotent — skips if already registered)
    run_stage register "$zip" --market "$MARKET" --city "$city" --state "$STATE" || {
        FAILED+=("$zip:register"); continue
    }

    # Stage 2: ingest — pulls parcels from KC ArcGIS (~5-15K parcels per ZIP)
    run_stage ingest "$zip" || { FAILED+=("$zip:ingest"); continue; }

    # Stage 3: geocode — derives lat/lng for any parcels missing it
    # (most KC parcels come with coordinates so this is fast)
    run_stage geocode "$zip" || { FAILED+=("$zip:geocode"); continue; }

    # Stage 4: classify — assigns archetypes (llc_investor_mature,
    # individual_long_tenure, trust_aging, etc) based on owner_type +
    # tenure. Drives signal_family + Tier 3 BUILD NOW cards.
    run_stage classify "$zip" || { FAILED+=("$zip:classify"); continue; }

    # Stage 5: band — assigns Band 1/2/3 priority based on signal density,
    # value tier, and structural fit. Drives selector cap allocations.
    run_stage band "$zip" || { FAILED+=("$zip:band"); continue; }

    # Stage 6: publish — flips zip_coverage_v3.status to 'live'.
    # --force bypasses the prerequisite check for first_investigation_at
    # (which would normally require running the SerpAPI investigate step).
    # Confirmed safe: SerpAPI data is not surfaced in the live dossier UI,
    # so publishing without it loses no agent-visible value.
    run_stage publish "$zip" --force || { FAILED+=("$zip:publish"); continue; }

    SUCCESS=$((SUCCESS + 1))
    ZIP_TIME=$((SECONDS - ZIP_START))
    log "✓✓ $zip onboarded in ${ZIP_TIME}s"
done

# ── Summary ────────────────────────────────────────────────────────
TOTAL_TIME=$((SECONDS - START_TIME))
hdr "Summary"
log "Total time: ${TOTAL_TIME}s"
log "Successful: $SUCCESS / ${#ZIPS[@]}"

if [[ ${#FAILED[@]} -gt 0 ]]; then
    log "Failed stages:"
    for f in "${FAILED[@]}"; do
        log "  $f"
    done
    log ""
    log "To retry a failed ZIP, run individual stages directly:"
    log "  python -m backend.ingest.zip_builder <stage> <zip> [args]"
    exit 1
fi

log ""
log "All ZIPs are LIVE. Agents can now subscribe and briefings will generate."
log ""
log "Next: run the harvester matcher to populate raw_signal_matches_v3 for the new ZIPs:"
log "  curl -X POST -H \"X-Admin-Key: \$ADMIN_KEY\" \\"
log "    https://web-production-2d85.up.railway.app/api/harvest/run"
log ""
log "Then verify by visiting the new briefings:"
for entry in "${ZIPS[@]}"; do
    zip=${entry%%:*}
    log "  https://web-production-2d85.up.railway.app/zip/$zip"
done
