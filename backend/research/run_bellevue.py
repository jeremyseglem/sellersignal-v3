"""
SellerSignal v2 — End-to-end test on Bellevue 98004.

Feeds:
- Owner DB: /home/claude/kc-data/bellevue-98004-owners.json (6,658 parcels)
- Deed chain: /home/claude/kc-data/EXTR_RPSale.csv (King County sales CSV)
- Obituary signals: harvested during today's session (29 entries, Bellevue WA)
- Retirement signals: 0 (need LinkedIn scraper or press SERP, not wired)
"""
import json
from pathlib import Path

from pipeline import run_pipeline


# ═══════════════════════════════════════════════════════════════════════
# OBITUARY SIGNALS HARVESTED TODAY (April 17, 2026)
# All confirmed Bellevue, WA in obituary text
# ═══════════════════════════════════════════════════════════════════════
OBITUARY_SIGNALS = [
    {"name": "Patricia Ann Rutledge",       "date": "2026-03-20", "context": "Alzheimer's, Bellevue WA",              "source": "dignitymemorial.com"},
    {"name": "Harriet Ellen Brooks",        "date": "2026-03-24", "context": "age 92, Bellevue WA",                   "source": "dignitymemorial.com"},
    {"name": "Steven Robert Williams",      "date": "2026-03-01", "context": "born 1945, long-time Bellevue",         "source": "dignitymemorial.com"},
    {"name": "Katherine Jo Hinman",         "date": "2026-01-01", "context": "Bellevue WA",                            "source": "everloved.com"},
    {"name": "Sarah Nelson",                "date": "2025-08-01", "context": "age 45, Bellevue",                       "source": "everloved.com"},
    {"name": "Liang-Tang Linda Lo Lee",     "date": "2026-02-11", "context": "age 70, Bellevue WA",                    "source": "everloved.com"},
    {"name": "William Henry Walker Jr",     "date": "2026-01-27", "context": "age 75, Bellevue",                       "source": "everloved.com"},
    {"name": "James Patrick Tierney",       "date": "2026-03-29", "context": "age 87, Bellevue civil engineer",        "source": "dignitymemorial.com"},
    {"name": "Craig Groshart",              "date": "2026-02-10", "context": "longtime Bellevue",                      "source": "bellevuereporter.com"},
    {"name": "Donald Eugene Hancock Sr",    "date": "2026-03-01", "context": "Bellevue WA",                            "source": "echovita.com"},
    {"name": "Gerald Edward Jaderholm Sr",  "date": "2026-03-01", "context": "Bellevue WA",                            "source": "echovita.com"},
    {"name": "Polly Anderson",              "date": "2026-02-15", "context": "age 93, Bellevue, widow of Robert",      "source": "seattletimes.com"},
    {"name": "Garth Thomas",                "date": "2025-09-10", "context": "Bellevue home, pancreatic cancer",       "source": "seattletimes.com"},
    {"name": "Gordon Wilson Gilbert Jr",    "date": "2025-05-16", "context": "age 96, Bellevue home",                  "source": "seattletimes.com"},
    {"name": "Linda L Williams",            "date": "2026-02-01", "context": "age 80, born 1945",                      "source": "dignitymemorial.com"},
    {"name": "Helen Petrakou Stoneman",     "date": "2026-01-15", "context": "long-time Bellevue",                     "source": "dignitymemorial.com"},
    {"name": "Eugenia O'Keefe Murphy",      "date": "2026-02-05", "context": "age 81, Bellevue WA",                    "source": "dignitymemorial.com"},
    {"name": "Devorah Weinstein",           "date": "2026-04-11", "context": "age 85, Bellevue WA",                    "source": "seattletimes.com"},
    {"name": "Victor Elfendahl Parker",     "date": "2025-04-15", "context": "longtime home in Medina",               "source": "seattletimes.com"},
    {"name": "Adabelle Whitney Gardner",    "date": "2026-02-15", "context": "born 1930, Bellevue American family",    "source": "seattletimes.com"},
    {"name": "Kemp Edward Hiatt Sr",        "date": "2026-03-15", "context": "age 92, real estate developer",          "source": "seattletimes.com"},
    {"name": "Patricia Ann Dahlin",         "date": "2026-03-25", "context": "age 80, husband Douglas Dahlin",         "source": "seattletimes.com"},
    {"name": "Marilyn Joan Anderson",       "date": "2026-04-11", "context": "age 93, Mercer Island",                  "source": "dignitymemorial.com"},
    {"name": "Rande Kenneth Bidgood",       "date": "2026-03-30", "context": "age 78, Bellevue WA",                    "source": "dignitymemorial.com"},
    {"name": "Sidney Irene Clausen",        "date": "2025-07-15", "context": "plane crash",                            "source": "seattletimes.com"},
    {"name": "Beth Dahlstrom",              "date": "2026-03-01", "context": "Seattle area",                           "source": "seattletimes.com"},
    {"name": "Janny Hartley",               "date": "2026-04-12", "context": "born 1929",                              "source": "seattletimes.com"},
    {"name": "Joan Carol Dehn Whidden",     "date": "2026-03-10", "context": "age 89",                                 "source": "seattletimes.com"},
]

RETIREMENT_SIGNALS: list[dict] = []  # none harvested with working name match yet

OWNERS_PATH = "/home/claude/kc-data/bellevue-98004-owners.json"
DEED_CSV = "/home/claude/kc-data/EXTR_RPSale.csv"
USE_CODES_PATH = "/home/claude/kc-data/bellevue-98004-use-codes.json"
MAILING_PATH = "/home/claude/kc-data/bellevue-98004-mailing.json"
ZILLOW_EVENTS_PATH = "/home/claude/kc-data/bellevue-98004-zillow-events.json"
DIVORCE_CSV = "/home/claude/kc-data/demo-divorce-filings.csv"
RECORDER_CSV = "/home/claude/kc-data/demo-recorder-docs.csv"


def main():
    print("=" * 80)
    print("SellerSignal v2 — Bellevue 98004 signal-first run")
    print("=" * 80)
    print()

    owners_db = json.load(open(OWNERS_PATH))
    use_codes = json.load(open(USE_CODES_PATH))
    mailing_addresses = json.load(open(MAILING_PATH))
    zillow_raw = json.load(open(ZILLOW_EVENTS_PATH))
    zillow_events_by_pin = {k: v for k, v in zillow_raw.items() if not k.startswith("_")}
    print(f"Loaded {len(owners_db)} parcels from owner DB")
    print(f"Loaded {len(use_codes)} parcel use-codes")
    print(f"Loaded {len(mailing_addresses)} mailing records")
    print(f"Loaded Zillow listing events for {len(zillow_events_by_pin)} parcels")
    print(f"Demo divorce filings CSV:  {DIVORCE_CSV}")
    print(f"Demo recorder docs CSV:    {RECORDER_CSV}\n")

    result = run_pipeline(
        zip_code="98004",
        owners_db=owners_db,
        deed_csv_path=DEED_CSV,
        use_codes=use_codes,
        mailing_addresses=mailing_addresses,
        obituary_signals=OBITUARY_SIGNALS,
        retirement_signals=RETIREMENT_SIGNALS,
        zillow_events_by_pin=zillow_events_by_pin,
        divorce_filings_csv=DIVORCE_CSV,
        recorder_docs_csv=RECORDER_CSV,
    )

    # Write outputs
    out_dir = Path("/home/claude/sellersignal_v2/out")
    out_dir.mkdir(exist_ok=True)
    (out_dir / "briefing.md").write_text(result["markdown"])
    (out_dir / "briefing-manifest.json").write_text(
        json.dumps(result["manifest"], indent=2, default=str)
    )

    print()
    print("=" * 80)
    print("PIPELINE COMPLETE")
    print("=" * 80)
    print(f"Leads shipped: {len(result['leads'])}")
    print(f"Reviews total: {len(result['reviews'])}")
    print(f"  Confirmed: {sum(1 for r in result['reviews'] if r.candidate_status == 'confirmed')}")
    print(f"  Weak:      {sum(1 for r in result['reviews'] if r.candidate_status == 'weak')}")
    print(f"  Rejected:  {sum(1 for r in result['reviews'] if r.candidate_status == 'rejected')}")
    print()
    print("Output files:")
    print(f"  {out_dir / 'briefing.md'}")
    print(f"  {out_dir / 'briefing-manifest.json'}")


if __name__ == "__main__":
    main()
