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
  return name.split(/\s+/).map((w) => {
    if (w.length <= 2) return w.toUpperCase();
    return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
  }).join(' ');
}

export function generateSixLetters(p) {
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
  // Estate: owner has died, heirs are involved. Direct-mail to
  // "firstname" would be tone-deaf; address the estate generically.
  const isEstate = ownerTypeRaw === 'estate' ||
                   /\b(ESTATE|HEIRS|DECEASED|SURVIVOR)\b/i.test(p.ownerName || p.owner_name || '');
  const yearsOwned = p.yearsOwned ?? p.tenure_years ?? null;

  const greeting = isEstate
    ? `To the estate of the owner`
    : isLLC
      ? `To the ownership of ${propertyAddress}`
      : isTrust
        ? `To the trustees`
        : `Dear ${firstName}`;

  const ownerTypeContext = isEstate
    ? 'an estate navigating the settlement of an inherited property'
    : isAbsentee
      ? 'an out-of-area owner who had been holding the property for years'
      : isTrust
        ? 'a property held in trust with multiple stakeholders to consider'
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
