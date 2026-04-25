import { Link } from 'react-router-dom';
import Logo from './Logo.jsx';

// SiteFooter — minimal, present on marketing pages and any page where
// the agent might want a privacy / terms / contact link. Authenticated
// app pages (briefing, territories) skip the footer to maximize map
// real estate.
//
// Visual language: ivory background to match the canvas, subtle border
// at the top to separate from page content, muted dim type for the
// links and copyright.
export default function SiteFooter() {
  return (
    <footer style={{
      marginTop: 'var(--space-2xl)',
      padding: '40px 32px 32px',
      borderTop: '1px solid var(--border)',
      background: 'var(--bg)',
      fontFamily: 'var(--font-sans)',
    }}>
      <div style={{
        maxWidth: 1100,
        margin: '0 auto',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        gap: 'var(--space-md)',
      }}>
        <Logo tone="dark" size="small" />

        <div style={{
          display: 'flex',
          gap: 24,
          fontSize: 12,
          color: 'var(--text-tertiary)',
        }}>
          <Link to="/privacy" style={footerLinkStyle}>Privacy</Link>
          <Link to="/terms"   style={footerLinkStyle}>Terms</Link>
          <a href="mailto:contact@sellersignal.co" style={footerLinkStyle}>Contact</a>
        </div>

        <div style={{
          fontSize: 11,
          color: 'var(--text-tertiary)',
          marginTop: 8,
        }}>
          &copy; {new Date().getFullYear()} SellerSignal. Territory intelligence
          for luxury real estate.
        </div>
      </div>
    </footer>
  );
}

const footerLinkStyle = {
  color: 'var(--text-tertiary)',
  textDecoration: 'none',
  transition: 'color 0.15s ease',
};
