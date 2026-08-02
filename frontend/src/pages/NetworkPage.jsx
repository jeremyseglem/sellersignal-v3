/*
 * NetworkPage — the Buyer Network demand tool. DARK LAUNCH.
 *
 * Reachable only by direct URL (/network). No nav links anywhere.
 * Double-gated: AuthGate (signed in) + server allowlist — the status
 * probe 404s for anyone not on MARKETPLACE_ALLOWLIST, and this page
 * silently redirects home, indistinguishable from a dead URL.
 *
 * Three views: registry (needs list) → compose (the client brief) →
 * report (the match result). The form is data-driven: it renders only
 * the filters that are actually populated for the chosen ZIPs, with
 * live parcel counts beside each — a ZIP only offers what its county
 * grades. Signature element: the tier bar — likely sellers (A), then
 * structural archetypes (B), then the rest (C), as one proportional
 * band. "N of these homes are held by likely sellers" is the sentence
 * no MLS can render.
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { network, safeErrorMessage } from '../api/client.js';

const F = {
  display: 'var(--font-display)',
  serif: 'var(--font-serif)',
  sans: 'var(--font-sans)',
};

const VIEW_LABELS = {
  lake_wa: 'Lake Washington', lake_samm: 'Lake Sammamish', rainier: 'Mt. Rainier',
  olympics: 'Olympics', cascades: 'Cascades', skyline: 'City skyline',
  sound: 'Puget Sound', territorial: 'Territorial', lake_river_creek: 'Lake / river / creek',
  mountain: 'Mountain', other: 'Other view',
};
const FEATURE_LABELS = {
  pool: 'Pool', spa: 'Spa', sauna: 'Sauna', deck: 'Deck',
  sprinkler_system: 'Sprinkler system', brick_stone: 'Brick / stone exterior',
  daylight_basement: 'Daylight basement', golf_adjacent: 'Golf fairway adjacent',
  greenbelt_adjacent: 'Greenbelt adjacent', wfnt_access_rights: 'Deeded water access',
  top_floor: 'Top floor (condo)', end_unit: 'End unit (condo)',
  parking_garage: 'Garage parking (condo)', historic_site: 'Historic designation',
};
const EXCLUDE_LABELS = {
  power_lines: 'No power lines', flood_plain: 'Not in flood plain',
};
const TIER_META = {
  A: { label: 'Likely to sell', sub: 'court record',
       color: 'var(--call-now)', bg: 'var(--call-now-bg)' },
  B: { label: 'May be open', sub: 'ownership pattern',
       color: 'var(--build-now)', bg: 'var(--build-now-bg)' },
  C: { label: 'Fits the brief', sub: 'no signal yet',
       color: 'var(--hold)', bg: 'var(--hold-bg)' },
};

function money(v) {
  if (v == null) return '—';
  return '$' + Number(v).toLocaleString();
}

/* ── Shared bits ─────────────────────────────────────────────────── */

function Label({ children }) {
  return (
    <div style={{ fontFamily: F.sans, fontSize: 11, letterSpacing: '0.12em',
      textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 6 }}>
      {children}
    </div>
  );
}

function Input(props) {
  return (
    <input {...props} style={{ width: '100%', boxSizing: 'border-box',
      background: 'var(--bg-input)', border: '1px solid var(--border)',
      borderRadius: 6, padding: '10px 12px', fontFamily: F.sans, fontSize: 14,
      color: 'var(--text)', outline: 'none', ...(props.style || {}) }} />
  );
}

function Btn({ kind = 'primary', children, ...rest }) {
  const styles = kind === 'primary'
    ? { background: 'var(--accent)', color: '#fff', border: '1px solid var(--accent)' }
    : kind === 'danger'
      ? { background: 'transparent', color: 'var(--call-now)', border: '1px solid var(--call-now)' }
      : { background: 'transparent', color: 'var(--text)', border: '1px solid var(--border-strong)' };
  return (
    <button {...rest} style={{ ...styles, borderRadius: 6, padding: '10px 18px',
      fontFamily: F.sans, fontSize: 13, fontWeight: 600, letterSpacing: '0.02em',
      cursor: rest.disabled ? 'not-allowed' : 'pointer',
      opacity: rest.disabled ? 0.5 : 1, ...(rest.style || {}) }}>
      {children}
    </button>
  );
}

function Toggle({ on, onClick, children, count }) {
  return (
    <button onClick={onClick} style={{
      display: 'inline-flex', alignItems: 'center', gap: 8,
      background: on ? 'var(--accent-dim)' : 'var(--bg-card)',
      border: `1px solid ${on ? 'var(--accent)' : 'var(--border)'}`,
      color: on ? 'var(--accent)' : 'var(--text-secondary)',
      borderRadius: 999, padding: '7px 14px', fontFamily: F.sans, fontSize: 13,
      fontWeight: on ? 600 : 500, cursor: 'pointer' }}>
      {children}
      {count != null && (
        <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{count.toLocaleString()}</span>
      )}
    </button>
  );
}

/* ── Tier bar — the signature element ────────────────────────────── */

function TierBar({ tiers, matched }) {
  const total = Math.max(matched, 1);
  return (
    <div>
      <div style={{ display: 'flex', height: 14, borderRadius: 7, overflow: 'hidden',
        border: '1px solid var(--border)' }}>
        {['A', 'B', 'C'].map(t => (
          (tiers[t] || 0) > 0 && (
            <div key={t} title={`${TIER_META[t].label}: ${tiers[t]}`}
              style={{ width: `${(tiers[t] / total) * 100}%`,
                minWidth: tiers[t] > 0 ? 6 : 0, background: TIER_META[t].color }} />
          )
        ))}
      </div>
      <div style={{ display: 'flex', gap: 22, marginTop: 10, flexWrap: 'wrap' }}>
        {['A', 'B', 'C'].map(t => (
          <div key={t} style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ width: 9, height: 9, borderRadius: 2, background: TIER_META[t].color,
              display: 'inline-block', transform: 'translateY(0.5px)' }} />
            <span style={{ fontFamily: F.display, fontSize: 22, color: 'var(--text)' }}>
              {(tiers[t] || 0).toLocaleString()}
            </span>
            <span style={{ fontFamily: F.sans, fontSize: 12, color: 'var(--text-secondary)' }}>
              {TIER_META[t].label}
              <span style={{ color: 'var(--text-tertiary)' }}> · {TIER_META[t].sub}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── The page ────────────────────────────────────────────────────── */

export default function NetworkPage() {
  const nav = useNavigate();
  const [gate, setGate] = useState('checking'); // checking | open
  const [view, setView] = useState('registry'); // registry | compose | report
  const [needs, setNeeds] = useState([]);
  const [activeNeed, setActiveNeed] = useState(null);
  const [runResult, setRunResult] = useState(null);
  const [reportRows, setReportRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let dead = false;
    network.status()
      .then(() => { if (!dead) { setGate('open'); refreshNeeds(); } })
      .catch(() => { if (!dead) nav('/', { replace: true }); });
    return () => { dead = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refreshNeeds() {
    try { setNeeds((await network.needs()).needs || []); }
    catch (e) { setError(safeErrorMessage(e)); }
  }

  async function openReport(need, freshRun = null) {
    setBusy(true); setError('');
    try {
      const run = freshRun || (await network.runMatch(need.id));
      const rep = await network.report(need.id, '?limit=40');
      setActiveNeed(need); setRunResult(run.report ? run : rep.run ? { ...rep.run, ...rep.run.report ? {} : {} } : run);
      setRunResult({ report: run.report || rep.run?.report, matched: run.matched ?? rep.run?.matched, candidates: run.candidates ?? rep.run?.candidates });
      setReportRows(rep.matches || []);
      setView('report');
    } catch (e) { setError(safeErrorMessage(e)); }
    finally { setBusy(false); }
  }

  if (gate === 'checking') {
    return <div style={{ minHeight: '100vh', background: 'var(--bg)' }} />;
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', paddingBottom: 80 }}>
      {/* Masthead */}
      <div style={{ background: 'var(--bg-dark)', padding: '26px 0 22px' }}>
        <div style={{ maxWidth: 980, margin: '0 auto', padding: '0 28px',
          display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontFamily: F.sans, fontSize: 10, letterSpacing: '0.22em',
              textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 6 }}>
              SellerSignal · Private preview
            </div>
            <div style={{ fontFamily: F.display, fontSize: 30, color: 'var(--text-inverse)' }}>
              Buyer Network
            </div>
          </div>
          <div style={{ fontFamily: F.serif, fontSize: 13, fontStyle: 'italic',
            color: 'rgba(245,240,235,0.55)', maxWidth: 340, textAlign: 'right' }}>
            Search homes that aren't for sale. Rank them by who's likely to sell.
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 980, margin: '0 auto', padding: '30px 28px 0' }}>
        {error && (
          <div style={{ background: 'var(--call-now-bg)', border: '1px solid var(--call-now)',
            color: 'var(--call-now)', borderRadius: 8, padding: '10px 14px',
            fontFamily: F.sans, fontSize: 13, marginBottom: 18 }}>
            {error}
          </div>
        )}

        {view === 'registry' && (
          <Registry needs={needs} busy={busy}
            onCompose={() => { setView('compose'); setError(''); }}
            onOpen={(n) => openReport(n)} />
        )}
        {view === 'compose' && (
          <Compose
            onCancel={() => setView('registry')}
            onCreated={async (need, run) => { await refreshNeeds(); openReport(need, run); }}
            setError={setError} />
        )}
        {view === 'report' && activeNeed && (
          <Report need={activeNeed} result={runResult} rows={reportRows} busy={busy}
            onBack={() => { setView('registry'); refreshNeeds(); }}
            onRerun={() => openReport(activeNeed)} />
        )}
      </div>
    </div>
  );
}

/* ── Registry (needs dashboard) ──────────────────────────────────── */

function Registry({ needs, onCompose, onOpen, busy }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 22 }}>
        <div style={{ fontFamily: F.display, fontSize: 22, color: 'var(--text)' }}>
          Clients
        </div>
        <Btn onClick={onCompose}>New search</Btn>
      </div>
      {needs.length === 0 ? (
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 10, padding: '46px 30px', textAlign: 'center' }}>
          <div style={{ fontFamily: F.display, fontSize: 19, color: 'var(--text)', marginBottom: 8 }}>
            No searches yet
          </div>
          <div style={{ fontFamily: F.serif, fontSize: 14, color: 'var(--text-secondary)' }}>
            Set up a client's search and see every matching home — listed or not.
          </div>
        </div>
      ) : needs.map(n => (
        <div key={n.id} style={{ background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 10, padding: '16px 20px', marginBottom: 12,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontFamily: F.serif, fontSize: 16, color: 'var(--text)', marginBottom: 4 }}>
              {n.client_ref || 'Unnamed client'}
            </div>
            <div style={{ fontFamily: F.sans, fontSize: 12, color: 'var(--text-secondary)' }}>
              {(n.zips || []).join(' · ')}
              {n.price_min != null || n.price_max != null
                ? `  ·  ${money(n.price_min)}–${money(n.price_max)}` : ''}
              {n.beds_min ? `  ·  ${n.beds_min}+ bd` : ''}
              {n.status !== 'active' ? `  ·  ${n.status}` : ''}
            </div>
          </div>
          <Btn kind="ghost" disabled={busy} onClick={() => onOpen(n)}>
            {busy ? 'Matching…' : 'See matches'}
          </Btn>
        </div>
      ))}
    </div>
  );
}

/* ── Compose (the client brief) ──────────────────────────────────── */

function Compose({ onCancel, onCreated, setError }) {
  const [zipText, setZipText] = useState('');
  const [avail, setAvail] = useState(null);   // /filters payload for zips
  const [loadingAvail, setLoadingAvail] = useState(false);
  const [saving, setSaving] = useState(false);
  const [f, setF] = useState({ client_ref: '', price_min: '', price_max: '',
    beds_min: '', baths_min: '', sqft_min: '', year_built_min: '',
    year_built_max: '', soft_notes: '' });
  const [flags, setFlags] = useState({});       // feature bool toggles
  const [excludes, setExcludes] = useState({}); // power_lines etc.
  const [viewCats, setViewCats] = useState([]); // selected view categories
  const [viewMin, setViewMin] = useState(3);

  const zips = useMemo(() =>
    zipText.split(/[,\s]+/).map(z => z.trim()).filter(z => /^\d{5}$/.test(z)).slice(0, 12),
    [zipText]);

  useEffect(() => {
    if (!zips.length) { setAvail(null); return; }
    let dead = false;
    setLoadingAvail(true);
    network.filters(zips.join(','))
      .then(r => { if (!dead) setAvail(r.filters); })
      .catch(() => { if (!dead) setAvail(null); })
      .finally(() => { if (!dead) setLoadingAvail(false); });
    return () => { dead = true; };
  }, [zips.join(',')]); // eslint-disable-line react-hooks/exhaustive-deps

  // Aggregate availability across chosen zips
  const agg = useMemo(() => {
    if (!avail) return null;
    const feats = {}; const views = {}; const core = {}; let parcels = 0;
    Object.values(avail).forEach(z => {
      parcels += z.parcels || 0;
      Object.entries(z.features || {}).forEach(([k, v]) => { feats[k] = (feats[k] || 0) + v; });
      Object.entries(z.views || {}).forEach(([k, v]) => { views[k] = (views[k] || 0) + v; });
      Object.entries(z.core || {}).forEach(([k, v]) => { core[k] = (core[k] || 0) + v; });
    });
    return { feats, views, core, parcels };
  }, [avail]);

  async function submit() {
    setSaving(true); setError('');
    try {
      const feature_filters = {};
      Object.entries(flags).forEach(([k, v]) => { if (v) feature_filters[k] = true; });
      Object.entries(excludes).forEach(([k, v]) => { if (v) feature_filters[k] = false; });
      if (viewCats.length) {
        feature_filters.view_any = viewCats;
        feature_filters.view_cat_min = viewMin;
      }
      const body = {
        zips,
        client_ref: f.client_ref || null,
        price_min: f.price_min ? Number(f.price_min) : null,
        price_max: f.price_max ? Number(f.price_max) : null,
        beds_min: f.beds_min ? Number(f.beds_min) : null,
        baths_min: f.baths_min ? Number(f.baths_min) : null,
        sqft_min: f.sqft_min ? Number(f.sqft_min) : null,
        year_built_min: f.year_built_min ? Number(f.year_built_min) : null,
        year_built_max: f.year_built_max ? Number(f.year_built_max) : null,
        soft_notes: f.soft_notes || null,
        attestation: true,
      };
      Object.keys(body).forEach(k => body[k] == null && delete body[k]);
      if (Object.keys(feature_filters).length) body.feature_filters = feature_filters;
      const created = await network.createNeed(body);
      const run = await network.runMatch(created.need.id);
      onCreated(created.need, run);
    } catch (e) { setError(safeErrorMessage(e)); setSaving(false); }
  }

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const sortedViews = agg ? Object.entries(agg.views).sort((a, b) => b[1] - a[1]) : [];
  const sortedFeats = agg ? Object.entries(agg.feats)
    .filter(([k]) => FEATURE_LABELS[k]).sort((a, b) => b[1] - a[1]) : [];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
        marginBottom: 6 }}>
        <div style={{ fontFamily: F.display, fontSize: 22, color: 'var(--text)' }}>
          New search
        </div>
        <button onClick={onCancel} style={{ background: 'none', border: 'none',
          fontFamily: F.sans, fontSize: 13, color: 'var(--text-secondary)',
          cursor: 'pointer', textDecoration: 'underline' }}>
          Back to registry
        </button>
      </div>
      <div style={{ fontFamily: F.serif, fontSize: 14, color: 'var(--text-secondary)', marginBottom: 24 }}>
        This searches every home in these ZIPs, not just listings. Filters appear only where the county records that data.
      </div>

      <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 10, padding: 24 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18 }}>
          <div style={{ gridColumn: '1 / -1' }}>
            <Label>Client reference (private to you)</Label>
            <Input placeholder="e.g. The Hendersons — relocating from SF"
              value={f.client_ref} onChange={set('client_ref')} />
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <Label>Where (ZIP codes, up to 12)</Label>
            <Input placeholder="98040, 98004" value={zipText}
              onChange={(e) => setZipText(e.target.value)} />
            {agg && (
              <div style={{ fontFamily: F.sans, fontSize: 12, color: 'var(--text-tertiary)', marginTop: 6 }}>
                {agg.parcels.toLocaleString()} homes in these ZIPs
                {loadingAvail ? ' · checking what filters are available…' : ''}
              </div>
            )}
          </div>
          <div><Label>Price from</Label>
            <Input placeholder="2,000,000" inputMode="numeric" value={f.price_min} onChange={set('price_min')} /></div>
          <div><Label>Price to</Label>
            <Input placeholder="4,500,000" inputMode="numeric" value={f.price_max} onChange={set('price_max')} /></div>
          <div><Label>Bedrooms (min)</Label>
            <Input placeholder="4" inputMode="numeric" value={f.beds_min} onChange={set('beds_min')} /></div>
          <div><Label>Bathrooms (min)</Label>
            <Input placeholder="2.5" inputMode="decimal" value={f.baths_min} onChange={set('baths_min')} /></div>
          <div><Label>Sqft (min)</Label>
            <Input placeholder="3,000" inputMode="numeric" value={f.sqft_min} onChange={set('sqft_min')} /></div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div><Label>Built after</Label>
              <Input placeholder="1990" inputMode="numeric" value={f.year_built_min} onChange={set('year_built_min')} /></div>
            <div><Label>Built before</Label>
              <Input placeholder="" inputMode="numeric" value={f.year_built_max} onChange={set('year_built_max')} /></div>
          </div>
        </div>

        {sortedViews.length > 0 && (
          <div style={{ marginTop: 26 }}>
            <Label>Views (county-graded)</Label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
              {sortedViews.map(([k, count]) => (
                <Toggle key={k} count={count} on={viewCats.includes(k)}
                  onClick={() => setViewCats(v => v.includes(k) ? v.filter(x => x !== k) : [...v, k])}>
                  {VIEW_LABELS[k] || k}
                </Toggle>
              ))}
            </div>
            {viewCats.length > 0 && (
              <div style={{ display: 'flex', gap: 6 }}>
                {[1, 2, 3, 4].map(n => (
                  <Toggle key={n} on={viewMin === n} onClick={() => setViewMin(n)}>
                    {n}+
                  </Toggle>
                ))}
              </div>
            )}
          </div>
        )}

        {sortedFeats.length > 0 && (
          <div style={{ marginTop: 26 }}>
            <Label>Must have</Label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {sortedFeats.map(([k, count]) => (
                <Toggle key={k} count={count} on={!!flags[k]}
                  onClick={() => setFlags(x => ({ ...x, [k]: !x[k] }))}>
                  {FEATURE_LABELS[k]}
                </Toggle>
              ))}
            </div>
          </div>
        )}

        {agg && (
          <div style={{ marginTop: 26 }}>
            <Label>Must not have</Label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {Object.entries(EXCLUDE_LABELS).map(([k, label]) => (
                <Toggle key={k} on={!!excludes[k]}
                  onClick={() => setExcludes(x => ({ ...x, [k]: !x[k] }))}>
                  {label}
                </Toggle>
              ))}
            </div>
          </div>
        )}

        <div style={{ marginTop: 26 }}>
          <Label>Notes about this client (not used for matching)</Label>
          <textarea value={f.soft_notes} onChange={set('soft_notes')} rows={3}
            placeholder="West-facing preferred. Will renovate for the right lot."
            style={{ width: '100%', boxSizing: 'border-box', background: 'var(--bg-input)',
              border: '1px solid var(--border)', borderRadius: 6, padding: '10px 12px',
              fontFamily: F.serif, fontSize: 14, color: 'var(--text)', resize: 'vertical' }} />
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 26 }}>
          <Btn kind="ghost" onClick={onCancel}>Cancel</Btn>
          <Btn disabled={!zips.length || saving} onClick={submit}>
            {saving ? 'Searching…' : 'See matches'}
          </Btn>
        </div>
      </div>
    </div>
  );
}

/* ── Report — Zillow-clear, address-blind ────────────────────────
 * The buyer side never sees which home it is. Cards describe the home
 * (price, beds/baths/sqft, year, features, area, how long it's been
 * held) and the seller-likelihood badge — never the address or parcel
 * id. That's the blind-matching contract: demand learns what exists,
 * supply identity stays with the territory owner.
 */

function Report({ need, result, rows, busy, onBack, onRerun }) {
  const rep = result?.report || {};
  const tiers = rep.tiers || { A: 0, B: 0, C: 0 };
  const matched = result?.matched ?? 0;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
        marginBottom: 6 }}>
        <div style={{ fontFamily: F.display, fontSize: 22, color: 'var(--text)' }}>
          {need.client_ref || 'Unnamed client'}
        </div>
        <div style={{ display: 'flex', gap: 14 }}>
          <button onClick={onRerun} disabled={busy} style={{ background: 'none', border: 'none',
            fontFamily: F.sans, fontSize: 13, color: 'var(--accent)', cursor: 'pointer',
            textDecoration: 'underline' }}>
            {busy ? 'Matching…' : 'Refresh matches'}
          </button>
          <button onClick={onBack} style={{ background: 'none', border: 'none',
            fontFamily: F.sans, fontSize: 13, color: 'var(--text-secondary)', cursor: 'pointer',
            textDecoration: 'underline' }}>
            All clients
          </button>
        </div>
      </div>

      <div style={{ fontFamily: F.display, fontSize: 34, color: 'var(--text)', margin: '10px 0 2px' }}>
        {matched.toLocaleString()} homes match
      </div>
      <div style={{ fontFamily: F.serif, fontSize: 14.5, color: 'var(--text-secondary)', marginBottom: 18 }}>
        in {(need.zips || []).join(' · ')} — none of them on the market.
      </div>

      <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 10, padding: '20px 22px', marginBottom: 24 }}>
        <TierBar tiers={tiers} matched={matched} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(290px, 1fr))',
        gap: 14 }}>
        {rows.map(m => <HomeCard key={m.id || m.pin} m={m} />)}
      </div>
    </div>
  );
}

function HomeCard({ m }) {
  const d = m.detail || {}; const ft = d.features || {};
  const meta = TIER_META[m.tier] || TIER_META.C;

  const specs = [
    d.bedrooms != null ? `${d.bedrooms} bd` : null,
    d.bathrooms != null ? `${d.bathrooms} ba` : null,
    d.sqft ? `${Number(d.sqft).toLocaleString()} sqft` : null,
  ].filter(Boolean).join('  |  ');

  const chips = [];
  if (d.year_built) chips.push(`Built ${d.year_built}`);
  if (ft.pool) chips.push('Pool');
  if (d.waterfront) chips.push('Waterfront');
  const vd = ft.views || {};
  const topView = Object.entries(vd).sort((a, b) => b[1] - a[1])[0];
  if (topView) chips.push(`${VIEW_LABELS[topView[0]] || 'View'}`);
  if (ft.bldg_grade >= 10) chips.push('High-end build');
  if (ft.golf_adjacent) chips.push('On the fairway');
  if (d.acres >= 0.5) chips.push(`${d.acres} acres`);

  const held = d.tenure_years != null ? Math.round(d.tenure_years) : null;

  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 10, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 4, background: meta.color }} />
      <div style={{ padding: '14px 16px 15px', display: 'flex', flexDirection: 'column',
        flexGrow: 1 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <div style={{ fontFamily: F.display, fontSize: 20, color: 'var(--text)' }}>
            {money(d.total_value)}
          </div>
          <div style={{ fontFamily: F.sans, fontSize: 11.5, color: 'var(--text-tertiary)' }}>
            {d.city ? `${d.city} ` : ''}{m.zip_code}
          </div>
        </div>
        <div style={{ fontFamily: F.sans, fontSize: 13.5, color: 'var(--text)', marginTop: 4 }}>
          {specs || 'Details on file'}
        </div>
        {chips.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
            {chips.slice(0, 4).map(c => (
              <span key={c} style={{ fontFamily: F.sans, fontSize: 11.5,
                color: 'var(--text-secondary)', background: 'var(--bg)', borderRadius: 4,
                padding: '3px 8px', border: '1px solid var(--border)' }}>
                {c}
              </span>
            ))}
          </div>
        )}
        <div style={{ marginTop: 'auto', paddingTop: 12, display: 'flex',
          justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontFamily: F.sans, fontSize: 11.5, color: 'var(--text-tertiary)' }}>
            {held != null ? `Held ${held} yrs` : ''}
          </span>
          <span style={{ background: meta.bg, color: meta.color, borderRadius: 4,
            padding: '3px 9px', fontFamily: F.sans, fontSize: 10.5, fontWeight: 700,
            letterSpacing: '0.07em', textTransform: 'uppercase' }}>
            {meta.label}
          </span>
        </div>
      </div>
    </div>
  );
}
