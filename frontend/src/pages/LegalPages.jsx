import SiteLayout from '../components/shell/SiteLayout.jsx';

// PrivacyPage / TermsPage — minimal scaffolds. Real legal copy lives
// in a future commit (likely lifted/adapted from the legacy site's
// /privacy.html and /terms.html, then reviewed). For now both render
// as placeholders so the footer links don't 404.

export function PrivacyPage() {
  return (
    <SiteLayout mode="public" contentMaxWidth={680}>
      <h1 style={titleStyle}>Privacy Policy</h1>
      <p style={bodyStyle}>
        Privacy policy content coming soon.
      </p>
    </SiteLayout>
  );
}

export function TermsPage() {
  return (
    <SiteLayout mode="public" contentMaxWidth={680}>
      <h1 style={titleStyle}>Terms of Service</h1>
      <p style={bodyStyle}>
        Terms of service content coming soon.
      </p>
    </SiteLayout>
  );
}

const titleStyle = {
  fontFamily: 'var(--font-display)',
  fontSize: 36,
  fontWeight: 600,
  color: 'var(--text)',
  marginBottom: 'var(--space-md)',
  letterSpacing: '-0.01em',
};

const bodyStyle = {
  fontFamily: 'var(--font-serif)',
  color: 'var(--text-secondary)',
  fontSize: 15,
  lineHeight: 1.7,
};
