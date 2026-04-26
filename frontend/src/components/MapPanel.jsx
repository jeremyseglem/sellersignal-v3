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
// CALL NOW: warm crimson, the strongest visual.
// BUILD NOW: gold (matches Estate brand accent).
const PICK_STYLES = {
  call_now: {
    color: '#9E4B3C',
    radius: 9,
    fillOpacity: 0.95,
    weight: 2,
  },
  build_now: {
    color: '#8B6914',
    radius: 8,
    fillOpacity: 0.9,
    weight: 1.8,
  },
  strategic_hold: {
    color: '#5A7247',
    radius: 6,
    fillOpacity: 0.55,
    weight: 1.4,
  },
};

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
      // along the short axis. Cap at 13 — that's the operator-tested
      // sweet spot where individual streets are readable and dot
      // density doesn't smear into a single blob.
      map.fitBounds([
        [bounds.min_lat, bounds.min_lng],
        [bounds.max_lat, bounds.max_lng],
      ], { padding: [40, 40], maxZoom: 13 });
    } else {
      map.setView([47.6101, -122.2015], 13);  // Default: Bellevue
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

    const addMarker = (p, opts) => {
      const marker = L.circleMarker([p.lat, p.lng], {
        radius:       opts.radius,
        color:        opts.color,
        fillColor:    opts.color,
        fillOpacity:  opts.fillOpacity,
        weight:       opts.weight,
        opacity:      opts.opacity ?? 1,
      });
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
      });
    }

    // Layer 2: strategic holds
    for (const p of holdParcels) {
      addMarker(p, PICK_STYLES.strategic_hold);
    }

    // Layer 3: picks (build_now first, call_now on top — call_now
    // is the strongest signal so it should be the visually loudest).
    for (const p of buildNowParcels) {
      addMarker(p, PICK_STYLES.build_now);
    }
    for (const p of callNowParcels) {
      addMarker(p, PICK_STYLES.call_now);
    }
  }, [mapData, playbook, onPickPin]);

  // Fly to selected pin
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedPin) return;
    const marker = markersRef.current[selectedPin];
    if (marker) {
      const latlng = marker.getLatLng();
      map.flyTo(latlng, Math.max(map.getZoom(), 17), { duration: 0.8 });
      marker.setStyle({
        weight: 4,
        color: SELECTION_RING_COLOR,
        radius: (marker.options.radius || 5) + 2,
      });
    }
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
      left: 12,
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
