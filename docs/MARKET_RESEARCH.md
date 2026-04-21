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
