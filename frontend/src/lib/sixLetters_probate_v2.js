/**
 * Probate sequence — voice draft v2
 *
 * Voice match against three samples provided by Jeremy:
 *   1. Broken Americana (fiction, Chs 1-3)  — clause-stacking,
 *      physical specificity, dry restraint
 *   2. The Agency letterhead (transactional) — em-dash cadence, plain
 *      words/complex sentences, names the elephant, restraint as
 *      confidence ("just an open door, whenever the timing is right")
 *   3. WARD op-ed (argumentative)            — disclaims credentials,
 *      anticipates objections, ends on weight, willingness to use
 *      strong figures
 *
 * Cross-cutting patterns applied:
 *   - Em-dashes as load-bearing punctuation; warmth lives after the dash
 *   - Plain vocabulary, complex sentence structure
 *   - Disclaim what we're NOT doing as a way of building trust
 *   - End on the actual point, not a sign-off paragraph
 *   - Restraint over reach ("a few materials" not "comprehensive")
 *   - Name the elephant directly when one is in the room
 *
 * What I deliberately removed from the prior shipped version:
 *   - "I'd be glad to" / "I'd welcome" hedge-language
 *   - "Warm regards" / "With respect" sign-offs that do warmth work
 *     the body should be doing
 *   - Choppy short paragraphs (Jeremy's prose runs longer)
 *   - Any sentence that reads as Anthropic house style
 *
 * Structure parity with prior version: same 6 letters, same Day
 * 1/30/60/90/135/180 cadence, same input shape (prFirst,
 * decedentName, propertyAddress, neighborhood). Drop-in replacement
 * if approved.
 */

export function _probateSequence_v2({ prFirst, decedentName, propertyAddress, neighborhood }) {
  // Greeting: PR first name when known, "the family" otherwise. The
  // deceased is named once in letter 1 — never as the addressee, only
  // as the reason for writing — and not named again. Repeating the
  // name across six letters would feel performative.
  const greeting = prFirst ? `Dear ${prFirst}` : `To the family`;
  const decedentRef = decedentName
    ? `${decedentName}'s estate`
    : `the estate`;

  return [
    {
      num: 1,
      name: 'The Introduction',
      dayLabel: 'Day 1',
      trigger: 'Sent immediately upon enrollment — first contact, no asks',
      body: `${greeting},

I'm writing because I came across the filing for ${decedentRef} and wanted to introduce myself directly, rather than wait for a moment that may or may not come. My name is [your name], and I'm a real estate agent who works with families navigating the question of what to do with a home after someone has passed.

I'm not asking anything of you in this letter. The decision about ${propertyAddress} — when, whether, how — is yours, and it should be made on your timeline, not anyone else's. What I want you to know is that whenever that conversation feels useful, I'm available, and I'll bring more to it than a number on a piece of paper.

Until then, please accept my condolences. I'll write again in a few weeks.

[Your name]`,
    },

    {
      num: 2,
      name: 'A Note, Not a Nudge',
      dayLabel: 'Day 30',
      trigger: 'Sent 30 days in — confirms presence without asking anything',
      body: `${greeting},

A month on, I wanted to follow up briefly — not to ask anything, but because in my experience the families who eventually find the right outcome with a property like this are the ones who started the conversation early, when there was no urgency. Not "early" in the sense of rushing — early in the sense of having someone to call before the question becomes pressing.

That's the whole reason I'm writing again. The administration of an estate has its own rhythms — paperwork, accountings, conversations between siblings or cousins or attorneys — and a property decision often gets pushed to the back of that pile until it can't be pushed any further. By then the choices are narrower than they needed to be.

If you'd like to talk through what selling ${propertyAddress} would actually look like — even informally, even hypothetically — I'm here. If not, I'll keep writing on the cadence I planned, and I won't take silence as anything other than what it is.

[Your name]`,
    },

    {
      num: 3,
      name: 'What Usually Comes Up',
      dayLabel: 'Day 60',
      trigger: 'Sent 60 days in — first letter that contains substance, framed as practical',
      body: `${greeting},

Two months in. Rather than write another note that says "I'm still here," I want to share a few things I've learned about properties in ${neighborhood} that go through estate transitions, in case any of it is useful — now or later.

First, the timing question. Most families assume an estate-held property has to be sold quickly, and that's almost never true. The estate's needs vary, and the right pace depends on the specifics — outstanding debts, the wishes of the heirs, what the property itself needs before listing. A good agent's first job is to understand which of those is actually pressing and which is being assumed.

Second, the basis question. The cost basis of an inherited property is usually stepped up to its value at the date of death, which can change the tax math significantly. Most people I work with want a defensible valuation as of that date, written down, regardless of whether they decide to sell — because the question comes up later, often unexpectedly, and the answer is much harder to reconstruct after the fact.

Third, what a sale actually nets. Between commission, prep work, capital improvements done versus deferred, and the timing of the close relative to other estate events, the net to the estate can vary by twenty or thirty thousand dollars on the same property — sometimes more. A current valuation isn't just a number. It's a planning tool.

If any of that would be useful to have in writing for ${propertyAddress}, I can put it together. No commitment of any kind on your end.

[Your name]`,
    },

    {
      num: 4,
      name: 'The Direct Offer',
      dayLabel: 'Day 90',
      trigger: 'Sent 90 days in — explicit, declarative, low-friction ask',
      body: `${greeting},

Three months in, and I want to make a single direct offer.

I'll prepare a current valuation of ${propertyAddress} for the estate's records, at no cost and with no obligation. That means: recent comparable sales in ${neighborhood}, a defensible market value as of today's date, an honest read on what the property would sell for if listed in the next 30/60/90 days, and a one-page summary you can hand to an attorney or an accountant or keep in a file for whenever it becomes relevant.

The reason I'm framing this as a direct offer rather than a soft suggestion is that it's actually useful — and most people who say "I should get one of those at some point" never do, and then later wish they had. The valuation takes me a few hours. It costs you nothing. It might matter; it might not. But you'll have it.

Reply with a single sentence — "Yes, please" — and I'll have it to you within a week.

[Your name]`,
    },

    {
      num: 5,
      name: 'A Practical Note',
      dayLabel: 'Day 135',
      trigger: 'Sent 135 days in — re-engagement, observational rather than promotional',
      body: `${greeting},

I haven't heard back from you, which is fine — there's no obligation in the direction of any of these letters, and I've never assumed otherwise.

I want to offer one observation, and then I'll close out this sequence in a few weeks.

The families I've worked with who handled an estate's property well — meaning they ended up where they wanted to be, on a timeline that suited them — almost always had one thing in common. They got a current valuation early, before any decisions had to be made. Not because they were planning to sell, but because the number itself clarified what their actual options were. Sometimes the right answer turned out to be "sell now," sometimes "hold for a few years," sometimes "transfer to a family member who wants to live there." But none of those answers was visible until the math was in front of them.

I'm not telling you this to push the offer in my last letter. I'm telling you because in my experience it's true, and because if I were on your side of this conversation I'd want to know it.

[Your name]`,
    },

    {
      num: 6,
      name: 'A Standing Offer',
      dayLabel: 'Day 180',
      trigger: 'Final letter — closes the sequence, leaves the door open',
      body: `${greeting},

This is the last of the letters I planned to write. I won't keep sending them on a schedule — I've said what I think is worth saying, and the rest is timing.

Two things to leave you with.

First, the offer doesn't expire. Whenever you want a current valuation of ${propertyAddress} — whether that's six months from now or six years — I'll prepare one. The terms haven't changed: no cost, no commitment, no follow-up calls unless you ask for them.

Second, if when the time comes you've decided to work with someone else, that's fine too. The point of this sequence wasn't to win your business through volume of mail. It was to make sure that if our paths crossed at the right moment, you knew who I was. That's done now.

Whenever you need me,

[Your name]`,
    },
  ];
}
