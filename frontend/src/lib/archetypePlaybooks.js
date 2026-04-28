/**
 * archetypePlaybooks.js — the canonical playbook for each lead archetype.
 *
 * Per the v4 spec, the dossier renders five sections (WHY / NEXT STEP
 * / CONTACT / WHAT TO SAY / EVIDENCE) but the *content* shifts by
 * archetype. Probate is not Investor is not Long-tenure. Each archetype
 * gets its own micro-product inside the same shell.
 *
 * This file holds the static parts: section labels, primary action
 * label and verb, the outcome dropdown options, the wait-window flag,
 * the tone descriptor for "What to say" generation. Dynamic content
 * (the actual letter copy, the evidence list, the equity computation)
 * is composed at render time from the dossier data.
 *
 * Detection order in detectArchetype():
 *   1. Probate (any harvester match with signal_type=probate)
 *   2. Divorce (any harvester match with signal_type=divorce)
 *   3. Estate transition (estate_heirs in archetype, no probate filing)
 *   4. Investor exit (LLC/investor owner with mature tenure)
 *   5. Long-tenure (individual owner, 15+ years)
 *   FALLBACK: 'general' — generic playbook with neutral copy
 *
 * The fallback is critical because real data has edge cases the spec
 * doesn't enumerate (government parcels, recent flips, multi-family
 * owners). The dossier never goes silent — it always renders one of
 * these six playbooks.
 */

export const ARCHETYPES = {
  // ── 1. Probate ────────────────────────────────────────────────
  probate: {
    key: 'probate',
    label: 'Probate',
    tone: 'condolence-first',
    primaryAction: {
      label: 'Send handwritten letter',
      kind: 'send-letter',
    },
    outcomes: [
      'Got response',
      'No response',
      'Listing discussion',
      'Closed',
    ],
    waitWindow: false,
    showEquity: false,
    // Hint shown next to the archetype badge in the dossier header.
    headlineHint: 'Probate-driven seller',
  },

  // ── 2. Divorce ────────────────────────────────────────────────
  // The only archetype where the right action is sometimes "wait."
  // The waitWindow flag tells the dossier to render a hold banner
  // instead of the primary send button, until 60+ days from filing.
  divorce: {
    key: 'divorce',
    label: 'Divorce',
    tone: 'neutral-brief',
    primaryAction: {
      label: 'Send introduction letter',
      kind: 'send-letter',
    },
    outcomes: [
      'Got response',
      'No response',
      'Listing discussion',
      'Closed',
    ],
    waitWindow: true,           // 60-day hold from filing
    waitWindowDays: 60,
    showEquity: false,
    headlineHint: 'Divorce-driven seller',
  },

  // ── 3. Estate transition (no filing yet) ──────────────────────
  estateTransition: {
    key: 'estateTransition',
    label: 'Estate transition',
    tone: 'relational-trusted-intro',
    primaryAction: {
      label: 'Send introduction letter',
      kind: 'send-letter',
    },
    outcomes: [
      'Open to conversation',
      'Not interested',
      'Future follow-up',
    ],
    waitWindow: false,
    showEquity: true,           // long family hold often = significant equity
    headlineHint: 'Estate transition profile',
  },

  // ── 4. Investor exit ──────────────────────────────────────────
  investor: {
    key: 'investor',
    label: 'Investor exit window',
    tone: 'rational-opportunity',
    primaryAction: {
      label: 'Send off-market inquiry',
      kind: 'send-letter',
    },
    outcomes: [
      'Interested',
      'Not interested',
      'Considering sale',
      'Listing discussion',
      'Closed',
    ],
    waitWindow: false,
    showEquity: true,           // equity arithmetic is the killer detail here
    headlineHint: 'Investor disposition window',
  },

  // ── 5. Long-tenure ────────────────────────────────────────────
  longTenure: {
    key: 'longTenure',
    label: 'Long-tenure owner',
    tone: 'relational-soft-intro',
    primaryAction: {
      label: 'Send introduction letter',
      kind: 'send-letter',
    },
    outcomes: [
      'Open to conversation',
      'Not interested',
      'Staying long-term',
      'Future follow-up',
    ],
    waitWindow: false,
    showEquity: true,
    headlineHint: 'Long-tenure homeowner',
  },

  // ── 6. General fallback ───────────────────────────────────────
  // Catch-all when no specific archetype detects. Used for: government
  // parcels, very recent flips, owner_type='unknown', edge cases. The
  // copy is intentionally generic — better to say something neutral
  // and accurate than to fake an archetype.
  general: {
    key: 'general',
    label: 'Lead',
    tone: 'neutral',
    primaryAction: {
      label: 'Send introduction letter',
      kind: 'send-letter',
    },
    outcomes: [
      'Got response',
      'No response',
      'Listing discussion',
      'Closed',
    ],
    waitWindow: false,
    showEquity: false,
    headlineHint: null,
  },
};


/**
 * detectArchetype(dossier) → archetype playbook
 *
 * Inspects the dossier's data and returns the right ARCHETYPES entry.
 * The detection order matters: harvester-driven signals (probate,
 * divorce) take precedence over structural ones (long-tenure, investor)
 * because they're stronger evidence.
 */
export function detectArchetype(dossier) {
  if (!dossier) return ARCHETYPES.general;

  const matches = dossier.harvester_matches || [];
  const parcel = dossier.parcel || {};
  const signalFamily = dossier.signal_family || parcel.signal_family;
  const archetype = dossier.archetype || parcel.archetype;

  // Strict probate match present → Probate archetype, regardless of
  // contact_status. The dossier shell handles no_pr_yet / unworkable_pr
  // states inside the playbook (the wait/hold rendering for those
  // states is in the WHY section, not a separate archetype).
  if (matches.some((m) => m.signal_type === 'probate')) {
    return ARCHETYPES.probate;
  }

  // Divorce match → Divorce archetype with the wait-window behavior.
  if (matches.some((m) => m.signal_type === 'divorce')) {
    return ARCHETYPES.divorce;
  }

  // Estate transition: signal_family or archetype name suggests
  // family-event-cluster without a court filing.
  if (signalFamily === 'family_event_cluster'
      || archetype === 'estate_heirs') {
    return ARCHETYPES.estateTransition;
  }

  // Investor: LLC ownership or investor disposition signal family.
  // owner_type 'llc' is the cleanest indicator. signal_family
  // 'investor_disposition' covers the rest.
  const ownerType = (parcel.owner_type || '').toLowerCase();
  if (ownerType === 'llc'
      || signalFamily === 'investor_disposition'
      || archetype === 'llc_investor_mature'
      || archetype === 'llc_investor_early'
      || archetype === 'llc_long_hold') {
    return ARCHETYPES.investor;
  }

  // Long-tenure: individual owner with 15+ years tenure. The 15-year
  // threshold matches the spec's "long-tenure" framing — owners who've
  // been put a meaningful chunk of life into the home and statistically
  // start considering moves around year 12+.
  if (ownerType === 'individual'
      && parcel.tenure_years != null
      && parcel.tenure_years >= 15) {
    return ARCHETYPES.longTenure;
  }

  // Trust-held with long tenure rolls into long-tenure for V1 — the
  // playbook copy is similar enough (relational, low pressure) that
  // a separate archetype isn't yet justified. Future split possible.
  if (ownerType === 'trust' && (parcel.tenure_years || 0) >= 10) {
    return ARCHETYPES.longTenure;
  }

  return ARCHETYPES.general;
}


/**
 * computeEquity(dossier) → number | null
 *
 * Equity = current estimated value − last arms-length sale price.
 * Returns null if either piece is missing. Used in CONTACT section
 * for investor and long-tenure archetypes where the equity figure
 * is the killer detail.
 *
 * NOT a market-timing prediction. Just arithmetic on two known numbers.
 */
export function computeEquity(dossier) {
  if (!dossier) return null;
  const parcel = dossier.parcel || {};
  const current = parcel.total_value;
  const lastPrice =
       dossier.last_arms_length_price
    ?? parcel.last_transfer_price
    ?? null;
  if (!current || !lastPrice || lastPrice <= 0) return null;
  const delta = current - lastPrice;
  if (delta <= 0) return null;     // negative equity makes no sense to display
  return delta;
}


/**
 * formatEquity(dollars) → string
 *
 * Same display convention as the rest of the app: $X.XM for millions,
 * $XK for thousands, $X for under-thousand.
 */
export function formatEquity(dollars) {
  if (dollars == null) return null;
  if (dollars >= 1_000_000) return `+$${(dollars / 1_000_000).toFixed(1)}M since acquisition`;
  if (dollars >= 1_000)     return `+$${Math.round(dollars / 1_000)}K since acquisition`;
  return `+$${Math.round(dollars)} since acquisition`;
}


/**
 * isWithinWaitWindow(dossier, archetype) → boolean
 *
 * For divorce archetype, returns true if the case was filed less
 * than archetype.waitWindowDays days ago (default 60). The dossier
 * uses this to render the wait banner instead of the send button.
 */
export function isWithinWaitWindow(dossier, archetype) {
  if (!archetype.waitWindow) return false;
  const matches = dossier?.harvester_matches || [];
  // Use the most recent matching signal_type as the anchor. For
  // divorce archetype that'll be the divorce filing.
  const targetType = archetype.key === 'divorce' ? 'divorce' : null;
  const candidates = targetType
    ? matches.filter((m) => m.signal_type === targetType)
    : matches;
  if (candidates.length === 0) return false;
  const dates = candidates
    .map((m) => m.event_date || m.matched_at)
    .filter(Boolean)
    .map((d) => new Date(d).getTime())
    .filter((t) => !isNaN(t));
  if (dates.length === 0) return false;
  const filed = Math.max(...dates);
  const ageDays = (Date.now() - filed) / (1000 * 60 * 60 * 24);
  return ageDays < (archetype.waitWindowDays || 60);
}


/**
 * waitWindowOpensDate(dossier, archetype) → Date | null
 *
 * Computes the date when the wait window expires. Used in the
 * "outreach window opens [date]" copy.
 */
export function waitWindowOpensDate(dossier, archetype) {
  if (!archetype.waitWindow) return null;
  const matches = dossier?.harvester_matches || [];
  const targetType = archetype.key === 'divorce' ? 'divorce' : null;
  const candidates = targetType
    ? matches.filter((m) => m.signal_type === targetType)
    : matches;
  if (candidates.length === 0) return null;
  const dates = candidates
    .map((m) => m.event_date || m.matched_at)
    .filter(Boolean)
    .map((d) => new Date(d).getTime())
    .filter((t) => !isNaN(t));
  if (dates.length === 0) return null;
  const filed = Math.max(...dates);
  return new Date(filed + (archetype.waitWindowDays || 60) * 24 * 60 * 60 * 1000);
}
