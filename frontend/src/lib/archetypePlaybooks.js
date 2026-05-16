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
      label: 'Direct mail',
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
    // Default Phone/Letter/Door scripts — addressed to the personal
    // representative when one is identified, otherwise "the family."
    // These render immediately for every probate lead, no LLM call
    // needed. Deep Signal output (when generated) takes precedence
    // per-channel; defaults stay as fallback.
    //
    // Tokens substituted at render time:
    //   {pr_first}    — personal_representative.name_first if known
    //   {decedent}    — decedent name (last, first) if known
    //   {address}     — parcel.address
    //   {city}        — parcel.city
    defaultScripts: {
      phone: 'Hello {pr_first}, this is [your name] with [your brokerage]. I came across the estate filing for {decedent} and wanted to reach out personally. I work with families navigating decisions about a property after a loss, and I\'d be glad to help when the time is right. There\'s no rush — I\'m happy to be a resource whenever you\'re ready to talk.',
      letter: 'Dear {pr_first},\n\nI\'m writing with my sincere condolences on your loss. I work with families in {city} who are navigating decisions about a home after a loved one passes, and I wanted to introduce myself in case I can be helpful.\n\nThere\'s no expectation here — only an offer. When you\'re ready, I can walk you through the options for {address}, including the timing question, what the home might bring in today\'s market, and what choices you have. Until then, take the time you need.\n\nWarm regards,\n[Your name]',
      door: 'Hi {pr_first} — sorry to drop in unannounced. My name is [your name], I work with families in {city} who are managing a property after a loss. I\'m not here to ask anything of you — I just wanted to introduce myself in person and leave you my card. Whenever you\'re ready to talk through the options for the home, I\'m available.',
    },
  },

  // ── 2. Divorce ────────────────────────────────────────────────
  divorce: {
    key: 'divorce',
    label: 'Divorce',
    tone: 'neutral-brief',
    primaryAction: {
      label: 'Direct mail',
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
    // Tokens: {owner_first}, {address}, {city}
    // Tone is deliberately discreet — divorce-related outreach is
    // sensitive and the wait_window is enforced separately. These
    // scripts are the "after the wait" outreach.
    defaultScripts: {
      phone: 'Hello {owner_first}, this is [your name] with [your brokerage]. I work with homeowners in {city} who are weighing their options around a property. If selling {address} is something you\'re considering, I\'d be glad to walk you through what the home might bring in today\'s market — no pressure, just information when you\'re ready.',
      letter: 'Dear {owner_first},\n\nI\'m [your name] with [your brokerage], and I work with homeowners in {city} who are evaluating their options around a property.\n\nIf selling {address} is something you\'re weighing — now or down the road — I\'d be glad to share a current valuation and walk through the choices available. There\'s no obligation in reaching out. I\'m simply here as a resource whenever the timing makes sense for you.\n\nBest regards,\n[Your name]',
      door: 'Hi {owner_first}, my name is [your name] with [your brokerage]. I work with homeowners in the area who are thinking through their options around a property. I just wanted to introduce myself and leave a card — feel free to reach out whenever it\'s a good time.',
    },
  },

  // ── 3. Estate transition (no filing yet) ──────────────────────
  estateTransition: {
    key: 'estateTransition',
    label: 'Estate transition',
    tone: 'relational-trusted-intro',
    primaryAction: {
      label: 'Direct mail',
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
    // Tokens: {owner_first}, {address}, {city}
    defaultScripts: {
      phone: 'Hello {owner_first}, this is [your name] with [your brokerage]. I noticed your family\'s long history with {address} and wanted to introduce myself. I work with homeowners in {city} who are thinking through what comes next for a long-held property. Whenever you\'re weighing options — whether that\'s now or in the future — I\'d be glad to be a resource.',
      letter: 'Dear {owner_first},\n\nI\'m [your name] with [your brokerage]. I work with homeowners in {city} who are thinking through the next chapter for a long-held property — whether that\'s passing it on, selling, or simply weighing options.\n\nIf {address} is on your mind, I\'d be glad to share what the home might bring in today\'s market and walk through the choices available. No pressure on timing. I\'m happy to be a resource whenever it\'s useful.\n\nBest regards,\n[Your name]',
      door: 'Hi {owner_first}, my name is [your name] with [your brokerage]. I work with homeowners in {city} thinking through what comes next for a long-held property. I just wanted to introduce myself and leave a card — happy to talk whenever the timing is right for you.',
    },
  },

  // ── 4. Investor exit ──────────────────────────────────────────
  investor: {
    key: 'investor',
    label: 'Investor exit window',
    tone: 'rational-opportunity',
    primaryAction: {
      label: 'Direct mail',
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
    // Tokens: {owner_name}, {address}, {city}
    // Institutional voice — addresses the entity, not an individual.
    // Brief and business-tone. This archetype is for LLC owners and
    // long-hold investors where the conversation is about cap-rate,
    // disposition timing, and 1031 considerations.
    defaultScripts: {
      phone: 'Hello, this is [your name] with [your brokerage]. I\'m calling on behalf of {owner_name} regarding {address}. I work with investor-owners in {city} who are evaluating their portfolio. If a disposition window or off-market sale is on the table, I\'d welcome a brief conversation about current market conditions and what the property might bring.',
      letter: 'To whom it may concern at {owner_name},\n\nI\'m [your name] with [your brokerage]. I work with investor-owners in {city} who are evaluating disposition timing on long-held properties.\n\nIf {address} is one you\'re considering — whether for an off-market sale, a 1031 exchange, or simply weighing the current value — I\'d welcome a brief conversation. I can share recent comparable transactions and a current valuation, with no obligation.\n\nBest regards,\n[Your name]',
      door: 'Hi, my name is [your name] with [your brokerage]. I\'m hoping to leave a card for whoever manages this property — I work with investor-owners in {city} weighing disposition options. Happy to talk whenever it\'s useful.',
    },
  },

  // ── 5. Long-tenure ────────────────────────────────────────────
  longTenure: {
    key: 'longTenure',
    label: 'Long-tenure owner',
    tone: 'relational-soft-intro',
    primaryAction: {
      label: 'Direct mail',
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
    // Tokens: {owner_first}, {address}, {city}, {tenure_years}
    // Tone: respectful, soft, no urgency. Long-tenure owners have no
    // immediate need to sell — the script acknowledges that and offers
    // to be a resource for "whenever."
    defaultScripts: {
      phone: 'Hello {owner_first}, this is [your name] with [your brokerage]. I work with long-time homeowners in {city} and noticed your tenure at {address}. I\'m not calling because I think you should sell — I\'m calling because I want to be a resource whenever options come up. Happy to share a current valuation if it\'s useful.',
      letter: 'Dear {owner_first},\n\nI\'m [your name] with [your brokerage], and I work with long-time homeowners in {city}.\n\nI don\'t write to suggest you should sell {address} — your tenure here speaks to a real connection to the home. I write because when long-time owners do consider options — whether years from now or for a family reason — they often appreciate having someone to call. I\'d like to be that someone if and when it\'s useful.\n\nWith respect,\n[Your name]',
      door: 'Hi {owner_first}, my name is [your name] with [your brokerage]. I work with long-time homeowners in {city} and just wanted to introduce myself. No agenda — happy to be a resource whenever you have a question about the market or your options.',
    },
  },

  // ── 6. General fallback ───────────────────────────────────────
  general: {
    key: 'general',
    label: 'Lead',
    tone: 'neutral',
    primaryAction: {
      label: 'Direct mail',
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
    // Tokens: {owner_first}, {address}, {city}
    defaultScripts: {
      phone: 'Hello {owner_first}, this is [your name] with [your brokerage]. I work with homeowners in {city} and wanted to introduce myself. If options around {address} ever come up — now or down the road — I\'d be glad to be a resource.',
      letter: 'Dear {owner_first},\n\nI\'m [your name] with [your brokerage]. I work with homeowners in {city} on questions related to selling, valuation, and timing.\n\nIf {address} ever comes up for consideration — whether soon or in the future — I\'d be glad to share a current valuation and walk through the options. No obligation in reaching out.\n\nBest regards,\n[Your name]',
      door: 'Hi {owner_first}, my name is [your name] with [your brokerage]. I work with homeowners in {city} and just wanted to introduce myself. Happy to be a resource whenever it\'s useful.',
    },
  },
};


/**
 * resolveDefaultScripts(archetype, dossier) → { phone, letter, door }
 *
 * Substitutes tokens in the archetype's defaultScripts against the
 * dossier data. Returns the three rendered scripts as plain strings.
 *
 * Token resolution rules:
 *   {pr_first}      — personal_representative.name_first from harvester
 *                     match (probate). Falls back to "Friend" when not
 *                     known so the script remains readable.
 *   {decedent}      — decedent's name from harvester match (probate).
 *                     Falls back to "your loved one" when not known.
 *   {owner_first}   — first word of dossier.parcel.owner_name. Falls
 *                     back to "Friend" for empty / weird formats.
 *   {owner_name}    — full owner_name (entity-friendly, used for LLC).
 *   {address}       — parcel.address. Falls back to "this property".
 *   {city}          — parcel.city. Falls back to "the area".
 *   {tenure_years}  — rounded tenure_years if available.
 *
 * The fallback strings are deliberate: a script that says "Dear
 * Friend" reads worse than one with a real name, but it never reads
 * WRONG. The previous Deep Signal bug was a script that confidently
 * addressed a deceased person — fallbacks here never invent.
 */
export function resolveDefaultScripts(archetype, dossier) {
  if (!archetype || !archetype.defaultScripts) return null;
  const tpl = archetype.defaultScripts;

  const parcel = dossier?.parcel || {};
  const matches = dossier?.harvester_matches || [];

  // Find the personal_representative across harvester_matches —
  // probate matches surface this. Take the first one with a name_first
  // (since some matches might carry only the petitioner without a
  // resolved first name).
  let pr = null;
  let decedent = null;
  for (const m of matches) {
    if (!pr && m.personal_representative && m.personal_representative.name_first) {
      pr = m.personal_representative;
    }
    if (!decedent && m.signal_type === 'probate') {
      // Scan all_case_parties for the deceased role.
      const parties = m.all_case_parties || [];
      const dec = parties.find((p) => p.role === 'deceased' || p.role === 'decedent');
      if (dec && (dec.name_first || dec.name_last)) {
        decedent = dec;
      }
    }
    if (pr && decedent) break;
  }

  // Owner first name = first whitespace-delimited token of owner_name.
  // Skip if owner_name is empty or looks like a trust/LLC (contains
  // "Trust", "LLC", "Inc", etc.) — those archetypes use {owner_name}
  // instead.
  const ownerName = parcel.owner_name || dossier?.owner_name || '';
  const looksLikeEntity = /\b(trust|llc|inc|corp|company|co\.?|partners|llp|lp)\b/i.test(ownerName);
  const ownerFirst = (!looksLikeEntity && ownerName)
    ? ownerName.trim().split(/\s+/)[0]
    : null;

  // Resolve tokens with safe fallbacks — never invent.
  const tokens = {
    pr_first:    pr?.name_first || 'Friend',
    decedent:    decedent
                   ? `${decedent.name_first || ''} ${decedent.name_last || ''}`.trim()
                   : 'your loved one',
    owner_first: ownerFirst || 'Friend',
    owner_name:  ownerName || 'the property owner',
    address:     parcel.address || 'this property',
    city:        parcel.city || 'the area',
    tenure_years: parcel.tenure_years
                   ? `${Math.round(parcel.tenure_years)}` : '',
  };

  const fill = (s) => s.replace(/\{(\w+)\}/g, (_, key) =>
    tokens[key] !== undefined ? tokens[key] : `{${key}}`);

  return {
    phone:  fill(tpl.phone),
    letter: fill(tpl.letter),
    door:   fill(tpl.door),
  };
}


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
