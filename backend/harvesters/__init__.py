"""
SellerSignal v3 Harvesters
==========================

Harvesters replace SerpAPI as the primary signal discovery layer.

Each harvester pulls from ONE primary source (court, recorder, obituary
feed, SOS, etc.) and writes structured rows into raw_signals_v3. A
separate matcher then resolves party_names against owner_canonical_v3
and feeds the existing investigations_v3 / scoring flow.

Architecture principle: query per-filing, not per-parcel.

- Per-parcel queries: 6,658 parcels × 10 ZIPs × monthly = 665K queries/mo
- Per-filing queries: KC has ~10K probate+divorce filings/mo total

Per-filing scales horizontally: adding a new ZIP adds ZERO scraping load
because we already pull county-wide, we just match against more parcels.

Harvester interface (see base.py):

    class MyHarvester(BaseHarvester):
        source_type = 'my_source'
        jurisdiction = 'WA_KING'

        def harvest(self, since_date, until_date=None) -> Iterator[RawSignal]:
            ...
"""
