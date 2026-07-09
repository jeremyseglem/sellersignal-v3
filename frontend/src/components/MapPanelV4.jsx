import { useEffect, useRef, useState, useMemo } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { mapApi } from '../api/client.js';

/*
 * MapPanelV4 (MIGRATION_V4.md Phase 4) — same contract as MapPanel.jsx:
 *   ({ mapData, playbook, selectedPin, onPickPin })
 * The Leaflet panel remains untouched in-tree; BriefingPage chooses.
 *
 * Three altitudes:
 *   ATLAS     — warm-dusk vector, parcel fabric (real lot polygons via
 *               /api/map/{zip}/lot-polygons, centroid dots as fallback)
 *   SATELLITE — treated Esri imagery develops as you descend
 *   EARTH     — Google photorealistic 3D tiles; appears ONLY if
 *               /api/map/earth-config authorizes (territory owners);
 *               deck.gl loads on first tap (dynamic import).
 *
 * Family color semantics preserved from the V3 panel, luminance-tuned
 * for ink. Selection = gold. Clicks route through onPickPin exactly as
 * the Leaflet panel does — in Earth mode via point-in-polygon over the
 * lot fabric (draped layers aren't pickable).
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
  const readyRef = useRef(false);
  const overlayRef = useRef(null);
  const lotIndexRef = useRef([]);
  const [alt, setAlt] = useState('atlas');
  const [earthKey, setEarthKey] = useState(null); // null=unknown, ''=unavailable
  const [lots, setLots] = useState(null);

  const zip = mapData?.zip_code || mapData?.zip || (mapData?.parcels?.[0]?.zip_code);

  // category per pin from the playbook — same derivation as MapPanel.jsx
  const catByPin = useMemo(() => {
    const m = new Map();
    for (const l of playbook?.call_now || []) m.set(l.pin, 'call_now');
    for (const l of playbook?.build_now || []) if (!m.has(l.pin)) m.set(l.pin, 'build_now');
    for (const l of playbook?.strategic_holds || []) if (!m.has(l.pin)) m.set(l.pin, 'hold');
    return m;
  }, [playbook]);

  const feats = useMemo(() => {
    const out = [];
    (mapData?.parcels || []).forEach((p, i) => {
      if (p.lat == null || p.lng == null) return;
      out.push({
        i, pin: String(p.pin), lat: p.lat, lng: p.lng,
        cat: catByPin.get(p.pin) || 'none',
        fam: p.signal_family || null,
      });
    });
    return out;
  }, [mapData, catByPin]);

  // ── earth availability (velvet rope): server decides ──
  useEffect(() => {
    let dead = false;
    mapApi.earthConfig()
      .then((d) => { if (!dead) setEarthKey(d?.key || ''); })
      .catch(() => { if (!dead) setEarthKey(''); });
    return () => { dead = true; };
  }, []);

  // ── lot polygons (dots fallback if empty) ──
  useEffect(() => {
    if (!zip) return;
    let dead = false;
    setLots(null);
    mapApi.lotPolygons(zip)
      .then((d) => { if (!dead) setLots(d?.polygons || {}); })
      .catch(() => { if (!dead) setLots({}); });
    return () => { dead = true; };
  }, [zip]);

  const colorExpr = useMemo(() => {
    const expr = ['match', ['get', 'fam']];
    Object.entries(FAMILY_COLORS).forEach(([k, v]) => expr.push(k, v));
    expr.push(FAMILY_DEFAULT);
    return expr;
  }, []);

  // ── map lifecycle ──
  useEffect(() => {
    if (!el.current || !feats.length || mapRef.current) return;
    const lats = feats.map((f) => f.lat), lngs = feats.map((f) => f.lng);
    const map = new maplibregl.Map({
      container: el.current,
      style: 'https://tiles.openfreemap.org/styles/positron',
      bounds: [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
      fitBoundsOptions: { padding: 40 },
      pitch: 45, maxPitch: 70,
      attributionControl: { compact: true },
    });
    mapRef.current = map;

    map.on('load', () => {
      for (const l of map.getStyle().layers) {
        try {
          const id = l.id.toLowerCase();
          if (l.type === 'background') map.setPaintProperty(l.id, 'background-color', '#14110C');
          else if (l.type === 'fill') map.setPaintProperty(l.id, 'fill-color', id.includes('water') ? '#16232B' : '#191510');
          else if (l.type === 'line') map.setPaintProperty(l.id, 'line-color', /motorway|trunk|primary|secondary/.test(id) ? '#4A4234' : '#2A2419');
          else if (l.type === 'symbol') {
            if (/place|city|town|road|street|transportation|highway|waterway|water_name/.test(id)) {
              map.setPaintProperty(l.id, 'text-color', '#A89A80');
              map.setPaintProperty(l.id, 'text-halo-color', '#0D0B07');
              try { map.setPaintProperty(l.id, 'text-halo-width', 1.4); } catch (e) {}
            } else map.setLayoutProperty(l.id, 'visibility', 'none');
          }
        } catch (e) {}
      }
      map.addSource('sat', {
        type: 'raster',
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
        tileSize: 256, attribution: 'Imagery © Esri',
      });
      map.addLayer({
        id: 'sat', type: 'raster', source: 'sat', layout: { visibility: 'none' },
        paint: { 'raster-opacity': ['interpolate', ['linear'], ['zoom'], 13.8, 0, 15.2, 0.9], 'raster-saturation': -0.12, 'raster-contrast': 0.06 },
      });
      // centroid dots — always present; the fabric's fallback and Earth's index seed
      map.addSource('pts', {
        type: 'geojson',
        data: {
          type: 'FeatureCollection',
          features: feats.map((f) => ({
            type: 'Feature', id: f.i,
            geometry: { type: 'Point', coordinates: [f.lng, f.lat] },
            properties: { pin: f.pin, cat: f.cat, fam: f.fam },
          })),
        },
      });
      map.addLayer({
        id: 'p-dots', type: 'circle', source: 'pts',
        paint: {
          'circle-color': colorExpr,
          'circle-radius': ['interpolate', ['linear'], ['zoom'],
            12, ['match', ['get', 'cat'], 'none', 1.4, 'hold', 2.2, 'build_now', 2.8, 3.4],
            16, ['match', ['get', 'cat'], 'none', 3.5, 'hold', 5, 'build_now', 6, 7.5]],
          'circle-opacity': ['match', ['get', 'cat'], 'none', 0.45, 'hold', 0.8, 1, 1],
          'circle-stroke-width': ['case', ['boolean', ['feature-state', 'sel'], false], 2.4, 0],
          'circle-stroke-color': GOLD,
        },
      });
      map.on('click', 'p-dots', (e) => {
        const f = e.features[0];
        if (f && onPickPin) onPickPin(f.properties.pin);
      });
      map.on('mouseenter', 'p-dots', () => { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', 'p-dots', () => { map.getCanvas().style.cursor = ''; });
      readyRef.current = true;
      map.fire('ss:ready');
    });

    return () => {
      readyRef.current = false;
      if (overlayRef.current) { try { map.removeControl(overlayRef.current); } catch (e) {} overlayRef.current = null; }
      map.remove(); mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feats.length > 0]);

  // ── lot fabric arrives (or not — dots stand) ──
  useEffect(() => {
    const map = mapRef.current;
    if (!map || lots == null) return;
    const apply = () => {
      const lotFeats = [];
      lotIndexRef.current = [];
      for (const f of feats) {
        const g = lots[f.pin];
        if (!g) continue;
        lotFeats.push({ type: 'Feature', id: f.i, geometry: g, properties: { pin: f.pin, cat: f.cat, fam: f.fam } });
        lotIndexRef.current.push({ i: f.i, pin: f.pin, bbox: geomBounds(g), geom: g });
      }
      if (!lotFeats.length) return;
      if (map.getSource('lots')) {
        map.getSource('lots').setData({ type: 'FeatureCollection', features: lotFeats });
        return;
      }
      map.addSource('lots', { type: 'geojson', data: { type: 'FeatureCollection', features: lotFeats } });
      map.addLayer({
        id: 'lot-fill', type: 'fill', source: 'lots',
        paint: {
          'fill-color': colorExpr,
          'fill-opacity': ['case', ['boolean', ['feature-state', 'hover'], false],
            ['match', ['get', 'cat'], 'none', 0.3, 0.5],
            ['match', ['get', 'cat'], 'none', 0.1, 'hold', 0.22, 'build_now', 0.28, 0.36]],
        },
      }, 'p-dots');
      map.addLayer({
        id: 'lot-line', type: 'line', source: 'lots',
        paint: {
          'line-color': colorExpr,
          'line-width': ['match', ['get', 'cat'], 'none', 0.5, 'hold', 0.8, 1, 1.2],
          'line-opacity': 0.85,
        },
      }, 'p-dots');
      map.addLayer({
        id: 'lot-sel', type: 'line', source: 'lots',
        paint: {
          'line-color': GOLD, 'line-width': 2.6,
          'line-opacity': ['case', ['boolean', ['feature-state', 'sel'], false], 1, 0],
        },
      });
      let hov = null;
      map.on('mousemove', 'lot-fill', (e) => {
        map.getCanvas().style.cursor = 'pointer';
        const id = e.features[0]?.id;
        if (hov !== null && hov !== id) map.setFeatureState({ source: 'lots', id: hov }, { hover: false });
        if (id !== undefined) { map.setFeatureState({ source: 'lots', id }, { hover: true }); hov = id; }
      });
      map.on('mouseleave', 'lot-fill', () => {
        map.getCanvas().style.cursor = '';
        if (hov !== null) { map.setFeatureState({ source: 'lots', id: hov }, { hover: false }); hov = null; }
      });
      map.on('click', 'lot-fill', (e) => {
        const f = e.features[0];
        if (f && onPickPin) onPickPin(f.properties.pin);
      });
      // with the fabric present, quiet the redundant dots
      try { map.setPaintProperty('p-dots', 'circle-opacity', ['match', ['get', 'cat'], 'call_now', 1, 0]); } catch (e) {}
    };
    if (readyRef.current) apply(); else map.once('ss:ready', apply);
  }, [lots, feats, colorExpr, onPickPin]);

  // ── selection follows the briefing exactly as the Leaflet panel does ──
  const prevSel = useRef(null);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    const f = feats.find((x) => x.pin === String(selectedPin));
    const clear = (i) => {
      try { map.setFeatureState({ source: 'pts', id: i }, { sel: false }); } catch (e) {}
      try { map.setFeatureState({ source: 'lots', id: i }, { sel: false }); } catch (e) {}
    };
    if (prevSel.current != null) clear(prevSel.current);
    if (!f) { prevSel.current = null; return; }
    prevSel.current = f.i;
    try { map.setFeatureState({ source: 'pts', id: f.i }, { sel: true }); } catch (e) {}
    try { map.setFeatureState({ source: 'lots', id: f.i }, { sel: true }); } catch (e) {}
    map.flyTo({ center: [f.lng, f.lat], zoom: Math.max(map.getZoom(), 16), duration: 800 });
  }, [selectedPin, feats]);

  // ── altitudes ──
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

  async function earthOn() {
    const map = mapRef.current;
    if (!map || !earthKey) return;
    try {
      const deck = await import('deck.gl');
      const firstSymbol = (map.getStyle().layers.find((l) => l.type === 'symbol') || {}).id;
      if (overlayRef.current) map.removeControl(overlayRef.current);
      overlayRef.current = new deck.MapboxOverlay({
        interleaved: true,
        getCursor: () => 'crosshair',
        onClick: (info) => {
          if (!info.coordinate || !onPickPin) return;
          const hit = pipFind(info.coordinate[0], info.coordinate[1]);
          if (hit) { onPickPin(hit); return; }
          let best = null, bd = 1e9;
          for (const f of feats) {
            const dx = (f.lng - info.coordinate[0]) * 76500, dy = (f.lat - info.coordinate[1]) * 111000;
            const dd = dx * dx + dy * dy;
            if (dd < bd) { bd = dd; best = f.pin; }
          }
          if (best && bd < 45 * 45) onPickPin(best);
        },
        layers: [
          new deck.Tile3DLayer({
            id: 'g3d',
            data: `https://tile.googleapis.com/v1/3dtiles/root.json?key=${encodeURIComponent(earthKey)}`,
            operation: 'terrain+draw', beforeId: firstSymbol,
            loadOptions: { '3d-tiles': { maximumScreenSpaceError: 24 } },
          }),
          new deck.GeoJsonLayer({
            id: 'lots3d',
            data: { type: 'FeatureCollection', features: lotIndexRef.current.map((l) => ({ type: 'Feature', geometry: l.geom })) },
            stroked: true, filled: false, getLineColor: [198, 161, 91, 70],
            getLineWidth: 1, lineWidthUnits: 'pixels', beforeId: firstSymbol,
            extensions: [new deck._TerrainExtension()],
          }),
        ],
      });
      map.addControl(overlayRef.current);
      ['sat', 'lot-fill', 'lot-line', 'lot-sel', 'p-dots'].forEach((id) => {
        try { map.setLayoutProperty(id, 'visibility', 'none'); } catch (e) {}
      });
      for (const l of map.getStyle().layers) {
        if (l.type === 'symbol') {
          try {
            map.setPaintProperty(l.id, 'text-color', '#FFFFFF');
            map.setPaintProperty(l.id, 'text-halo-color', 'rgba(0,0,0,0.95)');
            map.setPaintProperty(l.id, 'text-halo-width', 2.2);
          } catch (e) {}
        }
      }
      map.easeTo({ zoom: Math.max(map.getZoom(), 16), pitch: 58, duration: 1600 });
    } catch (e) {
      earthOff();
    }
  }
  function earthOff() {
    const map = mapRef.current;
    if (!map) return;
    if (overlayRef.current) { try { map.removeControl(overlayRef.current); } catch (e) {} overlayRef.current = null; }
    ['lot-fill', 'lot-line', 'lot-sel', 'p-dots'].forEach((id) => {
      try { map.setLayoutProperty(id, 'visibility', 'visible'); } catch (e) {}
    });
    for (const l of map.getStyle().layers) {
      if (l.type === 'symbol') {
        try {
          map.setPaintProperty(l.id, 'text-color', '#A89A80');
          map.setPaintProperty(l.id, 'text-halo-color', '#0D0B07');
          map.setPaintProperty(l.id, 'text-halo-width', 1.4);
        } catch (e) {}
      }
    }
  }
  function switchAlt(a) {
    const map = mapRef.current;
    if (!map) return;
    setAlt(a);
    if (a === 'atlas') {
      earthOff();
      try { map.setLayoutProperty('sat', 'visibility', 'none'); } catch (e) {}
      map.easeTo({ pitch: 45, duration: 900 });
    }
    if (a === 'sat') {
      earthOff();
      try { map.setLayoutProperty('sat', 'visibility', 'visible'); } catch (e) {}
      map.easeTo({ zoom: Math.max(map.getZoom(), 15.6), pitch: 38, duration: 1200 });
    }
    if (a === 'earth') earthOn();
  }

  const pill = (key, label) => (
    <button key={key} onClick={() => switchAlt(key)}
      style={{
        background: 'rgba(13,11,7,0.82)', backdropFilter: 'blur(6px)',
        border: `1px solid ${alt === key ? 'var(--accent, #C6A15B)' : 'var(--border, #2A241A)'}`,
        color: alt === key ? 'var(--accent-hover, #E9CD8F)' : 'var(--text-tertiary, #7A7264)',
        fontFamily: 'var(--v4-font-mono, monospace)', fontSize: 10, letterSpacing: '0.12em',
        padding: '8px 12px', borderRadius: 2, cursor: 'pointer', textTransform: 'uppercase',
      }}>{label}</button>
  );

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', minHeight: 320, background: 'var(--bg-dark, #0D0B07)' }}>
      <div ref={el} style={{ position: 'absolute', inset: 0 }} />
      <div style={{ position: 'absolute', top: 12, right: 12, zIndex: 5, display: 'flex', gap: 6 }}>
        {pill('atlas', 'Atlas')}
        {pill('sat', 'Satellite')}
        {earthKey ? pill('earth', 'Earth') : null}
      </div>
      {alt === 'earth' && (
        <div style={{
          position: 'absolute', left: 12, bottom: 26, zIndex: 5, color: '#ddd',
          fontFamily: 'Inter, sans-serif', fontSize: 10, textShadow: '0 1px 3px rgba(0,0,0,.8)',
        }}>Map data © Google</div>
      )}
    </div>
  );
}
