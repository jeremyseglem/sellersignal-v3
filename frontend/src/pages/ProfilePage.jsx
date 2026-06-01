import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import SiteLayout from '../components/shell/SiteLayout.jsx';
import { useAuth } from '../lib/AuthContext.jsx';
import { getAccessToken } from '../lib/supabase.js';
import { billing, safeErrorMessage } from '../api/client.js';

// ProfilePage — agent-editable profile form. Fields drive both the
// authenticated header (full_name) and Session 4 letter automation
// (full_name + brokerage + phone + license_number + signature_url +
// headshot_url + logo_url all flow into the rendered letterhead).
//
// Image uploads (headshot, signature, logo) are not wired in this
// session — those need Supabase Storage buckets + signed-upload
// flow. Session 3 wires Storage and the upload widget; for now the
// fields are URL-only inputs so the data model is honest.
export default function ProfilePage() {
  const { profile, refreshProfile, signOut } = useAuth();

  // Form state mirrors the profile fields. Initialized from the
  // profile context once it loads. Local edits stay in form state
  // until the user clicks Save, which PUTs to /api/profile and then
  // refreshes the context.
  const [form, setForm] = useState({
    full_name:      '',
    phone:          '',
    brokerage:      '',
    license_number: '',
    license_state:  '',
    headshot_url:   '',
    signature_url:  '',
    logo_url:       '',
  });
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(null);
  const [error, setError]     = useState(null);

  // Sync form with profile context whenever it changes
  // (initial load, after a manual refresh, etc).
  useEffect(() => {
    if (profile) {
      setForm({
        full_name:      profile.full_name      || '',
        phone:          profile.phone          || '',
        brokerage:      profile.brokerage      || '',
        license_number: profile.license_number || '',
        license_state:  profile.license_state  || '',
        headshot_url:   profile.headshot_url   || '',
        signature_url:  profile.signature_url  || '',
        logo_url:       profile.logo_url       || '',
      });
    }
  }, [profile]);

  const change = (field) => (e) => {
    setForm((f) => ({ ...f, [field]: e.target.value }));
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      const token = await getAccessToken();
      if (!token) throw new Error('Not signed in');

      const res = await fetch('/api/profile', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(form),
      });
      if (!res.ok) {
        const t = await res.text().catch(() => '');
        throw new Error(t || `Save failed (${res.status})`);
      }
      await refreshProfile();
      setSavedAt(new Date());
    } catch (err) {
      setError(err.message || 'Could not save profile.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <SiteLayout
      agent={profile}
      onSignOut={signOut}
      mode="authenticated"
      contentMaxWidth={680}
    >
      <header style={{ marginBottom: 'var(--space-xl)' }}>
        <div style={{
          fontSize: 11,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: 'var(--text-tertiary)',
          fontWeight: 600,
          marginBottom: 6,
          fontFamily: 'var(--font-sans)',
        }}>
          Account
        </div>
        <h1 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 36,
          fontWeight: 600,
          letterSpacing: '-0.01em',
          color: 'var(--text)',
        }}>
          Your profile
        </h1>
        <p style={{
          fontFamily: 'var(--font-serif)',
          color: 'var(--text-secondary)',
          fontSize: 15,
          fontStyle: 'italic',
          marginTop: 'var(--space-xs)',
        }}>
          Used in your dossier header and any letters SellerSignal
          sends on your behalf.
        </p>
      </header>

      {error && (
        <div style={{
          marginBottom: 'var(--space-md)',
          padding: '12px 14px',
          background: 'var(--call-now-bg)',
          color: 'var(--call-now)',
          borderRadius: 'var(--radius-sm)',
          fontSize: 13,
          fontFamily: 'var(--font-sans)',
        }}>
          {error}
        </div>
      )}

      <form onSubmit={handleSave}>
        <Section title="Identity">
          <Field label="Full name"      value={form.full_name}      onChange={change('full_name')}      placeholder="Jeremy Seglem" />
          <Field label="Phone"          value={form.phone}          onChange={change('phone')}          placeholder="(406) 555-1234" />
          <Field label="Brokerage"      value={form.brokerage}      onChange={change('brokerage')}      placeholder="The Agency · Bozeman" />
          <Row>
            <Field label="License number" value={form.license_number} onChange={change('license_number')} placeholder="123456789" />
            <Field label="License state"  value={form.license_state}  onChange={change('license_state')}  placeholder="WA" maxLength={4} />
          </Row>
        </Section>

        <Section title="Letter assets" subtitle="Used on automated outreach. Image upload UI lands next; for now paste public URLs.">
          <Field label="Headshot URL"     value={form.headshot_url}  onChange={change('headshot_url')}  placeholder="https://…" />
          <Field label="Signature URL"    value={form.signature_url} onChange={change('signature_url')} placeholder="https://…" />
          <Field label="Logo URL"         value={form.logo_url}      onChange={change('logo_url')}      placeholder="https://…" />
        </Section>

        <VoiceSection profile={profile} />

        <BillingSection profile={profile} />

        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-md)',
          marginTop: 'var(--space-xl)',
        }}>
          <button
            type="submit"
            disabled={saving}
            style={{
              padding: '12px 24px',
              fontSize: 14,
              fontWeight: 600,
              fontFamily: 'var(--font-sans)',
              color: 'var(--text-inverse)',
              background: saving ? 'var(--text-tertiary)' : 'var(--accent)',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              cursor: saving ? 'not-allowed' : 'pointer',
            }}
          >
            {saving ? 'Saving…' : 'Save profile'}
          </button>
          {savedAt && (
            <span style={{
              fontSize: 12,
              color: 'var(--text-tertiary)',
              fontStyle: 'italic',
              fontFamily: 'var(--font-serif)',
            }}>
              Saved {savedAt.toLocaleTimeString()}
            </span>
          )}
        </div>
      </form>
    </SiteLayout>
  );
}


// ── Field group helpers ─────────────────────────────────────────
function Section({ title, subtitle, children }) {
  return (
    <section style={{
      marginBottom: 'var(--space-xl)',
      padding: 'var(--space-lg)',
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)',
    }}>
      <h2 style={{
        fontFamily: 'var(--font-display)',
        fontSize: 18,
        fontWeight: 600,
        color: 'var(--text)',
        marginBottom: subtitle ? 4 : 'var(--space-md)',
      }}>
        {title}
      </h2>
      {subtitle && (
        <div style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 12,
          color: 'var(--text-tertiary)',
          fontStyle: 'italic',
          marginBottom: 'var(--space-md)',
        }}>
          {subtitle}
        </div>
      )}
      {children}
    </section>
  );
}

function Row({ children }) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '2fr 1fr',
      gap: 'var(--space-md)',
    }}>
      {children}
    </div>
  );
}

function Field({ label, value, onChange, placeholder, maxLength }) {
  return (
    <div style={{ marginBottom: 'var(--space-md)' }}>
      <label style={{
        display: 'block',
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        color: 'var(--text-tertiary)',
        marginBottom: 6,
        fontFamily: 'var(--font-sans)',
      }}>
        {label}
      </label>
      <input
        type="text"
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        maxLength={maxLength}
        style={{
          width: '100%',
          padding: '10px 12px',
          fontSize: 14,
          fontFamily: 'var(--font-serif)',
          color: 'var(--text)',
          background: 'var(--bg-input)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          boxSizing: 'border-box',
          outline: 'none',
        }}
      />
    </div>
  );
}


// VoiceSection — state-aware section linking to /profile/voice. When
// the agent hasn't completed voice onboarding, leads with a stronger
// CTA ("Set up your voice profile"). When complete, shows
// "Voice profile complete" with a quieter Edit link. Discovers itself
// from profile.voice_onboarding_completed_at.
function VoiceSection({ profile }) {
  const completed = Boolean(profile?.voice_onboarding_completed_at);

  return (
    <section style={{
      marginBottom: 'var(--space-xl)',
      padding: 'var(--space-lg)',
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)',
    }}>
      <h2 style={{
        fontFamily: 'var(--font-display)',
        fontSize: 18,
        fontWeight: 600,
        color: 'var(--text)',
        margin: 0,
        marginBottom: 'var(--space-xs)',
      }}>
        Your voice
      </h2>
      <p style={{
        fontFamily: 'var(--font-serif)',
        fontSize: 14,
        color: 'var(--text-secondary)',
        lineHeight: 1.55,
        marginTop: 0,
        marginBottom: 'var(--space-md)',
      }}>
        {completed
          ? 'Your phone, letter, and door scripts are generated and rendering on every lead. Refine your voice profile or regenerate scripts anytime.'
          : 'Generate phone, letter, and door scripts in your own voice. We ask how you sound, how you approach sellers, and what makes you you. Takes about ten minutes.'}
      </p>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-md)',
        flexWrap: 'wrap',
      }}>
        <Link
          to="/profile/voice"
          style={{
            display: 'inline-block',
            padding: '10px 18px',
            fontSize: 13,
            fontWeight: 600,
            fontFamily: 'var(--font-sans)',
            color: completed ? 'var(--text)' : 'var(--text-inverse, #fff)',
            background: completed ? 'transparent' : 'var(--accent)',
            border: completed ? '1px solid var(--border)' : 'none',
            borderRadius: 'var(--radius-md)',
            textDecoration: 'none',
            letterSpacing: '0.02em',
          }}
        >
          {completed ? 'Edit voice profile →' : 'Set up your voice profile →'}
        </Link>
        {completed && profile?.voice_onboarding_completed_at && (
          <span style={{
            fontSize: 12,
            color: 'var(--text-tertiary)',
            fontStyle: 'italic',
            fontFamily: 'var(--font-serif)',
          }}>
            Last generated {new Date(profile.voice_onboarding_completed_at).toLocaleDateString()}
          </span>
        )}
      </div>
    </section>
  );
}


// ── Billing section ─────────────────────────────────────────────
// Surfaces subscription state + actions for paid agents. Only renders
// when the agent has a Stripe customer on file — beta agents (no
// stripe_customer_id) and operators see no Subscription section.
//
// Shows:
//   • Next billing date (from Stripe current_period_end)
//   • Commitment end date (cancel_at)
//   • "Renew for another 3 months" button — visible only when within
//     30 days of commitment end, per backend's eligibility check
//   • "Manage subscription →" link to Stripe Customer Portal
//
// Renewal opens at T-30 and stays open until T-0. Outside that window
// the Renew button is hidden (not just disabled — surfacing a button
// the agent can't use today is just noise). The next-billing line is
// always visible so the agent knows the subscription is healthy.
function BillingSection({ profile }) {
  const [opening, setOpening] = useState(false);
  const [renewing, setRenewing] = useState(false);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState(null);  // backend subscription-status payload
  const [statusLoading, setStatusLoading] = useState(true);

  // Fetch subscription status on mount. Beta agents (no stripe_customer_id)
  // never reach this fetch — the early return below short-circuits before
  // the effect runs. For paid agents the status drives the renew button.
  useEffect(() => {
    if (!profile?.stripe_customer_id) return;
    let cancelled = false;
    (async () => {
      try {
        const s = await billing.subscriptionStatus();
        if (!cancelled) setStatus(s);
      } catch (e) {
        if (!cancelled) {
          // Non-fatal — we can still show the Manage Subscription button
          // even without status. The Renew button just stays hidden.
          console.warn('subscription status fetch failed:', e);
        }
      } finally {
        if (!cancelled) setStatusLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [profile?.stripe_customer_id]);

  // Operators and beta agents — no portal access. Render nothing
  // rather than a disabled section.
  if (!profile?.stripe_customer_id) {
    return null;
  }

  async function openPortal() {
    setOpening(true);
    setError(null);
    try {
      const { portal_url } = await billing.portalLink('/profile');
      if (!portal_url) throw new Error('No portal URL returned');
      window.location.href = portal_url;
    } catch (e) {
      setError(safeErrorMessage(e, 'Could not open billing portal'));
      setOpening(false);
    }
  }

  async function handleRenew() {
    setRenewing(true);
    setError(null);
    try {
      const result = await billing.renew();
      if (!result?.renewed) throw new Error('Renewal did not complete');
      // Refresh the status to reflect the new cancel_at.
      const fresh = await billing.subscriptionStatus();
      setStatus(fresh);
    } catch (e) {
      setError(safeErrorMessage(e, 'Could not renew subscription'));
    } finally {
      setRenewing(false);
    }
  }

  // Format unix timestamps as friendly dates.
  function formatTs(unix) {
    if (!unix) return null;
    return new Date(unix * 1000).toLocaleDateString(undefined, {
      year: 'numeric', month: 'long', day: 'numeric',
    });
  }

  const nextBillingDate = formatTs(status?.current_period_end);
  const commitmentEndDate = formatTs(status?.cancel_at);
  const showRenew = status?.eligible_for_renewal === true;
  const daysLeft = status?.days_until_cancel;

  return (
    <section style={{
      marginBottom: 'var(--space-xl)',
      paddingBottom: 'var(--space-xl)',
      borderBottom: '1px solid var(--border)',
    }}>
      <h2 style={{
        fontFamily: 'var(--font-display)',
        fontSize: 20,
        fontWeight: 600,
        color: 'var(--text)',
        marginBottom: 'var(--space-sm)',
      }}>
        Subscription
      </h2>

      {/* Status summary — always shown when we have data */}
      {!statusLoading && status?.has_subscription && (
        <div style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 14,
          color: 'var(--text-secondary)',
          marginBottom: 'var(--space-md)',
          lineHeight: 1.7,
        }}>
          <div>
            <span style={{ color: 'var(--text-tertiary)' }}>Territory:</span>{' '}
            <span style={{ color: 'var(--text)' }}>{status.zip_code}</span>
          </div>
          {nextBillingDate && (
            <div>
              <span style={{ color: 'var(--text-tertiary)' }}>Next billing:</span>{' '}
              <span style={{ color: 'var(--text)' }}>{nextBillingDate}</span>
            </div>
          )}
          {commitmentEndDate && (
            <div>
              <span style={{ color: 'var(--text-tertiary)' }}>Commitment ends:</span>{' '}
              <span style={{ color: 'var(--text)' }}>{commitmentEndDate}</span>
              {typeof daysLeft === 'number' && daysLeft >= 0 && (
                <span style={{
                  color: showRenew ? 'var(--accent)' : 'var(--text-tertiary)',
                  fontStyle: 'italic',
                  marginLeft: 8,
                  fontSize: 13,
                }}>
                  ({daysLeft} {daysLeft === 1 ? 'day' : 'days'} left)
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {error && (
        <div style={{
          marginBottom: 'var(--space-md)',
          padding: '12px 14px',
          background: 'var(--call-now-bg)',
          color: 'var(--call-now)',
          borderRadius: 'var(--radius-sm)',
          fontSize: 13,
          fontFamily: 'var(--font-sans)',
        }}>
          {error}
        </div>
      )}

      {/* Renewal CTA — visible only inside the 30-day window */}
      {showRenew && (
        <div style={{
          padding: 'var(--space-md)',
          background: 'var(--accent-tint, rgba(140, 109, 58, 0.08))',
          borderRadius: 'var(--radius-md)',
          marginBottom: 'var(--space-md)',
        }}>
          <p style={{
            fontFamily: 'var(--font-serif)',
            fontSize: 14,
            color: 'var(--text)',
            margin: '0 0 var(--space-sm) 0',
            lineHeight: 1.5,
          }}>
            Your commitment ends in {daysLeft} {daysLeft === 1 ? 'day' : 'days'}.
            Renew now to extend your exclusive access to {status.zip_code} by
            another 3 months. You&rsquo;ll continue to be billed monthly &mdash;
            no upfront charge for the extension.
          </p>
          <button
            type="button"
            onClick={handleRenew}
            disabled={renewing}
            style={{
              padding: '10px 20px',
              fontSize: 13,
              fontWeight: 600,
              fontFamily: 'var(--font-sans)',
              color: 'var(--text-inverse)',
              background: renewing ? 'var(--text-tertiary)' : 'var(--accent)',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              cursor: renewing ? 'not-allowed' : 'pointer',
            }}
          >
            {renewing ? 'Renewing…' : `Renew ${status.zip_code} for 3 more months`}
          </button>
        </div>
      )}

      <p style={{
        fontFamily: 'var(--font-serif)',
        fontSize: 13,
        color: 'var(--text-tertiary)',
        marginBottom: 'var(--space-md)',
        fontStyle: 'italic',
      }}>
        Manage your payment method, view invoices, or cancel your
        territory subscription. Cancellation releases your ZIP
        immediately.
      </p>

      <button
        type="button"
        onClick={openPortal}
        disabled={opening}
        style={{
          padding: '10px 20px',
          fontSize: 13,
          fontWeight: 600,
          fontFamily: 'var(--font-sans)',
          color: 'var(--text)',
          background: 'transparent',
          border: '1px solid var(--border-strong, var(--border))',
          borderRadius: 'var(--radius-md)',
          cursor: opening ? 'not-allowed' : 'pointer',
          opacity: opening ? 0.6 : 1,
        }}
      >
        {opening ? 'Opening…' : 'Manage subscription →'}
      </button>
    </section>
  );
}
