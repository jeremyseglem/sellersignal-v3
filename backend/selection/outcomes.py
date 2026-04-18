"""
outcomes.py — Outcome state for lead tracking.

Schema: outcomes.json
{
  "leads": {
    "<pin>": {
      "pin": "...",
      "address": "...",
      "status": "NEW | CONTACTED | RESPONDED | MEETING | LISTING | LOST | DEAD",
      "first_surfaced": "2026-04-18",
      "last_surfaced": "2026-04-18",
      "contact_date": null,
      "response": null,
      "next_step": null,
      "notes": null,
      "agent": null,
      "updated_at": "..."
    }
  }
}

Rules for selector integration:
  DEAD → permanently excluded from future selection
  LOST → excluded for 90 days, then eligible again
  LISTING, MEETING → excluded (already converted/in-progress)
  NEW, CONTACTED, RESPONDED → eligible to resurface after 4-week cooldown
"""
import json, os
from datetime import datetime, timedelta

OUTCOMES_PATH = '/home/claude/sellersignal_v2/out/outcomes.json'


def load_outcomes():
    if not os.path.exists(OUTCOMES_PATH):
        return {'leads': {}}
    return json.load(open(OUTCOMES_PATH))


def save_outcomes(outcomes):
    with open(OUTCOMES_PATH, 'w') as f:
        json.dump(outcomes, f, indent=2, default=str)


def register_surfaced(outcomes, picks, week_of):
    """Mark these picks as surfaced this week. Creates NEW records if not present."""
    now = datetime.now().isoformat()
    for L in picks:
        pin = L['pin']
        rec = outcomes['leads'].get(pin, {
            'pin': pin,
            'address': L.get('address'),
            'status': 'NEW',
            'first_surfaced': week_of,
            'contact_date': None,
            'response': None,
            'next_step': None,
            'notes': None,
            'agent': None,
        })
        rec['last_surfaced'] = week_of
        rec['updated_at'] = now
        outcomes['leads'][pin] = rec
    return outcomes


def get_excluded_pins(outcomes):
    """Pins to permanently or temporarily exclude based on outcome status."""
    excluded = set()
    now = datetime.now()
    for pin, rec in outcomes['leads'].items():
        status = rec.get('status', 'NEW')
        if status == 'DEAD':
            excluded.add(pin)  # permanent
        elif status in ('LISTING', 'MEETING'):
            excluded.add(pin)  # already in-progress
        elif status == 'LOST':
            # 90-day cooldown
            last = rec.get('updated_at') or rec.get('last_surfaced')
            if last:
                try:
                    last_dt = datetime.fromisoformat(last.replace('Z', '+00:00'))
                    if now - last_dt < timedelta(days=90):
                        excluded.add(pin)
                except Exception:
                    pass
    return excluded


def status_for(outcomes, pin):
    return outcomes['leads'].get(pin, {}).get('status', 'NEW')
