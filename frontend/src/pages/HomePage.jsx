import { Link } from 'react-router-dom';
import SiteLayout from '../components/shell/SiteLayout.jsx';
import Logo from '../components/shell/Logo.jsx';

// HomePage — the public landing at `/`.
//
// Concept: a private notebook. Cover is dark; pages inside are cream.
// What you see is what an agent who has been let inside would see —
// a curated rolodex of who's about to sell, written in their voice,
// not a software product brochure. Editorial restraint, not marketing
// hype. The metaphor itself is the punch.
//
// Structure (top to bottom):
//   1. Cover — dark hero, single line of typography, gold wordmark
//   2. Two notebook entries — long-tenure + estate transition
//   3. The voice — single quiet section explaining what makes the
//      letters land
//   4. The territory — eleven King County ZIPs, a guest list
//   5. Footer — closes the cover

const AUTH_REQUIRED = import.meta.env.VITE_AUTH_REQUIRED === 'true';

export default function HomePage() {
  return (
    <SiteLayout mode="public" showFooter>
      <Cover />
      <NotebookSpread />
      <VoiceSection />
      <TerritoryList />
      <Closing />
    </SiteLayout>
  );
}


// ─────────────────────────────────────────────────────────────────
// Cover — the dark hero. The book cover.
// ─────────────────────────────────────────────────────────────────
function Cover() {
  return (
    <section style={{
      position: 'relative',
      minHeight: 'calc(100vh - 56px)',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      alignItems: 'center',
      padding: '140px 32px 120px',
      overflow: 'hidden',
      background: 'var(--bg-dark)',
      color: 'var(--text-inverse)',
    }}>
      {/* Soft amber glow above the headline — fireplace cast, not a spotlight */}
      <div style={{
        position: 'absolute',
        top: '12%',
        left: '50%',
        width: 720,
        height: 480,
        transform: 'translateX(-50%)',
        background: 'radial-gradient(ellipse, rgba(186, 137, 47, 0.18) 0%, rgba(186, 137, 47, 0.05) 35%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      {/* Faint gold rule below the headline, the kind found at the top of a chapter */}
      <div style={{
        position: 'absolute',
        left: '50%',
        bottom: '34%',
        width: 80,
        height: 1,
        transform: 'translateX(-50%)',
        background: 'linear-gradient(90deg, transparent, rgba(186, 137, 47, 0.6), transparent)',
        pointerEvents: 'none',
      }} />

      <div style={{
        position: 'relative',
        zIndex: 1,
        maxWidth: 760,
        textAlign: 'center',
      }}>
        <div style={{ marginBottom: 56 }}>
          <Logo tone="light" size="hero" />
        </div>

        <div style={{
          fontSize: 11,
          letterSpacing: '0.32em',
          textTransform: 'uppercase',
          color: 'rgba(186, 137, 47, 0.85)',
          fontFamily: 'var(--font-sans)',
          fontWeight: 600,
          marginBottom: 32,
        }}>
          Private &middot; By Invitation
        </div>

        <h1 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(38px, 5vw, 60px)',
          lineHeight: 1.12,
          color: 'var(--text-inverse)',
          marginBottom: 28,
          letterSpacing: '-0.015em',
          fontWeight: 500,
        }}>
          A private record of who is{' '}
          <em style={{
            fontStyle: 'italic',
            color: 'rgba(186, 137, 47, 0.9)',
            fontWeight: 500,
          }}>about to sell.</em>
        </h1>

        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 17,
          color: 'rgba(245, 240, 235, 0.55)',
          lineHeight: 1.75,
          maxWidth: 480,
          margin: '0 auto 56px',
          fontStyle: 'italic',
        }}>
          One copy. One agent per territory. The rest of the market
          is reading newspapers.
        </p>

        <div style={{
          display: 'flex',
          gap: 16,
          justifyContent: 'center',
          flexWrap: 'wrap',
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
      </div>
    </section>
  );
}


// ─────────────────────────────────────────────────────────────────
// NotebookSpread — two entries that look like pages from a kept book
// ─────────────────────────────────────────────────────────────────
function NotebookSpread() {
  return (
    <section style={{
      background: 'var(--bg)',
      padding: '120px 32px',
    }}>
      <div style={{ maxWidth: 980, margin: '0 auto' }}>
        <Eyebrow>From the rolodex</Eyebrow>

        <h2 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(32px, 3.6vw, 44px)',
          lineHeight: 1.18,
          letterSpacing: '-0.01em',
          color: 'var(--text)',
          fontWeight: 500,
          marginBottom: 16,
          maxWidth: 720,
        }}>
          What an entry looks like &mdash; written for the agent, in the agent&rsquo;s voice.
        </h2>

        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 16,
          color: 'var(--text-secondary)',
          lineHeight: 1.75,
          maxWidth: 640,
          marginBottom: 64,
          fontStyle: 'italic',
        }}>
          Each entry surfaces a household at a moment that matters &mdash; long
          tenure, a transition, an estate decision &mdash; and the first letter
          to send, drafted in the agent&rsquo;s own cadence. Names below are
          illustrative.
        </p>

        <NotebookEntry
          archetype="Long-tenure homeowner"
          name="M. Hartwell"
          address="Northeast 1st Street, Bellevue"
          tenure="14 years on the property"
          context="Quiet long-tenure pattern. Tax appeal filed last quarter. He won't list publicly."
          letter={`Dear M. Hartwell,\n\nI'm not writing to ask whether you're thinking about selling. That's your decision, on your timeline. What I do want you to know is that for a property like yours — held this long, in this neighborhood — how it gets brought to market matters enormously.\n\nMost properties at this level don't trade on the open market. They move through a small private network of qualified buyers who prefer to transact discreetly. For a home like yours, that network is often where the right buyer is found.\n\nNo pressure. No follow-up calls. Just an open door, whenever the timing is right.`}
        />

        <NotebookEntry
          archetype="Estate transition"
          name="C. Aldridge (trustee)"
          address="Bellevue Way, Bellevue"
          tenure="Family trust holding"
          context="Trustee managing a property decision on behalf of beneficiaries. Institutional timeline."
          letter={`Dear Trustees,\n\nI work with families administering significant property decisions and understand that as trustees you are operating within a fiduciary framework, on your timeline, in coordination with counsel.\n\nWhen and if disposition becomes part of the conversation, the way a property like this is brought to market will matter — the buyer pool that can transact within trust requirements is narrow, and finding them through traditional listing rarely returns full value.\n\nNo pressure, and nothing required. Simply an open line, when the time is right.`}
        />
      </div>
    </section>
  );
}


function NotebookEntry({ archetype, name, address, tenure, context, letter }) {
  return (
    <article style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)',
      padding: '48px 56px',
      marginBottom: 32,
      boxShadow: 'var(--shadow-md)',
      // Subtle aged-paper feel: a hairline gold rule on the left edge
      // like the binding of a notebook
      borderLeft: '3px solid var(--accent)',
    }}>
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
          letterSpacing: '0.16em',
          textTransform: 'uppercase',
          color: 'var(--accent)',
          fontWeight: 700,
          fontFamily: 'var(--font-sans)',
        }}>
          {archetype}
        </div>
        <div style={{
          fontSize: 11,
          color: 'var(--text-tertiary)',
          fontFamily: 'var(--font-sans)',
          fontStyle: 'italic',
        }}>
          Entry &mdash; sample
        </div>
      </div>

      <h3 style={{
        fontFamily: 'var(--font-display)',
        fontSize: 28,
        fontWeight: 500,
        color: 'var(--text)',
        margin: 0,
        letterSpacing: '-0.005em',
        marginBottom: 6,
      }}>
        {name}
      </h3>
      <div style={{
        fontFamily: 'var(--font-serif)',
        fontSize: 14,
        color: 'var(--text-secondary)',
        marginBottom: 4,
      }}>
        {address}
      </div>
      <div style={{
        fontFamily: 'var(--font-serif)',
        fontSize: 14,
        color: 'var(--text-tertiary)',
        marginBottom: 'var(--space-lg)',
        fontStyle: 'italic',
      }}>
        {tenure}
      </div>

      <div style={{
        fontFamily: 'var(--font-serif)',
        fontSize: 14,
        color: 'var(--text)',
        lineHeight: 1.7,
        marginBottom: 'var(--space-lg)',
        paddingLeft: 'var(--space-md)',
        borderLeft: '2px solid var(--border)',
      }}>
        {context}
      </div>

      <div style={{
        fontSize: 10,
        letterSpacing: '0.16em',
        textTransform: 'uppercase',
        color: 'var(--text-tertiary)',
        fontWeight: 700,
        fontFamily: 'var(--font-sans)',
        marginBottom: 'var(--space-sm)',
      }}>
        First letter &middot; in your voice
      </div>
      <div style={{
        fontFamily: 'var(--font-serif)',
        fontSize: 15,
        color: 'var(--text)',
        lineHeight: 1.75,
        whiteSpace: 'pre-wrap',
        background: 'var(--bg-input)',
        padding: 'var(--space-lg)',
        borderRadius: 'var(--radius-md)',
      }}>
        {letter}
      </div>
    </article>
  );
}


// ─────────────────────────────────────────────────────────────────
// VoiceSection — the philosophy, briefly. Single section, restrained.
// ─────────────────────────────────────────────────────────────────
function VoiceSection() {
  return (
    <section style={{
      background: 'var(--bg)',
      padding: '120px 32px',
      borderTop: '1px solid var(--border)',
    }}>
      <div style={{ maxWidth: 720, margin: '0 auto' }}>
        <Eyebrow>The voice</Eyebrow>

        <h2 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(30px, 3.4vw, 42px)',
          lineHeight: 1.2,
          letterSpacing: '-0.01em',
          color: 'var(--text)',
          fontWeight: 500,
          marginBottom: 'var(--space-lg)',
        }}>
          The first agent to reach a household shouldn&rsquo;t sound like the other twelve.
        </h2>

        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 17,
          color: 'var(--text-secondary)',
          lineHeight: 1.85,
          marginBottom: 'var(--space-md)',
        }}>
          Most outreach in this industry sounds like outreach. The same
          phrases &mdash; &ldquo;I hope this letter finds you well,&rdquo; &ldquo;I&rsquo;d welcome
          the opportunity&rdquo; &mdash; arriving in the same week, from agents the
          recipient has no way of distinguishing.
        </p>

        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 17,
          color: 'var(--text-secondary)',
          lineHeight: 1.85,
          marginBottom: 'var(--space-md)',
        }}>
          SellerSignal generates outreach in the agent&rsquo;s own voice.
          Their cadence. Their stance on how directly to engage, how
          often to follow up, whether to reference the situation by
          name. The result reads like a letter the agent wrote after
          dinner &mdash; not one a service produced for them.
        </p>

        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 17,
          color: 'var(--text-secondary)',
          lineHeight: 1.85,
        }}>
          The recipient cannot tell the difference. That is the point.
        </p>
      </div>
    </section>
  );
}


// ─────────────────────────────────────────────────────────────────
// TerritoryList — eleven ZIPs. A guest list, not a feature grid.
// ─────────────────────────────────────────────────────────────────
function TerritoryList() {
  // Honest static data. Status here is intentionally vague — we don't
  // surface real claimed/available status on the public homepage, only
  // inside the authenticated app where claims are actually made.
  const territories = [
    { zip: '98004', city: 'Bellevue' },
    { zip: '98005', city: 'Bellevue' },
    { zip: '98006', city: 'Bellevue' },
    { zip: '98007', city: 'Bellevue' },
    { zip: '98033', city: 'Kirkland' },
    { zip: '98039', city: 'Medina' },
    { zip: '98040', city: 'Mercer Island' },
    { zip: '98052', city: 'Redmond' },
    { zip: '98105', city: 'Seattle &mdash; University District' },
    { zip: '98112', city: 'Seattle &mdash; Madison Park' },
    { zip: '98199', city: 'Seattle &mdash; Magnolia' },
  ];

  return (
    <section style={{
      background: 'var(--bg-card)',
      padding: '120px 32px',
      borderTop: '1px solid var(--border)',
    }}>
      <div style={{ maxWidth: 760, margin: '0 auto' }}>
        <Eyebrow>The territory</Eyebrow>

        <h2 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(30px, 3.4vw, 42px)',
          lineHeight: 1.2,
          letterSpacing: '-0.01em',
          color: 'var(--text)',
          fontWeight: 500,
          marginBottom: 'var(--space-md)',
        }}>
          Eleven ZIPs in King County. One agent each.
        </h2>

        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 16,
          color: 'var(--text-secondary)',
          lineHeight: 1.75,
          marginBottom: 'var(--space-2xl)',
          fontStyle: 'italic',
        }}>
          Each ZIP is held exclusively by the agent who claims it. There is
          one rolodex per territory, and one agent reading it.
        </p>

        <ul style={{
          listStyle: 'none',
          padding: 0,
          margin: 0,
          borderTop: '1px solid var(--border)',
        }}>
          {territories.map((t) => (
            <li
              key={t.zip}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'baseline',
                padding: '20px 0',
                borderBottom: '1px solid var(--border)',
                gap: 16,
              }}
            >
              <div style={{
                fontFamily: 'var(--font-display)',
                fontSize: 22,
                fontWeight: 500,
                color: 'var(--text)',
                letterSpacing: '-0.005em',
              }}>
                <span dangerouslySetInnerHTML={{ __html: t.city }} />
              </div>
              <div style={{
                display: 'flex',
                gap: 16,
                alignItems: 'baseline',
                fontFamily: 'var(--font-sans)',
                fontSize: 14,
              }}>
                <span style={{ color: 'var(--text-tertiary)' }}>
                  {t.zip}
                </span>
              </div>
            </li>
          ))}
        </ul>

        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 14,
          color: 'var(--text-tertiary)',
          fontStyle: 'italic',
          marginTop: 'var(--space-xl)',
          textAlign: 'center',
        }}>
          Currently invite-only. Availability shown to claimed agents inside.
        </p>
      </div>
    </section>
  );
}


// ─────────────────────────────────────────────────────────────────
// Closing — back to dark, mirroring the cover. Single restrained CTA.
// ─────────────────────────────────────────────────────────────────
function Closing() {
  return (
    <section style={{
      background: 'var(--bg-dark)',
      color: 'var(--text-inverse)',
      padding: '120px 32px',
      textAlign: 'center',
    }}>
      <div style={{ maxWidth: 640, margin: '0 auto' }}>
        <h2 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(30px, 3.4vw, 42px)',
          lineHeight: 1.2,
          letterSpacing: '-0.01em',
          color: 'var(--text-inverse)',
          fontWeight: 500,
          marginBottom: 'var(--space-md)',
        }}>
          Held by one. Worth what they make of it.
        </h2>
        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 16,
          color: 'rgba(245, 240, 235, 0.55)',
          lineHeight: 1.75,
          marginBottom: 'var(--space-xl)',
          fontStyle: 'italic',
        }}>
          Currently in private beta. Available to a small number of agents
          in King County, Washington.
        </p>

        <div style={{
          display: 'flex',
          gap: 16,
          justifyContent: 'center',
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


// ─── shared eyebrow label ────────────────────────────────────────
function Eyebrow({ children }) {
  return (
    <div style={{
      fontSize: 10,
      fontWeight: 700,
      color: 'var(--accent)',
      letterSpacing: '0.18em',
      textTransform: 'uppercase',
      marginBottom: 'var(--space-md)',
      fontFamily: 'var(--font-sans)',
    }}>
      {children}
    </div>
  );
}


// ─── CTAs ─────────────────────────────────────────────────────────
const ctaBase = {
  padding: '15px 36px',
  borderRadius: 6,
  fontSize: 14,
  fontWeight: 600,
  fontFamily: 'var(--font-sans)',
  textDecoration: 'none',
  display: 'inline-block',
  letterSpacing: '0.04em',
  transition: 'all 0.2s ease',
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
  border: '1px solid rgba(245, 240, 235, 0.32)',
  color: 'rgba(245, 240, 235, 0.85)',
};
