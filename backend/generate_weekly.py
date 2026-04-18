#!/usr/bin/env python3
"""
generate_weekly.py — Full weekly pipeline runner.

  1. Run selector → this-weeks-picks.json + update playbook-history.json + outcomes.json
  2. Render PDF  → this-weeks-plays-auto.pdf
  3. Build XLSX  → this-weeks-tracking.xlsx (agent fills this in)
  4. Print summary

Usage:
  python3 generate_weekly.py
"""
import sys
sys.path.insert(0, '/home/claude/sellersignal_v2')

from weekly_selector import generate_weekly_playbook
from render_playbook import render
from generate_tracking_sheet import build_workbook
from datetime import datetime

# 1. Run selection
result = generate_weekly_playbook()

# 2. Render PDF
rendered = render(
    '/home/claude/sellersignal_v2/out/this-weeks-picks.json',
    '/home/claude/sellersignal_v2/out/this-weeks-plays-auto.pdf',
)

# 3. Build tracking XLSX
tracking_path, tracking_size = build_workbook(
    '/home/claude/sellersignal_v2/out/this-weeks-picks.json',
    '/home/claude/sellersignal_v2/out/this-weeks-tracking.xlsx',
)

# 4. Summary
wk = datetime.now().strftime('%B %-d, %Y')
print(f"\n═══ SellerSignal Weekly Playbook — Week of {wk} ═══\n")
print(f"Recent-week exclusions:   {result['excluded_for_recency']}")
print(f"Outcome-based exclusions: {result['excluded_for_outcome']}")

shortfalls = result.get('shortfalls', {})
total_short = sum(shortfalls.values())
if total_short:
    print(f"\n⚠  Section shortfalls:")
    for section, n in shortfalls.items():
        if n:
            print(f"    {section.replace('_',' ').upper():18} short by {n}")
    print()
else:
    print()

for section, title in [('call_now', 'CALL NOW'),
                        ('build_now', 'BUILD NOW'),
                        ('strategic_holds', 'STRATEGIC HOLDS')]:
    print(f"── {title} ──")
    for L in result[section]:
        val = (L.get('value') or 0) / 1_000_000
        print(f"   {L.get('address','—'):38} ${val:>6.1f}M   {L.get('signal_family','')}")
    print()

print(f"✓ Playbook PDF:   {rendered['path']}")
print(f"  ({rendered['size']:,} bytes · {rendered['pages']} page)")
print(f"✓ Tracking XLSX:  {tracking_path}")
print(f"  ({tracking_size:,} bytes)")

