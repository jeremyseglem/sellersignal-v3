import { useEffect, useRef } from 'react';
import L from 'leaflet';

// Color per category — matches the CSS tokens
const CATEGORY_COLORS = {
  call_now:         '#9E4B3C',
  build_now:        '#8B6914',
  hold:             '#A89B8A',
  avoid:            '#6B6D70',
  uninvestigated:   '#D9CEBF',
  strategic_hold:   '#5A7247',
};

const CATEGORY_RADIUS = {
  call_now:         8,
  build_now:        7,
  hold:             5,
  avoid:            5,
  uninvestigated:   3,
  strategic_hold:   6,
};

export default function MapPanel({ mapData, selectedPin, onPickPin }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef({});

  // Initialize Leaflet map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const bounds = mapData.bounds;
    const map = L.map(containerRef.current, {
      zoomControl: true,
      attributionControl: true,
    });

    // Use a warm, muted tile layer to match the Estate aesthetic
    // (Stadia Alidade Smooth or CartoDB Positron both work; using Positron as safe default)
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
      subdomains: 'abcd',
      maxZoom: 20,
    }).addTo(map);

    if (bounds) {
      map.fitBounds([
        [bounds.min_lat, bounds.min_lng],
        [bounds.max_lat, bounds.max_lng],
      ], { padding: [20, 20] });
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

  // Render parcels as pins
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapData?.parcels) return;

    // Clear old markers
    Object.values(markersRef.current).forEach((m) => map.removeLayer(m));
    markersRef.current = {};

    // Add new markers
    for (const p of mapData.parcels) {
      if (!p.lat || !p.lng) continue;

      const color = CATEGORY_COLORS[p.category] || CATEGORY_COLORS.uninvestigated;
      const radius = CATEGORY_RADIUS[p.category] || 4;

      const marker = L.circleMarker([p.lat, p.lng], {
        radius,
        color: color,
        fillColor: color,
        fillOpacity: 0.7,
        weight: 1.5,
        opacity: 1,
      });

      marker.on('click', () => onPickPin(p.pin));
      marker.on('mouseover', () => marker.setStyle({ weight: 3 }));
      marker.on('mouseout',  () => marker.setStyle({ weight: 1.5 }));

      marker.addTo(map);
      markersRef.current[p.pin] = marker;
    }
  }, [mapData, onPickPin]);

  // Fly to selected pin
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedPin) return;
    const marker = markersRef.current[selectedPin];
    if (marker) {
      const latlng = marker.getLatLng();
      map.flyTo(latlng, Math.max(map.getZoom(), 17), { duration: 0.8 });
      // Temporarily enlarge the selected pin
      marker.setStyle({ weight: 4, radius: (marker.options.radius || 5) + 2 });
    }
  }, [selectedPin]);

  return (
    <div
      ref={containerRef}
      style={{
        position: 'absolute',
        inset: 0,
      }}
    />
  );
}
