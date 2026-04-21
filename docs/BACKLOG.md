# SellerSignal v3 — Feature & Signal Backlog

Last updated: 2026-04-20

This document tracks signal types, data sources, and architectural decisions
we've discussed but haven't shipped. It is the source of truth for "what's
in the queue."

---

## Beta milestone: King County 10-ZIP benchmark

**Scope**: 10 KC ZIPs covering ultra-luxury, luxury, luxury urban, 
mid-market urban, gentrifying, investor-heavy, and tech-suburban markets.

**Target ZIPs** (subject to adjustment):
| ZIP | Market type |
|---|---|
| 98004 Bellevue | Ultra-luxury eastside (already loaded) |
| 98039 Medina | Ultra-luxury, trust-heavy |
| 98040 Mercer Island | Luxury, long-tenure |
| 98112 Madison Park / Madrona | Urban luxury |
| 98122 Central District | Gentrifying mid-market |
| 98144 Beacon Hill | Mid-market, investor mix |
| 98105 University District | Rental investor heavy |
| 98052 Redmond | Tech-mid, newer ownership |
| 98118 Columbia City / Rainier Valley | Emerging, investor activity |
| 98102 Capitol Hill / Westlake | Condo-dominated, high turnover |

**Why this scope proves the thesis**: variation forces the scoring engine
to handle luxury estate-planning signals (Medina) alongside mid-market
probate/divorce (Beacon Hill) alongside investor disposition (U-District,
Columbia City). If signals surface meaningfully across all, the product
works beyond luxury.

**Cost to load**:
- Parcel ingest: free (KC Assessor GIS)
- Geometry backfill: free (KC ArcGIS)
- Canonicalization: ~$65 (Haiku 4.5 × 9 new ZIPs × 6K avg parcels)
- **Total: ~$100 one-time**

**Harvester architecture decision — critical**: query per-filing, not
per-parcel. Scraping WA Courts for every owner name (60K lookups across
10 ZIPs) would rate-limit us. Instead: pull all new probate + divorce
filings in KC for a date range (~1,000-1,200 records/month total), match
party names against canonicalized owners in memory. Scales horizontally —
adding a 11th or 100th ZIP adds zero scraping load since we're already
pulling county-wide filings anyway.

**Success criteria**:
- 15-50 tiered seller leads per ZIP (Tier 1 call-now w/ chain of custody,
  Tier 2 build-now, candidate pool background)
- Signal density varies appropriately by market type
- Cohort amplifiers (policy, STR bans, 1031) measurably lift conversion
- Unit economics: <$5/ZIP/month ongoing
- 3+ beta agents per ZIP report lead quality above par vs existing lists

---

## Architectural decisions (approved, not yet built)

### 1. Harvester infrastructure (replace SerpAPI for primary signal discovery)

**Why**: SerpAPI costs ~$95/ZIP when investigating full Band 2+ scope. At
beta scale (20 agents × 20 ZIPs) that's ~$1,900/month in SerpAPI alone.
Direct harvesters can produce ~90-95% of the same data at near-zero marginal
cost, with better structure and source provenance.

**Sources to build (King County first)**:

| Source | Approach | Est. Build | Value |
|---|---|---|---|
| KC Superior Court | Scrape Odyssey portal for probate + divorce | 2-3 days | Very high — highest-quality single source for life events |
| Washington SOS | Scrape CCFS for LLC/trust filings + officer changes | 1-2 days | Medium — good for LLC ownership transitions |
| Zillow sitemap | Scrape sitemap + listing detail pages | 2 days | High — listing history is core signal |
| Obituary feeds | RSS from Seattle Times + local papers + funeral homes | 1-2 days per source | Very high — direct life event corroboration |
| Legacy.com | Cloudflare-blocked, requires residential proxy (~$30/mo) | 1 day + proxy setup | High but costly |

**Total KC build: 5-8 days focused work.** Each new market (Maricopa,
Mecklenburg) needs its own court portal scraper since they use different
software.

**Keep SerpAPI as narrow fallback**: per-ZIP budget cap (~$25/ZIP/month
max), reserved for specific high-value leads where an agent explicitly
clicks "Deep Signal" for extra validation.

### 2. Signal scoring refinement

**Problem**: current scoring treats `type='probate', trust='high'` as
call_now trigger regardless of actual source. A court filing and a
20-year-old web directory mentioning "probate" currently score the same.

**Fix**: add `source_type` stamp to all signals:
- `court_record` / `legal_filing` / `obituary_rss` → can drive call_now
  alone when strict owner match confirms
- `listing_site` → medium confidence, needs corroboration
- `web_match` → low confidence, goes to "candidate pool" until second signal

**Candidate pool**: new `candidate_leads_v3` table for parcels with one
low-confidence signal. Not shown to agents until a second independent
signal hits, at which point they promote to the visible playbook.

### 3. Within-call_now tiering

Once scope expands, 10+ call_now leads is too many to pick 1-3 from. Add
tiers within call_now:

- **Tier 1 — "Drop everything"**: 2+ HIGH-trust signals across different
  categories (e.g., court probate + obituary). Strict owner match.
  Usually 1-5 per ZIP.
- **Tier 2 — "This week"**: 1 HIGH-trust signal OR 2+ MEDIUM. Strict match.
  Maybe 5-20 per ZIP.
- **Tier 3 — "Worth a call"**: 1 medium signal with strict match, or 1
  high with surname-only. 20-50 per ZIP.

UI: Tier 1 gets its own distinct top section with dedicated badge color.
Tier 2/3 render as sub-headers under "Call Now."

---

## New signal types to add

### 4. Policy / political pressure signals (as multiplier, not evidence)

**Core principle**: a signal applying to everyone in a jurisdiction carries
zero discriminating information. Policy pressure **multiplies** existing
individual signals — it's never a trigger alone.

**Scoring mechanics**:
```
IF parcel matches policy cohort (A ∧ B ∧ C) AND has individual signal
  final_pressure = base_pressure + 0.5 (capped at 3)
ELSE
  final_pressure = base_pressure
```

**Initial cohorts to track**:

**Montana 2023 reassessment (statewide):**
- A: state = MT
- B: assessed value ≥ $1M
- C: tenure ≥ 5 years
- Optional D: individual ownership (LLCs have different calculus)
- Optional E: purchased pre-2010 (biggest basis-to-current gap)

**Washington 2023 capital gains tax (state):**
- A: state = WA
- B: assessed value ≥ $1M (cap gains only on gains > $250K)
- C: tenure ≥ 5 years (enough appreciation to trigger)
- Optional D: individual ownership

**Short-term rental bans (jurisdiction-specific)** — see §5 below.

**Jurisdictional mill levy passage (per-county):**
- A: in jurisdiction that passed a new levy in last 24 months
- B: assessed value in top half of jurisdiction (disproportionate dollar hit)
- C: individual ownership

**Data shape**:
- New `policy_events` table: event metadata (type, jurisdiction, effective
  date, magnitude, who-affected criteria)
- Populated manually initially (Jeremy has domain knowledge; 20-40 events
  covers KC + Maricopa + Mecklenburg + Gallatin meaningfully)
- LLM-monitored feed later (Claude scans Ballotpedia, state legislatures
  weekly for relevant bills)

**UI expression**: dossier shows cohort match as a contextual banner,
NOT as evidence. Example: "Jurisdictional Pressure: Matches Montana 2024
reassessment cohort (long-tenure, $1M+ assessed, individual owner). This
context elevates other signals — not evidence on its own."

**Measurement**: store cohort matches explicitly so we can later measure
conversion lift vs parcels with only individual signals.

### 5. Short-term rental ban tracking

**Why**: STR bans force investors onto a 12-24 month disposition timeline.
Bozeman's 2024 ban is a canonical example — investors who built STR
portfolios must sell, convert to long-term rental (worse ROI), or fight
(usually loses). Same dynamic in Park City UT, Whitefish MT, many tourist
towns.

**Cohort criteria**:
- A: parcel is in a jurisdiction with a recent STR ban or restriction
- B: owner is LLC (investor ownership pattern)
- C: property is a single-family detached (not condo/owner-occ)
- D: purchased in 2017-2023 window (STR investment era)
- Optional E: had active STR business license in affected jurisdiction

**Data sources** (cheapest first):

| Source | Approach | Cost | Coverage |
|---|---|---|---|
| City STR registration records | Direct public lookup (Bozeman has this) | Free | Per-city, complete |
| State lodging tax remittance | Public records request | Free | State-level |
| AirDNA | Commercial API subscription | $50-500/month | National, automated |
| Airbnb/Vrbo scrape | Address-level requires paid proxy + login | $30+/month proxy | Low — platforms hide addresses |

**Recommended path**: start with city registration records for initial
markets (Bozeman, Whitefish, Bellevue, Charlotte). AirDNA subscription
when we expand beyond 3-5 jurisdictions.

**Treatment**: behaves like policy_pressure — a cohort modifier, not a
standalone signal. A Bozeman LLC-owned SFD bought in 2021 is a cohort
match; the cohort match + any listing-history hit or business-license-
lapsed signal = call_now.

### 6. 1031 exchange tracking

**Why**: 1031 creates a hard 45-day / 180-day deadline. Both sides of the
exchange are forced action. Seller-side: just got cash, must redeploy.
Buyer-side: recently acquired, possible to exchange again for disposition.

**What's trackable**:

1. **QI names on deeds** (Phase 1, cheap):
   - Known Qualified Intermediaries: IPX1031, First American 1031, Asset
     Preservation Inc, Investment Property Exchange Services, Accruit,
     Starker Services
   - During canonicalization, flag any owner or prior owner matching a QI
     naming pattern
   - Coverage: ~30-50% of active 1031s
   - Cost: essentially free — just string matching

2. **Temporal pattern matching** (Phase 2, requires deed harvester):
   - Entity sold Property A, same entity bought Property B within 180
     days → flag `suspected_1031_exchange`
   - Requires KC deed harvester to be live first (see §1)
   - Cost: free at query time once harvester runs

3. **Commercial listing keywords** (Phase 3, legal caveat):
   - LoopNet / CoStar listings often say "1031 exchange opportunity"
   - Scrapable but ToS prohibits — judgment call
   - Useful when expanding to commercial/mixed-use

**What's NOT trackable**:
- IRS Form 8824 filings (taxpayer-private)
- QI internal records (proprietary)
- Title company data (private)

**Market fit**: limited to investment property. Residential primary
residences are excluded from 1031. Applies mostly to:
- MT ranches / recreational land
- Bozeman STR portfolios
- Investment residential in tourist markets
- Commercial / mixed-use

Rough estimate: 2-5% of luxury residential parcels have 1031 exposure.
Lower hit rate than probate/obituary but very high signal quality when
present (deadline-forced action).

**Treatment**: confirmed QI-on-deed with strict match → call_now-eligible
as single signal (structurally conclusive). Inferred temporal pattern →
build_now corroborating evidence only.

---

## UI / UX backlog

### 7. CRM layer (from Node.js port)

Contact outcomes, follow-ups, action tracking. Port from
`github.com/jeremyseglem/sellersignal` (~300 lines in server.js + 
`contact_outcome` / `agent_behavior` Supabase tables).

### 8. Mail enrollment + credits + Stripe

Automated mailer sending, credit purchase, send-due automation. Port from
Node.js `/api/mail/*` endpoints + Lob.com integration.

### 9. Territory claim + agent profile

Beta-claim flow, waitlist, territory exclusivity per agent. Port from
Node.js `/api/claim/*` endpoints.

### 10. Investigate-this-parcel button

**Killed — do not build.** Per decision on 2026-04-20, agents browse
pre-investigated leads only. Non-lead parcels get basic dossier (owner,
address, value, tenure, Street View, why-not-selling read) but no
on-demand investigation trigger. Rationale: pricing model complexity
+ unpredictable SerpAPI spend.

---

## Shipped this week (2026-04-17 → 2026-04-20)

- Owner canonicalizer + strict matcher (Haiku 4.5 parser, STRONG vs
  SURNAME_ONLY match tiers, 28 tests passing)
- Admin endpoints: `/rescore/:zip`, `/canonicalize/:zip`, `/geometry/:zip`
- Geometry backfill (99.97% coverage of 98004)
- SPA routing fix
- Richer dossier + lead cards (owner type tag, tenure, signal family,
  property grid, transfer history)
- Stats header with territory metrics
- Search + filter + sort in briefing
- Deep Signal endpoint + UI (LLM-generated scripts with CRITICAL DATA
  HONESTY prompt)
- Six Letters client-side generator + modal
- Value-tier filter removed from investigation scope selector (all Band
  2+ eligible regardless of value)

---

## Open architectural decisions

**D1**: When harvesters are built, do we keep SerpAPI at all or rip it out
entirely? Current thinking: keep as narrow fallback with tight budget gate,
reserved for agent-initiated "Deep Signal" validation clicks.

**D2**: Candidate pool — do we show these to agents in any form (e.g.,
"being watched" badge) or truly hide until corroboration? Leaning toward
hide; surfacing low-confidence leads dilutes agent trust.

**D3**: Policy event curation — full manual, full LLM-monitored, or hybrid?
Leaning hybrid: Jeremy + team handwrite the 20-40 major events initially,
weekly Claude scan catches new passage.

**D4**: Beta launch blockers — what MUST ship vs what can wait? Current
list of "must ship before beta":
- CRM layer (agents need to track outcomes)
- Mail enrollment (the core differentiator)
- Harvester for at least KC probate (makes economics work)
- Territory claim (prevents two agents on same ZIP)

Everything else (policy signals, 1031, STR ban tracking) can ship during
beta as additive features.
