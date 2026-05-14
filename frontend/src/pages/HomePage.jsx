import { Link } from 'react-router-dom';
import SiteLayout from '../components/shell/SiteLayout.jsx';
import Logo from '../components/shell/Logo.jsx';

// HomePage — the public landing at `/`.
//
// Direction: this page reads in the same voice as the briefing page.
// Same typographic hierarchy (Playfair 28-32pt headlines with the
// call-now red on the lead number, italic serif oracle line, small-
// caps eyebrows). No metaphors, no editorial flourishes — direct,
// declarative product copy in the register the agent will see again
// the moment they're inside the product.
//
// Structure (top to bottom):
//   1. Hero — number-led headline, oracle subhead
//   2. Built by an agent — moat: not engineer-built, not investor-pitched
//   3. Sample lead — single lead-row-style card with a real-looking
//      entry (synthetic name, illustrative archetype labels, sample
//      letter excerpt)
//   4. Voice — what the system writes for the agent. Two short
//      paragraphs, one sample-letter excerpt.
//   5. Two-sided personalization — moat: agent voice + lead-specific
//      archetype treatment, not one-size-fits-all
//   6. Territory — condensed list, real availability count, moat:
//      one-agent-per-ZIP as structural exclusivity, not pricing
//   7. Footer CTA — direct, no metaphor

export default function HomePage() {
  return (
    <SiteLayout mode="public" showFooter>
      <Hero />
      <BuiltByAgent />
      <SampleLead />
      <Voice />
      <TwoSidedPersonalization />
      <Territory />
      <FooterCTA />
    </SiteLayout>
  );
}


// ─────────────────────────────────────────────────────────────────
// Hero — number-led, briefing-page register
// ─────────────────────────────────────────────────────────────────
function Hero() {
  return (
    <section style={{
      background: 'var(--bg)',
      padding: '120px 32px 80px',
      borderBottom: '1px solid var(--border)',
    }}>
      <div style={{ maxWidth: 880, margin: '0 auto' }}>
        <div style={{ marginBottom: 'var(--space-2xl)' }}>
          <Logo tone="dark" size="hero" />
        </div>

        <div style={{
          fontSize: 10,
          fontWeight: 600,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: 'var(--text-tertiary)',
          marginBottom: 'var(--space-md)',
          fontFamily: 'var(--font-sans)',
        }}>
          Private &middot; By Invitation
        </div>

        <h1 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(36px, 4.4vw, 56px)',
          fontWeight: 600,
          color: 'var(--text)',
          lineHeight: 1.12,
          letterSpacing: '-0.015em',
          marginBottom: 'var(--space-md)',
        }}>
          We <span style={{ color: 'var(--call-now)' }}>find</span>{' '}
          sellers before they even know they&rsquo;re sellers.
        </h1>

        <div style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontSize: 17,
          color: 'var(--text-secondary)',
          lineHeight: 1.6,
          marginBottom: 'var(--space-xl)',
          maxWidth: 640,
        }}>
          SellerSignal surfaces the life events that force a property
          decision &middot; long before the listing call. Probate,
          divorce, estate transition, foreclosure. We identify the
          decision-maker by name, verify their contact, and deliver
          them weekly in your exclusive ZIP. Built by a working agent.
        </div>

        <div style={{
          display: 'flex',
          gap: 'var(--space-md)',
          flexWrap: 'wrap',
          marginBottom: 'var(--space-lg)',
        }}>
          <Link to="/login" style={ctaPrimary}>Sign in</Link>
          <Link to="/signup" style={ctaGhost}>Request access</Link>
        </div>

        <div style={{
          fontSize: 11,
          letterSpacing: '0.06em',
          color: 'var(--text-tertiary)',
          fontFamily: 'var(--font-sans)',
          fontStyle: 'italic',
        }}>
          Private &middot; by invitation &middot; one agent per ZIP.
        </div>
      </div>
    </section>
  );
}


// ─────────────────────────────────────────────────────────────────
// BuiltByAgent — the credibility moat. Counter-positions vs typical
// lead-gen tools that were built by engineers selling to investors
// and retrofitted for agents. Sits right after the hero because it's
// what reframes everything that follows: this product is not a
// generic stack with an agent skin.
// ─────────────────────────────────────────────────────────────────
function BuiltByAgent() {
  return (
    <section style={{
      background: 'var(--bg)',
      padding: '80px 32px',
      borderBottom: '1px solid var(--border)',
    }}>
      <div style={{ maxWidth: 720, margin: '0 auto' }}>
        <h2 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(28px, 3.2vw, 38px)',
          fontWeight: 600,
          color: 'var(--text)',
          lineHeight: 1.18,
          letterSpacing: '-0.01em',
          marginBottom: 'var(--space-md)',
        }}>
          Built by agents. For agents.
        </h2>

        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 16,
          color: 'var(--text-secondary)',
          lineHeight: 1.8,
          marginBottom: 'var(--space-md)',
        }}>
          Most lead-gen tools are built by engineers selling to investors
          and retrofitted for agents who never asked for them. SellerSignal
          is the opposite.
        </p>

        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 16,
          color: 'var(--text-secondary)',
          lineHeight: 1.8,
        }}>
          Every script, every signal, every choice about when to call
          and when to wait &mdash; designed by a working agent against
          the situations agents face every week. The difference between
          a product that hands you a list and one that hands you a
          strategy.
        </p>
      </div>
    </section>
  );
}


// ─────────────────────────────────────────────────────────────────
// SampleLead — a single lead-row-style card. Same visual language
// as the real briefing's lead rows, slightly stylized for context.
// ─────────────────────────────────────────────────────────────────
function SampleLead() {
  return (
    <section style={{
      background: 'var(--bg-card)',
      padding: '80px 32px',
      borderBottom: '1px solid var(--border)',
    }}>
      <div style={{ maxWidth: 880, margin: '0 auto' }}>
        <Eyebrow>What an entry looks like</Eyebrow>

        <h2 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(28px, 3.2vw, 38px)',
          fontWeight: 600,
          color: 'var(--text)',
          lineHeight: 1.18,
          letterSpacing: '-0.01em',
          marginBottom: 'var(--space-md)',
        }}>
          Each lead surfaces a household at a moment that matters &mdash;
          and the person who actually makes the decision.
        </h2>

        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 16,
          color: 'var(--text-secondary)',
          lineHeight: 1.7,
          marginBottom: 'var(--space-2xl)',
          maxWidth: 620,
        }}>
          Not the deceased homeowner. Not the LLC. The personal
          representative, by name. A real entry from the briefing &mdash;
          with the first letter that would be sent, drafted in the
          agent&rsquo;s voice. Names below are illustrative.
        </p>

        {/* Lead-row style card — left rule + name + signal + body */}
        <article style={{
          background: 'var(--bg)',
          border: '1px solid var(--border)',
          borderLeft: '3px solid var(--call-now)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-xl)',
        }}>
          {/* Header row — archetype label + week */}
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
            marginBottom: 'var(--space-md)',
            flexWrap: 'wrap',
            gap: 8,
          }}>
            <div style={{
              fontSize: 10,
              fontWeight: 700,
              color: 'var(--call-now)',
              letterSpacing: '0.14em',
              textTransform: 'uppercase',
              fontFamily: 'var(--font-sans)',
            }}>
              Probate &middot; Family PR identified
            </div>
            <div style={{
              fontSize: 11,
              color: 'var(--text-tertiary)',
              fontFamily: 'var(--font-sans)',
              fontStyle: 'italic',
            }}>
              Filed 4 days ago
            </div>
          </div>

          {/* Name */}
          <div style={{
            fontFamily: 'var(--font-display)',
            fontSize: 26,
            fontWeight: 600,
            color: 'var(--text)',
            letterSpacing: '-0.005em',
            marginBottom: 4,
          }}>
            J. Bryant
          </div>

          {/* Address + tenure */}
          <div style={{
            fontFamily: 'var(--font-serif)',
            fontSize: 14,
            color: 'var(--text-secondary)',
            marginBottom: 'var(--space-lg)',
          }}>
            5421 Lakeview Drive &middot; 14-year tenure &middot;
            personal representative confirmed
          </div>

          {/* Sample letter excerpt */}
          <div style={{
            fontSize: 10,
            fontWeight: 700,
            color: 'var(--text-tertiary)',
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            fontFamily: 'var(--font-sans)',
            marginBottom: 'var(--space-sm)',
          }}>
            Day 1 &middot; in your voice
          </div>
          <div style={{
            fontFamily: 'var(--font-serif)',
            fontSize: 15,
            color: 'var(--text)',
            lineHeight: 1.75,
            background: 'var(--bg-input)',
            padding: 'var(--space-lg)',
            borderRadius: 'var(--radius-md)',
            whiteSpace: 'pre-wrap',
          }}>
{`Dear Joseph,

I work with families navigating decisions about a home, and I wanted to reach out regarding the property on Lakeview Drive. That's your decision, on your timeline.

What I do want you to know: at this level, the difference between a well-executed sale and a missed opportunity often comes down to one thing — who is running the process. I also maintain a private network of qualified buyers who prefer to transact discreetly, outside the public market.

No pressure, no follow-up calls. Just an open door, whenever the timing is right.`}
          </div>
        </article>
      </div>
    </section>
  );
}


// ─────────────────────────────────────────────────────────────────
// Voice — short, direct, two paragraphs
// ─────────────────────────────────────────────────────────────────
function Voice() {
  return (
    <section style={{
      background: 'var(--bg)',
      padding: '100px 32px',
      borderBottom: '1px solid var(--border)',
    }}>
      <div style={{ maxWidth: 720, margin: '0 auto' }}>
        <Eyebrow>The voice</Eyebrow>

        <h2 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(28px, 3.2vw, 38px)',
          fontWeight: 600,
          color: 'var(--text)',
          lineHeight: 1.18,
          letterSpacing: '-0.01em',
          marginBottom: 'var(--space-lg)',
        }}>
          Outreach drafted in the agent&rsquo;s voice. Not a house style.
        </h2>

        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 16,
          color: 'var(--text-secondary)',
          lineHeight: 1.8,
          marginBottom: 'var(--space-md)',
        }}>
          Most outreach in this industry sounds like outreach. SellerSignal
          captures the agent&rsquo;s cadence, stance, and bio at onboarding,
          then generates phone, letter, and door scripts across six
          archetypes &mdash; in their voice.
        </p>

        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 16,
          color: 'var(--text-secondary)',
          lineHeight: 1.8,
        }}>
          Lead-specific details are substituted at view time. The recipient
          reads a letter that sounds like the agent wrote it after dinner.
        </p>
      </div>
    </section>
  );
}


// ─────────────────────────────────────────────────────────────────
// TwoSidedPersonalization — the lead-side analytics moat. The Voice
// section just established agent-side personalization (the script
// sounds like the agent). This section establishes the other side:
// each lead is treated differently based on signal type. A probate
// is not a divorce is not a foreclosure. Six archetypes, six
// approaches.
// ─────────────────────────────────────────────────────────────────
function TwoSidedPersonalization() {
  return (
    <section style={{
      background: 'var(--bg)',
      padding: '100px 32px',
      borderBottom: '1px solid var(--border)',
    }}>
      <div style={{ maxWidth: 720, margin: '0 auto' }}>
        <Eyebrow>Both sides</Eyebrow>

        <h2 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(28px, 3.2vw, 38px)',
          fontWeight: 600,
          color: 'var(--text)',
          lineHeight: 1.18,
          letterSpacing: '-0.01em',
          marginBottom: 'var(--space-md)',
        }}>
          Two-sided personalization.
        </h2>

        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 16,
          color: 'var(--text-secondary)',
          lineHeight: 1.8,
          marginBottom: 'var(--space-md)',
        }}>
          The agent&rsquo;s voice goes one way. The lead&rsquo;s
          situation goes the other. A probate is not a divorce is not
          a foreclosure is not an obituary &mdash; each one is a
          different person at a different moment, with a different
          need.
        </p>

        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 16,
          color: 'var(--text-secondary)',
          lineHeight: 1.8,
        }}>
          SellerSignal treats them differently. Six archetypes, six
          approaches. What to say, when to call, when to wait, when
          to write instead. The opposite of one-size-fits-all.
        </p>
      </div>
    </section>
  );
}


// ─────────────────────────────────────────────────────────────────
// Territory — condensed list, no per-ZIP grid
// ─────────────────────────────────────────────────────────────────
function Territory() {
  return (
    <section style={{
      background: 'var(--bg-card)',
      padding: '100px 32px',
      borderBottom: '1px solid var(--border)',
    }}>
      <div style={{ maxWidth: 720, margin: '0 auto' }}>
        <Eyebrow>The territory</Eyebrow>

        <h2 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(28px, 3.2vw, 38px)',
          fontWeight: 600,
          color: 'var(--text)',
          lineHeight: 1.18,
          letterSpacing: '-0.01em',
          marginBottom: 'var(--space-md)',
        }}>
          One agent per ZIP. Held exclusively.
        </h2>

        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 16,
          color: 'var(--text-secondary)',
          lineHeight: 1.7,
          marginBottom: 'var(--space-lg)',
        }}>
          Each territory is owned by one agent &mdash; entirely. The
          data, the contact info, the briefing &mdash; yours alone.
          Most lead-gen tools sell the same lead to ten buyers and
          call it scale. SellerSignal sells one territory to one
          agent and calls it ownership. Additional markets opening
          selectively.
        </p>
      </div>
    </section>
  );
}


// ─────────────────────────────────────────────────────────────────
// Footer CTA — single restrained closer
// ─────────────────────────────────────────────────────────────────
function FooterCTA() {
  return (
    <section style={{
      background: 'var(--bg)',
      padding: '100px 32px',
      textAlign: 'left',
    }}>
      <div style={{ maxWidth: 720, margin: '0 auto' }}>
        <h2 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(26px, 3vw, 34px)',
          fontWeight: 600,
          color: 'var(--text)',
          lineHeight: 1.2,
          letterSpacing: '-0.01em',
          marginBottom: 'var(--space-md)',
        }}>
          Access is by invitation.
        </h2>

        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 16,
          color: 'var(--text-secondary)',
          lineHeight: 1.7,
          marginBottom: 'var(--space-xl)',
        }}>
          We&rsquo;re selective about the agents we work with and the
          markets we open. If your territory isn&rsquo;t live yet, we
          can tell you when it will be.
        </p>

        <div style={{
          display: 'flex',
          gap: 'var(--space-md)',
          flexWrap: 'wrap',
        }}>
          <Link to="/login" style={ctaPrimary}>Sign in</Link>
          <Link to="/signup" style={ctaGhost}>Request access</Link>
        </div>
      </div>
    </section>
  );
}


// ── shared eyebrow ────────────────────────────────────────────────
function Eyebrow({ children }) {
  return (
    <div style={{
      fontSize: 10,
      fontWeight: 700,
      color: 'var(--accent)',
      letterSpacing: '0.16em',
      textTransform: 'uppercase',
      marginBottom: 'var(--space-md)',
      fontFamily: 'var(--font-sans)',
    }}>
      {children}
    </div>
  );
}


// ── CTAs ──────────────────────────────────────────────────────────
const ctaBase = {
  padding: '14px 32px',
  borderRadius: 'var(--radius-md)',
  fontSize: 14,
  fontWeight: 600,
  fontFamily: 'var(--font-sans)',
  textDecoration: 'none',
  display: 'inline-block',
  letterSpacing: '0.04em',
  transition: 'all 0.15s ease',
};

const ctaPrimary = {
  ...ctaBase,
  background: 'var(--accent)',
  color: 'var(--text-inverse)',
  border: '1px solid var(--accent)',
};

const ctaGhost = {
  ...ctaBase,
  background: 'transparent',
  border: '1px solid var(--border-strong)',
  color: 'var(--text)',
};
