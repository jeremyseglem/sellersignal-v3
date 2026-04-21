# SellerSignal — Post-KC Market Research

Researched 2026-04-20 via public sources. Each market assessed for
harvester feasibility along five dimensions:

1. **Parcel data** — can we ingest the full parcel inventory?
2. **Court records** — can we scrape probate + divorce filings?
3. **Recorder / deed data** — can we scrape transfers, NODs, lis pendens?
4. **STR regulations** — is there a ban cohort to capture?
5. **Signal volume** — how big is the market?

Feasibility tiers:
- **HIGH** — clean APIs, public search forms, no major blockers
- **MEDIUM-HIGH** — scrapable with work, no structural blockers
- **MEDIUM** — some portals are clean, others harder
- **LOW** — significant barriers (authentication, CAPTCHA, ToS)

---

## Maricopa County (Phoenix / Scottsdale) — HIGH FEASIBILITY

**Parcels**: ~1.8M. The Assessor provides a proper JSON API at
`api.mcassessor.maricopa.gov` with documented endpoints for parcel
details, property info, address, valuation history, search. Full
bulk data is also freely downloadable at the Data Sales page
(`mcassessor.maricopa.gov/page/data_sales/`) — no request form
required, everything "as-is" but free.

GIS open data portal (`data-maricopa.opendata.arcgis.com`) provides
free shapefile downloads of parcel geometry and subdivisions.

**Court records**: Superior Court has a public Docket search at
`superiorcourt.maricopa.gov/docket/ProbateCourtCases/caseSearch.asp`
specifically for probate cases. Search by name or case number.
Shows docket entries (not document images) — but party names,
filing dates, case numbers are all exposed.

For document-level access, AZ has a statewide eAccess portal that
serves all counties (including Maricopa). Some document categories
are free, others have fees.

Family Court / Divorce uses the same Superior Court system with the
main case search at `judicialbranch.maricopa.gov`.

**Recorder / deeds**: Maricopa County Recorder at
`recorder.maricopa.gov` — has public document search. Safeguard
Public Service document registration notifications are free.
Structured fields (grantor, grantee, date, instrument type) in
search results.

**STR regulations**: Phoenix has loose rules; Scottsdale has been
trying to tighten. No sweeping Scottsdale ban — AZ state law in 2022
limited local STR bans. Cohort signal weaker here than Bozeman.

**Signal volume**: massive. 1.8M parcels = probably 3K-5K probate
filings/month county-wide, similar for divorces, plus foreclosure
activity. High signal density.

**Build time estimate**: 2-3 days for parcel ingest (API is clean),
2-3 days for probate docket scraper, 1-2 days for recorder scraper.
Maricopa is probably the cleanest harvester build of all markets
because of the API availability.

---

## Mecklenburg County (Charlotte) — MEDIUM-HIGH FEASIBILITY

**Parcels**: ~337,482 residential parcels. Median sale price $418K.
Primary portal is POLARIS at `polaris3g.mecklenburgcountync.gov`
(free public access to ownership, assessment, GIS). Assessor's
Office maintains `cao.mecknc.gov` with property characteristics.

No published JSON API — data access is through the POLARIS UI or
GIS open data portal at `mecklenburg-county-data-dashboard-meckgov.hub.arcgis.com`.
Can script against POLARIS or use the GIS hub for bulk downloads.

Spatialest runs the property record card search at
`property.spatialest.com/nc/mecklenburg`.

**Court records**: NC switched to a statewide eCourts portal in
October 2023. Current cases (post-Oct 9, 2023) are accessible via
Portal at `nccourts.gov/locations/mecklenburg-county`. Search by
party name, case number, etc.

**Critical gap**: pre-October 2023 court records are NOT on the
eCourts portal. For historical cases you must email
`Mecklenburg.Estates@nccourts.org` (estates) or
`Mecklenburg.Criminal@nccourts.org` etc. This is an email-based
request process, not programmatically scrapable.

For our use case (finding CURRENT seller signals), the post-Oct 2023
portal is sufficient — we only need recent probate/divorce activity.
Historical records don't matter for active signals.

**Recorder / deeds**: Mecklenburg Register of Deeds at
`deeds.mecknc.gov/services/real-estate-records` provides online
search of real estate documents recorded since March 1990. Deed
details include parties, dates, instrument types. Scrapable.

**STR regulations**: NC has state preemption issues. Charlotte has
tried to regulate but state law limits what cities can do. Cohort
signal present but weaker than Bozeman.

**Signal volume**: large. 337K parcels in a growing metro.

**Build time estimate**: 2 days parcel ingest (POLARIS scrape or GIS
download), 2-3 days NC eCourts Portal scraper (new system, unknown
quirks), 1-2 days Register of Deeds scraper. Total ~6-8 days.

**Risk**: NC eCourts Portal is new (Oct 2023). System may change.
Worth testing against real cases before committing to scraper work.

---

## Palm Beach County (FL) — HIGH FEASIBILITY

**Parcels**: ~683,820 parcels (591,553 residential, 18,733
commercial, rest). PAPA (Property Appraiser Public Access) at
`pbcpao.gov` is the free public portal — no login required. Search
by owner name, address, or Parcel Control Number (PCN).

GIS REST service at
`maps.co.palm-beach.fl.us/arcgis/rest/services/Parcels/Parcels/MapServer`
provides structured parcel geometry query capability. Standard
ArcGIS REST — easy to batch-query.

Open data portal at `opendata2-pbcgov.opendata.arcgis.com` has
downloadable datasets.

Bulk data available via custom quotes from the Property Appraiser's
office for larger asks.

**Court records**: Palm Beach County Clerk of Court has a separate
portal (not PAPA). Clerk of Court is where probate and civil cases
live. FL statewide court case search exists but quality varies by
county; Palm Beach has its own Clerk of Court public records portal.

Probate in FL moves through the Circuit Court. Palm Beach Clerk
maintains public access records.

**Recorder / deeds**: Palm Beach County Clerk & Comptroller also
maintains the official records (deeds, mortgages, liens). Online
search available via the Clerk's records portal.

**STR regulations**: FL has been fighting state pre-emption battles.
Counties/cities within Palm Beach vary — some beachfront
municipalities restrict STRs, others don't. Palm Beach itself and
parts of Boca have restrictions. Complex per-zip cohort work.

**Signal volume**: huge. Palm Beach County is one of FL's wealthiest.

**Special FL dynamic — Homestead + Save Our Homes portability**:
FL's homestead exemption caps assessed value increases. When owners
sell and move OUT of state, they lose the homestead. This creates a
strong disincentive to move — AND a strong cohort signal when it
DOES happen. Long-tenure homestead properties with recent sale
activity are high-interest.

**Build time estimate**: 2 days parcel ingest (GIS REST is clean),
2-3 days Clerk of Court probate scraper, 2 days recorder scraper.
Total ~6-7 days.

---

## Gallatin County, MT (Bozeman) — MEDIUM FEASIBILITY

**Parcels**: ~43,018 parcels. Much smaller than other markets.
Median assessed value $654,500. iTax system at
`itax.gallatin.mt.gov/` (Tyler Technologies) provides current tax
and parcel search.

State-level MT cadastral at `svc.mt.gov/msl/mtcadastral/` provides
parcel viewer statewide, including Gallatin.

Gallatin County's own GIS at `gis.gallatin.mt.gov` has property
data views.

No JSON API that I found. Scraping Tyler's iTax system is required
for bulk ingest. Tyler Technologies also runs Eagle for recorder
data — consistent vendor, so scrapers can share patterns.

**Court records**: Montana Judicial Branch runs statewide court
records search. Gallatin County Clerk of District Court maintains
probate records. MT has less automated online access than WA/AZ/FL;
more records may require in-person or phone requests.

This is a real gap — smaller counties often have less digitized
data. Testing is required.

**Recorder / deeds**: Gallatin County Clerk & Recorder uses Tyler
Eagle at `GallatinCountyMT-TCMweb.tylerhost.net/eaglecm/web`.
Document search by parties, dates, instrument types. Scrapable.

**STR regulations — STRONG COHORT SIGNAL**:

This is the most interesting STR market we've looked at.

**Ordinance 2149** effective **December 14, 2023** bans all new
Type 3 STRs (non-owner-occupied entire-home rentals) in the City of
Bozeman. Approximately **100 Legacy Type 3 STRs** were grandfathered
in, but:

- Permits cannot be transferred if the property is sold
- Legacy status terminates on permit expiration or property transfer
- If a Legacy Type 3 lapses, the property cannot operate as STR again

This creates a forced-seller cohort: LLC or investor owners of Type
3 properties in residential districts who either:
1. Have already lost Legacy status (lapsed permit)
2. Are fighting ban and losing
3. Are approaching permit renewal and face uncertainty
4. Recently sold/transferred and the property is now effectively
   non-STR-eligible

This is a precise, documented cohort with a clear timeline pressure.

Plus **Gallatin County** (surrounding jurisdiction) is also moving
toward STR elimination per planning commission rulings in 2024.

**Signal volume**: smaller. 43K parcels = probably 60-100 probate
filings/year, 80-150 divorces. Per-parcel signal density matters more
than raw volume because fewer options.

**Advantage for Jeremy**: this is his home market. He knows the
properties, knows the investors, can validate signals by ground-truth
(he knows which LLC-owned property changed hands recently).

**Build time estimate**: 2 days parcel ingest (Tyler iTax scraper +
state cadastral integration), 3 days court scraper (less automated,
more edge cases), 2 days Tyler Eagle recorder scraper. Total ~7 days.

---

## Cross-cutting observations

### Court system landscape by state

No two states run the same court portal software. Each requires its
own scraper:

| State | System | Portal URL | Access |
|---|---|---|---|
| WA | State-wide CF + KC Odyssey | `dw.courts.wa.gov` + KC Clerk | POST form, no CAPTCHA |
| AZ | eAccess + Docket | `judicialbranch.maricopa.gov` | Public, some docs fee |
| NC | eCourts Portal | `nccourts.gov` | Since Oct 2023 only |
| FL | County Clerks | per-county | Varies |
| MT | District Courts | state + per-county | Less digitized |

**Implication**: each state = separate harvester. The PATTERN is
consistent (public search → structured results → match to parcels)
but the implementation is per-state. Budget 5-8 days of harvester
work per new state.

### Assessor data landscape by state

| State | System | Access |
|---|---|---|
| WA | KC Assessor ArcGIS | Free, public REST |
| AZ | Maricopa `api.mcassessor.maricopa.gov` | Free JSON API, bulk downloads |
| NC | POLARIS + GIS hub | Free public, no API |
| FL | PAPA + ArcGIS REST | Free public, clean REST |
| MT | Tyler iTax + state cadastral | Free public, scrapable |

Maricopa and Palm Beach are the cleanest for parcel ingestion. King
County (done) was easy. Mecklenburg and Gallatin require more
scraping work.

### STR cohort signal ranking

1. **Bozeman (Gallatin)** — STRONGEST. Specific ordinance, dated,
   affects ~100 grandfathered properties + all investor-owned SFDs
2. **Scottsdale portion of Maricopa** — MEDIUM. State pre-emption
   limits severity, but some local pressure exists
3. **Palm Beach** — MEDIUM-COMPLEX. Per-municipality variation
4. **Charlotte (Mecklenburg)** — WEAK. NC state law limits
   regulation, narrow cohort

---

## Recommended rollout order post-KC

Based on feasibility × agent availability × signal density:

1. **King County** (in progress)
2. **Maricopa** — cleanest data landscape, largest market, strong
   agent appeal. The Assessor API alone makes this 40% faster than
   other markets.
3. **Palm Beach** — PAPA + ArcGIS REST are clean. FL homestead
   creates unique signal opportunities. Luxury market matches
   Jeremy's profile.
4. **Mecklenburg** — newer eCourts Portal has some risk. Strong
   growing market.
5. **Gallatin** — Jeremy's home market, strong STR signal, but
   smallest volume. Best saved for when we want a Montana proof
   point and Jeremy wants to dogfood.

This order minimizes first-mover risk (MEC eCourts is new, MT is
less automated) and gets harvester pattern proven on clean
infrastructure (AZ, FL) before tackling the harder systems.

### Per-market cost estimate

Same pattern as KC: parcel ingest is free, Haiku canonicalization is
~$65 per county, harvester build is 5-8 days of work. Ongoing: ~$0
in compute, maybe a residential proxy ($30/month ceiling) if a
target site needs one.

**Full rollout cost across all 5 markets (KC + 4 new)**:
- One-time dev: 30-40 focused days (5-8 per market)
- Canonicalization: ~$325 total
- Ongoing: ~$50-75/month total infrastructure

Versus SerpAPI equivalent at beta scale: $1,900+/month forever.

---

## Honest risks

1. **MT portal data quality unknown.** Gallatin may have less
   automated access than major metros. Testing required.
2. **NC eCourts portal is new.** October 2023 system, unknown
   scraping quirks. Test against real probate cases before
   committing.
3. **FL Clerk of Court is per-county complex.** Palm Beach's system
   needs hands-on exploration.
4. **STR cohort is small signal outside MT.** Don't over-index on
   this as primary value prop in AZ/NC/FL.
5. **Scrapers break.** Expect 2-4 hrs/month per source in
   maintenance across all markets. At 5 markets × 3 sources each =
   20-60 hrs/year of scraper upkeep.
6. **Government portals sometimes block IP ranges.** Residential
   proxy may be needed for 2-3 sources across the portfolio.

---

# Major Metro Expansion Research

Researched 2026-04-20. Adds LA County, NYC (5 boroughs), Miami-Dade,
Cook County (Chicago), and Denver.

## Los Angeles County — MEDIUM FEASIBILITY (big caveat)

**Scale**: ~2.4M parcels. Includes Beverly Hills, Malibu, Santa
Monica, West Hollywood as separate cities under one county assessor.
Probably the single largest luxury real estate market in the US.

**Parcels**: Free downloads via LA County Enterprise GIS
(`egis-lacounty.hub.arcgis.com`) and LA City Geohub
(`geohub.lacity.org`). Bulk shapefiles, CSV exports. No API but
downloads are fine for ingest.

**Court records — THE CATCH**: LA Superior Court charges public
access fees per search under California Rule of Court 2.506 / Gov
Code 68150(l). Each name lookup on `lacourt.org/paos/v2public/CivilIndex/`
incurs a fee. This is unique — the only market we've researched
with explicit per-search pricing.

Workarounds:
1. **Commercial aggregators** (UniCourt, Trellis.Law) scrape LA
   Superior daily and resell via API. They eat court fees,
   probably $0.05-0.20/query at scale or subscription tiers.
2. **Batch by date range** — if fees are per-query not per-result,
   pull all new probate filings in a time window as one query.
   Needs verification.

Signal volume: LA Superior had **12,490 probate cases in 2021**,
**13,063 in 2022**. Massive if affordable.

**Recorder**: LA County Registrar-Recorder/County Clerk
(`rrcc.lacounty.gov`). Public online search, scrapable. NODs, lis
pendens, trustee sales.

**STR**: LA home-sharing ordinance + per-city regs (Beverly Hills
stricter, West Hollywood strictest). Cohort varies.

**Luxury fit**: enormous. BH, Malibu, Holmby Hills, Bel-Air,
Brentwood — multi-generational wealth estates with consistent
probate activity.

**Build**: 3-4 days parcel, 3-5 days court via aggregator (or 5-8
direct), 2-3 days recorder. 8-13 total.

**Net**: highest-reward, most complicated. Save for Phase 3.

---

## New York City — HIGH FEASIBILITY (gold standard data)

> **NYC COOP / CONDO NUANCE.** Two structural data-access facts
> worth knowing upfront. Both affect the approach but neither
> makes NYC infeasible.
>
> **Condos**: indexed by Borough-Block-Lot (BBL). Condo buildings
> occupy one tax lot per building, so PLUTO (the first-hit NYC
> parcel dataset) returns the sponsor entity or condo association
> as "owner" rather than individual unit owners. Per-unit
> ownership exists in ACRIS via condo declarations but requires
> cross-referencing unit numbers to deed records. Doable, adds
> a couple days of engineering vs a KC-style scan.
>
> **Coops** (~70-75% of Manhattan apartments): cooperative
> corporation owns the building. "Owners" are shareholders with
> proprietary leases. Unit transfers are stock transfers, NOT
> deeds — so they don't appear in ACRIS as DEEDs.
>
> **HOWEVER — coops are not invisible.** They're documented in
> parallel data streams:
>
> 1. **UCC-1 Financing Statements with Cooperative Addendum**
>    (NY Form UCC1CAd, revised 2001). When a coop is purchased
>    with a loan (majority of cases), the lender MUST file a
>    UCC-1 with the NYC City Register. Contains: debtor's exact
>    full legal name (matched to NY ID per 2014 law), number of
>    shares, apartment number, complete building address, and
>    city tax block/lot. **This is ACRIS-filed and public.**
>
> 2. **UCC-3 Termination Statements**. Filed when the loan is
>    paid off (typically at sale). Marks owner exit + turnover.
>
> 3. **RPTT (Real Property Transfer Tax)** filings. NYC requires
>    RPTT on every coop transfer for tax purposes. Public via
>    NYC Department of Finance.
>
> 4. **Surrogate's Court probate filings**. When a coop
>    shareholder dies, the executor files an inventory listing
>    "X shares of [Coop Corp], appurtenant to Apt XY at
>    [address]." The seller signal we actually want shows up
>    here as text.
>
> **Query direction matters**: searching ACRIS for DEED
> documents misses coops entirely. Searching for UCC-1 / UCC-3 /
> RPTT document types surfaces them cleanly. Same ACRIS system,
> different document-type filter.
>
> **Coverage by financing type**:
> - Financed coop buyers (~60-70%): fully captured via UCC-1
> - Cash coop buyers (~30-40%, mostly luxury Manhattan): no
>   UCC-1, but still captured via RPTT at purchase + probate at
>   death (which is when the seller signal hits anyway)
> - Every coop transfer regardless of financing: RPTT captures
> - Every coop decedent: Surrogate's Court captures
>
> **Practical net**: NYC coops require a harvester that
> understands UCC-1CAd + RPTT document types on top of standard
> deed parsing. Maybe 2-3 extra days of engineering. Then coops
> are as visible as condos.
>
> **Remaining gap**: a cash-buyer coop owner who's alive and has
> no court activity is hard to tie to a unit proactively. But
> the moment any seller signal hits them (probate, divorce,
> UCC-3 termination from refinance activity), they become
> visible. For seller intelligence this is fine — we care about
> pressure events, not a static ownership roster.

**Scale**: ~1M parcels across 5 boroughs (Manhattan, Brooklyn,
Queens, Bronx, Staten Island).

**Parcels + Deeds — best public real estate data in America**:

**ACRIS** (Automated City Register Information System) via NYC Open
Data provides free downloadable CSVs:
- `ACRIS - Real Property Master` — every recorded document
- `ACRIS - Real Property Legals` — parcel + legal descriptions
- `ACRIS - Real Property Parties` — all grantors/grantees
- `ACRIS - Real Property References` — cross-references
- `ACRIS - Real Property Remarks` — document notes

Full history back to 1966. Covers 4 of 5 boroughs natively (Staten
Island via Richmond County Clerk). A GitHub project
(`fitnr/acris-download`) provides a Makefile that downloads the
entire dataset and imports into PostgreSQL with one command.
**Easiest ingest of any market we've researched.**

**Court records — Surrogate's Court handles probate** per borough.
Unified Court System eCourts (`nycourts.gov`) provides online case
search by party name. Scrapable.

**STR — HUGE COHORT SIGNAL**: NYC **Local Law 18** (September 2023)
requires STR host registration with the Mayor's Office of Special
Enforcement. Effectively banned most Airbnb — **~97% drop in listings**.
Largest forced-sell cohort of any US market. Pre-2023 investor STR
portfolios are now either selling at discount, converting to
long-term rental (money-losing), or operating illegally.

Registered/rejected hosts are public record via NYC Open Data.

Plus: **421a tax abatement expirations** are a known NYC seller
signal. Properties with expiring 421a benefits face sudden tax
hikes.

**Build**: 2-3 days parcel+deed (ACRIS is clean), 3-4 days
Surrogate's Court (5 boroughs), 1-2 days LL18 tracker. ~7-9 total.

**Net**: probably the single highest-value market. Best data, huge
luxury inventory, unique LL18 cohort.

---

## Miami-Dade County — HIGH FEASIBILITY

**Scale**: ~900K parcels. Miami Beach, Fisher Island, Coral Gables,
Coconut Grove, Bal Harbour. Heavy international buyer presence =
LLC/trust ownership.

**Parcels**: Bulk CSV via `bbs.miamidadepa.gov` — free account with
"credits" system (mild friction). Property Appraiser search free at
`miamidade.gov/pa`. GIS Open Data Hub at `gis-mdc.opendata.arcgis.com`.

**Court / recorder**: Miami-Dade Clerk of Court handles both court
records and deed recording. Online search available. FL homestead +
SOH portability = strong cohort for out-of-state movers.

**STR**: FL pre-emption battles. County-level loose. City-level
varies (Miami Beach strict, Miami moderate).

**Build**: 2-3 days parcel, 2-3 days Clerk of Court. ~5-6 total.

---

## Cook County, IL (Chicago) — HIGH FEASIBILITY

**Scale**: ~1.8M parcels across Chicago + 133 other municipalities.
Luxury (Gold Coast, Lincoln Park) + working-class + investment.

**Parcels + Deeds**: Excellent open data:
- Cook County Open Data Portal (`datacatalog.cookcountyil.gov`) —
  assessor parcel sales, property tax, full datasets
- Cook Central GIS Hub (`hub-cookcountyil.opendata.arcgis.com`)
- **Clerk absorbed Recorder of Deeds in 2020**, records unified.
  Public search by address/PIN/grantor/grantee at
  `cookcountyclerkil.gov/recordings/search-recordings`

**Court**: Circuit Court of Cook County. Public docket lookup.
Scrapable.

**STR**: Chicago's 2016 Shared Housing Ordinance requires license,
unit caps. Moderate cohort — less severe than NYC.

**Build**: 2-3 days parcel, 3-4 days court, 1-2 days deed (unified
now). ~6-9 total.

**Net**: clean infrastructure, large market.

---

## Denver (City & County combined) — HIGH FEASIBILITY

**Scale**: ~205K parcels. Smaller but with strong luxury pockets
(Cherry Creek, Washington Park, Highlands) and investor activity.

**Parcels**: Free. `denvergov.org/Property` + Spatialest.

**Recorder**: Denver Clerk & Recorder has 11M+ documents since 1859
online. Free public search.

**Court**: Denver County Court + CO Second Judicial District
(probate). State search at `coloradocourts.gov`. Scrapable.

**STR — STRONG COHORT**: Denver requires STR to be primary
residence, single-STR-per-host rule. Aggressive enforcement since
2017. ~80% of commercial investor STR operations exited.

**Build**: 1-2 days parcel, 2-3 days court, 1-2 days recorder.
~5-6 total.

**Net**: clean data, strong STR cohort, smaller volume but quality.

---

## Cross-metro comparison

| Market | Parcels | Data Access | STR Cohort | Build Days |
|---|---|---|---|---|
| **NYC (5 boroughs)** | ~1M | **BEST (ACRIS)** | **STRONGEST** (LL18) | 7-9 |
| **LA County** | ~2.4M | Parcels free, courts FEE | Medium (per-city) | 8-13 |
| **Cook County** | ~1.8M | Excellent open data | Medium | 6-9 |
| **Miami-Dade** | ~900K | Good + credits | Weak county-level | 5-6 |
| **Denver** | ~205K | Very clean | **Strong** (primary-res rule) | 5-6 |

---

## Revised 10-market rollout order

**Phase 1 — Prove harvester model on free-data markets**:
1. King County (in progress)
2. **Maricopa** — cleanest API
3. **Cook County** — clean open data, unified Clerk/Recorder
4. **NYC — conditional on property mix**. ACRIS is gold standard
   for what it covers, but see coop/condo caveat above. Only
   prioritize here if beta agents work Brooklyn brownstones,
   Queens/Staten Island single-family, or new-development condos
   (with extra unit-level engineering). Skip or deprioritize if
   agents work Manhattan coops.

**Phase 2 — Expand luxury coverage**:
5. **Palm Beach** — PAPA clean, FL homestead signals
6. **Miami-Dade** — FL homestead + international buyers
7. **Denver** — strong STR cohort, smaller scale

**Phase 3 — Special cases**:
8. **LA County** — highest-value but court fee complication; solve
   via Trellis.Law/UniCourt integration. Only worth it when luxury
   agent pipeline justifies
9. **Mecklenburg** — NC eCourts is new, test carefully

**Phase 4 — Home market**:
10. **Gallatin (Bozeman)** — smallest volume, strongest STR cohort,
    Jeremy's market

---

## Full 10-market rollout economics

- **Dev**: 60-80 focused days total (each state's courts differ)
- **Canonicalization**: ~$1,000-1,500 total (Haiku 4.5)
- **Ongoing**: ~$100-150/month infrastructure
- **LA aggregator fees** if pursued: +$100-200/month
- **Total beta-scale infrastructure for all 10 markets: $200-400/month**
- **vs SerpAPI equivalent: $19,000+/month**

**50-100x improvement in unit economics at full rollout.**

---

## Honest bottom line

**The harvester model is feasible across every major US metro.**

Variations:
- Data access: NYC > Maricopa > Cook > Palm Beach > Miami-Dade >
  Denver > KC > LA > Mecklenburg > Gallatin
- Signal volume: LA > NYC > Cook > Maricopa > KC > Miami-Dade >
  Palm Beach > Denver > Mecklenburg > Gallatin
- STR cohort: NYC > Bozeman > Denver > Scottsdale (Maricopa) > LA >
  Chicago > others (weak)
- Luxury agent appeal: LA > NYC > Palm Beach > Miami-Dade > KC >
  Denver > Gallatin > others

**No market has a structural blocker.** LA's per-search court fee is
solvable via commercial aggregator. Everything else scrapable.

**Real constraint is engineering time.** Each state's courts are
their own harvester. 5-10 days of focused work per state. Scaling
requires either hiring a data engineer or a multi-month harvester
sprint.

The thesis holds: no-cost-per-scan seller intelligence works in
every market that matters.
