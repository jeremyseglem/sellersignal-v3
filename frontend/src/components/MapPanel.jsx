import { useEffect, useRef } from 'react';
import L from 'leaflet';

// ──────────────────────────────────────────────────────────────────
// Tiered visibility map.
//
// Three render layers, painted bottom-to-top so the eye sees the
// brightest, most actionable dots last:
//
//   Layer 1 — STRUCTURAL HEATMAP (background)
//     Every classified parcel that isn't a pick this week. Colored
//     by signal_family group, small radius (3px), low opacity. The
//     density of this layer is the territory's signal landscape —
//     the agent sees that an LLC pocket on 8th Ave is dense with
//     investor-disposition candidates without those competing for
//     attention against actual picks.
//
//   Layer 2 — STRATEGIC HOLDS (medium)
//     Parcels in this week's strategic_holds picks. Slightly larger
//     (6px), distinct color, half opacity. Visible but quiet.
//
//   Layer 3 — PICKS THIS WEEK (foreground)
//     CALL NOW (red, 9px) and BUILD NOW (gold, 8px) picks. Full
//     opacity, larger radius, the eye lands here first.
//
// Every dot is still clickable and selects the parcel. Picks just
// have visual priority.
// ──────────────────────────────────────────────────────────────────

// ── Layer 3 (foreground) styles ─────────────────────────────────
// Base sizes at zoom 14 (fitBounds default). Pins scale up dynamically
// at higher zooms via the zoom listener below — see scaleForZoom().
// At low zoom, pins start small (5-7px) so 65 Call Now dots in 98004
// don't smear into a single red blob. At street-level zoom (16+),
// pins grow to 9-11px so they're easy to click.
//
// Fill opacity is also reduced from the prior 0.95/0.90 — at high
// density, partial transparency lets overlapping dots reveal real
// territory shape rather than masking it.
const PICK_STYLES = {
  call_now: {
    color: '#9E4B3C',
    radius: 6,
    fillOpacity: 0.85,
    weight: 1.6,
  },
  build_now: {
    color: '#8B6914',
    radius: 5,
    fillOpacity: 0.78,
    weight: 1.4,
  },
  strategic_hold: {
    color: '#5A7247',
    radius: 4,
    fillOpacity: 0.5,
    weight: 1.2,
  },
};

// Zoom-responsive radius scaling.
// At zoom 14 (fit-bounds default): scale = 1.0 (use base radius)
// At zoom 16: scale ≈ 1.5 (street-level — pins grow)
// At zoom 18+: scale ≈ 2.0 (parcel-level — easy to click)
// At zoom 12 or below (zoom out beyond fit): scale ≈ 0.7 (shrinks
// further so a regional view doesn't smear).
function scaleForZoom(zoom) {
  if (zoom == null) return 1;
  if (zoom <= 12) return 0.7;
  if (zoom <= 14) return 1.0;
  if (zoom <= 16) return 1.0 + (zoom - 14) * 0.25;
  if (zoom <= 18) return 1.5 + (zoom - 16) * 0.25;
  return 2.0;
}

// ── Layer 1 (background) styles per signal-family group ─────────
// Map raw archetype names to family groups so distinct LLC-mature
// vs LLC-long-hold render the same gold-family color but different
// from trust-aging or silent-transition. Keeps the heatmap legible.
const ARCHETYPE_TO_FAMILY = {
  trust_young:            'trust_aging',
  trust_mature:           'trust_aging',
  trust_aging:            'trust_aging',
  llc_investor_early:     'investor_disposition',
  llc_investor_mature:    'investor_disposition',
  llc_long_hold:          'investor_disposition',
  individual_recent:      'silent_transition',
  individual_settled:     'silent_transition',
  individual_long_tenure: 'silent_transition',
  absentee_active:        'dormant_absentee',
  absentee_dormant:       'dormant_absentee',
  estate_heirs:           'family_event_cluster',
};

// Background dot color per family. Muted versions of the pick
// colors so the heatmap reads as the same palette without competing
// against the bright picks. Fill opacity is low (0.18-0.22) — these
// are atmospheric, not interactive-feeling.
const FAMILY_BG_COLORS = {
  investor_disposition:  '#C5A572', // muted gold
  trust_aging:           '#A8B8A0', // muted sage
  silent_transition:     '#B8A892', // muted sand
  dormant_absentee:      '#8FA3B0', // muted slate-blue
  family_event_cluster:  '#C49A8C', // muted terracotta
};

const FAMILY_BG_DEFAULT = '#D9CEBF'; // pale neutral

// Selection emphasis color
const SELECTION_RING_COLOR = '#2C2418';


export default function MapPanel({ mapData, playbook, selectedPin, onPickPin }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef({});

  // Build a pin -> section lookup from the playbook so each parcel
  // can be classified into its render layer in a single pass.
  // Recomputed each render but cheap (sub-millisecond) since the
  // playbook is already in memory and small (<500 picks per ZIP).
  const pickSections = (() => {
    const m = new Map();
    if (playbook) {
      for (const lead of playbook.call_now || [])         m.set(lead.pin, 'call_now');
      for (const lead of playbook.build_now || [])        m.set(lead.pin, 'build_now');
      for (const lead of playbook.strategic_holds || [])  m.set(lead.pin, 'strategic_hold');
    }
    return m;
  })();

  // Initialize Leaflet map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const bounds = mapData.bounds;
    const map = L.map(containerRef.current, {
      zoomControl: true,
      attributionControl: true,
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
      subdomains: 'abcd',
      maxZoom: 20,
    }).addTo(map);

    if (bounds) {
      // fitBounds without a maxZoom over-zooms-out on long-thin ZIPs
      // (e.g., 98004 stretches ~6 miles north-south along Lake
      // Washington but only ~1 mile east-west). Without a cap, Leaflet
      // chooses a zoom that fits the long axis, which crams dots
      // along the short axis. Cap at 14 — tested against 98004's
      // long-thin shape, this gives enough headroom that the action
      // pins don't smear into a single blob while still keeping the
      // full ZIP boundary visible.
      map.fitBounds([
        [bounds.min_lat, bounds.min_lng],
        [bounds.max_lat, bounds.max_lng],
      ], { padding: [40, 40], maxZoom: 14 });
    } else {
      map.setView([47.6101, -122.2015], 14);  // Default: Bellevue
    }

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      markersRef.current = {};
    };
  }, []);

  // Render parcels in three layers (background → holds → picks).
  // Painting order matters because Leaflet draws later markers on
  // top — picks must be added LAST so they sit visually above the
  // background heatmap.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapData?.parcels) return;

    // Clear old markers
    Object.values(markersRef.current).forEach((m) => map.removeLayer(m));
    markersRef.current = {};

    // Bucket parcels by render layer in one pass.
    const backgroundParcels = [];
    const holdParcels       = [];
    const buildNowParcels   = [];
    const callNowParcels    = [];

    for (const p of mapData.parcels) {
      if (!p.lat || !p.lng) continue;
      const section = pickSections.get(p.pin);
      if (section === 'call_now')             callNowParcels.push(p);
      else if (section === 'build_now')       buildNowParcels.push(p);
      else if (section === 'strategic_hold')  holdParcels.push(p);
      else                                    backgroundParcels.push(p);
    }

    const addMarker = (p, opts, layer) => {
      // Apply current zoom scale at creation. The zoom listener
      // (set up in a separate useEffect) keeps these in sync as
      // the user zooms. We store the base opts on the marker so
      // the listener can rescale without re-deriving them.
      const zoom = map.getZoom();
      const scale = scaleForZoom(zoom);
      const marker = L.circleMarker([p.lat, p.lng], {
        radius:       opts.radius * scale,
        color:        opts.color,
        fillColor:    opts.color,
        fillOpacity:  opts.fillOpacity,
        weight:       opts.weight,
        opacity:      opts.opacity ?? 1,
      });
      // Stash the base options so the zoom listener can rescale
      // without losing the marker's identity. Also stash the
      // semantic layer ('pick' | 'hold' | 'background') so the
      // dim-on-select treatment can target the right markers.
      marker._ssBaseOpts = opts;
      marker._ssLayer = layer;
      marker.on('click', () => onPickPin(p.pin));
      marker.on('mouseover', () => marker.setStyle({ weight: opts.weight + 1.5 }));
      marker.on('mouseout',  () => marker.setStyle({ weight: opts.weight }));
      marker.addTo(map);
      markersRef.current[p.pin] = marker;
    };

    // Layer 1: structural heatmap
    for (const p of backgroundParcels) {
      const family = ARCHETYPE_TO_FAMILY[p.signal_family] || null;
      const color  = (family && FAMILY_BG_COLORS[family]) || FAMILY_BG_DEFAULT;
      addMarker(p, {
        color,
        radius:      3,
        fillOpacity: 0.22,
        weight:      0.6,
        opacity:     0.5,
      }, 'background');
    }

    // Layer 2: strategic holds
    for (const p of holdParcels) {
      addMarker(p, PICK_STYLES.strategic_hold, 'hold');
    }

    // Layer 3: picks (build_now first, call_now on top — call_now
    // is the strongest signal so it should be the visually loudest).
    for (const p of buildNowParcels) {
      addMarker(p, PICK_STYLES.build_now, 'pick');
    }
    for (const p of callNowParcels) {
      addMarker(p, PICK_STYLES.call_now, 'pick');
    }
  }, [mapData, playbook, onPickPin]);

  // Zoom-responsive pin sizing. Listen for zoom changes and rescale
  // every marker's radius using its stashed base opts. Without this,
  // pins stay the same pixel size at every zoom level — which is
  // why 98004 looked like a sea slug at the fit-bounds default.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const handleZoom = () => {
      const scale = scaleForZoom(map.getZoom());
      for (const marker of Object.values(markersRef.current)) {
        const base = marker._ssBaseOpts;
        if (!base) continue;
        marker.setRadius(base.radius * scale);
      }
    };
    map.on('zoomend', handleZoom);
    return () => { map.off('zoomend', handleZoom); };
  }, []);

  // Dim non-selected pins when a lead is open. The selected pin
  // gets emphasized by the existing flyTo+setStyle effect below;
  // this effect handles everything else by reducing opacity on
  // background and non-selected pick markers, so the agent's eye
  // lands cleanly on the chosen lead.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const markers = markersRef.current;

    if (!selectedPin) {
      // Restore everything to base style
      for (const marker of Object.values(markers)) {
        const base = marker._ssBaseOpts;
        if (!base) continue;
        marker.setStyle({
          opacity:     base.opacity ?? 1,
          fillOpacity: base.fillOpacity,
        });
      }
      return;
    }

    // A pin is selected — dim everything else
    for (const [pin, marker] of Object.entries(markers)) {
      if (pin === selectedPin) continue;
      const base = marker._ssBaseOpts;
      if (!base) continue;
      const dimFactor = marker._ssLayer === 'background' ? 0.25 : 0.4;
      marker.setStyle({
        opacity:     (base.opacity ?? 1) * dimFactor,
        fillOpacity: base.fillOpacity * dimFactor,
      });
    }
  }, [selectedPin, mapData, playbook]);

  // Fly to selected pin and emphasize it. Pairs with the dim-others
  // effect above — the selected pin reads as the focal point because
  // (1) it's larger, (2) it has a thick selection ring, (3) everything
  // else is dimmed.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const markers = markersRef.current;

    // Restore prior selected pin to base style (zoom-scaled radius).
    // Tracked on the map ref so we can find it after selectedPin
    // has changed.
    const prev = map._ssLastSelected && markers[map._ssLastSelected];
    if (prev && prev._ssBaseOpts) {
      const base = prev._ssBaseOpts;
      const scale = scaleForZoom(map.getZoom());
      prev.setStyle({
        weight: base.weight,
        color: base.color,
        fillColor: base.color,
      });
      prev.setRadius(base.radius * scale);
    }
    map._ssLastSelected = selectedPin;

    if (!selectedPin) return;
    const marker = markers[selectedPin];
    if (!marker) return;

    const latlng = marker.getLatLng();
    map.flyTo(latlng, Math.max(map.getZoom(), 17), { duration: 0.8 });

    // Emphasize: thick selection ring, original fill color preserved
    // for identity, radius bumped above the zoom-scaled baseline.
    const base = marker._ssBaseOpts;
    const scale = scaleForZoom(map.getZoom());
    const baseRadius = base ? base.radius * scale : (marker.options.radius || 5);
    marker.setStyle({
      weight: 4,
      color: SELECTION_RING_COLOR,
    });
    marker.setRadius(baseRadius + 3);
    // Ensure selected pin is visually on top of everything
    if (marker.bringToFront) marker.bringToFront();
  }, [selectedPin]);

  return (
    <div style={{ position: 'absolute', inset: 0 }}>
      <div
        ref={containerRef}
        style={{ position: 'absolute', inset: 0 }}
      />
      <MapLegend />
    </div>
  );
}


// ── Legend overlay ──────────────────────────────────────────────
// Bottom-left, semi-transparent. Tells the agent what each color
// means without needing a tooltip.
function MapLegend() {
  const swatch = (color, opacity = 1) => ({
    display: 'inline-block',
    width: 12,
    height: 12,
    borderRadius: 6,
    background: color,
    opacity,
    marginRight: 8,
    flexShrink: 0,
  });
  const row = {
    display: 'flex',
    alignItems: 'center',
    fontSize: 11,
    color: 'var(--text)',
    lineHeight: 1.6,
  };
  return (
    <div style={{
      position: 'absolute',
      right: 12,
      bottom: 12,
      padding: '10px 14px',
      background: 'rgba(245, 240, 235, 0.94)',
      borderRadius: 6,
      boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
      pointerEvents: 'none',
      zIndex: 1000,
      maxWidth: 220,
      fontFamily: 'var(--font-sans)',
    }}>
      <div style={{
        fontSize: 9,
        fontWeight: 700,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        color: 'var(--text-tertiary)',
        marginBottom: 6,
      }}>
        This week
      </div>
      <div style={row}>
        <span style={swatch(PICK_STYLES.call_now.color)} />
        Call now
      </div>
      <div style={row}>
        <span style={swatch(PICK_STYLES.build_now.color)} />
        Build now
      </div>
      <div style={row}>
        <span style={swatch(PICK_STYLES.strategic_hold.color, 0.7)} />
        Watch list
      </div>

      <div style={{
        fontSize: 9,
        fontWeight: 700,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        color: 'var(--text-tertiary)',
        marginTop: 10,
        marginBottom: 6,
      }}>
        Territory
      </div>
      <div style={row}>
        <span style={swatch(FAMILY_BG_COLORS.investor_disposition, 0.5)} />
        Investor-held
      </div>
      <div style={row}>
        <span style={swatch(FAMILY_BG_COLORS.trust_aging, 0.5)} />
        Trust-held
      </div>
      <div style={row}>
        <span style={swatch(FAMILY_BG_COLORS.silent_transition, 0.5)} />
        Long-tenure individual
      </div>
      <div style={row}>
        <span style={swatch(FAMILY_BG_COLORS.dormant_absentee, 0.5)} />
        Out-of-area owner
      </div>
    </div>
  );
}
