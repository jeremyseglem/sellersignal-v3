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
