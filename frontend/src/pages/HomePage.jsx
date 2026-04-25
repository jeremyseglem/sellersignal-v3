import { Link } from 'react-router-dom';
import SiteLayout from '../components/shell/SiteLayout.jsx';
import Logo from '../components/shell/Logo.jsx';

// HomePage — the marketing landing at `/`. Full-bleed hero on the
// dark gradient backdrop, then a few content sections, then the
// footer. Public mode (signed-out nav).
//
// This is the Session 1 scaffold: hero + CTAs + skeletal sections.
// Session 3 will fill in real value-prop copy, sample dossier
// imagery, the "47 indicators" cards, and any case studies. For now
// the structure exists so the routing works and the visual language
// is locked in.
export default function HomePage() {
  return (
    <SiteLayout mode="public" showFooter>
      <Hero />
      <Section
        label="What it is"
        title="A weekly briefing of who's about to sell."
        body="SellerSignal monitors public records — court filings, tax notices, ownership transitions — and flags the property owners most likely to sell within 90 days. You get a curated weekly list, not a database."
      />
      <Section
        label="How it works"
        title="One territory. One agent. Real signals."
        body="Each ZIP code is exclusive to one agent. We surface forced transitions (probate, divorce, foreclosure), structural intelligence (long-tenure owners, investor disposition windows), and behavioral patterns — never speculation, never scraped MLS data."
      />
      <Section
        label="The output"
        title="Who to call. Why now. What to say."
        body="Every lead in your weekly briefing answers the questions that matter. Personal representative names from probate dockets. Investor entities approaching disposition cycles. A starter script for the first conversation. Then it gets out of your way."
      />
    </SiteLayout>
  );
}


// ── Hero ─────────────────────────────────────────────────────────
// Full-bleed dark gradient. Centered logo + headline + CTAs. Pulled
// from the legacy reference but rebuilt cleanly with design tokens.
function Hero() {
  return (
    <section style={{
      position: 'relative',
      minHeight: 'calc(100vh - 56px)',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      alignItems: 'center',
      padding: '120px 32px 100px',
      overflow: 'hidden',
      background: 'linear-gradient(165deg, #3B4F42 0%, #4A6355 25%, #5C7668 50%, #4A5E50 75%, #3A4A3E 100%)',
      color: 'var(--text-inverse)',
    }}>
      {/* Soft glow above the headline */}
      <div style={{
        position: 'absolute',
        top: '15%',
        left: '50%',
        width: 600,
        height: 400,
        transform: 'translateX(-50%)',
        background: 'radial-gradient(ellipse, rgba(200,220,195,0.12) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      {/* Faint horizon line below the headline */}
      <div style={{
        position: 'absolute',
        left: 0,
        right: 0,
        top: '52%',
        height: 1,
        background: 'linear-gradient(90deg, transparent 5%, rgba(245,240,235,0.08) 25%, rgba(245,240,235,0.14) 50%, rgba(245,240,235,0.08) 75%, transparent 95%)',
        pointerEvents: 'none',
      }} />

      <div style={{
        position: 'relative',
        zIndex: 1,
        maxWidth: 800,
        textAlign: 'center',
      }}>
        <div style={{ marginBottom: 32 }}>
          <Logo tone="light" size="hero" />
        </div>

        <h1 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(40px, 5.5vw, 66px)',
          lineHeight: 1.08,
          color: 'var(--text-inverse)',
          marginBottom: 24,
          letterSpacing: '-0.02em',
          textShadow: '0 2px 30px rgba(0, 0, 0, 0.15)',
          fontWeight: 600,
        }}>
          Know who&rsquo;s going to sell <em style={{
            fontStyle: 'italic',
            color: 'rgba(245, 240, 235, 0.72)',
          }}>before they list.</em>
        </h1>

        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 17,
          color: 'rgba(245, 240, 235, 0.62)',
          lineHeight: 1.75,
          maxWidth: 540,
          margin: '0 auto 40px',
        }}>
          A weekly briefing of property owners most likely to sell within
          90 days, backed by court records, ownership history, and structural
          signals — exclusive to one agent per ZIP.
        </p>

        <div style={{
          display: 'flex',
          gap: 14,
          justifyContent: 'center',
          flexWrap: 'wrap',
        }}>
          <Link to="/signup" style={ctaPrimary}>Request access</Link>
          <Link to="/login"  style={ctaGhost}>Sign in</Link>
        </div>

        <div style={{
          marginTop: 28,
          fontSize: 12,
          color: 'rgba(245, 240, 235, 0.4)',
          letterSpacing: '0.04em',
        }}>
          Currently invite-only · Live in <strong style={{ color: 'rgba(245,240,235,0.6)' }}>King County, WA</strong>
        </div>
      </div>
    </section>
  );
}


// ── Content section ──────────────────────────────────────────────
function Section({ label, title, body }) {
  return (
    <section style={{
      padding: '100px 32px',
      maxWidth: 880,
      margin: '0 auto',
    }}>
      <div style={{
        fontSize: 10,
        fontWeight: 700,
        color: 'var(--accent)',
        letterSpacing: '0.14em',
        textTransform: 'uppercase',
        marginBottom: 14,
        fontFamily: 'var(--font-sans)',
      }}>
        {label}
      </div>
      <h2 style={{
        fontFamily: 'var(--font-display)',
        fontSize: 'clamp(28px, 3.2vw, 40px)',
        lineHeight: 1.2,
        marginBottom: 16,
        letterSpacing: '-0.01em',
        color: 'var(--text)',
        fontWeight: 600,
      }}>
        {title}
      </h2>
      <p style={{
        fontFamily: 'var(--font-serif)',
        color: 'var(--text-secondary)',
        fontSize: 16,
        lineHeight: 1.8,
        maxWidth: 620,
      }}>
        {body}
      </p>
    </section>
  );
}


// ── CTA button styles ────────────────────────────────────────────
const ctaBase = {
  padding: '16px 40px',
  borderRadius: 8,
  fontSize: 15,
  fontWeight: 600,
  fontFamily: 'var(--font-sans)',
  textDecoration: 'none',
  transition: 'all 0.2s ease',
  display: 'inline-block',
};
const ctaPrimary = {
  ...ctaBase,
  background: 'var(--text-inverse)',
  color: 'var(--text)',
  border: 'none',
};
const ctaGhost = {
  ...ctaBase,
  background: 'transparent',
  border: '1px solid rgba(245, 240, 235, 0.28)',
  color: 'rgba(245, 240, 235, 0.78)',
};
