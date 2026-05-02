/**
 * Trust archetype — voice draft v2 (letter + phone + door)
 *
 * Voice match: same Jeremy register as probate (clause-stacking,
 * em-dash cadence, disclaim what we're NOT doing, restraint as
 * confidence). The dial that turns: less personal warmth — the
 * recipient is wearing an institutional hat — and explicit
 * acknowledgment of fiduciary capacity from the first line.
 *
 * The 6-letter sequence stays in the same Day 1/30/60/90/135/180
 * cadence as probate. Phone and door are NEW shapes, formatted as
 * text strings with structure embedded so they render legibly in
 * the existing single-string content slot. When the data model
 * eventually moves to structured arrays, this same content slots
 * into branches/sections cleanly.
 *
 * Substance considerations specific to trust:
 *   - Trust accounting and beneficiary distributions are real
 *     mechanics, not euphemisms. Reference them when relevant.
 *   - Trustees often field "should we sell or distribute in kind"
 *     questions. The valuation is a planning tool for either path.
 *   - Step-up basis at grantor death applies for revocable trusts;
 *     for irrevocable trusts the math differs. Don't claim to know
 *     which one this is from public data — speak to "the question
 *     of basis" generically.
 *   - "Trustee" can be one person or several. Default to plural
 *     ("the trustees") in the body when uncertain.
 */

// ─── 6-LETTER SEQUENCE ─────────────────────────────────────────────────

export function _trustSequence_v2({ propertyAddress, neighborhood }) {
  // Greeting: institutional, plural-by-default. If the data later
  // surfaces a single trustee name, this can be specialized; for now
  // "Trustees" handles every case correctly.
  const greeting = `To the Trustees`;

  return [
    {
      num: 1,
      name: 'The Introduction',
      dayLabel: 'Day 1',
      trigger: 'Sent immediately upon enrollment — first contact, no asks',
      body: `${greeting},

I'm writing because the trust holding ${propertyAddress} crossed my desk, and I wanted to introduce myself directly rather than wait for a moment that may or may not come. My name is [your name], and I'm a real estate agent who works regularly with trusts and estates in ${neighborhood} — situations where the property sits inside a fiduciary structure, and where the question of what to do with it gets answered through trust instruments and beneficiary conversations rather than typical homeowner decisions.

I'm not asking anything of you in this letter. The question of whether and when ${propertyAddress} comes to market is a fiduciary one, made by the trustees in coordination with counsel and the beneficiaries, on whatever timeline is right for the trust. What I want you to know is that whenever a real estate decision becomes part of that conversation, I'm available, and I'll bring more to it than a number on a piece of paper.

I'll write again in a few weeks.

[Your name]`,
    },

    {
      num: 2,
      name: 'A Note, Not a Nudge',
      dayLabel: 'Day 30',
      trigger: 'Sent 30 days in — confirms presence without asking anything',
      body: `${greeting},

A month on, I wanted to follow up briefly. Trust-held real estate decisions tend to move on a slower clock than personal sales — partly because they have to, partly because there's rarely an external force pushing the timeline. That's a feature, not a bug, but it does mean the property question often gets revisited in cycles rather than resolved on a fixed date.

I'm writing to say that whenever it's relevant — at a beneficiary meeting, after a settlement of accounts, at the end of a tax year — having a current valuation of ${propertyAddress} on hand makes those cycles considerably easier. Not because anyone is being asked to act on it, but because the conversation moves faster when the math is in front of the people having it.

If that would be useful to have prepared, I can put it together for the trust's records. No commitment, no expectation of follow-up.

[Your name]`,
    },

    {
      num: 3,
      name: 'What Usually Comes Up',
      dayLabel: 'Day 60',
      trigger: 'Sent 60 days in — substantive, framed as planning material',
      body: `${greeting},

Two months in. Rather than write another note that says I'm still here, I want to share a few things that come up regularly when trusts hold real estate in ${neighborhood} — in case any of it is useful as you and the beneficiaries work through the property's place in the trust.

First, the question of disposition versus distribution-in-kind. A trust holding a single significant property usually has to choose between selling and distributing the proceeds, or transferring the property itself to a beneficiary. The right answer depends on the specifics — beneficiary tax positions, whether the property generates income, whether one beneficiary wants it and the others don't — but it almost never gets answered well without a current, defensible valuation in hand. The valuation is the document that makes the conversation possible.

Second, the question of basis. Real estate inside a trust has its own basis mechanics, and they vary depending on whether the trust is revocable or irrevocable, when the property entered the trust, and what events have occurred since. I'm not in a position to advise on any of that — your trust counsel and accountant own those calls — but I will say that most trustees I work with want a written valuation as of a specific date, regardless of which basis question is in play. It's the kind of document that's easy to commission now and meaningfully harder to reconstruct later.

Third, what a sale actually nets to the trust. Between commission, marketing costs, capital improvements done versus deferred, and the timing of the close relative to the trust's tax year, the net to the trust on the same property can vary by tens of thousands of dollars. A current valuation is the tool that lets the trustees see those variables before they have to be decided.

If a written valuation of ${propertyAddress} would be useful for the trust's records, I can prepare one. No commitment of any kind on the trust's end.

[Your name]`,
    },

    {
      num: 4,
      name: 'The Direct Offer',
      dayLabel: 'Day 90',
      trigger: 'Sent 90 days in — explicit, low-friction offer addressed to fiduciary',
      body: `${greeting},

Three months in, and I want to make a single direct offer.

I'll prepare a current written valuation of ${propertyAddress} for the trust's records, at no cost and with no obligation. That means: recent comparable sales in ${neighborhood}, a defensible market value as of today's date, an honest read on what the property would sell for if listed in the next 30/60/90 days, and a one-page summary the trustees can hand to counsel, an accountant, or a beneficiary at the next meeting.

I'm framing this as a direct offer rather than a soft suggestion because it's actually useful — fiduciaries who have current documentation on the trust's largest asset make better decisions, faster, with fewer second meetings. The cost to the trust is zero. The cost to you is one sentence in reply.

"Yes, please prepare a valuation" — and I'll have it to the trustees within a week.

[Your name]`,
    },

    {
      num: 5,
      name: 'A Practical Note',
      dayLabel: 'Day 135',
      trigger: 'Sent 135 days in — observational, sets up the standing offer',
      body: `${greeting},

I haven't heard back, which is fine — I've never assumed otherwise.

I want to leave one observation, and then I'll close out this sequence in a few weeks.

The trustees I've worked with who handled trust-held real estate well — meaning the property ended up where it needed to be, in a way that served the beneficiaries and held up under any later scrutiny — almost always shared one habit. They commissioned a current valuation early, before any disposition decision was on the table. Not because they were planning to sell, but because the document itself created clarity. It made the next beneficiary meeting easier. It made the trust's annual accounting cleaner. It gave counsel something concrete to reference.

I'm not telling you this to push the offer in my last letter. I'm telling you because in my experience it's true — and because if I were a trustee on the receiving end of a letter like this, I'd want to know it.

[Your name]`,
    },

    {
      num: 6,
      name: 'A Standing Offer',
      dayLabel: 'Day 180',
      trigger: 'Final letter — closes the sequence, leaves the door open',
      body: `${greeting},

This is the last of the letters I planned to write to the trust. I won't keep sending them on a schedule — I've said what I think is worth saying, and the rest is timing.

Two things to leave you with.

First, the offer doesn't expire. Whenever the trustees want a current written valuation of ${propertyAddress} — six months from now, six years, whenever the question becomes relevant — I'll prepare one. The terms haven't changed: no cost to the trust, no commitment, no follow-up calls unless the trustees ask for them.

Second, if when the time comes the trustees have decided to work with another agent, that's fine too. The point of this sequence wasn't to win the trust's business through volume of mail. It was to make sure that if our paths crossed at the right moment, you knew who I was. That's done now.

Whenever the trust needs me,

[Your name]`,
    },
  ];
}


// ─── PHONE SCRIPT ──────────────────────────────────────────────────────
// Renders as a single string with section headers and clear branching.
// Format chosen for readability under call pressure: short labels in
// caps, indented branches, agent's lines marked "YOU:".
//
// Branch logic: 3 most common reactions covered, plus a graceful exit.

export function _trustPhoneScript_v2({ propertyAddress }) {
  return `BEFORE YOU CALL
Confirm you have the trustee's contact, not the grantor's. If the
trust is in administration after a grantor death, the trustee is
typically the spouse, an adult child, or named professional. The
call posture: respectful of fiduciary duty, not chatty.

OPENER (first 10 seconds)
YOU: "Good morning — is this [trustee's name]? My name is [your
     name], I'm calling on a real estate matter regarding ${propertyAddress}.
     This isn't a sales call — I work with trusts and estates and
     wanted to introduce myself in case real estate becomes part of
     the trust's planning. Do you have ninety seconds?"

If they say YES, continue to REASON.
If they say NO or "wrong time," go to GRACEFUL EXIT.

REASON (the next 30 seconds)
YOU: "I came across ${propertyAddress} as a trust-held property and
     wanted to be on the trust's radar before any decision about the
     property is being made. Most trustees I work with eventually
     need a current valuation for one of three reasons — a beneficiary
     meeting, a tax filing, or a disposition decision — and the
     valuation is much more useful when it's already on hand than
     when it needs to be commissioned under time pressure. I'm
     offering to prepare one for the trust at no cost and no
     commitment. That's the entire reason for the call."

LIKELY REACTIONS

  If they say "send me information / send me a valuation":
  YOU: "I will. Can you give me an email address that's appropriate
       for the trust's correspondence? I'll have a written valuation
       and a short cover note to you within a week. No follow-up
       calls unless you ask for them."

  If they say "we're not selling / not interested":
  YOU: "Understood — and just to be clear, the offer isn't tied to
       a sale. Trustees often want a written valuation on file even
       when there's no plan to sell, because it makes the next
       beneficiary meeting or accounting cleaner. If that's still
       not useful, I'll leave you alone. Either way, you have my
       number now."

  If they say "I'm in the middle of something / call back":
  YOU: "Of course — I won't keep you. Can I send a brief letter
       instead? It covers the same ground in two paragraphs and
       doesn't require a call. If you're interested after reading
       it, the next move is yours."

GRACEFUL EXIT (any negative or pressed-for-time signal)
YOU: "I appreciate the time. I'll follow up with a short letter
     that lays out the offer in writing — feel free to discard it
     if it's not useful. Have a good rest of your day."

AFTER THE CALL
- If they accepted: prepare the valuation within five business days.
  Send via email with one sentence: "Here's the valuation we
  discussed. No follow-up calls unless you ask for them."
- If they declined: log the call, do not call again. The letter
  sequence continues on its own cadence.
- If voicemail: leave a 20-second message. "Hello — this is [your
  name], a real estate agent in ${propertyAddress}'s area. I'm not
  selling anything, and I won't call back. I'm sending a letter
  with a one-time offer that may or may not be relevant to the
  trust. Apologies for the cold call."`;
}


// ─── DOOR SCRIPT ──────────────────────────────────────────────────────
// Door knocks for trust-held property are unusual — the property is
// often vacant or occupied by a beneficiary, not the trustee. The
// situational note up front matters more than the script itself.

export function _trustDoorScript_v2({ propertyAddress, neighborhood }) {
  return `BEFORE YOU KNOCK — JUDGMENT CALL
Trust-held property may not be occupied by anyone connected to the
trust. The person who answers could be a beneficiary, a tenant, a
caretaker, or someone with no role at all. Door knocks for trust
properties are often more useful as a leave-behind than as a
conversation. Pause on the porch and read the situation before you
ring:

  - If the property looks occupied (current vehicles, lights on,
    landscaping maintained): proceed to the script.
  - If the property looks unoccupied or transitional (estate sale
    signs, papers on the porch, vacant landscaping): do NOT knock.
    Leave a card and a handwritten note ("Hello — I'm [your name],
    a real estate agent who works with trusts in ${neighborhood}. If
    you or the trust ever wants a current valuation of this
    property, please call. No obligation.") in the door.
  - If you can see active grief or a recent loss (memorial flowers,
    a wreath, family gathering visible): leave a card and walk away.
    A door knock at that moment is the wrong call.

OPENER (when you do knock)
YOU: "Good [morning / afternoon] — sorry to interrupt. My name is
     [your name], I'm a real estate agent in ${neighborhood}. I'm
     not selling anything and I won't take much of your time. I
     understand this property is held in trust, and I wanted to
     leave a card for whoever serves as trustee — in case real
     estate ever becomes part of the trust's planning. Are you
     connected to the trust, or is there someone better I should
     reach?"

LIKELY REACTIONS

  If they ARE the trustee (or beneficiary acting on the trust's behalf):
  YOU: "I appreciate it. I work regularly with trusts in
       ${neighborhood} and offer a free written valuation for the
       trust's records — no obligation, no follow-up calls. Would
       it be useful for me to prepare one?" If yes, get an email
       and depart. Don't oversell.

  If they're a tenant / caretaker / unrelated:
  YOU: "No worries. Could you pass this card along, or let me know
       how I'd reach the trustee? If not, I'll leave the card and
       won't bother anyone further." Hand them the card. Leave.

  If they're hostile or confused:
  YOU: "I understand — apologies for the interruption. Here's my
       card, please pass it along if it's relevant, and I'll let
       you go." Step back from the door. Walk away.

LEAVE-BEHIND
Always leave: business card, plus a handwritten short note on the
back or on a separate slip — three sentences max. Suggested copy:

  "[Trustee or family name] — I'm a real estate agent in
   ${neighborhood} who works with trusts. If a current valuation of
   ${propertyAddress} would be useful for the trust, please call.
   No obligation. — [Your name]"

AFTER THE VISIT
- Log the visit: time, who answered, outcome.
- Do not return for at least 60 days, regardless of outcome.
- The letter sequence continues on its own cadence whether or not
  a door knock happened.`;
}
