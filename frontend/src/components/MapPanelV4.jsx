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

  const feats = useMemo(() => {
    const out = [];
    (mapData?.parcels || []).forEach((p, i) => {
      if (p.lat == null || p.lng == null) return;
      out.push({
        i,
        pin: p.pin,                                // untouched identity
        key: String(p.pin).replace(/\D/g, ''),     // digit key for lot matching
        lat: p.lat, lng: p.lng,
        cat: catByPin.get(p.pin) || 'none',
        fam: p.signal_family || null,
      });
    });
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
  function resolveClick(lng, lat) {
    const hit = pipFind(lng, lat);
    if (hit != null) return hit;
    let best = null, bd = 1e9;
    for (const f of featsRef.current) {
      const dx = (f.lng - lng) * 76500, dy = (f.lat - lat) * 111000;
      const dd = dx * dx + dy * dy;
      if (dd < bd) { bd = dd; best = f.pin; }
    }
    return bd < 45 * 45 ? best : null;
  }

  useEffect(() => {
    if (!el.current || !feats.length || mapRef.current) return;
    const lats = feats.map((f) => f.lat), lngs = feats.map((f) => f.lng);
    const map = new maplibregl.Map({
      container: el.current,
      style: 'https://tiles.openfreemap.org/styles/positron',
      bounds: [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
      fitBoundsOptions: { padding: 40 },
      pitch: 50, maxPitch: 72,
      attributionControl: { compact: true },
    });
    mapRef.current = map;

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
            properties: { idx: f.i, cat: f.cat, fam: f.fam },
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
            12, ['match', ['get', 'cat'], 'none', 1.4, 'hold', 2.2, 'build_now', 2.8, 3.6],
            16, ['match', ['get', 'cat'], 'none', 3.5, 'hold', 5, 'build_now', 6, 8]],
          'circle-opacity': ['match', ['get', 'cat'], 'none', 0.5, 'hold', 0.85, 1],
          'circle-stroke-width': ['case', ['boolean', ['feature-state', 'sel'], false], 2.4, 0],
          'circle-stroke-color': GOLD,
        },
      });
      map.on('click', 'p-dots', (e) => {
        const f = e.features[0];
        if (f && onPickPin) {
          const feat = featsRef.current[f.properties.idx];
          if (feat) onPickPin(feat.pin);
        }
      });
      map.on('mouseenter', 'p-dots', () => { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', 'p-dots', () => { map.getCanvas().style.cursor = ''; });

      // lot fabric — Earth's click resolution + faint drape
      mapApi.lotPolygons(zip).then((d) => {
        const lots = d?.polygons || {};
        lotIndexRef.current = [];
        for (const f of featsRef.current) {
          const g = lots[f.key];
          if (!g) continue;
          lotIndexRef.current.push({ i: f.i, pin: f.pin, bbox: geomBounds(g), geom: g });
        }
        if (earthOnRef.current) refreshEarthLayers(); // eslint-disable-line no-use-before-define
      }).catch(() => {});

      // ── EARTH: the map, not a mode ──
      let deckMods = null;
      let earthKey = null;
      async function loadDeck() {
        if (deckMods) return deckMods;
        const [mb, geo, lyr, ext] = await Promise.all([
          import('@deck.gl/mapbox'),
          import('@deck.gl/geo-layers'),
          import('@deck.gl/layers'),
          import('@deck.gl/extensions').catch(() => null),
        ]);
        deckMods = {
          MapboxOverlay: mb.MapboxOverlay,
          Tile3DLayer: geo.Tile3DLayer,
          GeoJsonLayer: lyr.GeoJsonLayer,
          TerrainExtension: ext ? (ext._TerrainExtension || ext.TerrainExtension) : null,
        };
        return deckMods;
      }
      function earthLayers(key) {
        const { Tile3DLayer, GeoJsonLayer, TerrainExtension } = deckMods;
        const firstSymbol = (map.getStyle().layers.find((l) => l.type === 'symbol') || {}).id;
        const layers = [
          new Tile3DLayer({
            id: 'g3d',
            data: `https://tile.googleapis.com/v1/3dtiles/root.json?key=${encodeURIComponent(key)}`,
            operation: 'terrain+draw', beforeId: firstSymbol,
            loadOptions: { '3d-tiles': { maximumScreenSpaceError: 24 } },
            onTileError: () => {},
          }),
        ];
        if (TerrainExtension && lotIndexRef.current.length) {
          layers.push(new GeoJsonLayer({
            id: 'lots3d',
            data: { type: 'FeatureCollection', features: lotIndexRef.current.map((l) => ({ type: 'Feature', geometry: l.geom })) },
            stroked: true, filled: false, getLineColor: [198, 161, 91, 70],
            getLineWidth: 1, lineWidthUnits: 'pixels', beforeId: firstSymbol,
            extensions: [new TerrainExtension()],
          }));
        }
        return layers;
      }
      function selLayer() {
        const { GeoJsonLayer, TerrainExtension } = deckMods || {};
        if (!GeoJsonLayer) return null;
        const hit = lotIndexRef.current.find((l) => String(l.pin) === String(selPinRef.current));
        if (!hit) return null;
        return new GeoJsonLayer({
          id: 'sel3d', data: { type: 'Feature', geometry: hit.geom },
          stroked: true, filled: false, getLineColor: [233, 205, 143, 255],
          getLineWidth: 3, lineWidthUnits: 'pixels',
          extensions: TerrainExtension ? [new TerrainExtension()] : [],
        });
      }
      function refreshEarthLayers() {
        if (overlayRef.current && earthKey) {
          const base = earthLayers(earthKey);
          const sel = selLayer();
          try { overlayRef.current.setProps({ layers: sel ? [...base, sel] : base }); } catch (e) {}
        }
      }
      earthRefreshRef.current = refreshEarthLayers;
      try {
        const cfg = await mapApi.earthConfig();      // 403/404 → catch → satellite
        if (!cfg?.key) throw new Error('earth not configured');
        await loadDeck();
        earthKey = cfg.key;
        overlayRef.current = new deckMods.MapboxOverlay({
          interleaved: true,
          getCursor: () => 'crosshair',
          onClick: (info) => {
            if (!info.coordinate || !onPickPin) return;
            const pin = resolveClick(info.coordinate[0], info.coordinate[1]);
            if (pin != null) onPickPin(pin);
          },
          layers: earthLayers(earthKey),
        });
        map.addControl(overlayRef.current);
        earthOnRef.current = true;
        // clicks anywhere on the mesh — maplibre still owns events in
        // interleaved mode, so this fires even when no deck layer picks
        map.on('click', (e) => {
          if (!earthOnRef.current || !onPickPin) return;
          const pin = resolveClick(e.lngLat.lng, e.lngLat.lat);
          if (pin != null) onPickPin(pin);
        });
        map.getCanvas().style.cursor = 'crosshair';
        // ground yields to the mesh; labels re-lit; leads stay on top
        for (const l of map.getStyle().layers) {
          try {
            if (l.type === 'symbol') {
              map.setPaintProperty(l.id, 'text-color', '#FFFFFF');
              map.setPaintProperty(l.id, 'text-halo-color', 'rgba(0,0,0,0.95)');
              map.setPaintProperty(l.id, 'text-halo-width', 2.2);
            } else if (l.id !== 'p-dots' && ['fill', 'line', 'background'].includes(l.type)) {
              map.setLayoutProperty(l.id, 'visibility', 'none');
            }
          } catch (e) {}
        }
        try {
          map.setPaintProperty('p-dots', 'circle-opacity',
            ['match', ['get', 'cat'], 'call_now', 1, 'build_now', 0.85, 'hold', 0.6, 0]);
          map.setPaintProperty('p-dots', 'circle-stroke-width',
            ['case', ['boolean', ['feature-state', 'sel'], false], 2.4,
              ['match', ['get', 'cat'], 'call_now', 1, 0]]);
          map.setPaintProperty('p-dots', 'circle-stroke-color',
            ['case', ['boolean', ['feature-state', 'sel'], false], GOLD, 'rgba(13,11,7,0.9)']);
        } catch (e) {}
        if (creditRef.current) creditRef.current.style.display = 'block';
        map.easeTo({ pitch: 58, duration: 1200 });
      } catch (e) {
        console.error('[MapPanelV4] Earth unavailable — satellite fallback:', e);
        map.addSource('sat', {
          type: 'raster',
          tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
          tileSize: 256, attribution: 'Imagery © Esri',
        });
        map.addLayer({
          id: 'sat', type: 'raster', source: 'sat',
          paint: { 'raster-opacity': 0.92, 'raster-saturation': -0.12, 'raster-contrast': 0.06 },
        }, 'p-dots');
        map.addSource('sel-lot', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addLayer({ id: 'sel-lot', type: 'line', source: 'sel-lot',
          paint: { 'line-color': GOLD, 'line-width': 2.6 } });
      }
    });

    return () => {
      if (overlayRef.current) { try { map.removeControl(overlayRef.current); } catch (e) {} overlayRef.current = null; }
      earthOnRef.current = false;
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
    if (earthOnRef.current && earthRefreshRef.current) {
      earthRefreshRef.current();
    } else {
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
