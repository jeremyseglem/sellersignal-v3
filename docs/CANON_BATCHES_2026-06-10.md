# Pending canon batches — submitted 2026-06-10
Ingest each when status=ended:
POST /api/admin/canon-batch/ingest/{batch_id}?zip_code={zip}  (X-Admin-Key)

| zip | batch_id | unique names |
|-----|----------|--------------|
| 85377 | msgbatch_01CEL2Su5kgECED3So7TYAuV | 2405 |
| 98008 | msgbatch_01V7fVepb2yphfW1WnxH5Doe | 7441 |
| 98065 | msgbatch_01KnM8hwUNXA455LNpfRLcvC | 4692 |
| 98028 | msgbatch_01GG3Zho1MJA9euMFznWuYip | 7026 |
| 98011 | msgbatch_0192i7UUa2zAK92vPiee44NK | 7466 |
| 98177 | msgbatch_01G18HfSJQVqizYy2fwv2FL9 | 7302 |
| 98102 | msgbatch_01GzXPBu1eFjoBrhUbtwWL6p | 5275 |
| 98109 | msgbatch_0179qCYoBFPj3Uk7bjD5NYnA | 5836 |
| 98275 | msgbatch_01ErzhUzHVk4BEWmfhRc4w39 | 1848 |
| 98012 | msgbatch_01WVykGWCW9fqw57TwWKyqgS | 9855 |
| 98021 | msgbatch_01PU2HwAL9wuCUfzQ1pVDFiV | 4938 |

Remaining 18 AZ ZIPs: not yet submitted (pending 85377 quality check).
canonicalize-autofill: PAUSED — resume after all ingests.
NOTE: a couple of submits required retries after "Server disconnected" — if any
duplicate batches exist at Anthropic for the same ZIP, ingest is idempotent.

## AZ batches submitted later 2026-06-10 (ingest with ?zip_code= as above)
| 85018 | msgbatch_01C926QRuU486EGM3mQpfRGq | 10736 |
| 85028 | msgbatch_012NqZgFc76V93EfeX31sj97 | 8129 |
| 85050 | msgbatch_013Ey2aphSqSqCf78NbhZW5r | 11675 |
| 85054 | msgbatch_01GTq7ZNmn3FMMvX3HZLCj8i | 3592 |
| 85085 | msgbatch_013J3b7SAW2wzynG2PJG3bjP | 9482 |
| 85086 | msgbatch_01GFyj2KSZgzPzPRUcHmBDhv | 15446 |
| 85207 | msgbatch_01KZRWQPeKjLpQivPR2AB6E7 | 17140 |
| 85249 | msgbatch_01VuTNZTHPbYrmQG5P7iMfGL | 17608 |
| 85253 | msgbatch_019gLZhTNMWWHHkDoXHgJudN | 8756 |
| 85255 | msgbatch_01T8erYDjzuZyiENXyj8xRZV | 20496 |
| 85259 | msgbatch_01MFXPh4RGwLZZnsnLro9QpS | 9158 |
| 85260 | msgbatch_01NsLFaFCxZ8QVKSX9Li1KKr | 15303 |
| 85262 | msgbatch_01H35GS1kVJgqU9Dkqx7QzGM | 9967 |
| 85266 | msgbatch_01288WgZk6MHxUasam5dWeRf | 6835 |
| 85268 | msgbatch_0113utajZhG5sUJJ6V5fTCJa | 13742 |
| 85284 | msgbatch_01VHTV3WPmUoZYLDsNvmKEuY | 6773 |
| 85298 | msgbatch_018itJupNK13Lq751qKU2gk6 | 15309 |
| 85331 | msgbatch_01HJexkyiiAAkDA1aCd1v18v | 14373 |

Ingested so far: 85377, 98008, 98065, 98028, 98011, 98109, 98275, 98012.
Still in_progress at last poll: 98177, 98102, 98021.
85254 re-run: NOT submitted (Jeremy's call; would fix 439 low-conf rows, ~$2).
