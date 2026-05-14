import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import L from 'leaflet';

import { zipPolygons, notifications, safeErrorMessage } from '../../api/client.js';

/**
 * TerritoryMap — geographic territory selector.
 *
 * Renders a Leaflet map with one polygon per covered ZIP, colored by the
 * viewer's relationship to that ZIP:
 *
 *   - mine       : your claimed territory (gold fill, gold border)
 *   - claimed    : claimed by another agent (muted/dashed)
 *   - available  : open to claim (green tint)
 *
 * Click any polygon → stats card slides in from the right (or bottom on
 * mobile). Card content varies by status:
 *
 *   - mine       : "Open this week's briefing" → /zip/{zip}
 *   - claimed    : Notify-me form. Submitting POSTs to
 *                  /api/notifications/subscribe; success state shows
 *                  a confirmation. Per product: no agent name shown
 *                  for claimed ZIPs, only "Claimed".
 *   - available  : "Claim this territory" → calls onClaimRequest(zip)
 *                  which the parent handles (existing claim flow).
 *
 * Props
 *   role           "operator" | "agent"
 *   myZip          string | null   — agent's claimed ZIP (or null)
 *   zips           [{ zip_code, parcel_count, current_call_now_count,
 *                     status, claimed_by_user_id, ... }, ...]
 *   defaultEmail   string          — pre-fill the notify-me form
 *   onClaimRequest (zip_code) => void — bubbles to parent's claim modal
 *
 * Architecture notes
 *   - Map and Leaflet layer state lives in refs; React state only
 *     drives the stats-card UI. This avoids re-rendering Leaflet on
 *     every state change.
 *   - Polygons are fetched from /api/zip-polygons (public, cacheable).
 *     The server filters to live ZIPs already; we still merge with
 *     the `zips` prop to enrich each feature with parcel/lead counts
 *     and ownership status.
 *   - For tiny ZIPs like 98039 (Medina, ~1.27 sq mi), clicking on
 *     mobile is hard. Polygons stay clickable, but we also render an
 *     invisible larger circle marker per ZIP to widen the hit target
 *     on touch devices. Done with a transparent CircleMarker on the
 *     same click handler.
 */

// ─── Status helpers ──────────────────────────────────────────────────────
// Maps the API's three-state response to our three-state UI vocabulary.
//   API: 'mine' | 'claimed_by_other' | 'available'
//   UI:  'mine' | 'claimed'          | 'available'
// (Differs from /api/agent/territory-status only in the second name —
// API uses 'claimed_by_other' for clarity, UI uses 'claimed' for terseness.)
function statusForZip(zip, myZip, zipRecord) {
  // If the record is missing entirely (polygon present but ZIP not in
  // our coverage payload), treat as available — defensive default.
  if (!zipRecord) return 'available';
  const apiStatus = zipRecord.status;
  if (apiStatus === 'mine') return 'mine';
  if (apiStatus === 'claimed_by_other') return 'claimed';
  if (apiStatus === 'available') return 'available';
  // Fallback: my_zip match, then default to available.
  if (myZip && zip === myZip) return 'mine';
  return 'available';
}

const POLY_STYLE = {
  mine: {
    fillColor:   '#8B6914',
    fillOpacity: 0.55,
    color:       '#6B5310',
    weight:      2.5,
  },
  claimed: {
    fillColor:   '#BFB6A8',
    fillOpacity: 0.42,
    color:       '#9C9080',
    weight:      1.5,
    dashArray:   '4,4',
  },
  available: {
    fillColor:   '#4F7B57',
    fillOpacity: 0.20,
    color:       '#4F7B57',
    weight:      1.8,
  },
};

const POLY_HOVER_BOOST = {
  fillOpacityDelta: 0.18,
  weightDelta:      0.8,
};

// ─── Component ───────────────────────────────────────────────────────────
export default function TerritoryMap({
  role,
  myZip,
  zips = [],
  defaultEmail = '',
  onClaimRequest,
}) {
  const navigate = useNavigate();

  // Refs for Leaflet objects — never depend on these in render.
  const mapEl       = useRef(null);
  const mapInstance = useRef(null);
  const layerGroup  = useRef(null);
  const labelGroup  = useRef(null);

  // Index `zips` array by zip_code for O(1) lookup
  const zipIndex = useMemo(() => {
    const m = {};
    for (const z of zips) m[z.zip_code] = z;
    return m;
  }, [zips]);

  // Stats card state (the only thing that drives re-renders)
  const [selected, setSelected]     = useState(null);   // zip_code or null
  const [polyError, setPolyError]   = useState(null);
  const [polysLoaded, setPolysLoaded] = useState(false);

  // Detect mobile for layout switch (bottom sheet vs sidebar). We
  // recompute on resize so device rotation works correctly.
  const [isNarrow, setIsNarrow] = useState(
    typeof window !== 'undefined' ? window.innerWidth < 720 : false
  );
  useEffect(() => {
    function onResize() { setIsNarrow(window.innerWidth < 720); }
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  // ─── Leaflet bootstrap ─────────────────────────────────────────────
  useEffect(() => {
    if (!mapEl.current || mapInstance.current) return;

    // Default center over Bellevue/Seattle, will fitBounds once polygons load.
    const map = L.map(mapEl.current, {
      center: [47.62, -122.20],
      zoom: 10,
      minZoom: 8,
      maxZoom: 14,
      zoomControl: true,
      attributionControl: true,
    });

    // Light basemap so our polygons own the visual hierarchy.
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
      subdomains: 'abcd',
      maxZoom: 19,
    }).addTo(map);

    mapInstance.current = map;
    layerGroup.current  = L.layerGroup().addTo(map);
    labelGroup.current  = L.layerGroup().addTo(map);

    return () => {
      map.remove();
      mapInstance.current = null;
    };
  }, []);

  // ─── Polygon fetch + render ─────────────────────────────────────────
  useEffect(() => {
    if (!mapInstance.current) return;

    let cancelled = false;
    zipPolygons.list()
      .then((collection) => {
        if (cancelled) return;
        renderPolygons(collection);
        setPolysLoaded(true);
      })
      .catch((e) => {
        if (cancelled) return;
        setPolyError(safeErrorMessage(e, 'Could not load territory boundaries'));
      });

    return () => { cancelled = true; };
    // We intentionally render only once (zipIndex changes are reflected
    // by re-styling existing layers, not re-rendering — see effect below).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function renderPolygons(collection) {
    if (!collection?.features?.length) return;
    const map = mapInstance.current;
    layerGroup.current.clearLayers();
    labelGroup.current.clearLayers();

    const featureLayers = [];

    for (const feature of collection.features) {
      const zip = feature.properties?.zip;
      if (!zip) continue;
      const zipRec = zipIndex[zip];
      const status = statusForZip(zip, myZip, zipRec);

      const layer = L.geoJSON(feature, {
        style: () => POLY_STYLE[status],
      });

      // Hit-target widening for tiny ZIPs (Medina): also add a
      // transparent circle marker at centroid that triggers the same
      // click. Doesn't affect appearance.
      const center = layer.getBounds().getCenter();
      const hitMarker = L.circleMarker(center, {
        radius: 18,
        opacity: 0,
        fillOpacity: 0,
        interactive: true,
      });

      const onClick = () => setSelected(zip);
      const onHoverIn = () => {
        layer.setStyle({
          ...POLY_STYLE[status],
          fillOpacity: Math.min(1, POLY_STYLE[status].fillOpacity + POLY_HOVER_BOOST.fillOpacityDelta),
          weight:      POLY_STYLE[status].weight + POLY_HOVER_BOOST.weightDelta,
        });
        layer.bringToFront();
      };
      const onHoverOut = () => {
        layer.setStyle(POLY_STYLE[status]);
      };

      layer.on('click', onClick);
      layer.on('mouseover', onHoverIn);
      layer.on('mouseout',  onHoverOut);
      hitMarker.on('click', onClick);

      layerGroup.current.addLayer(layer);
      layerGroup.current.addLayer(hitMarker);
      featureLayers.push(layer);

      // Permanent ZIP label at centroid
      L.marker(center, {
        icon: L.divIcon({
          className: 'ts-zip-label',
          html: `<span class="ts-zip-label-text">${zip}</span>`,
        }),
        interactive: false,
      }).addTo(labelGroup.current);
    }

    // Fit map bounds to the union of all polygons
    if (featureLayers.length) {
      const group = L.featureGroup(featureLayers);
      map.fitBounds(group.getBounds(), { padding: [40, 40] });
    }
  }

  // Re-style polygons when zipIndex/myZip changes (e.g. after a claim
  // succeeds and the prop updates). Keep it shallow — just walk
  // the existing layers and reset their styles.
  useEffect(() => {
    if (!polysLoaded || !layerGroup.current) return;
    layerGroup.current.eachLayer((layer) => {
      // GeoJSON layer → has feature property
      const f = layer.feature;
      if (!f) return;
      const zip = f.properties?.zip;
      if (!zip) return;
      const status = statusForZip(zip, myZip, zipIndex[zip]);
      layer.setStyle(POLY_STYLE[status]);
    });
  }, [zipIndex, myZip, polysLoaded]);

  // ─── Stats card ────────────────────────────────────────────────────
  const selectedZip = selected ? zipIndex[selected] : null;
  const selectedStatus = selected
    ? statusForZip(selected, myZip, selectedZip)
    : null;

  // Track whether the card has had a chance to mount. Triggering the
  // transition requires entering the DOM in an "off" state and then
  // toggling to "on" on the next frame — otherwise CSS transitions
  // never fire because the element starts at the final position.
  const [cardEntered, setCardEntered] = useState(false);
  useEffect(() => {
    if (selected) {
      // Microtask delay so the next paint catches the off→on flip
      const id = requestAnimationFrame(() => setCardEntered(true));
      return () => cancelAnimationFrame(id);
    } else {
      setCardEntered(false);
    }
  }, [selected]);

  return (
    <div style={STYLES.wrap}>
      {/* Inline styles for Leaflet label and hover transitions. Component
          is self-scoped via the `ts-` prefix. */}
      <style>{INLINE_CSS}</style>

      <div ref={mapEl} style={STYLES.map} />

      {polyError && (
        <div style={STYLES.errorBanner}>{polyError}</div>
      )}

      {!polysLoaded && !polyError && (
        <div style={STYLES.loadingOverlay}>
          <div style={STYLES.loadingText}>Drawing your territories…</div>
          <div style={STYLES.loadingBar}><div style={STYLES.loadingBarFill} /></div>
        </div>
      )}

      <Legend />

      {selected && (
        <StatsCard
          zip={selected}
          zipRecord={selectedZip}
          status={selectedStatus}
          role={role}
          isNarrow={isNarrow}
          defaultEmail={defaultEmail}
          entered={cardEntered}
          agentHasTerritory={!!myZip}
          onClose={() => setSelected(null)}
          onOpenBriefing={() => navigate(`/zip/${selected}`)}
          onClaim={() => {
            setSelected(null);
            onClaimRequest && onClaimRequest(selected);
          }}
        />
      )}
    </div>
  );
}

// ─── Stats card (right-side card on desktop, bottom sheet on mobile) ────
function StatsCard({
  zip, zipRecord, status, role, isNarrow,
  defaultEmail, entered, agentHasTerritory,
  onClose, onOpenBriefing, onClaim,
}) {
  const styleByStatus = {
    mine:      { accent: '#8B6914', label: 'Your territory' },
    claimed:   { accent: '#BFB6A8', label: 'Claimed' },
    available: { accent: '#4F7B57', label: 'Available' },
  };
  const cfg = styleByStatus[status];
  const parcels = zipRecord?.parcel_count || 0;
  // Contact Now: prefer the per-bucket total from the new API field;
  // fall back to legacy current_call_now_count (probate-only) for
  // backward compatibility with payloads that predate migration 022.
  const contactTotal = zipRecord?.contact_now_total
                    ?? zipRecord?.current_call_now_count
                    ?? 0;
  const buckets = zipRecord?.contact_now_buckets || null;
  const city    = zipRecord?.city || '—';

  // Slide-in transform. Off-state pushes the card 20px off-screen in
  // the appropriate direction; on-state lets transition settle to 0.
  const offTransform = isNarrow ? 'translateY(20px)' : 'translateX(20px)';
  const transitionStyle = {
    transform:   entered ? 'none' : offTransform,
    opacity:     entered ? 1 : 0,
    transition:  'transform 220ms cubic-bezier(0.32,0.72,0.24,1.06), opacity 180ms ease',
  };
  const cardStyle = {
    ...(isNarrow ? STYLES.cardMobile : STYLES.cardDesktop),
    ...transitionStyle,
  };

  return (
    <>
      {isNarrow && <div style={STYLES.cardBackdrop} onClick={onClose} />}
      <div style={cardStyle} role="dialog" aria-label={`Territory ${zip}`}>
        <div style={{ ...STYLES.cardAccent, background: cfg.accent }} />
        <button onClick={onClose} style={STYLES.cardClose} aria-label="Close">×</button>

        <div style={STYLES.cardHead}>
          <h3 style={STYLES.cardZip}>{zip}</h3>
          <div style={STYLES.cardCity}>{city}, WA</div>
          <span style={{ ...STYLES.statusPill, ...statusPillStyle(status) }}>
            {cfg.label}
          </span>
        </div>

        <div style={STYLES.cardBody}>
          <StatRow label="Parcels in territory" value={parcels.toLocaleString()} />
          <StatRow label="Contact now leads" value={contactTotal.toLocaleString()}
                   emphasis={contactTotal > 0} muted={contactTotal === 0} />
          {buckets && contactTotal > 0 && (
            <BucketBreakdown buckets={buckets} />
          )}
        </div>

        <div style={STYLES.cardFoot}>
          {status === 'mine' && (
            <button onClick={onOpenBriefing} style={STYLES.btnPrimaryDark}>
              Open this week’s briefing
            </button>
          )}
          {status === 'claimed' && role === 'operator' && (
            <button onClick={onOpenBriefing} style={STYLES.btnPrimaryDark}>
              Open briefing
            </button>
          )}
          {status === 'claimed' && role !== 'operator' && (
            <NotifyMeForm zip={zip} defaultEmail={defaultEmail} />
          )}
          {status === 'available' && role === 'agent' && !agentHasTerritory && (
            <button onClick={onClaim} style={STYLES.btnPrimary}>
              Claim this territory
            </button>
          )}
          {status === 'available' && role === 'agent' && agentHasTerritory && (
            <div style={STYLES.alreadyOwn}>
              You already hold a territory. Each agent gets one exclusive ZIP.
            </div>
          )}
          {status === 'available' && role === 'operator' && (
            <button onClick={onOpenBriefing} style={STYLES.btnPrimaryDark}>
              Open briefing
            </button>
          )}
        </div>
      </div>
    </>
  );
}

function statusPillStyle(s) {
  if (s === 'mine')      return { background: 'rgba(139,105,20,0.12)',  color: '#8B6914' };
  if (s === 'claimed')   return { background: 'rgba(191,182,168,0.30)', color: '#6B5D47' };
  return { background: 'rgba(79,123,87,0.15)',  color: '#4F7B57' };
}

function StatRow({ label, value, emphasis, muted }) {
  return (
    <div style={STYLES.statRow}>
      <span style={STYLES.statLabel}>{label}</span>
      <span style={{
        ...STYLES.statValue,
        ...(emphasis ? { color: '#8B6914', fontWeight: 500 } : {}),
        ...(muted    ? { color: '#9A8C76' } : {}),
      }}>{value}</span>
    </div>
  );
}

// ─── Per-bucket Contact Now breakdown ─────────────────────────────────
// Two rows of three buckets each, label · count. Compact so the popup
// stays the same height. Zero-count buckets are dimmed so the eye
// goes to where the leads actually are.
function BucketBreakdown({ buckets }) {
  const items = [
    { key: 'probate',  label: 'Probate'  },
    { key: 'divorce',  label: 'Divorce'  },
    { key: 'trust',    label: 'Trust'    },
    { key: 'llc',      label: 'LLC'      },
    { key: 'absentee', label: 'Absentee' },
    { key: 'tenure',   label: 'Tenure'   },
  ];
  return (
    <div style={{
      display:           'grid',
      gridTemplateColumns: '1fr 1fr 1fr',
      gap:                '6px 12px',
      marginTop:          '8px',
      paddingTop:         '8px',
      borderTop:          '1px solid rgba(155, 137, 99, 0.18)',
    }}>
      {items.map(({ key, label }) => {
        const count = buckets?.[key] || 0;
        const zero  = count === 0;
        return (
          <div key={key} style={{
            display:        'flex',
            justifyContent: 'space-between',
            fontFamily:     'var(--font-sans)',
            fontSize:       11,
            letterSpacing:  '0.02em',
            color:          zero ? '#9A8C76' : '#5C4F3A',
            opacity:        zero ? 0.55 : 1,
          }}>
            <span style={{ textTransform: 'uppercase' }}>{label}</span>
            <span style={{
              fontWeight: zero ? 400 : 600,
              color:      zero ? '#9A8C76' : '#8B6914',
            }}>
              {count}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ─── Notify-me form ────────────────────────────────────────────────────
function NotifyMeForm({ zip, defaultEmail }) {
  const [email, setEmail]     = useState(defaultEmail || '');
  const [state, setState]     = useState('idle');  // idle | submitting | success | error
  const [errMsg, setErrMsg]   = useState(null);

  async function submit(e) {
    e.preventDefault();
    if (!email || !email.includes('@')) {
      setErrMsg('Please enter a valid email address.');
      setState('error');
      return;
    }
    setState('submitting');
    setErrMsg(null);
    try {
      const result = await notifications.subscribe(zip, email);
      if (result?.ok) {
        setState('success');
      } else {
        setErrMsg('Could not subscribe. Try again?');
        setState('error');
      }
    } catch (err) {
      setErrMsg(safeErrorMessage(err, 'Subscribe failed'));
      setState('error');
    }
  }

  if (state === 'success') {
    return (
      <div style={STYLES.notifySuccess}>
        We’ll email you the moment {zip} releases.
      </div>
    );
  }

  return (
    <form onSubmit={submit} style={STYLES.notifyForm}>
      <p style={STYLES.notifyCopy}>
        Enter your email — we’ll let you know the moment this territory opens up.
      </p>
      <input
        type="email"
        required
        placeholder="you@example.com"
        value={email}
        onChange={(e) => { setEmail(e.target.value); setState('idle'); setErrMsg(null); }}
        style={STYLES.notifyInput}
        disabled={state === 'submitting'}
      />
      {errMsg && <div style={STYLES.notifyError}>{errMsg}</div>}
      <button
        type="submit"
        disabled={state === 'submitting'}
        style={{
          ...STYLES.btnPrimaryDark,
          ...(state === 'submitting' ? { opacity: 0.6, cursor: 'wait' } : {}),
        }}
      >
        {state === 'submitting' ? 'Subscribing…' : 'Notify me'}
      </button>
    </form>
  );
}

// ─── Legend ────────────────────────────────────────────────────────────
function Legend() {
  return (
    <div style={STYLES.legend}>
      <LegendItem swatch={POLY_STYLE.mine.fillColor}     label="Yours" />
      <LegendItem swatch={POLY_STYLE.claimed.fillColor}  label="Claimed" muted />
      <LegendItem swatch={POLY_STYLE.available.fillColor} label="Available" tint />
    </div>
  );
}
function LegendItem({ swatch, label, muted, tint }) {
  return (
    <span style={STYLES.legendItem}>
      <span style={{
        ...STYLES.legendSwatch,
        background: tint ? `${swatch}40` : swatch,
        opacity:    muted ? 0.7 : 1,
        borderColor: muted ? '#9C9080' : swatch,
      }} />
      {label}
    </span>
  );
}

// ─── Styles ────────────────────────────────────────────────────────────
const STYLES = {
  wrap: {
    position: 'relative',
    width: '100%',
    height: '70vh',
    minHeight: 480,
    borderRadius: 'var(--radius-md)',
    overflow: 'hidden',
    border: '1px solid var(--border)',
    background: 'var(--bg-card)',
  },
  map: { width: '100%', height: '100%' },
  errorBanner: {
    position: 'absolute', top: 12, left: 12, right: 12,
    padding: '12px 16px', background: 'rgba(158,75,60,0.10)',
    border: '1px solid #9E4B3C', borderRadius: 4,
    color: '#9E4B3C', fontSize: 13, zIndex: 600,
  },
  loadingOverlay: {
    position: 'absolute', inset: 0, background: 'var(--bg-card)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    flexDirection: 'column', gap: 12, zIndex: 500,
  },
  loadingText: {
    fontFamily: 'var(--font-serif)', fontStyle: 'italic',
    fontSize: 14, color: 'var(--text-secondary)',
  },
  loadingBar: {
    width: 200, height: 2, background: 'var(--border)', overflow: 'hidden', position: 'relative',
  },
  loadingBarFill: {
    position: 'absolute', top: 0, bottom: 0, left: 0, width: '30%',
    background: '#8B6914', animation: 'tsLoadSlide 1.4s ease-in-out infinite',
  },

  // ── Stats card (desktop) ──
  cardDesktop: {
    position: 'absolute', top: 24, right: 24, width: 360,
    background: 'var(--bg-card)', border: '1px solid var(--border)',
    borderRadius: 4, boxShadow: '0 8px 24px rgba(44,36,24,0.12)',
    zIndex: 1000, overflow: 'hidden',
  },
  // ── Stats card (mobile bottom sheet) ──
  cardMobile: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    background: 'var(--bg-card)', borderTop: '1px solid var(--border)',
    borderRadius: '8px 8px 0 0',
    boxShadow: '0 -4px 16px rgba(44,36,24,0.16)',
    zIndex: 1000, overflow: 'hidden',
    maxHeight: '70vh', overflowY: 'auto',
  },
  cardBackdrop: {
    position: 'absolute', inset: 0, background: 'rgba(44,36,24,0.32)',
    zIndex: 999,
  },
  cardAccent: { height: 3 },
  cardClose: {
    position: 'absolute', top: 10, right: 12, width: 28, height: 28,
    border: 'none', background: 'transparent', color: '#9A8C76',
    fontSize: 22, lineHeight: 1, cursor: 'pointer', zIndex: 10,
  },
  cardHead: { padding: '22px 24px 12px', borderBottom: '1px solid var(--border)' },
  cardZip: {
    fontFamily: 'var(--font-display)', fontSize: 36, fontWeight: 400,
    color: 'var(--text)', lineHeight: 1, marginBottom: 4,
  },
  cardCity: {
    fontFamily: 'var(--font-serif)', fontStyle: 'italic',
    fontSize: 16, color: 'var(--text-secondary)',
  },
  statusPill: {
    display: 'inline-block', marginTop: 8, padding: '3px 10px',
    borderRadius: 2, fontFamily: 'var(--font-sans)',
    fontSize: 10, fontWeight: 600, textTransform: 'uppercase',
    letterSpacing: '1.5px',
  },

  cardBody: { padding: '12px 24px' },
  statRow: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
    padding: '10px 0', borderBottom: '1px dotted var(--border)',
  },
  statLabel: {
    fontFamily: 'var(--font-sans)', fontSize: 11,
    textTransform: 'uppercase', letterSpacing: '1.5px',
    color: '#9A8C76', fontWeight: 500,
  },
  statValue: {
    fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 400,
    color: 'var(--text)',
  },

  cardFoot: {
    padding: '16px 24px 22px',
    background: 'var(--bg-input)',
    borderTop: '1px solid var(--border)',
  },
  btnPrimary: {
    display: 'block', width: '100%', padding: '14px 18px',
    border: 'none', borderRadius: 2,
    background: '#8B6914', color: 'var(--bg-card)',
    fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 600,
    textTransform: 'uppercase', letterSpacing: '2px', cursor: 'pointer',
    boxShadow: '0 2px 8px rgba(44,36,24,0.08)',
  },
  btnPrimaryDark: {
    display: 'block', width: '100%', padding: '14px 18px',
    border: 'none', borderRadius: 2,
    background: 'var(--text, #2C2418)', color: 'var(--bg-card)',
    fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 600,
    textTransform: 'uppercase', letterSpacing: '2px', cursor: 'pointer',
  },

  notifyForm: { display: 'flex', flexDirection: 'column', gap: 10 },
  notifyCopy: {
    fontFamily: 'var(--font-serif)', fontStyle: 'italic',
    fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5,
    margin: 0,
  },
  notifyInput: {
    width: '100%', padding: '12px 14px', borderRadius: 2,
    border: '1px solid var(--border)', background: 'var(--bg-card)',
    fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--text)',
    outline: 'none',
  },
  notifyError: {
    fontFamily: 'var(--font-sans)', fontSize: 12, color: '#9E4B3C',
  },
  notifySuccess: {
    fontFamily: 'var(--font-serif)', fontStyle: 'italic',
    fontSize: 14, lineHeight: 1.5, color: '#4F7B57',
    padding: '12px 14px', background: 'rgba(79,123,87,0.12)',
    borderRadius: 2,
  },

  alreadyOwn: {
    fontFamily: 'var(--font-serif)', fontStyle: 'italic',
    fontSize: 13, lineHeight: 1.5, color: 'var(--text-secondary)',
    padding: '12px 14px', background: 'rgba(191,182,168,0.20)',
    borderRadius: 2, textAlign: 'center',
  },

  // ── Legend ──
  legend: {
    position: 'absolute', top: 16, left: 16, zIndex: 600,
    display: 'flex', gap: 16, padding: '10px 14px',
    background: 'rgba(245,240,235,0.94)',
    border: '1px solid var(--border)', borderRadius: 4,
    boxShadow: '0 2px 8px rgba(44,36,24,0.06)',
    fontFamily: 'var(--font-sans)', fontSize: 11,
    textTransform: 'uppercase', letterSpacing: '1.5px',
    color: 'var(--text-secondary)', fontWeight: 500,
  },
  legendItem: { display: 'flex', alignItems: 'center', gap: 8 },
  legendSwatch: {
    width: 12, height: 12, borderRadius: 2,
    border: '1.5px solid', display: 'inline-block',
  },
};

// ─── Inline CSS (label rendering, animations — not expressible inline) ──
const INLINE_CSS = `
.ts-zip-label {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  pointer-events: none;
}
.ts-zip-label-text {
  font-family: var(--font-sans, 'DM Sans', sans-serif);
  font-weight: 600;
  font-size: 11px;
  color: var(--text, #2C2418);
  text-shadow:
    -1px -1px 0 var(--bg-card),
     1px -1px 0 var(--bg-card),
    -1px  1px 0 var(--bg-card),
     1px  1px 0 var(--bg-card);
  letter-spacing: 0.5px;
  white-space: nowrap;
}

@keyframes tsLoadSlide {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(420%); }
}

/* Mobile: hide the floating legend on very narrow screens to save space —
   the colors are intuitive once you've clicked one ZIP. */
@media (max-width: 480px) {
  .ts-legend-mobile-hide { display: none; }
}
`;
