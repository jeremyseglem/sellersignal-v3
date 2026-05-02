/**
 * Six Letters — a 6-letter seller cultivation sequence.
 *
 * Ported 1:1 from the Node.js production site's generateSixLetters()
 * function (public/sellersignal-briefing.html, line 5773). All letter
 * content is deterministic from parcel data — no LLM call, no cost.
 *
 * The letters escalate in intimacy and concreteness:
 *   Day 1   — Introduction: pure hello, no ask
 *   Day 30  — Context: market color, no ask
 *   Day 60  — Story: a comparable "recent sale" anecdote
 *   Day 90  — Offer: explicit "send me a valuation" offer
 *   Day 135 — Moment: "the market is moving"
 *   Day 180 — Conversation: final letter, asks only to be remembered
 */

function titleCaseStreet(s) {
  if (!s) return '';
  return s.split(/\s+/).map((w) => {
    if (/^\d/.test(w)) return w;
    if (/^(N|S|E|W|NE|NW|SE|SW)$/i.test(w)) return w.toUpperCase();
    if (/^(ST|AVE|BLVD|RD|DR|LN|CT|PL|TER|TRL|HWY|PKWY|CIR|WAY|APT|UNIT|STE)$/i.test(w)) {
      return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
    }
    return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
  }).join(' ');
}

function normalizeName(name) {
  if (!name) return '';
  // Entity tokens that should always be uppercased regardless of length —
  // "LLC", "INC", "CORP", etc. are universally rendered uppercase in
  // business contexts and reading "2412 Boston Llc" looks broken.
  const ENTITY_UPPER = new Set([
    'LLC', 'INC', 'CORP', 'CO', 'LP', 'LLP', 'PLLC', 'PC', 'NA',
    'LTD', 'GMBH', 'SA', 'AG', 'BV', 'PBC',
  ]);
  return name.split(/\s+/).map((w) => {
    const upper = w.toUpperCase().replace(/[^A-Z]/g, '');
    if (ENTITY_UPPER.has(upper)) return w.toUpperCase();
    if (w.length <= 2) return w.toUpperCase();
    return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
  }).join(' ');
}

export function generateSixLetters(p, harvesterMatches = [], archetypeKey = null) {
  const ownerTypeRaw = ((p.ownerType || p.owner_type || '') + '').toLowerCase();

  // Direct-mail seller cultivation is inappropriate for gov and
  // nonprofit owners. Cities, fire districts, churches, YMCAs etc.
  // aren't seller prospects and "Dear [firstname]" to a parish office
  // would be embarrassing. Return an empty array so the UI can hide
  // the Six Letters button rather than generating bad letters.
  if (ownerTypeRaw === 'gov' || ownerTypeRaw === 'nonprofit') {
    return [];
  }

  const fullName = normalizeName(p.ownerName || p.owner_name) || 'Property Owner';
  const firstName = fullName.split(/\s+/)[0];

  const propertyAddress = titleCaseStreet((p.address || 'your property').replace(/\s+/g, ' ').trim());
  const neighborhood = p.neighborhood || p.marketName || p.city || 'your area';
  const isAbsentee  = !!(p.isAbsentee ?? p.is_absentee);
  const isOutOfState = !!(p.isOutOfState ?? p.is_out_of_state);
  const isTrust = /trust/i.test(p.ownerName || p.owner_name || '') ||
                  ownerTypeRaw === 'trust' ||
                  ownerTypeRaw.includes('trust');
  const isLLC   = /\b(LLC|CORP|INC|HOLDINGS|PROPERTIES|GROUP|FOUNDATION)\b/i.test(p.ownerName || p.owner_name || '') ||
                  ownerTypeRaw === 'llc' ||
                  /(llc|corp|inc)/i.test(ownerTypeRaw);
  const isEstate = ownerTypeRaw === 'estate' ||
                   /\b(ESTATE|HEIRS|DECEASED|SURVIVOR)\b/i.test(p.ownerName || p.owner_name || '');
  const yearsOwned = p.yearsOwned ?? p.tenure_years ?? null;

  // ── Archetype-specific routing ──────────────────────────────────
  // The 6-letter sequence escalates differently depending on what
  // kind of seller we're talking to. Probate addressees are the
  // personal representative, not the deceased — and the body copy
  // reflects estate-decision timing rather than market urgency.
  // Divorce keeps tone discreet and brief. Investor LLC uses
  // institutional voice and cap-rate / 1031 framing. Trust is
  // institutional-respectful. Long-tenure and general fallback use
  // the original sequence (written for that profile).
  //
  // archetypeKey values come from frontend/src/lib/archetypePlaybooks.js
  // ARCHETYPES.{probate,divorce,investor,trust,longTenure,estateTransition,general}.key

  // Dig PR / decedent out of harvester_matches if present (for probate).
  let prFirst = null;
  let decedentName = null;
  for (const m of (harvesterMatches || [])) {
    if (!prFirst && m.personal_representative?.name_first) {
      prFirst = m.personal_representative.name_first;
    }
    if (!decedentName && m.signal_type === 'probate') {
      const parties = m.all_case_parties || [];
      const dec = parties.find((q) => q.role === 'deceased' || q.role === 'decedent');
      if (dec) {
        const f = dec.name_first || '';
        const l = dec.name_last || '';
        decedentName = `${f} ${l}`.trim() || null;
      }
    }
    if (prFirst && decedentName) break;
  }

  // Dispatch — explicit archetypeKey takes priority; auto-detected
  // entity flags below act as a fallback when archetypeKey isn't
  // passed (older callers of this generator).
  if (archetypeKey === 'probate') {
    return _probateSequence({ prFirst, decedentName, propertyAddress, neighborhood });
  }
  if (archetypeKey === 'divorce') {
    return _divorceSequence({ firstName, propertyAddress, neighborhood });
  }
  if (archetypeKey === 'investor' || isLLC) {
    return _investorSequence({ entityName: fullName, propertyAddress, neighborhood });
  }
  if (archetypeKey === 'trust' || isTrust) {
    return _trustSequence({ propertyAddress, neighborhood });
  }
  if (archetypeKey === 'estateTransition') {
    return _estateTransitionSequence({ firstName, propertyAddress, neighborhood, yearsOwned });
  }

  // ── Long-tenure / general fallback (the original sequence) ───
  // This is the seller cultivation cadence written originally for
  // long-tenure homeowners. It also applies to the general fallback
  // archetype where we have no specific signal but want to nurture.
  // The greeting handles isEstate/isOutOfState edge cases that may
  // arrive with no archetypeKey from older callers.
  const greeting = isEstate
    ? `To the estate of the owner`
    : `Dear ${firstName}`;

  const ownerTypeContext = isEstate
    ? 'an estate navigating the settlement of an inherited property'
    : isAbsentee
      ? 'an out-of-area owner who had been holding the property for years'
      : yearsOwned && yearsOwned > 15
        ? 'a longtime owner who had built significant equity over time'
        : 'a homeowner who had been quietly considering their options';

  const distanceAck = isOutOfState
    ? ` Even from a distance, your investment in ${neighborhood} represents real value, and you deserve to have someone watching it closely on your behalf.`
    : isAbsentee
      ? ` Owners who don't live at their property often miss the day-to-day signals of what their home is worth — I try to fill that gap.`
      : '';

  return [
    {
      num: 1,
      name: 'The Introduction',
      dayLabel: 'Day 1',
      trigger: 'Sent immediately upon enrollment',
      body: `${greeting},

I'm writing because I've been studying ${neighborhood} for some time, and your property at ${propertyAddress} caught my attention.

I'm not reaching out to ask for anything today. I just wanted to introduce myself as someone who pays close attention to this market — what's selling, what isn't, and what your property might be worth in today's environment if you ever decided to find out.${distanceAck}

If that's a conversation you'd like to have someday, I'd welcome it. If not, I'll continue watching the market and may write again when there's something worth sharing about your area specifically.

Either way, thank you for letting me introduce myself.

Warmly,`,
    },
    {
      num: 2,
      name: 'The Context',
      dayLabel: 'Day 30',
      trigger: 'Sent 30 days after enrollment, or earlier if a comparable property lists',
      body: `${greeting},

Following up on my note from last month — I wanted to share some context about what's actually happening in ${neighborhood} right now.

In the past 90 days, properties similar to yours have moved through this market at a pace that has surprised even local agents. Homes are changing hands at numbers that would have seemed optimistic a year ago, and the buyer pool for ${neighborhood} specifically remains deeper than supply.

For a property like yours at ${propertyAddress}, that translates to a meaningfully different valuation conversation than even six months ago. I'm not telling you this to push you toward anything. I'm telling you this because if I owned a home like yours, I'd want to know.

If you'd ever like a clearer picture of where your property sits in today's market — confidentially, no commitment — I'd be glad to put it together for you.

Best,`,
    },
    {
      num: 3,
      name: 'The Story',
      dayLabel: 'Day 60',
      trigger: 'Sent 60 days after enrollment, or earlier if a directly comparable sale closes nearby',
      body: `${greeting},

A property near you sold recently. I won't name the exact address out of respect for the seller's privacy, but the situation reminded me of yours — ${ownerTypeContext}, comparable in size and character to ${propertyAddress}.

The owner had been thinking about selling for over a year but had never taken the simple step of finding out what their home was actually worth in today's market. When they finally did, the number was higher than they expected. The decision became a lot easier.

I share this not as a sales pitch but as a pattern I see often. Most homeowners in ${neighborhood} who eventually sell tell me afterward that they wish they'd known their number sooner. Knowing doesn't commit you to anything — it just makes the eventual decision, whenever it comes, a real decision based on real information rather than a guess.

If that's something you'd like, you know where to find me.

Best,`,
    },
    {
      num: 4,
      name: 'The Offer',
      dayLabel: 'Day 90',
      trigger: 'Sent 90 days after enrollment',
      body: `${greeting},

I want to make this very simple.

I'd like to put together a confidential, no-obligation valuation of your property at ${propertyAddress}. I'll do the work — recent comparable sales on your block and in your immediate area, current market positioning, what I'd list it for if you were my client today, and what I'd realistically expect it to net you after closing costs.

You don't need to be considering selling. You don't need to call me back to discuss it. I'll just put it together and send it to you, and you can do whatever you want with it — file it away, ignore it, share it with your accountant, or use it as a starting point for a conversation when the time is right for you.

If you'd like me to prepare it, just call or text the number below. One sentence is enough: "Yes, send the valuation."

That's the entire ask.

Sincerely,`,
    },
    {
      num: 5,
      name: 'The Moment',
      dayLabel: 'Day 135',
      trigger: 'Sent 135 days in, or earlier if local market data shifts meaningfully',
      body: `${greeting},

Five months into our correspondence and I haven't heard back, which is completely fine. Most homeowners I write to don't respond to early letters, and I'd rather earn your eventual trust slowly than push for something you're not ready for.

But I'm writing today because the market in ${neighborhood} is in a moment that's worth your attention.

Inventory remains tight. Qualified buyers are still actively looking — I have several right now who would be interested in a property exactly like yours at ${propertyAddress}. And the rate environment, while uncertain, is creating motivation among buyers who don't want to wait any longer.

I'm not predicting anything. Markets always have moments, and the right moment to know your property's value is usually the moment before you wish you'd known it.

If you'd like that picture now, I can have it to you within 48 hours.

Best,`,
    },
    {
      num: 6,
      name: 'The Conversation',
      dayLabel: 'Day 180',
      trigger: 'Final letter — sent 180 days after enrollment',
      body: `${greeting},

This is the sixth letter I've written to you over the past six months. You haven't responded, and I want to acknowledge that with respect rather than persistence.

So I'm not going to ask you to call me again. I'm going to ask something different.

Whenever the day eventually comes — six months from now, two years from now, or ten — that you start thinking seriously about what your property at ${propertyAddress} might be worth and what selling it would actually look like, I'd like to be the person you call first. Not because I've earned it through these letters, but because by then I'll have spent over a year studying ${neighborhood} closely and watching how it's evolved.

If that day comes, just save my number. That's all I'm asking.

I'll keep watching the market. I won't write again unless something material changes that affects your property specifically.

With genuine respect,`,
    },
  ];
}


// ───────────────────────────────────────────────────────────────────
// Archetype-specific 6-letter sequences
//
// Each follows the same Day 1/30/60/90/135/180 cadence as the long-
// tenure default — preserves the modal's tab UI and Brian's mental
// model — but the body copy is rewritten for the archetype's actual
// situation. Every greeting is grounded in real data: PR first name
// for probate, owner first name for divorce, entity name for LLC,
// "Trustees" for trust, etc. We never address a deceased person.
// ───────────────────────────────────────────────────────────────────


function _probateSequence({ prFirst, decedentName, propertyAddress, neighborhood }) {
  // Greeting: PR first name when known, generic fallback otherwise.
  // We never use the deceased's name as the addressee. The decedent
  // is referenced once in letter 1 as part of acknowledging the
  // situation, and never named again — repeated naming would feel
  // intrusive.
  const greeting = prFirst ? `Dear ${prFirst}` : `To the family`;
  const decedentRef = decedentName
    ? `the estate of ${decedentName}`
    : `the estate`;

  return [
    {
      num: 1,
      name: 'The Introduction',
      dayLabel: 'Day 1',
      trigger: 'Sent immediately upon enrollment — keep tone respectful, no asks',
      body: `${greeting},

I came across the filing for ${decedentRef} and wanted to write briefly. I'm a real estate agent who works with families navigating decisions about a home after a loved one passes — I'm not reaching out today to discuss anything specific, just to introduce myself.

There's no expectation here, only an offer. When you're ready to think about what comes next for the property at ${propertyAddress} — whether that's months from now or longer — I'd be glad to be a resource.

Until then, please accept my sincere condolences.

With respect,`,
    },
    {
      num: 2,
      name: 'Checking In',
      dayLabel: 'Day 30',
      trigger: 'Sent 30 days after introduction — light touch, still no asks',
      body: `${greeting},

I wanted to follow up briefly on my earlier note. I imagine the past month has been full of details — the practical kind that come with settling an estate — and I don't want to add to that.

I'm writing only to say I'm still here, still available whenever questions about the property come up. Many of the families I've worked with have told me the most useful thing was just knowing they had someone they could call when the timing felt right, with no pressure to act.

If a question arises — about valuation, market timing, or what selling actually looks like in practice — please reach out. Otherwise, I'll write again when there's something worth sharing.

Warm regards,`,
    },
    {
      num: 3,
      name: 'What to Know',
      dayLabel: 'Day 60',
      trigger: 'Sent 60 days in — first letter that shares any substantive information',
      body: `${greeting},

Two months on, I wanted to share a few things that often come up around inherited or estate-held property in ${neighborhood} — not because you need to act, but because they're useful to know.

First, the timing question is yours. Properties held through probate or estate settlement can be sold at any pace — quickly when an estate needs to close, or slowly when families want time. Both are normal.

Second, valuation matters more in these situations than in typical sales. Stepped-up cost basis at the time of inheritance can meaningfully affect tax outcomes, which is why most estate sellers I work with want a clear, defensible number to anchor decisions.

Third, you don't need to commit to anything to get that number. I can put together a confidential valuation of ${propertyAddress} whenever you'd like, and you can use it however helps — share it with your attorney or accountant, file it for later, or simply have it for context.

No rush. Just here when needed.

Best,`,
    },
    {
      num: 4,
      name: 'The Quiet Offer',
      dayLabel: 'Day 90',
      trigger: 'Sent 90 days after enrollment — explicit but unpressured offer',
      body: `${greeting},

It's been three months since I first wrote, and I want to make a simple offer.

If a current valuation of ${propertyAddress} would be useful to you — for the estate's records, for an attorney conversation, or for any reason at all — I'd be glad to prepare one. I'll do the work: recent comparable sales, current market context, what the property would realistically sell for today, and what a sale would actually net once costs are accounted for.

You don't need to be considering selling. You don't need to call me back to discuss it. Just reply with one sentence — "Yes, please send a valuation" — and I'll have it to you within a week.

That's the entire ask. I won't follow up to push anything further.

Sincerely,`,
    },
    {
      num: 5,
      name: 'When the Time Comes',
      dayLabel: 'Day 135',
      trigger: 'Sent 135 days in — gentle re-engagement, no urgency',
      body: `${greeting},

I haven't heard from you, which is completely understandable — there's no right pace for these decisions.

I want to share one observation that may be useful. In my experience, families navigating an estate's property tend to make better decisions when they have current information than when they have to guess. The act of getting a clear valuation often clarifies the timing question on its own — sometimes the answer is "sell now," sometimes "hold for a year or two," sometimes "keep it in the family." But the right answer is rarely visible without the data.

If that's something you'd find helpful at any point, I'm here. I won't push, I won't follow up beyond the natural cadence of these letters, and I'll keep the offer open as long as you need.

In the meantime, I hope the past few months have brought some peace.

With respect,`,
    },
    {
      num: 6,
      name: 'A Standing Offer',
      dayLabel: 'Day 180',
      trigger: 'Final letter — closes the formal sequence with a standing offer',
      body: `${greeting},

This is the last of my regular letters. I won't keep writing on a schedule — I've said what I think is useful to say, and the rest is timing.

But I want to leave you with this: my offer doesn't expire. Whenever the moment comes that you want a clear, current picture of what the property at ${propertyAddress} is worth — whether that's six months from now or six years — please reach out. I'd be glad to help, and the conversation will start the same way it would today: no pressure, no commitment, just useful information when you're ready for it.

Until then, please know I'm thinking of your family with respect.

Whenever you need me,`,
    },
  ];
}


function _divorceSequence({ firstName, propertyAddress, neighborhood }) {
  // Tone: discreet, brief, neutral. Divorce is sensitive and the
  // 60-day wait window already prevents the very-early intrusive
  // letter. Letters are intentionally shorter than other sequences;
  // owners in this situation have less bandwidth for long copy.
  const greeting = `Dear ${firstName}`;

  return [
    {
      num: 1,
      name: 'The Introduction',
      dayLabel: 'Day 1',
      trigger: 'Sent after the 60-day wait window has cleared',
      body: `${greeting},

I'm a real estate agent who works with homeowners in ${neighborhood} on questions related to selling, valuation, and timing.

I'm not reaching out today because I think you should sell. I'm reaching out to introduce myself in case you'd find it useful to have someone to call. Conversations about a property are often easier when you have an outside perspective — and I'm happy to be that, whenever it's helpful.

If a question comes up about ${propertyAddress}, I'm available. Until then, no expectation here.

Best,`,
    },
    {
      num: 2,
      name: 'Available',
      dayLabel: 'Day 30',
      trigger: 'Sent 30 days after introduction — short, no asks',
      body: `${greeting},

A brief follow-up to say I'm still here.

Decisions about a property tend to surface gradually — and there's no right answer about timing. When a question does come up about ${propertyAddress}, even a small one, please feel free to reach out.

Otherwise I'll be quiet. I'll write again only if there's something specifically worth sharing.

Best,`,
    },
    {
      num: 3,
      name: 'The Information',
      dayLabel: 'Day 60',
      trigger: 'Sent 60 days in — first letter with substantive market information',
      body: `${greeting},

Two months on, I wanted to share some context about ${neighborhood} that you may find useful — not as pressure, just as information.

Properties similar to yours have moved at a steady pace this year. Inventory is tight, buyers are active, and valuations have held meaningfully higher than even twelve months ago. For a property like ${propertyAddress}, that translates to a clearer picture of what the home would bring today than was possible recently.

If knowing that number would be helpful — for any reason, even just for clarity — I can put together a confidential valuation. It's the kind of thing many homeowners find useful to have on hand whether they're actively considering selling or not.

Best,`,
    },
    {
      num: 4,
      name: 'The Offer',
      dayLabel: 'Day 90',
      trigger: 'Sent 90 days in — explicit valuation offer',
      body: `${greeting},

I want to make this simple.

I can prepare a confidential, no-obligation valuation of ${propertyAddress}: recent comparable sales, current market positioning, what the home would likely sell for today, and what a sale would net after costs.

You don't need to be considering selling. Just reply with one sentence — "Yes, please send the valuation" — and I'll have it to you within a week. No follow-up pressure, no further outreach beyond what you ask for.

Sincerely,`,
    },
    {
      num: 5,
      name: 'A Useful Number',
      dayLabel: 'Day 135',
      trigger: 'Sent 135 days in — light re-engagement',
      body: `${greeting},

I haven't heard back, which is fine — most homeowners I write to don't respond to early letters, and I'd rather earn trust slowly than push.

I'm writing today only because, in my experience, the homeowners who eventually sell tend to say afterward that they wish they'd known their property's current value sooner. Not because the number itself was decisive, but because having it made every subsequent conversation easier — with family, with attorneys, with their own thinking.

That valuation offer remains open. One sentence is all it takes.

Best,`,
    },
    {
      num: 6,
      name: 'A Standing Offer',
      dayLabel: 'Day 180',
      trigger: 'Final letter — closes the formal sequence',
      body: `${greeting},

This is the last of my regular letters.

I won't keep writing on a schedule. But the offer doesn't expire — whenever the question of ${propertyAddress} comes up, in any form, I'd like to be the person you call. Not because of these letters, but because by then I'll have spent over a year watching ${neighborhood} closely.

Save my number. That's all I'm asking.

With respect,`,
    },
  ];
}


function _investorSequence({ entityName, propertyAddress, neighborhood }) {
  // Tone: institutional, business-cadence, market-data forward.
  // Investor LLCs respond to numbers, comp transactions, 1031 timing,
  // cap-rate framing — not to relational warmth. Letters are
  // shorter and more transactional than other sequences.
  const greeting = `To ${entityName}`;

  return [
    {
      num: 1,
      name: 'The Introduction',
      dayLabel: 'Day 1',
      trigger: 'Sent immediately upon enrollment',
      body: `${greeting},

I'm a real estate agent who works with investor-owners in ${neighborhood}, and I wanted to introduce myself in connection with the property at ${propertyAddress}.

I'm not writing to ask for anything today. I work with portfolios where dispositions are evaluated against cap rate, market timing, and 1031 considerations, and I make a point of staying available to owners who may want to revisit their position when conditions warrant.

If a disposition window opens — now or later — I'd welcome a brief conversation.

Regards,`,
    },
    {
      num: 2,
      name: 'Market Context',
      dayLabel: 'Day 30',
      trigger: 'Sent 30 days after introduction — substantive market data',
      body: `${greeting},

Following up briefly with market context for ${neighborhood} relevant to the property at ${propertyAddress}.

Recent transaction activity suggests sustained buyer demand at price levels meaningfully above prior cycle highs. Cap rates on stabilized residential have compressed modestly; off-market trades are clearing at premiums to listed comps in several recent cases.

For an owner evaluating disposition timing, the current environment continues to favor sellers willing to consider off-market or pre-listing engagement. If that's a conversation worth having, I'd be glad to share specific recent comps relevant to your asset.

Regards,`,
    },
    {
      num: 3,
      name: 'Comparable Activity',
      dayLabel: 'Day 60',
      trigger: 'Sent 60 days in — references comparable transaction activity',
      body: `${greeting},

A comparable property in your immediate market traded recently at terms I think are worth flagging. Out of respect for the seller's confidentiality I won't name the asset, but the situation is directly relevant: the owner had held the property for several years, was not actively marketing it, and engaged with a private buyer through an off-market introduction.

Outcome: cleared at a premium to the public listing comps, structured for tax efficiency, closed quickly.

The pattern matters because it's repeatable. If a similar disposition path makes sense for ${propertyAddress} — whether immediately or as a stalking-horse conversation for later — I can put together a current valuation and outline what an off-market engagement would look like.

Regards,`,
    },
    {
      num: 4,
      name: 'The Disposition Inquiry',
      dayLabel: 'Day 90',
      trigger: 'Sent 90 days in — explicit valuation and disposition framing',
      body: `${greeting},

I want to make a direct offer.

I'll prepare a current valuation of ${propertyAddress} along with an off-market disposition outline: recent comp transactions, current market positioning, projected net proceeds, and any 1031 timing considerations relevant to your position. Confidential, no obligation, delivered within a week.

If a disposition is on the table this year, the analysis is genuinely useful. If it's not, the document goes in a file and we revisit when conditions warrant.

Reply with one line — "Yes, send the analysis" — and I'll start.

Sincerely,`,
    },
    {
      num: 5,
      name: 'Timing Note',
      dayLabel: 'Day 135',
      trigger: 'Sent 135 days in — re-engagement on market timing',
      body: `${greeting},

A short note on timing for ${neighborhood}.

Inventory remains tight. Buyer pools at the price points relevant to ${propertyAddress} continue to clear at faster cadences than 12 months ago. The rate environment is creating a moving target, and several investor-owners I've worked with this year have moved on dispositions earlier than they originally planned.

If revisiting your position is worthwhile, the offer to prepare a current valuation and disposition outline remains open.

Regards,`,
    },
    {
      num: 6,
      name: 'A Standing Channel',
      dayLabel: 'Day 180',
      trigger: 'Final letter — closes the formal sequence with a relationship offer',
      body: `${greeting},

This closes the formal sequence.

I'll continue tracking ${neighborhood} and the comparable set relevant to ${propertyAddress}. If a meaningful market shift, a comparable transaction, or an off-market buyer interest emerges that's specifically relevant to your asset, I'll write again on that basis — not on a schedule.

In the meantime, the channel stays open. When timing aligns, a single email opens it.

Regards,`,
    },
  ];
}


function _trustSequence({ propertyAddress, neighborhood }) {
  // Tone: institutional-respectful. Trust ownership often means
  // multiple stakeholders, professional trustee, and longer
  // decision horizons. Letters acknowledge the structural
  // complexity rather than pushing relational warmth.
  const greeting = `To the trustees`;

  return [
    {
      num: 1,
      name: 'The Introduction',
      dayLabel: 'Day 1',
      trigger: 'Sent immediately upon enrollment',
      body: `${greeting},

I'm a real estate agent who works with trustees and trust beneficiaries in ${neighborhood}, and I wanted to introduce myself in connection with the property at ${propertyAddress}.

Trust-held properties often involve longer decision horizons and multiple stakeholders, and the right time to engage a real estate professional is often well before any decision is made. I make a point of being available to trustees who may want a clear picture of a property's value as part of broader trust administration — not because a sale is imminent, but because good information makes future decisions cleaner.

If that's useful, I'm here.

With respect,`,
    },
    {
      num: 2,
      name: 'Trustee Context',
      dayLabel: 'Day 30',
      trigger: 'Sent 30 days after introduction',
      body: `${greeting},

A brief follow-up. Many trustees I work with find that a current valuation of trust-held real estate is useful even outside of an active sale conversation — for trust accounting, for beneficiary distributions, for tax planning, or simply as part of the trustee's record-keeping.

If a current valuation of ${propertyAddress} would be useful for any of those purposes, I can prepare one confidentially and at no cost. It's the kind of document many trustees keep on file regardless of whether sale is being discussed.

Best,`,
    },
    {
      num: 3,
      name: 'Market Context',
      dayLabel: 'Day 60',
      trigger: 'Sent 60 days in — substantive market context',
      body: `${greeting},

Two months on, I wanted to share context about ${neighborhood} that may be relevant to your trust's records.

Property values in this market have held meaningfully higher than even twelve months ago, and inventory remains constrained. For a trust-held asset like ${propertyAddress}, the implications cut several ways — current valuation is materially different than recent appraisals likely show; if a future sale is contemplated as part of trust administration, current conditions favor sellers; and even where no sale is planned, having an accurate current number on file is good practice.

If you'd like that current valuation, I'm glad to prepare it.

Best,`,
    },
    {
      num: 4,
      name: 'The Offer',
      dayLabel: 'Day 90',
      trigger: 'Sent 90 days in — explicit valuation offer',
      body: `${greeting},

I want to make this concrete.

I can prepare a current, defensible valuation of ${propertyAddress} suitable for trust records: recent comparable sales, current market positioning, expected sale value, and notes on market conditions specific to ${neighborhood}. Confidential, no obligation, delivered within a week.

A sale doesn't need to be on the table. Many trustees keep such valuations in their records as standard practice. Reply with one sentence — "Yes, please prepare the valuation" — and I'll begin.

Sincerely,`,
    },
    {
      num: 5,
      name: 'When Decisions Arise',
      dayLabel: 'Day 135',
      trigger: 'Sent 135 days in — gentle re-engagement',
      body: `${greeting},

I haven't heard back, which is appropriate — trust-held properties don't move on outside schedules.

A note for whenever a property decision does come up. Trustees who engage early — well before a decision is required — tend to navigate sales more cleanly than those who engage at the moment of need. Comparable data, market context, and a current valuation are all easier to assemble before a decision than during one.

If that early-engagement model is useful for ${propertyAddress}, I'm glad to begin. The same offer stands.

With respect,`,
    },
    {
      num: 6,
      name: 'Standing Availability',
      dayLabel: 'Day 180',
      trigger: 'Final letter — closes the formal sequence',
      body: `${greeting},

This closes the formal sequence.

I'll continue tracking ${neighborhood} and will reach out only if a market development, comparable transaction, or relevant change emerges that's specifically meaningful to ${propertyAddress}.

In the meantime, the offer remains: a current valuation, prepared confidentially, available whenever the trust has reason for one. A single reply opens that conversation.

With respect,`,
    },
  ];
}


function _estateTransitionSequence({ firstName, propertyAddress, neighborhood, yearsOwned }) {
  // Tone: family-relational, acknowledging long history with the
  // property. Estate transition (no court filing yet) means we're
  // catching the family before formal probate — relational warmth
  // matters more than urgency or institutional voice.
  const greeting = `Dear ${firstName}`;
  const tenureRef = yearsOwned && yearsOwned > 15
    ? `your family's long history with ${propertyAddress}`
    : `your family's connection to ${propertyAddress}`;

  return [
    {
      num: 1,
      name: 'The Introduction',
      dayLabel: 'Day 1',
      trigger: 'Sent immediately upon enrollment',
      body: `${greeting},

I'm a real estate agent who works with families in ${neighborhood}, and I wanted to introduce myself.

I'm not writing because I think you should sell. I'm writing because I noticed ${tenureRef}, and in my experience, when families are eventually thinking through what comes next for a long-held home, they appreciate having someone they can call — not as a salesperson, but as a resource.

If that day comes, even years from now, I'd like to be that resource.

Warmly,`,
    },
    {
      num: 2,
      name: 'A Quiet Follow-Up',
      dayLabel: 'Day 30',
      trigger: 'Sent 30 days after introduction',
      body: `${greeting},

A brief follow-up to my note from last month.

Decisions about a long-held family home are rarely sudden — they unfold over months or years, and the right answer depends on family conversations as much as market conditions. I won't presume to know your family's situation. I'm writing only to say I'm available whenever questions surface.

If a question comes up — about ${propertyAddress}, about the market, about the practical mechanics of selling a home eventually — please reach out.

Best,`,
    },
    {
      num: 3,
      name: 'Useful to Know',
      dayLabel: 'Day 60',
      trigger: 'Sent 60 days in — first letter with substantive content',
      body: `${greeting},

Two months on, a few things often come up around long-held family homes that may be useful to know — not because you need to act, but because they're easier to learn now than later.

First, valuations of long-held homes tend to surprise families. Properties held for many years frequently appraise at multiples of purchase price, and the equity picture is rarely accurate without a current number.

Second, tax considerations matter more for long-held homes than typical sales — capital gains exposure, step-up basis questions if the home has passed through generations, and sometimes 1031 strategies all come into play.

Third, none of this requires you to be considering a sale. A current valuation of ${propertyAddress}, prepared confidentially, is something many families keep on hand for planning purposes regardless of timing.

If that's useful, I'm glad to prepare it.

Best,`,
    },
    {
      num: 4,
      name: 'The Offer',
      dayLabel: 'Day 90',
      trigger: 'Sent 90 days in — explicit valuation offer',
      body: `${greeting},

I'd like to make a simple offer.

I can prepare a confidential, no-obligation current valuation of ${propertyAddress}: recent comparable sales, current market positioning, what the home would realistically sell for today, and what a sale would net after costs.

You don't need to be considering selling. Many families I work with use these valuations for estate planning, family conversations, or simply for clarity. Reply with one sentence — "Yes, please send the valuation" — and I'll have it to you within a week.

Sincerely,`,
    },
    {
      num: 5,
      name: 'A Family Question',
      dayLabel: 'Day 135',
      trigger: 'Sent 135 days in — gentle re-engagement',
      body: `${greeting},

I haven't heard back, which is fine — these are family decisions, and they don't run on outside schedules.

I'm writing today only to share an observation. The families I've worked with who eventually sold a long-held home almost universally said afterward that they wished they'd had a current valuation earlier — not because the number itself drove the decision, but because it grounded every subsequent family conversation in real information instead of guesses.

That offer remains open for ${propertyAddress}. A single reply is all it takes.

With respect,`,
    },
    {
      num: 6,
      name: 'Whenever the Day Comes',
      dayLabel: 'Day 180',
      trigger: 'Final letter — closes the formal sequence',
      body: `${greeting},

This is the last of my regular letters.

If the day eventually comes that your family begins thinking seriously about ${propertyAddress} — six months from now, two years, or longer — I'd like to be the person you call first. Not because of these letters, but because by then I'll have spent over a year watching ${neighborhood} closely.

Save my number. That's all I'm asking.

With genuine respect,`,
    },
  ];
}
