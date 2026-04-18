"""
SellerSignal — Synthesis Layer (Layer 3 of the 3-layer architecture)

Layer 1: Deterministic gating (rules over KC/ArcGIS/sales/mailing)
Layer 2: Evidence harvest (dossier compilation, done)
Layer 3: LLM synthesis (THIS MODULE)

For each dossier, this module calls the Anthropic API with a carefully-tuned
prompt and receives back a structured analyst-style narrative per lead.

Production costs (estimated):
  - Input: ~1,500 tokens per dossier (JSON + prompt)
  - Output: ~350 tokens per narrative
  - Claude Sonnet 4.6 pricing ≈ $0.003 per input 1K + $0.015 per output 1K
  - Per-lead cost: ~$0.010

  For top 500 Band 1+2 leads refreshed monthly: ~$5/month in API.
  For top 2,000 Eastside leads refreshed quarterly: ~$20/quarter.

Usage:
    python3 synthesize_lead_api.py --cohort band1
    python3 synthesize_lead_api.py --cohort top100
    python3 synthesize_lead_api.py --pin 1925059138  # single-lead test
"""
import json
import os
import sys
import argparse
import time
from typing import Optional

# Prompt is the single most important piece of this module.
# It's been refined against the 5 prototype syntheses to produce consistent output.

SYNTHESIS_SYSTEM_PROMPT = """You are a real estate intelligence analyst specializing in \
Eastside Seattle luxury markets. Your job is to read a property lead dossier and produce \
an analyst-style narrative that tells an agent what the data actually means, what's \
inferred vs confirmed, how to approach the owner, and what to avoid.

You must:
- Make inferences the structured data cannot — recognize patterns across the deed chain, \
ownership structure, mailing address, obit matches, and neighborhood context.
- Be honest about confidence. Weak matches are weak; flag them.
- Recommend specific cultivation angles that fit the owner's profile (trust structure, \
age, neighborhood, entity type).
- Never hallucinate. If you infer something, mark it as inference. Do NOT invent \
relationships, names, or events not supported by the dossier.
- Never use obit matches as confirmed death unless the match is strong (2+ given names \
+ uncommon surname or clear age/location alignment).

Output format (exactly these 5 sections, markdown-compatible):
### WHAT'S ACTUALLY HAPPENING
[2-3 sentences, plain English reading of what the data tells us]

### CONFIDENCE CHECK
[Honest assessment of what's confirmed vs inferred; flag weak links]

### CULTIVATION APPROACH
[Specific first-contact strategy — channel, angle, positioning]

### WHAT TO AVOID
[What NOT to do — common mistakes for this profile]

### CONFIDENCE ADJUSTMENT
[Net adjustment to inevitability score, in range -15 to +15 points, with reasoning]

Total output must be under 300 words. Use specific names, numbers, and addresses from \
the dossier. Write in confident, direct prose — no hedging weasel-words."""


def build_user_prompt(dossier: dict) -> str:
    """Convert a compiled dossier into the user-prompt format for the API."""
    return f"""LEAD DOSSIER:

Property: {dossier['address']} ({dossier['zip']})
Assessed value: ${dossier['value']:,}
Current band: {dossier['signal']['band']} — {dossier['signal']['band_label']}
Signal family: {dossier['signal']['family']} / {dossier['signal']['sub']}
Inevitability: {dossier['signal']['inevitability']*100:.0f}%
Timeline: {dossier['signal']['timeline_months']} months

OWNER:
Name: {dossier['owner']['name']}
Type: {dossier['owner']['type']}

{'GRANTOR (for trust): ' + dossier['grantor']['name'] if dossier.get('grantor') else ''}

TENURE:
{json.dumps(dossier.get('tenure') or {}, indent=2)}

DEED CHAIN (last 5):
{json.dumps(dossier.get('deed_chain_summary') or [], indent=2, default=str)}

MAILING:
{json.dumps(dossier.get('mailing') or {}, indent=2)}

{'OBIT MATCH: ' + json.dumps(dossier['obit_match'], indent=2, default=str) if dossier.get('obit_match') else ''}

{'CONVERGENT SIGNAL FAMILIES: ' + ', '.join(dossier.get('convergent_families') or []) if dossier.get('convergent_families') else ''}

NEIGHBORHOOD:
{json.dumps(dossier.get('neighborhood') or {}, indent=2)}

ESTIMATED OWNER AGE: {dossier.get('estimated_age') or 'unknown'}

{'RATIONALITY FLAGS: ' + json.dumps(dossier['rationality'], indent=2) if dossier.get('rationality') else ''}

Analyze this lead per the prescribed output format."""


def synthesize_via_api(dossier: dict, client=None) -> dict:
    """Call Anthropic API with the dossier, return structured synthesis."""
    try:
        from anthropic import Anthropic
    except ImportError:
        return {'error': 'anthropic package not installed. Run: pip install anthropic --break-system-packages'}

    if client is None:
        # Expects ANTHROPIC_API_KEY env var
        client = Anthropic()

    user_prompt = build_user_prompt(dossier)

    try:
        response = client.messages.create(
            model='claude-sonnet-4-5',  # fast+smart tradeoff; can swap to opus for deeper analysis
            max_tokens=500,
            system=SYNTHESIS_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': user_prompt}],
        )
        text = response.content[0].text
        return {
            'synthesis_markdown': text,
            'tokens_in': response.usage.input_tokens,
            'tokens_out': response.usage.output_tokens,
            'model': 'claude-sonnet-4-5',
        }
    except Exception as e:
        return {'error': str(e)}


def parse_synthesis(text: str) -> dict:
    """Parse the 5-section markdown output into a dict."""
    sections = {
        'whats_happening': '',
        'confidence_check': '',
        'cultivation_approach': '',
        'what_to_avoid': '',
        'confidence_adjustment': '',
    }
    section_map = {
        "WHAT'S ACTUALLY HAPPENING": 'whats_happening',
        'CONFIDENCE CHECK': 'confidence_check',
        'CULTIVATION APPROACH': 'cultivation_approach',
        'WHAT TO AVOID': 'what_to_avoid',
        'CONFIDENCE ADJUSTMENT': 'confidence_adjustment',
    }
    current = None
    buffer = []
    for line in text.splitlines():
        line = line.strip()
        matched = False
        for header, key in section_map.items():
            if header in line.upper():
                if current:
                    sections[current] = '\n'.join(buffer).strip()
                current = key
                buffer = []
                matched = True
                break
        if not matched and current:
            buffer.append(line)
    if current:
        sections[current] = '\n'.join(buffer).strip()
    return sections


def run(cohort_filter: str = 'band1', single_pin: Optional[str] = None, dry_run: bool = False):
    dossiers_path = '/home/claude/sellersignal_v2/out/synthesis-cohort-dossiers.json'
    dossiers = json.load(open(dossiers_path))

    # Apply cohort filter
    if single_pin:
        dossiers = [d for d in dossiers if d['pin'] == single_pin]
    elif cohort_filter == 'band1':
        dossiers = [d for d in dossiers if d['signal']['band'] == 1]
    elif cohort_filter == 'top100':
        dossiers = sorted(dossiers, key=lambda x: -(x['signal'].get('rank_score') or 0))[:100]

    print(f"Processing {len(dossiers)} dossiers via synthesis layer...")

    if dry_run:
        print("\n=== DRY RUN — showing prompt that would be sent for first dossier ===\n")
        if dossiers:
            print(build_user_prompt(dossiers[0])[:2000])
        return

    results = []
    total_in = total_out = 0
    for i, d in enumerate(dossiers, 1):
        print(f"  [{i}/{len(dossiers)}] {d['address']}...", end=' ', flush=True)
        result = synthesize_via_api(d)
        if 'error' in result:
            print(f"ERROR: {result['error']}")
        else:
            parsed = parse_synthesis(result['synthesis_markdown'])
            total_in += result['tokens_in']
            total_out += result['tokens_out']
            print(f"done ({result['tokens_in']}+{result['tokens_out']} tokens)")
            results.append({
                'pin': d['pin'], 'address': d['address'], 'value': d['value'],
                'band': d['signal']['band'],
                'synthesis_raw': result['synthesis_markdown'],
                'synthesis_parsed': parsed,
                'tokens_in': result['tokens_in'],
                'tokens_out': result['tokens_out'],
            })
        time.sleep(0.2)  # modest rate-limiting

    est_cost = (total_in * 0.003 / 1000) + (total_out * 0.015 / 1000)
    print(f"\nTotal tokens: {total_in} in, {total_out} out")
    print(f"Estimated API cost: ${est_cost:.2f}")

    out_path = '/home/claude/sellersignal_v2/out/synthesized-leads.json'
    with open(out_path, 'w') as f:
        json.dump({'results': results, 'total_cost_usd': est_cost,
                   'cohort': cohort_filter}, f, indent=2)
    print(f"Saved to {out_path}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--cohort', default='band1', choices=['band1', 'top100', 'all'])
    parser.add_argument('--pin', default=None, help='single-lead test')
    parser.add_argument('--dry-run', action='store_true', help='show prompt but do not call API')
    args = parser.parse_args()
    run(cohort_filter=args.cohort, single_pin=args.pin, dry_run=args.dry_run)
