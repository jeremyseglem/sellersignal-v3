"""
Tests for scripts/snapshot_fabric.py (monthly frozen fabric snapshot).

No network: a fake requests session implements the PostgREST and Storage
calls the script makes (select / eq / gt / order / limit; bucket get/create;
object get/post). Run: python tests/test_snapshot_fabric.py
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
from urllib.parse import urlparse

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
import snapshot_fabric as S  # noqa: E402

FAILS = PASSES = 0


def t(label, got, want):
    global FAILS, PASSES
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"         got={got!r}\n         want={want!r}")
        FAILS += 1
    else:
        PASSES += 1


class Resp:
    def __init__(self, code, body=None):
        self.status_code = code
        self._b = body
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        return self._b


class FakeSession:
    def __init__(self, parcels, matches, coverage, bucket=None, live_cols=None):
        self.tables = {"parcels_v3": parcels, "raw_signal_matches_v3": matches,
                       "zip_coverage_v3": coverage}
        self.bucket = bucket          # None | {"public": bool}
        self.objects = {}
        self.calls = []
        self.live_cols = live_cols or {}

    def _filter(self, rows, params):
        out = list(rows)
        for k, v in params.items():
            if k in ("select", "order", "limit"):
                continue
            op, val = v.split(".", 1)
            if op == "eq":
                out = [r for r in out if str(r.get(k)) == val]
            elif op == "gt":
                cast = int if k == "id" else str
                out = [r for r in out if cast(r.get(k)) > cast(val)]
        if "order" in params:
            out.sort(key=lambda r: r[params["order"]])
        sel = params.get("select", "*")
        if sel != "*":
            cols = sel.split(",")
            out = [{c: r.get(c) for c in cols} for r in out]
        if "limit" in params:
            out = out[: int(params["limit"])]
        return out

    def get(self, url, params=None, headers=None, timeout=None):
        path = urlparse(url).path
        self.calls.append(("GET", path, dict(params or {})))
        if path.startswith("/rest/v1/"):
            table = path.split("/")[-1]
            if (getattr(self, "timeout_zip", None) and table == "parcels_v3"
                    and params.get("zip_code") == f"eq.{self.timeout_zip}"
                    and int(params.get("limit", 0)) > 300):
                return Resp(500, {"code": "57014", "message": "canceling statement due to statement timeout"})
            rows = self.tables[table]
            if params.get("select") == "*" and table in self.live_cols:
                rows = [{c: r.get(c) for c in self.live_cols[table]} for r in rows]
            return Resp(200, self._filter(rows, params))
        if path == f"/storage/v1/bucket/{S.BUCKET}":
            return Resp(200, self.bucket) if self.bucket else Resp(400, {"error": "not found"})
        if path.startswith(f"/storage/v1/object/{S.BUCKET}/"):
            key = path[len(f"/storage/v1/object/{S.BUCKET}/"):]
            return Resp(200, {}) if key in self.objects else Resp(400, {"error": "not found"})
        raise AssertionError(path)

    def post(self, url, headers=None, json=None, data=None, timeout=None):
        path = urlparse(url).path
        self.calls.append(("POST", path, None))
        if path == "/storage/v1/bucket":
            self.bucket = {"public": json["public"]}
            return Resp(200, {})
        if path.startswith(f"/storage/v1/object/{S.BUCKET}/"):
            self.objects[path[len(f"/storage/v1/object/{S.BUCKET}/"):]] = data
            return Resp(200, {})
        raise AssertionError(path)


def mk():
    parcels = [{"pin": f"{z}{i:05d}", "zip_code": z, "market_key": "WA_KING",
                "owner_name": f"Owner {i}", "band": 1.0, "lat": 1.0}
               for z in ("98001", "98002") for i in range(2500 if z == "98001" else 3)]
    matches = [{"id": i, "raw_signal_id": i * 10, "pin": "x", "match_strength": "strict",
                "match_method": "m", "match_review_status": None, "matched_at": "t"}
               for i in range(1, 2301)]
    coverage = [{"zip_code": "98001", "market_key": "WA_KING", "status": "live"},
                {"zip_code": "98002", "market_key": "WA_KING", "status": "live"},
                {"zip_code": "98003", "market_key": "WA_KING", "status": "in_development"}]
    return parcels, matches, coverage


def read_gz(b):
    return [json.loads(l) for l in gzip.decompress(b).decode().splitlines()]


print("dry run")
p, m, c = mk()
fs = FakeSession(p, m, c)
man = S.run(S.Client("https://x.supabase.co", "k", fs), "2026-11-01", dry_run=True)
t("dry run uploads nothing", fs.objects, {})
t("dry run creates no bucket", fs.bucket, None)
t("only live ZIPs", man["zips"], 2)
t("parcels counted across pages (2,500 + 3)", man["parcels_total"], 2503)
t("matches keyset across pages", man["matches_total"], 2300)

print("write run")
p, m, c = mk()
fs = FakeSession(p, m, c, live_cols={"parcels_v3": ["pin", "zip_code", "market_key", "owner_name", "band", "lat"]})
man = S.run(S.Client("https://x.supabase.co", "k", fs), "2026-11-01", dry_run=False)
t("bucket created private", fs.bucket, {"public": False})
keys = sorted(fs.objects)
t("files written", keys, ["2026-11-01/manifest.json", "2026-11-01/matches.jsonl.gz",
                          "2026-11-01/parcels/98001.jsonl.gz", "2026-11-01/parcels/98002.jsonl.gz"])
uploads = [cl[1] for cl in fs.calls if cl[0] == "POST" and "/object/" in cl[1]]
t("manifest uploaded last", uploads[-1].endswith("/manifest.json"), True)
rows = read_gz(fs.objects["2026-11-01/parcels/98001.jsonl.gz"])
t("98001 rows round-trip", len(rows), 2500)
t("pins unique", len({r["pin"] for r in rows}), 2500)
t("columns = intended ∩ live (no lat, no invented fields)",
  sorted(rows[0].keys()), sorted(["pin", "zip_code", "market_key", "owner_name", "band"]))
mf = json.loads(fs.objects["2026-11-01/manifest.json"])
b = fs.objects["2026-11-01/parcels/98002.jsonl.gz"]
t("manifest sha256 matches file", mf["files"]["2026-11-01/parcels/98002.jsonl.gz"]["sha256"],
  hashlib.sha256(b).hexdigest())
t("manifest totals", (mf["parcels_total"], mf["matches_total"]), (2503, 2300))
mrows = read_gz(fs.objects["2026-11-01/matches.jsonl.gz"])
t("matches ids complete, in order", [r["id"] for r in mrows], list(range(1, 2301)))

print("immutability")
try:
    S.run(S.Client("https://x.supabase.co", "k", fs), "2026-11-01", dry_run=False)
    t("second write of same label refused", "no error", "error")
except RuntimeError as e:
    t("second write of same label refused", "immutable" in str(e), True)
before = dict(fs.objects)
S.run(S.Client("https://x.supabase.co", "k", fs), "2026-11-01", dry_run=False, force=True)
t("FORCE overrides", sorted(fs.objects) == sorted(before), True)

print("public bucket refused")
p, m, c = mk()
fs = FakeSession(p, m, c, bucket={"public": True})
try:
    S.run(S.Client("https://x.supabase.co", "k", fs), "2026-12-01", dry_run=False)
    t("public bucket refused", "no error", "error")
except RuntimeError as e:
    t("public bucket refused", "PUBLIC" in str(e), True)
t("nothing written to a public bucket", fs.objects, {})

print("ZIP filter")
p, m, c = mk()
fs = FakeSession(p, m, c)
man = S.run(S.Client("https://x.supabase.co", "k", fs), "2026-11-01", dry_run=True, zips_filter={"98002"})
t("filter respected", (man["zips"], man["parcels_total"]), (1, 3))

print("57014 adaptive page size")
p, m, c = mk()
fs = FakeSession(p, m, c)
fs.timeout_zip = "98001"
man = S.run(S.Client("https://x.supabase.co", "k", fs), "2026-11-01", dry_run=True)
t("timeout ZIP still fully read at a smaller page", man["parcels_total"], 2503)
lims = sorted({int(cl[2]["limit"]) for cl in fs.calls if cl[0] == "GET" and cl[2].get("zip_code") == "eq.98001"})
t("page shrank 1000 -> 500 -> 250", lims, [250, 500, 1000])
fs2 = FakeSession(p, m, c); fs2.timeout_zip = "98001"
S.MIN_PAGE, old = 500, S.MIN_PAGE
man2 = S.run(S.Client("https://x.supabase.co", "k", fs2), "2026-11-01", dry_run=True)
t("a ZIP still timing out at MIN_PAGE is recorded, not fatal",
  ([f["zip_code"] for f in man2["failed_zips"]], man2["partial"], man2["parcels_total"]),
  (["98001"], True, 3))
S.MIN_PAGE = old

print(f"\n{PASSES} passed, {FAILS} failed")
sys.exit(1 if FAILS else 0)
