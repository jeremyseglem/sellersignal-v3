/*
 * NetworkJoinPage — buyer-agent registration for the Buyer Network.
 * Direct URL only (/network/join). Requires sign-in (existing Supabase
 * auth); creates the buyer_agent seat in PENDING state. The network
 * itself stays dark — approval is per-seat by an operator, and the
 * pending roll is the verified buyer-agent audience.
 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { network, safeErrorMessage } from '../api/client.js';

const F = { display: 'var(--font-display)', serif: 'var(--font-serif)', sans: 'var(--font-sans)' };

const STATES = ['WA','MT','AZ','TX','FL','CT','MA','TN','CO','CA','NY','NJ','IL','OR','ID','NV','UT','GA','NC','SC','VA','MD','PA','OH','MI','MN','other'];

function Label({ children }) {
  return <div style={{ fontFamily: F.sans, fontSize: 11, letterSpacing: '0.12em',
    textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 6 }}>{children}</div>;
}
function Input(props) {
  return <input {...props} style={{ width: '100%', boxSizing: 'border-box',
    background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 6,
    padding: '10px 12px', fontFamily: F.sans, fontSize: 14, color: 'var(--text)',
    outline: 'none', ...(props.style || {}) }} />;
}

export default function NetworkJoinPage() {
  const [phase, setPhase] = useState('checking'); // checking | form | pending | active
  const [f, setF] = useState({ full_name: '', brokerage: '', phone: '',
    license_number: '', license_state: 'WA' });
  const [attest, setAttest] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let dead = false;
    network.joinStatus()
      .then(r => { if (!dead) setPhase(r.status === 'active' ? 'active'
        : r.status === 'pending' ? 'pending' : 'form'); })
      .catch(() => { if (!dead) setPhase('form'); });
    return () => { dead = true; };
  }, []);

  async function submit() {
    setSaving(true); setError('');
    try {
      const r = await network.join({ ...f, licensure_attested: attest });
      setPhase(r.status === 'active' ? 'active' : 'pending');
    } catch (e) { setError(safeErrorMessage(e)); }
    finally { setSaving(false); }
  }

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const ready = f.full_name && f.brokerage && f.license_number && f.license_state && attest;

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', paddingBottom: 80 }}>
      <div style={{ background: 'var(--bg-dark)', padding: '26px 0 22px' }}>
        <div style={{ maxWidth: 640, margin: '0 auto', padding: '0 28px' }}>
          <div style={{ fontFamily: F.sans, fontSize: 10, letterSpacing: '0.22em',
            textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 6 }}>
            SellerSignal · Buyer Network
          </div>
          <div style={{ fontFamily: F.display, fontSize: 28, color: 'var(--text-inverse)' }}>
            Represent a buyer. Search everything.
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 640, margin: '0 auto', padding: '30px 28px 0' }}>
        {phase === 'checking' && null}

        {phase === 'active' && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 10, padding: '40px 32px', textAlign: 'center' }}>
            <div style={{ fontFamily: F.display, fontSize: 22, color: 'var(--text)', marginBottom: 10 }}>
              Your seat is active
            </div>
            <Link to="/network" style={{ fontFamily: F.sans, fontSize: 14,
              color: 'var(--accent)' }}>
              Go to the Buyer Network →
            </Link>
          </div>
        )}

        {phase === 'pending' && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 10, padding: '40px 32px', textAlign: 'center' }}>
            <div style={{ fontFamily: F.display, fontSize: 22, color: 'var(--text)', marginBottom: 10 }}>
              Application received
            </div>
            <div style={{ fontFamily: F.serif, fontSize: 14.5, color: 'var(--text-secondary)',
              lineHeight: 1.6 }}>
              We verify every agent before opening a seat — that's what keeps
              the network worth being in. You'll get an email when yours is
              active.
            </div>
          </div>
        )}

        {phase === 'form' && (
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 10, padding: 26 }}>
            <div style={{ fontFamily: F.serif, fontSize: 14.5, color: 'var(--text-secondary)',
              lineHeight: 1.6, marginBottom: 22 }}>
              A seat lets you post client searches against every home in
              covered territories — listed or not — and hear from the agents
              who hold the matches. Seats are free, licensed-agents only,
              and every application is reviewed.
            </div>
            {error && (
              <div style={{ background: 'var(--call-now-bg)', border: '1px solid var(--call-now)',
                color: 'var(--call-now)', borderRadius: 8, padding: '10px 14px',
                fontFamily: F.sans, fontSize: 13, marginBottom: 16 }}>{error}</div>
            )}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div style={{ gridColumn: '1 / -1' }}>
                <Label>Full name</Label>
                <Input value={f.full_name} onChange={set('full_name')} placeholder="Courtney Miller" />
              </div>
              <div style={{ gridColumn: '1 / -1' }}>
                <Label>Brokerage</Label>
                <Input value={f.brokerage} onChange={set('brokerage')} placeholder="The Agency" />
              </div>
              <div>
                <Label>Phone</Label>
                <Input value={f.phone} onChange={set('phone')} placeholder="(206) 555-0100" />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 90px', gap: 10 }}>
                <div>
                  <Label>License number</Label>
                  <Input value={f.license_number} onChange={set('license_number')} placeholder="123456" />
                </div>
                <div>
                  <Label>State</Label>
                  <select value={f.license_state} onChange={set('license_state')}
                    style={{ width: '100%', background: 'var(--bg-input)',
                      border: '1px solid var(--border)', borderRadius: 6,
                      padding: '10px 8px', fontFamily: F.sans, fontSize: 14,
                      color: 'var(--text)' }}>
                    {STATES.map(st => <option key={st} value={st}>{st}</option>)}
                  </select>
                </div>
              </div>
            </div>
            <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginTop: 22,
              cursor: 'pointer', fontFamily: F.serif, fontSize: 13.5,
              color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              <input type="checkbox" checked={attest} onChange={e => setAttest(e.target.checked)}
                style={{ marginTop: 3, accentColor: 'var(--accent)' }} />
              <span>
                I attest that I hold an <b>active real estate license</b> in the
                state listed, and that the license number above is mine.
              </span>
            </label>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 22 }}>
              <button disabled={!ready || saving} onClick={submit}
                style={{ background: 'var(--accent)', color: '#fff',
                  border: '1px solid var(--accent)', borderRadius: 6,
                  padding: '11px 22px', fontFamily: F.sans, fontSize: 13.5,
                  fontWeight: 600, cursor: ready ? 'pointer' : 'not-allowed',
                  opacity: ready && !saving ? 1 : 0.5 }}>
                {saving ? 'Submitting…' : 'Apply for a seat'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
