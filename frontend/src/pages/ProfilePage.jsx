import { useEffect, useState } from 'react';
import SiteLayout from '../components/shell/SiteLayout.jsx';
import { useAuth } from '../lib/AuthContext.jsx';
import { getAccessToken } from '../lib/supabase.js';

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
