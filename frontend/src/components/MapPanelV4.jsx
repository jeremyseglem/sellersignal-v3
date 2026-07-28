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
            12, ['match', ['get', 'cat'], 'none', 1.4, 'hold', 2.2, 'build_now', 2.8, 3.6],
            16, ['match', ['get', 'cat'], 'none', 3.5, 'hold', 5, 'build_now', 6, 8]],
          'circle-opacity': ['match', ['get', 'cat'], 'none', 0.5, 'hold', 0.85, 1],
          'circle-stroke-width': ['case', ['boolean', ['feature-state', 'sel'], false], 2.4, 0],
          'circle-stroke-color': GOLD,
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
        // Kick the deck.gl chunk downloads off IN PARALLEL with the
        // earth-config round trip instead of after it — these are ~600KB
        // of dynamic imports and there's no reason they should wait on a
        // config fetch that doesn't feed them.
        const deckReady = loadDeck();
        const cfg = await mapApi.earthConfig();      // 403/404 → catch → satellite
        if (!cfg?.key) { deckReady.catch(() => {}); throw new Error('earth not configured'); }
        await deckReady;
        earthKey = cfg.key;
        overlayRef.current = new deckMods.MapboxOverlay({
          interleaved: true,
          getCursor: () => 'crosshair',
          onClick: (info) => {
            if (!info.coordinate) return;
            routeClick(info.coordinate[0], info.coordinate[1]);
          },
          layers: earthLayers(earthKey),
        });
        map.addControl(overlayRef.current);
        earthOnRef.current = true;
        // clicks anywhere on the mesh — maplibre still owns events in
        // interleaved mode, so this fires even when no deck layer picks
        map.on('click', (e) => {
          if (!earthOnRef.current) return;
          routeClick(e.lngLat.lng, e.lngLat.lat);
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
      ro.disconnect();
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
