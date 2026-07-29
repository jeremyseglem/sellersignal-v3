import { useEffect, useRef, useMemo } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { mapApi } from '../api/client.js';

/*
 * MapPanelV4 (MIGRATION_V4.md Phase 4) — same contract as MapPanel.jsx:
 *   ({ mapData, playbook, selectedPin, onPickPin })
 *
 * Per Jeremy 2026-07-09: the briefing map offers NO display choices.
 * Google photorealistic 3D ("Earth") IS the map. On mount we ask
 * /api/map/earth-config; when authorized the mesh loads immediately as
 * the base experience — street labels re-lit white above it, real lot
 * boundaries draped faintly, leads as glowing dots, and every click
 * resolved to a parcel by point-in-polygon over the legal lot fabric
 * (draped layers aren't pickable) with nearest-centroid fallback.
 *
 * If Earth isn't authorized/configured/loadable, the panel falls back
 * silently to treated satellite + parcel dots. No pills either way.
 *
 * deck.gl arrives via SCOPED dynamic imports (@deck.gl/mapbox etc.) —
 * the umbrella 'deck.gl' import produced no Vite chunk, which is why
 * Earth silently failed on 2026-07-09.
 *
 * Pins pass through UNTOUCHED (whatever type mapData carries) so
 * handlePickLead's identity checks always match.
 */

const FAMILY_COLORS = {
  investor_disposition: '#C6A15B',
  trust_aging: '#8FA97C',
  silent_transition: '#C4AE8A',
  dormant_absentee: '#7E97A6',
  family_event_cluster: '#C08A7A',
};
const FAMILY_DEFAULT = '#5D5545';
const GOLD = '#E9CD8F';

const geomBounds = (g) => {
  let minx = 1e9, miny = 1e9, maxx = -1e9, maxy = -1e9;
  const pp = g.type === 'MultiPolygon' ? g.coordinates : [g.coordinates];
  for (const poly of pp) for (const ring of poly) for (const [x, y] of ring) {
    if (x < minx) minx = x; if (x > maxx) maxx = x;
    if (y < miny) miny = y; if (y > maxy) maxy = y;
  }
  return [minx, miny, maxx, maxy];
};

export default function MapPanelV4({ mapData, playbook, selectedPin, onPickPin }) {
  const el = useRef(null);
  const mapRef = useRef(null);
  const overlayRef = useRef(null);
  const lotIndexRef = useRef([]);
  const featsRef = useRef([]);
  const earthOnRef = useRef(false);
  const earthRefreshRef = useRef(null);
  const selPinRef = useRef(null);
  const creditRef = useRef(null);

  const zip = mapData?.zip_code || mapData?.zip || mapData?.parcels?.[0]?.zip_code;

  const catByPin = useMemo(() => {
    const m = new Map();
    for (const l of playbook?.call_now || []) m.set(l.pin, 'call_now');
    for (const l of playbook?.build_now || []) if (!m.has(l.pin)) m.set(l.pin, 'build_now');
    for (const l of playbook?.strategic_holds || []) if (!m.has(l.pin)) m.set(l.pin, 'hold');
    return m;
  }, [playbook]);

  const CAT_RANK = { call_now: 3, build_now: 2, hold: 1, none: 0 };
  const feats = useMemo(() => {
    // Building-pin UX (2026-07-27): condo units (prop_type K) share their
    // complex's centroid — rendering each unit is pin confetti on one
    // rooftop. Group K parcels by KC Major (pin[:6]); one representative
    // pin per building carries a unit list + count. Category/family of
    // the building = its highest-ranked unit, so a building with one
    // call_now unit reads as call_now.
    const out = [];
    const bldg = new Map(); // major -> building feat
    (mapData?.parcels || []).forEach((p, i) => {
      if (p.lat == null || p.lng == null) return;
      const key = String(p.pin).replace(/\D/g, '');
      const cat = catByPin.get(p.pin) || 'none';
      const isCondo = String(p.prop_type || '').toUpperCase() === 'K';
      if (isCondo && key.length === 10) {
        const major = key.slice(0, 6);
        let b = bldg.get(major);
        if (!b) {
          b = {
            i, pin: p.pin, key, lat: p.lat, lng: p.lng,
            cat, fam: p.signal_family || null,
            units: [],
          };
          bldg.set(major, b);
          out.push(b);
        }
        b.units.push({ pin: p.pin, address: p.address || String(p.pin),
                       cat, fam: p.signal_family || null });
        if ((CAT_RANK[cat] || 0) > (CAT_RANK[b.cat] || 0)) {
          b.cat = cat; b.fam = p.signal_family || b.fam; b.pin = p.pin;
        }
        return;
      }
      out.push({
        i,
        pin: p.pin,                                // untouched identity
        key,                                       // digit key for lot matching
        lat: p.lat, lng: p.lng,
        cat, fam: p.signal_family || null,
      });
    });
    // re-index after grouping so feature ids stay dense + stable
    out.forEach((f, idx) => { f.i = idx; });
    return out;
  }, [mapData, catByPin]);
  featsRef.current = feats;

  function pipFind(x, y) {
    for (const l of lotIndexRef.current) {
      const [minx, miny, maxx, maxy] = l.bbox;
      if (x < minx || x > maxx || y < miny || y > maxy) continue;
      const pp = l.geom.type === 'MultiPolygon' ? l.geom.coordinates : [l.geom.coordinates];
      for (const poly of pp) {
        let inside = false; const ring = poly[0];
        for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
          const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
          if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) inside = !inside;
        }
        if (inside) return l.pin;
      }
    }
    return null;
  }
  const popupRef = useRef(null);
  function openUnitList(feat, lngLat) {
    try { if (popupRef.current) popupRef.current.remove(); } catch (e) {}
    const map = mapRef.current;
    if (!map) return;
    const wrap = document.createElement('div');
    wrap.style.cssText =
      'max-height:220px;overflow-y:auto;min-width:210px;' +
      'background:#14110C;border:1px solid #3A3226;border-radius:8px;' +
      'font-family:\'DM Sans\',sans-serif;';
    const head = document.createElement('div');
    head.textContent = `${feat.units.length} residences in this building`;
    head.style.cssText =
      'padding:8px 12px;color:#C6A15B;font-size:11px;letter-spacing:0.08em;' +
      'text-transform:uppercase;border-bottom:1px solid #2A2419;';
    wrap.appendChild(head);
    const rank = { call_now: 3, build_now: 2, hold: 1, none: 0 };
    const units = [...feat.units].sort((a, b) => (rank[b.cat] || 0) - (rank[a.cat] || 0));
    for (const u of units) {
      const row = document.createElement('div');
      row.style.cssText =
        'padding:7px 12px;color:#E8E0D0;font-size:12.5px;cursor:pointer;' +
        'display:flex;align-items:center;gap:8px;';
      const dot = document.createElement('span');
      dot.style.cssText =
        'width:7px;height:7px;border-radius:50%;flex:0 0 auto;' +
        `background:${u.cat === 'call_now' ? '#C6A15B' : u.cat === 'build_now' ? '#8A9A5B' : '#5A5346'};`;
      const label = document.createElement('span');
      label.textContent = u.address;
      row.appendChild(dot); row.appendChild(label);
      row.onmouseenter = () => { row.style.background = '#1E1912'; };
      row.onmouseleave = () => { row.style.background = 'transparent'; };
      row.onclick = () => {
        try { popupRef.current && popupRef.current.remove(); } catch (e) {}
        if (onPickPin) onPickPin(u.pin);
      };
      wrap.appendChild(row);
    }
    popupRef.current = new maplibregl.Popup({
      closeButton: true, closeOnClick: true, maxWidth: '300px',
      className: 'ss-unit-popup',
    }).setLngLat(lngLat).setDOMContent(wrap).addTo(map);
  }

  function routeClick(lng, lat) {
    const pin = resolveClick(lng, lat);
    if (pin == null) return;
    const feat = featsRef.current.find((f) => String(f.pin) === String(pin));
    if (feat && feat.units && feat.units.length > 1) {
      openUnitList(feat, { lng, lat });
      return;
    }
    if (onPickPin) onPickPin(pin);
  }

  function resolveClick(lng, lat) {
    const hit = pipFind(lng, lat);
    if (hit != null) return hit;
    let best = null, bd = 1e9;
    for (const f of featsRef.current) {
      const dx = (f.lng - lng) * 76500, dy = (f.lat - lat) * 111000;
      const dd = dx * dx + dy * dy;
      if (dd < bd) { bd = dd; best = f.pin; }
    }
    return bd < 120 * 120 ? best : null;
  }

  useEffect(() => {
    if (!el.current || !feats.length || mapRef.current) return;
    const lats = feats.map((f) => f.lat), lngs = feats.map((f) => f.lng);
    const map = new maplibregl.Map({
      container: el.current,
      style: 'https://tiles.openfreemap.org/styles/positron',
      bounds: [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
      fitBoundsOptions: { padding: 40 },
      pitch: 0, maxPitch: 0, dragRotate: false, pitchWithRotate: false,
      attributionControl: { compact: true },
    });
    mapRef.current = map;

    // Mobile: the map pane is display:none while the Leads tab is active,
    // so maplibre can initialize inside a 0×0 container. When the tab
    // switches to Map, resize the canvas and — if the map was born at
    // zero size — re-fit the ZIP bounds (the initial fit computed against
    // a zero-height viewport is meaningless).
    const bornHidden = !el.current.clientWidth || !el.current.clientHeight;
    let refitDone = !bornHidden;
    const ro = new ResizeObserver(() => {
      if (!el.current || !el.current.clientWidth || !el.current.clientHeight) return;
      map.resize();
      if (!refitDone) {
        refitDone = true;
        try {
          map.fitBounds(
            [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
            { padding: 40, duration: 0 },
          );
        } catch (e) {}
      }
    });
    ro.observe(el.current);

    map.on('load', async () => {
      for (const l of map.getStyle().layers) {
        try {
          const id = l.id.toLowerCase();
          if (l.type === 'background') map.setPaintProperty(l.id, 'background-color', '#14110C');
          else if (l.type === 'fill') {
            map.setPaintProperty(l.id, 'fill-color', id.includes('water') ? '#16232B' : '#191510');
            try { map.setPaintProperty(l.id, 'fill-outline-color', id.includes('water') ? '#1B2B34' : '#191510'); } catch (e) {}
          } else if (l.type === 'line') {
            map.setPaintProperty(l.id, 'line-color', /motorway|trunk|primary|secondary/.test(id) ? '#4A4234' : '#2A2419');
          } else if (l.type === 'symbol') {
            if (/place|city|town|road|street|transportation|highway|waterway|water_name/.test(id)) {
              map.setPaintProperty(l.id, 'text-color', '#A89A80');
              map.setPaintProperty(l.id, 'text-halo-color', '#0D0B07');
              try { map.setPaintProperty(l.id, 'text-halo-width', 1.4); } catch (e) {}
            } else map.setLayoutProperty(l.id, 'visibility', 'none');
          }
        } catch (e) {}
      }

      map.addSource('pts', {
        type: 'geojson',
        data: {
          type: 'FeatureCollection',
          features: feats.map((f) => ({
            type: 'Feature', id: f.i,
            geometry: { type: 'Point', coordinates: [f.lng, f.lat] },
            properties: { idx: f.i, cat: f.cat, fam: f.fam,
                          bcount: f.units ? f.units.length : 0 },
          })),
        },
      });
      const colorExpr = ['match', ['get', 'fam'],
        ...Object.entries(FAMILY_COLORS).flat(), FAMILY_DEFAULT];
      map.addLayer({
        id: 'p-dots', type: 'circle', source: 'pts',
        paint: {
          'circle-color': colorExpr,
          'circle-radius': ['interpolate', ['linear'], ['zoom'],
            12, ['match', ['get', 'cat'], 'none', 2, 'hold', 3, 'build_now', 4, 5],
            16, ['match', ['get', 'cat'], 'none', 4.5, 'hold', 6, 'build_now', 7.5, 9]],
          'circle-opacity': ['match', ['get', 'cat'], 'none', 0.75, 1],
          // Dark ring around every pin for contrast over bright imagery;
          // gold ring when selected.
          'circle-stroke-width': ['case', ['boolean', ['feature-state', 'sel'], false], 3, 1.4],
          'circle-stroke-color': ['case', ['boolean', ['feature-state', 'sel'], false], GOLD, 'rgba(10,8,5,0.9)'],
        },
      });
      map.addLayer({
        id: 'p-badges', type: 'symbol', source: 'pts',
        filter: ['>', ['get', 'bcount'], 1],
        layout: {
          'text-field': ['to-string', ['get', 'bcount']],
          'text-size': ['interpolate', ['linear'], ['zoom'], 12, 8, 16, 11],
          'text-offset': [0, -1.1],
          'text-allow-overlap': true,
        },
        paint: {
          'text-color': GOLD,
          'text-halo-color': 'rgba(13,11,7,0.95)',
          'text-halo-width': 1.4,
        },
      });
      map.on('click', 'p-dots', (e) => {
        const f = e.features[0];
        if (!f) return;
        const feat = featsRef.current[f.properties.idx];
        if (!feat) return;
        if (feat.units && feat.units.length > 1) {
          openUnitList(feat, e.lngLat);
          return;
        }
        if (onPickPin) onPickPin(feat.pin);
      });
      map.on('mouseenter', 'p-dots', () => { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', 'p-dots', () => { map.getCanvas().style.cursor = ''; });

      // Click anywhere on a property (not just the small pin dot) opens it:
      // resolve the click's lng/lat against the lot fabric (point-in-polygon),
      // falling back to nearest pin. Pure lng/lat on a flat map — always
      // accurate. The p-dots handler above still handles direct dot taps and
      // fires first; this catches taps on the parcel body.
      map.on('click', (e) => {
        // If a pin dot was directly hit, its handler already ran.
        const hits = map.queryRenderedFeatures(e.point, { layers: ['p-dots'] });
        if (hits && hits.length) return;
        const pin = resolveClick(e.lngLat.lng, e.lngLat.lat);
        if (pin == null) return;
        const feat = featsRef.current.find((x) => String(x.pin) === String(pin));
        if (feat && feat.units && feat.units.length > 1) {
          openUnitList(feat, e.lngLat);
        } else if (onPickPin) {
          onPickPin(pin);
        }
      });

      // lot fabric — Earth's click resolution + faint drape
      mapApi.lotPolygons(zip).then((d) => {
        const lots = d?.polygons || {};
        lotIndexRef.current = [];
        for (const f of featsRef.current) {
          // Buildings (grouped condo units) use the complex parcel's
          // footprint (Major+'0000') as their property lines.
          const g = (f.units && f.key.length === 10
                     ? lots[f.key.slice(0, 6) + '0000'] || lots[f.key]
                     : lots[f.key]);
          if (!g) continue;
          lotIndexRef.current.push({ i: f.i, pin: f.pin, bbox: geomBounds(g), geom: g });
        }
        if (earthRefreshRef.current) earthRefreshRef.current();
      }).catch(() => {});

      // ── SATELLITE BASEMAP (flat) ──
      // 3D Earth was removed 2026-07-29: mixing MapLibre's flat layers with
      // a deck.gl 3D terrain mesh caused persistent per-frame projection
      // drift (overlays sliding on pan/zoom) and broke picking (draped
      // layers lose the pick buffer). Flat satellite = same rich imagery,
      // one projection, everything clickable and locked.
      map.addSource('sat', {
        type: 'raster',
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
        tileSize: 256, maxzoom: 19, attribution: 'Imagery © Esri',
      });
      // Satellite sits under the pins but over the dark basemap.
      map.addLayer({
        id: 'sat', type: 'raster', source: 'sat',
        paint: { 'raster-opacity': 1, 'raster-saturation': -0.06, 'raster-contrast': 0.04 },
      }, 'p-dots');

      // Street + place names: the Esri satellite raster is imagery only (no
      // text), so overlay the transparent Reference layer (roads, highways,
      // place labels on a transparent background — built to sit over
      // imagery). Sits above satellite, below the pins.
      map.addSource('labels', {
        type: 'raster',
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}'],
        tileSize: 256, maxzoom: 19,
      });
      map.addLayer({
        id: 'labels', type: 'raster', source: 'labels',
        paint: { 'raster-opacity': 0.95 },
      }, 'p-dots');
      map.addSource('places', {
        type: 'raster',
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}'],
        tileSize: 256, maxzoom: 19,
      });
      map.addLayer({
        id: 'places', type: 'raster', source: 'places',
        paint: { 'raster-opacity': 0.9 },
      }, 'p-dots');

      // Property outlines were dropped 2026-07-29: every property already
      // has its own pin, so per-parcel outlines are redundant clutter over
      // satellite imagery. The lot fabric is still loaded (above) for
      // click-anywhere-on-parcel resolution and the selected-parcel
      // highlight — just not drawn as a persistent layer.
      map.addSource('sel-lot', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({
        id: 'sel-lot', type: 'line', source: 'sel-lot',
        paint: { 'line-color': GOLD, 'line-width': 3 },
      });
      // Selection highlight populate (was the outline populate).
      earthRefreshRef.current = () => {};
    });

    return () => {
      ro.disconnect();
      map.remove(); mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feats.length > 0, zip]);

  const prevSel = useRef(null);
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const f = feats.find((x) => String(x.pin) === String(selectedPin));
    if (prevSel.current != null) {
      try { map.setFeatureState({ source: 'pts', id: prevSel.current }, { sel: false }); } catch (e) {}
    }
    if (!f) { prevSel.current = null; return; }
    prevSel.current = f.i;
    try { map.setFeatureState({ source: 'pts', id: f.i }, { sel: true }); } catch (e) {}
    selPinRef.current = f.pin;
    if (earthRefreshRef.current) earthRefreshRef.current();
    {
      try {
        const hit = lotIndexRef.current.find((l) => String(l.pin) === String(f.pin));
        map.getSource('sel-lot')?.setData(hit
          ? { type: 'Feature', geometry: hit.geom }
          : { type: 'FeatureCollection', features: [] });
      } catch (e) {}
    }
    try { map.flyTo({ center: [f.lng, f.lat], zoom: Math.max(map.getZoom(), 16.2), duration: 800 }); } catch (e) {}
  }, [selectedPin, feats]);

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', minHeight: 320, background: 'var(--bg-dark, #0D0B07)' }}>
      <div ref={el} style={{ position: 'absolute', inset: 0 }} />
      <div ref={creditRef} style={{
        display: 'none', position: 'absolute', left: 12, bottom: 26, zIndex: 5, color: '#ddd',
        fontFamily: 'Inter, sans-serif', fontSize: 10, textShadow: '0 1px 3px rgba(0,0,0,.8)',
      }}>Map data © Google</div>
    </div>
  );
}
