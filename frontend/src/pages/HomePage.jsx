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
//   2. Sample lead — single lead-row-style card with a real-looking
//      entry (synthetic name, illustrative archetype labels, sample
//      letter excerpt)
//   3. Voice — what the system writes for the agent. Two short
//      paragraphs, one sample-letter excerpt.
//   4. Territory — condensed list, real availability count
//   5. Footer CTA — direct, no metaphor

const AUTH_REQUIRED = import.meta.env.VITE_AUTH_REQUIRED === 'true';


export default function HomePage() {
  return (
    <SiteLayout mode="public" showFooter>
      <Hero />
      <SampleLead />
      <Voice />
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
          <span style={{ color: 'var(--call-now)' }}>Eight</span>{' '}
          sellers to contact this week, in your voice.
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
          A weekly briefing of the property owners most likely to sell &middot;
          surfaced from court records, ownership history, and structural
          signals &middot; with first-touch outreach drafted in your own voice.
        </div>

        <div style={{
          display: 'flex',
          gap: 'var(--space-md)',
          flexWrap: 'wrap',
          marginBottom: 'var(--space-lg)',
        }}>
          {AUTH_REQUIRED ? (
            <>
              <Link to="/signup" style={ctaPrimary}>Request access</Link>
              <Link to="/login"  style={ctaGhost}>Sign in</Link>
            </>
          ) : (
            <>
              <Link to="/territories" style={ctaPrimary}>Open the briefing</Link>
              <Link to="/zip/98004"   style={ctaGhost}>Sample a territory</Link>
            </>
          )}
        </div>

        <div style={{
          fontSize: 11,
          letterSpacing: '0.06em',
          color: 'var(--text-tertiary)',
          fontFamily: 'var(--font-sans)',
          fontStyle: 'italic',
        }}>
          Eleven territories live. Eight currently held. Three open.
        </div>
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
          Each lead surfaces a household at a moment that matters.
        </h2>

        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 16,
          color: 'var(--text-secondary)',
          lineHeight: 1.7,
          marginBottom: 'var(--space-2xl)',
          maxWidth: 620,
        }}>
          A real entry pulled from the briefing &mdash; with the first
          letter that would be sent, drafted in the agent&rsquo;s voice.
          Names below are illustrative.
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
          Each territory is held by the agent who claims it. There is one
          rolodex per ZIP, and one agent reading it. Additional markets
          opening selectively.
        </p>

        <div style={{
          display: 'flex',
          gap: 'var(--space-2xl)',
          paddingTop: 'var(--space-md)',
          borderTop: '1px solid var(--border)',
          flexWrap: 'wrap',
        }}>
          <Stat label="Live" value="11" />
          <Stat label="Held" value="8" />
          <Stat label="Open" value="3" />
        </div>
      </div>
    </section>
  );
}


function Stat({ label, value }) {
  return (
    <div>
      <div style={{
        fontFamily: 'var(--font-display)',
        fontSize: 44,
        fontWeight: 600,
        color: 'var(--text)',
        lineHeight: 1,
        letterSpacing: '-0.02em',
      }}>
        {value}
      </div>
      <div style={{
        fontSize: 10,
        fontWeight: 700,
        color: 'var(--text-tertiary)',
        letterSpacing: '0.14em',
        textTransform: 'uppercase',
        fontFamily: 'var(--font-sans)',
        marginTop: 8,
      }}>
        {label}
      </div>
    </div>
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
          Currently in private beta. Three territories open.
        </h2>

        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 16,
          color: 'var(--text-secondary)',
          lineHeight: 1.7,
          marginBottom: 'var(--space-xl)',
        }}>
          Access is by invitation. Reach out and we&rsquo;ll send you the
          briefing for one week to see for yourself.
        </p>

        <div style={{
          display: 'flex',
          gap: 'var(--space-md)',
          flexWrap: 'wrap',
        }}>
          {AUTH_REQUIRED ? (
            <Link to="/signup" style={ctaPrimary}>Request access</Link>
          ) : (
            <Link to="/territories" style={ctaPrimary}>Open the briefing</Link>
          )}
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
