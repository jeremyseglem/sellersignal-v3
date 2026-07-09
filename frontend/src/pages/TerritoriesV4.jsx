import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { territory, billing } from '../api/client.js';
import { ClaimModal } from './TerritoriesPage.jsx';
import '../styles/territories-v4.css';

/*
 * TerritoriesV4 — the territory atlas (MIGRATION_V4.md Phase 3), ported
 * from the approved atlas demo onto the LIVE page's data and flows:
 *
 *   - Data: the same authed GET /agent/territory-status the V3 page uses
 *     (statuses mine / claimed_by_other / available, operator role,
 *     market_key), plus public /api/zip-polygons (real ZCTA boundaries)
 *     and /api/coverage/avg-values (assessed-value snapshot).
 *   - Copy: header/eyebrow/subhead and ZipCard lines verbatim from
 *     TerritoriesPage.jsx, including operator and my-zip variants.
 *   - Claim: the SAME ClaimModal component and the SAME Stripe Checkout
 *     call (billing.createCheckout) — the dive is theater in front of an
 *     unchanged transaction.
 *   - Earth mode deliberately absent (velvet rope: photorealism is the
 *     reward of ownership, not a browsing feature).
 */

const MARKET_LABELS = {
  WA_KING: 'Seattle Eastside',
  WA_SNOHOMISH: 'Edmonds & Snohomish',
  AZ_MARICOPA: 'Scottsdale & Phoenix',
  CT_FAIRFIELD: 'Greenwich',
  TX_DALLAS: 'Dallas & Park Cities',
  TX_TRAVIS: 'Austin & Lakeway',
  TX_COLLIN: 'Allen & Collin',
};
const marketLabel = (k) =>
  MARKET_LABELS[k] || (k ? k.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()) : 'Market');

const fmtVal = (v) => (!v ? null : v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : `$${Math.round(v / 1e3)}K`);

function geomBounds(geom) {
  let minx = 1e9, miny = 1e9, maxx = -1e9, maxy = -1e9;
  const polys = geom.type === 'MultiPolygon' ? geom.coordinates : [geom.coordinates];
  for (const poly of polys) for (const ring of poly) for (const [x, y] of ring) {
    if (x < minx) minx = x; if (x > maxx) maxx = x;
    if (y < miny) miny = y; if (y > maxy) maxy = y;
  }
  return [minx, miny, maxx, maxy];
}

// ── header copy — verbatim from TerritoriesPage.jsx ──
function Subhead({ role, myZip, zipCount }) {
  if (role === 'operator') {
    const n = zipCount ?? 0;
    return <>Watching all {n} ZIP{n === 1 ? '' : 's'} in real time. Click any to open the briefing.</>;
  }
  if (myZip) {
    return <>Your territory is {myZip}. Click below to open this week&rsquo;s playbook.</>;
  }
  return <>You have one territory. Pick the ZIP you want to work — it becomes yours exclusively.</>;
}

export default function TerritoriesV4() {
  const navigate = useNavigate();
  const mapEl = useRef(null);
  const mapRef = useRef(null);
  const tipRef = useRef(null);
  const markersRef = useRef([]);
  const [data, setData] = useState(null);       // territory-status payload
  const [polys, setPolys] = useState(null);     // {zip: geometry}
  const [avg, setAvg] = useState({});           // {zip: avg_value}
  const [err, setErr] = useState(null);
  const [activeMarket, setActiveMarket] = useState(null);
  const [railOpen, setRailOpen] = useState(false);
  const [diving, setDiving] = useState(false);
  // claim state — same shape/flow as the live page
  const [claimModal, setClaimModal] = useState(null);
  const [claiming, setClaiming] = useState(false);
  const [claimError, setClaimError] = useState(null);

  // ── load: live status + boundaries + values ──
  useEffect(() => {
    let dead = false;
    Promise.all([
      territory.status(),
      fetch('/api/zip-polygons').then((r) => r.json()),
      fetch('/api/coverage/avg-values').then((r) => (r.ok ? r.json() : { avg_by_zip: {} })).catch(() => ({ avg_by_zip: {} })),
    ]).then(([status, fc, av]) => {
      if (dead) return;
      const p = {};
      for (const f of fc.features || []) p[f.properties.zip] = f.geometry;
      setData(status);
      setPolys(p);
      setAvg(av.avg_by_zip || {});
    }).catch((e) => { if (!dead) setErr(e?.message || 'Could not load territories.'); });
    return () => { dead = true; };
  }, []);

  const zips = data?.zips || [];
  const role = data?.role;
  const myZip = data?.my_zip;
  const byZip = {};
  zips.forEach((z) => { byZip[z.zip_code] = z; });

  const markets = [];
  const seen = new Set();
  for (const z of zips) {
    const mk = z.market_key || 'OTHER';
    if (!seen.has(mk)) { seen.add(mk); markets.push(mk); }
  }

  const marketBounds = useCallback((mk) => {
    let b = null;
    for (const z of zips) {
      if ((z.market_key || 'OTHER') !== mk) continue;
      const g = polys?.[z.zip_code];
      if (!g) continue;
      const bb = geomBounds(g);
      b = b ? [Math.min(b[0], bb[0]), Math.min(b[1], bb[1]), Math.max(b[2], bb[2]), Math.max(b[3], bb[3])] : bb;
    }
    return b;
  }, [zips, polys]);

  // routes a territory interaction the way the live ZipCard does
  const openZip = useCallback((z) => {
    if (!z) return;
    const navigable = role === 'operator' || z.status === 'mine';
    if (navigable) { navigate(`/zip/${z.zip_code}`); return; }
    if (z.status !== 'available' || myZip) return; // claimed / already-holding: not navigable
    dive(z); // eslint-disable-line no-use-before-define
  }, [role, myZip, navigate]); // dive is stable per mount

  // ── the dive: camera drop + satellite develop + gold draw → ClaimModal ──
  const dive = useCallback((z) => {
    const map = mapRef.current, g = polys?.[z.zip_code];
    if (!map || !g) { setClaimModal(z); return; }
    setDiving(true);
    setRailOpen(false);
    const bb = geomBounds(g);
    map.fitBounds([[bb[0], bb[1]], [bb[2], bb[3]]], {
      padding: { top: 110, bottom: 80, left: 40, right: 40 }, pitch: 42, duration: 2200, essential: true,
    });
    try {
      map.getSource('dive').setData({ type: 'Feature', geometry: g });
      map.setPaintProperty('dive-line', 'line-gradient',
        ['step', ['line-progress'], '#E9CD8F', 0.001, 'rgba(0,0,0,0)']);
      map.setPaintProperty('dive-glow', 'line-opacity', 0);
    } catch (e) { /* draw is decoration; claim still proceeds */ }
    map.once('moveend', () => {
      try { map.setPaintProperty('dive-glow', 'line-opacity', 0.35); } catch (e) {}
      const t0 = performance.now(), dur = 1800;
      const step = (t) => {
        const p = Math.min(1, (t - t0) / dur), ez = 1 - Math.pow(1 - p, 3);
        try {
          map.setPaintProperty('dive-line', 'line-gradient',
            ['step', ['line-progress'], '#E9CD8F', Math.max(ez, 0.001), 'rgba(0,0,0,0)']);
        } catch (e) { return; }
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
      setTimeout(() => setClaimModal(z), 900);
    });
  }, [polys]);

  function closeClaim() {
    setClaimModal(null); setClaimError(null); setDiving(false);
    const map = mapRef.current;
    try {
      map.getSource('dive').setData({ type: 'FeatureCollection', features: [] });
      map.setPaintProperty('dive-glow', 'line-opacity', 0);
    } catch (e) {}
  }

  // ── same Stripe Checkout flow as TerritoriesPage.confirmClaim ──
  async function confirmClaim() {
    if (!claimModal) return;
    setClaiming(true);
    setClaimError(null);
    try {
      const { checkout_url } = await billing.createCheckout(claimModal.zip_code);
      if (!checkout_url) throw new Error('No checkout URL returned from server');
      window.location.href = checkout_url;
    } catch (e) {
      setClaimError(e?.message || 'Could not start checkout. Try again?');
      setClaiming(false);
    }
  }

  // ── the map ──
  useEffect(() => {
    if (!mapEl.current || !polys || !zips.length || mapRef.current) return;
    const firstMarket = markets[0];
    const bb = marketBounds(firstMarket) || [-122.45, 47.3, -121.9, 47.8];
    setActiveMarket(firstMarket);

    const map = new maplibregl.Map({
      container: mapEl.current,
      style: 'https://tiles.openfreemap.org/styles/positron',
      bounds: [[bb[0] - 0.05, bb[1] - 0.03], [bb[2] + 0.05, bb[3] + 0.03]],
      attributionControl: { compact: true },
    });
    mapRef.current = map;

    map.on('load', () => {
      // warm dusk restyle
      for (const l of map.getStyle().layers) {
        try {
          const id = l.id.toLowerCase();
          if (l.type === 'background') map.setPaintProperty(l.id, 'background-color', '#14110C');
          else if (l.type === 'fill') map.setPaintProperty(l.id, 'fill-color', id.includes('water') ? '#16232B' : '#191510');
          else if (l.type === 'line') map.setPaintProperty(l.id, 'line-color', /motorway|trunk|primary|secondary/.test(id) ? '#4A4234' : '#2A2419');
          else if (l.type === 'symbol') {
            if (/place|city|town/.test(id)) {
              map.setPaintProperty(l.id, 'text-color', '#9A8F7A');
              map.setPaintProperty(l.id, 'text-halo-color', '#0D0B07');
            } else map.setLayoutProperty(l.id, 'visibility', 'none');
          }
        } catch (e) {}
      }
      // satellite develops on the dive
      map.addSource('sat', {
        type: 'raster',
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
        tileSize: 256, attribution: 'Imagery © Esri',
      });
      map.addLayer({
        id: 'sat', type: 'raster', source: 'sat',
        paint: { 'raster-opacity': ['interpolate', ['linear'], ['zoom'], 11.2, 0, 12.8, 0.88], 'raster-saturation': -0.12, 'raster-contrast': 0.06 },
      });
      // the board
      const feats = zips.filter((z) => polys[z.zip_code]).map((z, i) => ({
        type: 'Feature', id: i, geometry: polys[z.zip_code],
        properties: { zip: z.zip_code, status: z.status },
      }));
      map.addSource('terr', { type: 'geojson', data: { type: 'FeatureCollection', features: feats } });
      map.addLayer({
        id: 't-fill', type: 'fill', source: 'terr',
        paint: {
          'fill-color': ['match', ['get', 'status'], 'claimed_by_other', '#0B0906', 'mine', '#E9CD8F', '#C6A15B'],
          'fill-opacity': ['case', ['boolean', ['feature-state', 'hover'], false],
            ['match', ['get', 'status'], 'claimed_by_other', 0.82, 'mine', 0.3, 0.22],
            ['match', ['get', 'status'], 'claimed_by_other', 0.78, 'mine', 0.18, 0.07]],
        },
      });
      map.addLayer({
        id: 't-line', type: 'line', source: 'terr',
        paint: {
          'line-color': ['match', ['get', 'status'], 'claimed_by_other', '#3A3226', 'mine', '#E9CD8F', '#C6A15B'],
          'line-width': ['match', ['get', 'status'], 'claimed_by_other', 1, 'mine', 2, 1.4],
          'line-opacity': 0.9,
        },
      });
      map.addSource('dive', { type: 'geojson', lineMetrics: true, data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({ id: 'dive-glow', type: 'line', source: 'dive', paint: { 'line-color': '#C6A15B', 'line-width': 9, 'line-opacity': 0, 'line-blur': 6 } });
      map.addLayer({
        id: 'dive-line', type: 'line', source: 'dive',
        paint: { 'line-width': 2.4, 'line-gradient': ['step', ['line-progress'], '#E9CD8F', 0.001, 'rgba(0,0,0,0)'] },
      });
      // seals: TAKEN for held, YOURS for the agent's own
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      zips.forEach((z) => {
        const g = polys[z.zip_code];
        if (!g) return;
        if (z.status === 'claimed_by_other' || z.status === 'mine') {
          const b = geomBounds(g);
          const el = document.createElement('div');
          el.className = 'seal' + (z.status === 'mine' ? ' mine' : '');
          el.textContent = z.status === 'mine' ? 'YOURS' : 'TAKEN';
          if (z.status === 'mine') {
            el.style.cursor = 'pointer';
            el.addEventListener('click', () => navigate(`/zip/${z.zip_code}`));
          }
          const mk = new maplibregl.Marker({ element: el })
            .setLngLat([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]).addTo(map);
          markersRef.current.push(mk);
        }
      });
      // hover
      let hov = null;
      map.on('mousemove', 't-fill', (e) => {
        const f = e.features[0]; if (!f) return;
        const z = byZip[f.properties.zip]; if (!z) return;
        const clickable = role === 'operator' || z.status === 'mine' || (z.status === 'available' && !myZip);
        map.getCanvas().style.cursor = clickable ? 'pointer' : 'default';
        if (hov !== null && hov !== f.id) map.setFeatureState({ source: 'terr', id: hov }, { hover: false });
        map.setFeatureState({ source: 'terr', id: f.id }, { hover: true }); hov = f.id;
        const tip = tipRef.current;
        if (tip) {
          const a = avg[z.zip_code];
          tip.style.display = 'block';
          tip.style.left = `${e.originalEvent.clientX + 16}px`;
          tip.style.top = `${e.originalEvent.clientY + 16}px`;
          tip.innerHTML =
            `${z.city || ''}, ${z.state || ''} · ${z.zip_code}<br><span class="t2">` +
            `${(z.parcel_count || 0).toLocaleString()} PARCELS · ${z.contact_now_total || 0} ON CONTACT NOW` +
            `${a ? ' · ' + fmtVal(a) + ' AVG' : ''}` +
            `${z.status === 'claimed_by_other' ? ' · TAKEN' : z.status === 'mine' ? ' · YOURS' : ''}</span>`;
        }
      });
      map.on('mouseleave', 't-fill', () => {
        map.getCanvas().style.cursor = '';
        if (tipRef.current) tipRef.current.style.display = 'none';
        if (hov !== null) { map.setFeatureState({ source: 'terr', id: hov }, { hover: false }); hov = null; }
      });
      map.on('click', 't-fill', (e) => {
        const f = e.features[0];
        if (f) openZip(byZip[f.properties.zip]);
      });
    });

    return () => {
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [polys, data]);

  function flyMarket(mk) {
    setActiveMarket(mk);
    closeClaim();
    const b = marketBounds(mk);
    if (b && mapRef.current) {
      mapRef.current.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 70, pitch: 0, duration: 1500 });
    }
  }

  // ── ZipCard content — verbatim strings from the live page ──
  function ctaLabel(z) {
    if (role === 'operator' || z.status === 'mine') return 'Open briefing →';
    if (z.status === 'available' && !myZip) return 'Claim this ZIP →';
    if (z.status === 'available') return 'Available';
    return 'Claimed';
  }
  function badge(z) {
    if (z.status === 'mine') return <span className="badge mine">YOURS</span>;
    if (z.status === 'claimed_by_other') {
      return <span className="badge taken">CLAIMED{role === 'operator' && z.claimed_by_name ? ` · ${z.claimed_by_name.toUpperCase()}` : ''}</span>;
    }
    return <span className="badge avail">AVAILABLE</span>;
  }

  if (err) {
    return (
      <div className="tv4">
        <div className="rail open"><div className="rail-head" style={{ paddingTop: 24 }}>
          <div className="eyebrow">Your territory</div>
          <div className="h1">Territories</div>
          <div className="sub">{err}</div>
        </div></div>
      </div>
    );
  }

  return (
    <div className="tv4">
      <div className="tv4-map" ref={mapEl} />
      <div className="tip" ref={tipRef} />

      <div className="chips">
        {markets.map((mk) => (
          <button key={mk} className={`chip ${mk === activeMarket ? 'on' : ''}`} onClick={() => flyMarket(mk)}>
            {marketLabel(mk)}<span className="n">{zips.filter((z) => (z.market_key || 'OTHER') === mk).length}</span>
          </button>
        ))}
      </div>

      {diving && <button className="tv4-back" onClick={closeClaim}>← Back to the atlas</button>}

      <div className={`rail ${railOpen ? 'open' : ''}`}>
        <div className="rail-grab" onClick={() => setRailOpen((o) => !o)} />
        <div className="rail-head">
          <div className="eyebrow">{role === 'operator' ? 'Operator dashboard' : 'Your territory'}</div>
          <div className="h1">
            {role === 'operator' ? 'All territories' : myZip ? 'Live briefings' : 'Choose your territory'}
          </div>
          <div className="sub"><Subhead role={role} myZip={myZip} zipCount={zips.length} /></div>
        </div>
        <div className="cards">
          {!data && <div className="mhead">LOADING TERRITORIES…</div>}
          {markets.map((mk) => (
            <div key={mk}>
              <div className="mhead">{marketLabel(mk)} · {zips.filter((z) => (z.market_key || 'OTHER') === mk).length}</div>
              {zips.filter((z) => (z.market_key || 'OTHER') === mk).map((z) => {
                const navigable = role === 'operator' || z.status === 'mine';
                const claimable = z.status === 'available' && !myZip && role !== 'operator';
                const dead = !navigable && !claimable;
                const a = avg[z.zip_code];
                return (
                  <div key={z.zip_code} className={`card ${dead ? 'dead' : ''}`}
                    onClick={() => openZip(z)}>
                    <div className="r1">
                      <span className="nm">{z.city}, {z.state} · {z.zip_code}</span>
                      {badge(z)}
                    </div>
                    <div className="r2">
                      {(z.parcel_count || 0).toLocaleString()} parcels · {z.contact_now_total || 0} on this week's CONTACT NOW{a ? ` · ${fmtVal(a)} avg home` : ''}
                    </div>
                    <div className="cta">{ctaLabel(z)}</div>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {claimModal && (
        <ClaimModal
          zip={claimModal}
          claiming={claiming}
          error={claimError}
          onConfirm={confirmClaim}
          onCancel={closeClaim}
        />
      )}
    </div>
  );
}
