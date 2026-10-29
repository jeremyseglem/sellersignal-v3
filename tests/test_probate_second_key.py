"""
Tests for the probate second key (Signal lab H2, claude/SIGNAL_LAB.md
2026-10-29 Run 2).

A King County probate decedent that shares a surname plus one other token
with a parcel owner used to be a strict (call-now) match even when the first
names disagree ('Robert Lee Okafor' vs 'Mary Lee Okafor') or both middle
initials are present and differ. The second key keeps those pairs as matches
but stamps them weak. Other sources are untouched.

All names below are invented. No network, no database.

Run: python tests/test_probate_second_key.py
"""
from __future__ import annotations

import sys
sys.path.insert(0, '.')

from backend.harvesters import matcher as M

FAILS = 0
PASSES = 0


def t(label, got, want):
    global FAILS, PASSES
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"         got={got!r}\n         want={want!r}")
        FAILS += 1
    else:
        PASSES += 1


print("═══ _second_key_ok ═══")
ok = M._second_key_ok
t("same first, same middle initial", ok("QUENTIN ARLO VELTMAN", "Quentin A Veltman"), True)
t("same first, middle on one side only", ok("QUENTIN VELTMAN", "Quentin A Veltman"), True)
t("same first, no middles", ok("QUENTIN VELTMAN", "Quentin Veltman"), True)
t("different first, shared middle", ok("QUENTIN ARLO VELTMAN", "Marisol Arlo Veltman"), False)
t("different first, shared middle initial", ok("QUENTIN A VELTMAN", "Dorian A Veltman"), False)
t("same first, middle initials differ", ok("QUENTIN R VELTMAN", "Quentin S Veltman"), False)
t("same first, full middles differ by initial", ok("QUENTIN ARLO VELTMAN", "Quentin Bram Veltman"), False)
t("same first, initial vs full middle agree", ok("QUENTIN B VELTMAN", "Quentin Bram Veltman"), True)
t("trust-formatted owner keeps old floor", ok("QUENTIN ARLO VELTMAN", "Veltman Family Trust"), True)
t("entity owner keeps old floor", ok("QUENTIN ARLO VELTMAN", "Veltman Holdings LLC"), True)
t("single-token filing keeps old floor", ok("VELTMAN", "Quentin Veltman"), True)
t("particle stripped before compare", ok("LAN THI VO", "Lan Thi Vo"), True)
t("empty names do not raise", ok("", ""), True)


print("═══ _dispatch_probate stamps strength ═══")
OWNERS = {
    "0000000001": {"owner_name": "Quentin A Veltman", "owner_type": "individual"},
    "0000000002": {"owner_name": "Marisol Arlo Veltman", "owner_type": "individual"},
    "0000000003": {"owner_name": "Quentin S Veltman", "owner_type": "individual"},
    "0000000004": {"owner_name": "Unrelated Person", "owner_type": "individual"},
}
USE = {pin: {"prop_type": "R"} for pin in OWNERS}


def run(source_type):
    row = {
        "source_type": source_type,
        "signal_type": "probate",
        "document_ref": "00-4-00000-0",
        "event_date": "2026-09-01",
        "party_names": [{"raw": "QUENTIN ARLO VELTMAN", "role": "decedent"}],
    }
    out = M._dispatch_probate(row, OWNERS, USE)
    return {c["parcel_id"]: c["trigger_hint"] for c in out}


kc = run("kc_superior_court")
t("KC: true owner matched strict", kc["0000000001"]["match_strength"], "strict")
t("KC: true owner has no second_key flag", "second_key" in kc["0000000001"], False)
t("KC: shared-middle relative kept but weak", kc["0000000002"]["match_strength"], "weak")
t("KC: weak pair is labelled", kc["0000000002"].get("second_key"), "failed")
t("KC: same first, wrong middle initial is weak", kc["0000000003"]["match_strength"], "weak")
t("KC: unrelated owner not matched", "0000000004" in kc, False)
t("KC: no match is deleted by the key (3 pins)", len(kc), 3)

other = run("wa_state_courts")
t("other source: unchanged, all strict",
  sorted(h["match_strength"] for h in other.values()), ["strict", "strict", "strict"])

print(f"\n{PASSES} passed, {FAILS} failed")
sys.exit(1 if FAILS else 0)
