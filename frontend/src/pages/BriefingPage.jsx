import { useEffect, useState, useMemo } from 'react';
import { useParams, useNavigate, Link, useSearchParams } from 'react-router-dom';
import {
  briefings,
  map as mapApi,
  parcels as parcelsApi,
  leadTags,
  leadInteractions,
} from '../api/client.js';
import { useAuth } from '../lib/AuthContext.jsx';
import MapPanel from '../components/MapPanel.jsx';
import ParcelDossier from '../components/ParcelDossierV2.jsx';
import SiteLayout from '../components/shell/SiteLayout.jsx';
import BriefingHeader from '../components/briefing/BriefingHeader.jsx';
import ActionList from '../components/briefing/ActionList.jsx';
import LeadRow from '../components/briefing/LeadRow.jsx';
import PipelineList from '../components/briefing/PipelineList.jsx';
import MapExplorePanel from '../components/briefing/MapExplorePanel.jsx';

const FILTER_OPTIONS = [
  { key: 'all',        label: 'All',        matches: () => true },
  { key: 'call_now',   label: 'Contact now',   matches: (lead) => lead.recommended_action?.category === 'call_now' },
  { key: 'build_now',  label: 'Build now',  matches: (lead) => lead.recommended_action?.category === 'build_now' },
  { key: 'hold',       label: 'Holds',      matches: (lead) => !lead.recommended_action?.category || lead.recommended_action?.category === 'hold' },
];

const SORT_OPTIONS = [
  { key: 'default',    label: 'Default order' },
  { key: 'value_desc', label: 'Value: high → low' },
  { key: 'value_asc',  label: 'Value: low → high' },
  { key: 'tenure_desc',label: 'Tenure: long → short' },
  { key: 'tenure_asc', label: 'Tenure: short → long' },
];

function sortLeads(leads, sortKey) {
  if (sortKey === 'default') return leads;
  const copy = [...leads];
  const byValue = (dir) => (a, b) => dir * ((a.value || 0) - (b.value || 0));
  const byTenure = (dir) => (a, b) => dir * ((a.tenure_years || 0) - (b.tenure_years || 0));
  const cmp =
      sortKey === 'value_desc'  ? byValue(-1)
    : sortKey === 'value_asc'   ? byValue(1)
    : sortKey === 'tenure_desc' ? byTenure(-1)
    : sortKey === 'tenure_asc'  ? byTenure(1)
    : null;
  if (cmp) copy.sort(cmp);
  return copy;
}

function searchLeads(leads, query) {
  if (!query || !query.trim()) return leads;
  const q = query.trim().toLowerCase();
  return leads.filter((L) => (
    (L.address && L.address.toLowerCase().includes(q)) ||
    (L.owner_name && L.owner_name.toLowerCase().includes(q)) ||
    (L.pin && L.pin.includes(q))
  ));
}

export default function BriefingPage(props) {
  return (
    <SiteLayout
      agent={props.agent || null}
      onSignOut={props.onSignOut || null}
      mode="authenticated"
      showFooter={false}
    >
      <BriefingBody />
    </SiteLayout>
  );
}

function BriefingBody() {
  const { zip } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { profile } = useAuth();

  // ── Territory gate ────────────────────────────────────────────
  // Non-operator agents may only view their assigned_zip. Anyone
  // else gets redirected — to their assigned ZIP if they have one,
  // or to /territories to claim. Operators bypass entirely.
  useEffect(() => {
    if (!profile) return;  // wait for profile to load
    if (profile.role === 'operator') return;
    if (profile.assigned_zip && profile.assigned_zip !== zip) {
      navigate(`/zip/${profile.assigned_zip}`, { replace: true });
      return;
    }
    if (!profile.assigned_zip) {
      navigate('/territories', { replace: true });
      return;
    }
  }, [profile, zip, navigate]);

  const [briefing, setBriefing] = useState(null);
  const [mapData, setMapData]   = useState(null);
  const [selectedPin, setSelectedPin] = useState(null);
  const [dossier, setDossier]   = useState(null);
  const [error, setError]       = useState(null);

  // UI state for left panel controls
  const [searchQuery, setSearchQuery] = useState('');
  const [filterKey, setFilterKey]     = useState('all');
  const [sortKey, setSortKey]         = useState('default');

  // Tag filter state. `availableTags` is the agent's distinct tag set
  // for this ZIP (with counts) — drives the chip list. `selectedTags`
  // is the agent's active filter. `tagFilteredPins` is the union of
  // pins matching any selected tag (null = no tag filter active).
  const [availableTags, setAvailableTags]     = useState([]);
  const [selectedTags, setSelectedTags]       = useState([]);
  const [tagFilteredPins, setTagFilteredPins] = useState(null);

  // Lead Memory: per-pin status map for the agent in this ZIP.
  // Shape: { [pin]: { status: 'working' | 'not_relevant' | 'sent_to_crm',
  //                    status_at, event_data } }
  // Used to render the Working section above the bucket tabs — pins
  // with status='working' get pulled out and shown at the top regardless
  // of which bucket they'd otherwise sit in.
  const [leadStatuses, setLeadStatuses] = useState({});

  // Load briefing + map on ZIP change.
  // The previous version also called coverageApi.stats(zip) just for
  // city/state — that endpoint paginates parcels and investigations
  // to compute medians and counts the page never displays, costing
  // ~14s cold. Briefing now returns city/state in zip_meta directly,
  // saving the round trip.
  useEffect(() => {
    setBriefing(null); setMapData(null);
    setDossier(null); setError(null);
    setSelectedTags([]); setTagFilteredPins(null); setAvailableTags([]);
    setLeadStatuses({});

    Promise.all([briefings.get(zip, false), mapApi.get(zip)])
      .then(([b, m]) => { setBriefing(b); setMapData(m); })
      .catch((e) => setError(e.detail?.message || e.message));

    // Load this agent's distinct tags for this ZIP (chip list source).
    // Independent of the briefing load — failure here just leaves the
    // chip row empty; doesn't block briefing rendering.
    leadTags.list(zip)
      .then((r) => setAvailableTags(r.tags || []))
      .catch(() => { /* not signed in or other; leave empty */ });

    // Load Lead Memory status map for this ZIP. Independent of the
    // briefing — failure here just hides the Working section, doesn't
    // block the page. Cold visitors (no auth) will get a 401 and the
    // section silently doesn't render.
    leadInteractions.byZip(zip)
      .then((r) => setLeadStatuses(r.statuses || {}))
      .catch(() => setLeadStatuses({}));
  }, [zip]);

  // Whenever selectedTags changes, fetch the union of matching pins.
  // Empty selection clears the filter (sets back to null).
  useEffect(() => {
    if (selectedTags.length === 0) {
      setTagFilteredPins(null);
      return;
    }
    let cancelled = false;
    Promise.all(selectedTags.map((t) => leadTags.byTag(t, zip)))
      .then((results) => {
        if (cancelled) return;
        const pins = new Set();
        for (const r of results) {
          for (const a of (r.assignments || [])) pins.add(a.pin);
        }
        setTagFilteredPins(pins);
      })
      .catch(() => { /* leave previous filter set */ });
    return () => { cancelled = true; };
  }, [selectedTags, zip]);

  const handleToggleTag = (tag) => {
    setSelectedTags((prev) => (
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    ));
  };

  // Synthesize the 'stats' object from briefing for any downstream
  // reads that still expect it. Mirrors the shape coverageApi.stats
  // returned: { city, state, parcel_count }.
  const stats = useMemo(() => {
    if (!briefing) return null;
    return {
      city:         briefing?.zip_meta?.city,
      state:        briefing?.zip_meta?.state,
      parcel_count: briefing?.stats?.total_parcels,
    };
  }, [briefing]);

  // Load dossier when a pin is selected
  useEffect(() => {
    if (!selectedPin) { setDossier(null); return; }
    parcelsApi.get(selectedPin)
      .then(setDossier)
      .catch((e) => console.error('Failed to load dossier:', e));
  }, [selectedPin]);

  const handlePickLead = (pin) => setSelectedPin(pin);

  // Sync the ?pin= query param into selectedPin. Runs on initial
  // load (so links from My Leads auto-open the dossier) AND when
  // the agent navigates to a different pin within the same ZIP
  // (e.g., clicking another lead in My Leads).
  useEffect(() => {
    const pinFromUrl = searchParams.get('pin');
    if (pinFromUrl) setSelectedPin(pinFromUrl);
  }, [searchParams]);

  // Apply search + filter + sort to each section. Filtered output
  // feeds the map (so pin highlights match what the agent searches),
  // not the briefing left panel — the action list is intentionally
  // unfiltered so search doesn't accidentally hide a Call Now.
  const filteredPlaybook = useMemo(() => {
    if (!briefing?.playbook) return null;
    const activeFilter = FILTER_OPTIONS.find((o) => o.key === filterKey) || FILTER_OPTIONS[0];
    const processSection = (leads) => {
      if (!leads) return [];
      let cur = searchLeads(leads, searchQuery);
      cur = cur.filter(activeFilter.matches);
      // Tag filter: only keep leads whose pin is in the matching set.
      // null = no tag filter active.
      if (tagFilteredPins) {
        cur = cur.filter((L) => tagFilteredPins.has(L.pin));
      }
      return sortLeads(cur, sortKey);
    };
    return {
      call_now:        processSection(briefing.playbook.call_now),
      build_now:       processSection(briefing.playbook.build_now),
      strategic_holds: processSection(briefing.playbook.strategic_holds),
    };
  }, [briefing, searchQuery, filterKey, sortKey, tagFilteredPins]);

  // ── Contact Now buckets ────────────────────────────────────────────
  // The briefing now ships six ranked buckets keyed by seller type
  // (probate, divorce, aging_trust, llc_long_hold, absentee,
  // long_tenure). Each is capped at 100. Falls back to the legacy
  // playbook.call_now array if the backend hasn't shipped buckets yet.
  const contactNowBuckets = briefing?.playbook?.contact_now || null;

  // Build the bucket list in display order. Labels are intentionally
  // short — agents speak in shorthand ("trust", "LLC") and shorter
  // labels let all six tabs fit on a typical desktop width without
  // horizontal scrolling. Order matches the selector precedence:
  // probate first, long-tenure last.
  const BUCKET_ORDER = [
    { key: 'probate',       label: 'Probate' },
    { key: 'divorce',       label: 'Divorce' },
    { key: 'aging_trust',   label: 'Trust' },
    { key: 'llc_long_hold', label: 'LLC' },
    { key: 'absentee',      label: 'Absentee' },
    { key: 'long_tenure',   label: 'Tenure' },
  ];

  // Compute counts per bucket from the actual rendered leads (not
  // pre-cap totals — those go in the subtle "X total" line per tab).
  const bucketCounts = useMemo(() => {
    if (!contactNowBuckets) return {};
    const out = {};
    for (const { key } of BUCKET_ORDER) {
      out[key] = (contactNowBuckets[key] || []).length;
    }
    return out;
  }, [contactNowBuckets]);

  // Default to the first non-empty bucket. If none have data, default
  // to probate (so the tabs still render and the user can see the
  // empty state).
  const defaultBucket = useMemo(() => {
    if (!contactNowBuckets) return null;
    for (const { key } of BUCKET_ORDER) {
      if ((contactNowBuckets[key] || []).length > 0) return key;
    }
    return 'probate';
  }, [contactNowBuckets]);

  const [activeBucket, setActiveBucket] = useState(null);

  // Sync activeBucket to defaultBucket once the briefing loads
  useEffect(() => {
    if (defaultBucket && !activeBucket) {
      setActiveBucket(defaultBucket);
    }
  }, [defaultBucket, activeBucket]);

  // actionLeads: which leads feed the ActionList component below.
  // - If buckets are present, render the active bucket
  // - Otherwise fall back to legacy playbook.call_now
  const actionLeads = useMemo(() => {
    if (contactNowBuckets && activeBucket) {
      return contactNowBuckets[activeBucket] || [];
    }
    return briefing?.playbook?.call_now || [];
  }, [contactNowBuckets, activeBucket, briefing]);
  const pipelineLeads = {
    buildNow: briefing?.playbook?.build_now || [],
    holds:    briefing?.playbook?.strategic_holds || [],
  };

  // Working leads: pins with status='working' in Lead Memory, mapped to
  // the lead object from wherever it currently lives in the briefing
  // (any bucket, build_now, or strategic_holds). Dedup by pin so a lead
  // that appears in multiple containers only renders once. Order: most
  // recently marked working first.
  const workingLeads = useMemo(() => {
    const workingPins = Object.entries(leadStatuses || {})
      .filter(([_, s]) => s?.status === 'working')
      .sort((a, b) => {
        const aT = a[1]?.status_at || '';
        const bT = b[1]?.status_at || '';
        return bT.localeCompare(aT);  // newest first
      })
      .map(([pin]) => pin);
    if (workingPins.length === 0) return [];

    // Build a single pin → lead map from every place a lead might appear
    // in the briefing. Buckets first (most likely source), then
    // build_now, then strategic_holds. First write wins per pin.
    const byPin = {};
    const addArr = (arr) => {
      for (const L of (arr || [])) {
        if (L?.pin && byPin[L.pin] === undefined) byPin[L.pin] = L;
      }
    };
    for (const k of Object.keys(contactNowBuckets || {})) {
      addArr(contactNowBuckets[k]);
    }
    addArr(briefing?.playbook?.call_now);
    addArr(briefing?.playbook?.build_now);
    addArr(briefing?.playbook?.strategic_holds);

    // Map ordered pins to lead objects, dropping any pin we couldn't
    // find in the current briefing (rare: agent marked working but the
    // lead has fallen out of every container).
    return workingPins
      .map((pin) => byPin[pin])
      .filter(Boolean);
  }, [leadStatuses, contactNowBuckets, briefing]);

  // Header counts use the briefing's own stats (computed from the
  // just-built playbook, so they always agree with the lists below).
  // Coverage stats are a fallback for parcel count when briefing.stats
  // doesn't carry it.
  //
  // Build Now and Strategic Holds are tracked separately rather than
  // summed: the oracle line above the action list only mentions the
  // pipeline count ("100 more in pipeline"), while the Pipeline
  // section header shows both ("100 in pipeline · 893 on watch list").
  // Combining them in the oracle would force a single label that fits
  // neither bucket — Build Now is active pipeline, Holds are watch
  // list, and "X more building" reads as jargon to a cold visitor.
  // Prefer build_now_total / strategic_holds_total — these are the
  // TRUE eligible-pool sizes the backend computes before applying
  // the render-list cap. Fall back to *_count (rendered-list size)
  // and finally to the local array length for backward compat.
  const buildNowCount =
      briefing?.stats?.build_now_total
   ?? briefing?.stats?.build_now_count
   ?? pipelineLeads.buildNow.length;
  const holdsCount    =
      briefing?.stats?.strategic_holds_total
   ?? briefing?.stats?.strategic_holds_count
   ?? pipelineLeads.holds.length;
  const parcelCount   =
      briefing?.stats?.total_parcels
   ?? stats?.parcel_count
   ?? mapData?.parcels?.length
   ?? 0;

  if (error) {
    return (
      <div style={{ padding: 'var(--space-xl)', maxWidth: 720, margin: '0 auto' }}>
        <Link to="/territories" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontSize: 13 }}>
          ← Back to territories
        </Link>
        <h2 style={{ marginTop: 'var(--space-md)', fontFamily: 'var(--font-display)' }}>
          {zip} isn&rsquo;t available
        </h2>
        <p style={{ color: 'var(--text-secondary)', marginTop: 'var(--space-sm)' }}>
          {String(error)}
        </p>
      </div>
    );
  }

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '420px 1fr',
      height: 'calc(100vh - 56px)',
      overflow: 'hidden',
    }}>
      {/* ── Left panel: action-first briefing ── */}
      <aside style={{
        background: 'var(--bg-card)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {profile?.role === 'operator' && (
          <div style={{
            padding: '8px 16px',
            background: 'var(--accent)',
            color: 'var(--text-inverse, #fff)',
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            fontFamily: 'var(--font-sans)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
          }}>
            <span>Operator view · {zip}</span>
            <Link to="/territories" style={{
              color: 'var(--text-inverse, #fff)',
              opacity: 0.85,
              textDecoration: 'none',
              fontSize: 11,
              fontWeight: 600,
            }}>
              All territories ↗
            </Link>
          </div>
        )}

        <BriefingHeader
          zip={zip}
          buildNowCount={buildNowCount}
          parcelCount={parcelCount}
          city={stats?.city}
          state={stats?.state}
          weekOf={briefing?.week_of}
        />

        <div style={{ flex: 1, overflowY: 'auto' }}>
          {!briefing && (
            <p style={{
              padding: 'var(--space-lg)',
              color: 'var(--text-tertiary)',
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
            }}>
              Loading briefing…
            </p>
          )}

          {briefing && actionLeads.length === 0 && (
            <div style={{
              padding: 'var(--space-lg)',
              fontFamily: 'var(--font-serif)',
              color: 'var(--text-secondary)',
            }}>
              <p style={{
                fontFamily: 'var(--font-display)',
                fontSize: 16,
                fontWeight: 600,
                color: 'var(--text)',
                marginBottom: 6,
              }}>
                No active leads this week
              </p>
              <p style={{ fontSize: 13, fontStyle: 'italic', lineHeight: 1.5 }}>
                The briefing refreshes weekly. Or explore the territory on
                the map — the pipeline is still building.
              </p>
            </div>
          )}

          {briefing && (
            <>
              {workingLeads.length > 0 && (
                <WorkingSection
                  leads={workingLeads}
                  selectedPin={selectedPin}
                  onPickLead={handlePickLead}
                />
              )}
              {contactNowBuckets && (
                <BucketTabs
                  buckets={BUCKET_ORDER}
                  counts={bucketCounts}
                  active={activeBucket}
                  onSelect={setActiveBucket}
                />
              )}
              <ActionList
                leads={actionLeads}
                selectedPin={selectedPin}
                onPickLead={handlePickLead}
                bucketKey={activeBucket}
              />
              <PipelineList
                buildNowLeads={pipelineLeads.buildNow}
                holdLeads={pipelineLeads.holds}
                buildNowTotal={buildNowCount}
                holdTotal={holdsCount}
                selectedPin={selectedPin}
                onPickLead={handlePickLead}
              />
            </>
          )}
        </div>
      </aside>

      {/* ── Right: map + exploration controls + dossier ── */}
      <main style={{ position: 'relative', background: 'var(--bg)' }}>
        {!mapData && (
          <div style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-tertiary)',
            fontFamily: 'var(--font-serif)',
            fontStyle: 'italic',
          }}>
            Loading territory map…
          </div>
        )}
        {mapData && (
          <MapPanel
            mapData={mapData}
            playbook={filteredPlaybook || briefing?.playbook}
            selectedPin={selectedPin}
            onPickPin={handlePickLead}
          />
        )}

        {/* Exploration controls overlaid on the map. Hidden until
            the briefing has loaded so the controls don't appear
            against an empty map. */}
        {briefing && (
          <MapExplorePanel
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            filterKey={filterKey}
            onFilterChange={setFilterKey}
            sortKey={sortKey}
            onSortChange={setSortKey}
            filterOptions={FILTER_OPTIONS}
            sortOptions={SORT_OPTIONS}
            availableTags={availableTags}
            selectedTags={selectedTags}
            onToggleTag={handleToggleTag}
          />
        )}

        {selectedPin && dossier && (
          <ParcelDossier
            dossier={dossier}
            onClose={() => setSelectedPin(null)}
            preferredSignalType={
              activeBucket === 'probate' ? 'probate'
              : activeBucket === 'divorce' ? 'divorce'
              : null
            }
          />
        )}
      </main>
    </div>
  );
}


// ════════════════════════════════════════════════════════════════════
//  WorkingSection — Lead Memory pinned-at-top view
// ════════════════════════════════════════════════════════════════════
//
// Renders leads the agent has marked status='working' via the dossier,
// pulled out of their current bucket and pinned above the bucket tabs.
// Stays visible across week rollovers so a lead being actively worked
// doesn't disappear just because a new high-rank lead bumped it out
// of the top 100 of its bucket.
//
// Leads are sourced from whatever container the briefing currently
// places them in (a bucket, build_now, or strategic_holds). If a
// working lead has fallen out of every container in the briefing
// (rare), it's silently dropped — agent can still find it via the
// dossier's history page.
//
// Reuses LeadRow for visual consistency with the action list. Accent
// color stays var(--call-now) — the visual signal is "this is a
// current focus."
function WorkingSection({ leads, selectedPin, onPickLead }) {
  if (!leads || leads.length === 0) return null;
  return (
    <section
      aria-label="Leads you're working on"
      style={{
        padding: 'var(--space-md) var(--space-lg) var(--space-lg)',
        borderBottom: '1px solid var(--border)',
        background: 'var(--bg-tinted, rgba(139, 105, 20, 0.04))',
      }}
    >
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        marginBottom: 'var(--space-sm)',
      }}>
        <div style={{
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: '#8B6914',
          fontFamily: 'var(--font-sans)',
        }}>
          Working
        </div>
        <div style={{
          fontSize: 11,
          color: 'var(--text-tertiary)',
          fontFamily: 'var(--font-sans)',
        }}>
          {leads.length} {leads.length === 1 ? 'lead' : 'leads'}
        </div>
      </div>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {leads.map((lead, i) => (
          <LeadRow
            key={lead.pin}
            lead={lead}
            index={i + 1}
            selected={lead.pin === selectedPin}
            accent="var(--call-now)"
            onClick={() => onPickLead(lead.pin)}
          />
        ))}
      </ul>
    </section>
  );
}


// ════════════════════════════════════════════════════════════════════
//  BucketTabs — Contact Now seller-type selector
// ════════════════════════════════════════════════════════════════════
//
// Renders six tabs above the action list, one per seller-type bucket.
// Each tab shows the count of leads currently in that bucket — that's
// it. No "rendered / total" ratios, no progress bars. The count IS
// what the bucket contains; agents don't need a denominator.
//
// Empty buckets are still rendered (dimmed) so the agent always sees
// the full menu of seller types even when today's batch is empty for
// some.
//
// Tighter padding + shorter labels = six tabs fit on a typical
// desktop width without horizontal scrolling.
function BucketTabs({ buckets, counts, active, onSelect }) {
  return (
    <div style={{
      display: 'flex',
      flexWrap: 'wrap',
      gap: 4,
      padding: '0 0 var(--space-md) 0',
      marginBottom: 'var(--space-sm)',
      borderBottom: '1px solid var(--border)',
    }}>
      {buckets.map(({ key, label }) => {
        const count = counts[key] || 0;
        const isActive = key === active;
        const isEmpty = count === 0;
        return (
          <button
            key={key}
            type="button"
            onClick={() => onSelect(key)}
            style={{
              flex: '0 1 auto',
              minWidth: 0,
              padding: '7px 12px',
              fontFamily: 'var(--font-sans)',
              fontSize: 12,
              fontWeight: isActive ? 700 : 500,
              letterSpacing: '0.01em',
              color: isActive ? 'var(--text)' :
                     isEmpty ? 'var(--text-tertiary)' : 'var(--text-secondary)',
              background: isActive ? 'var(--accent-dim)' : 'transparent',
              border: '1px solid',
              borderColor: isActive ? 'var(--accent)' : 'var(--border)',
              borderRadius: 'var(--radius-md, 6px)',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              transition: 'all 0.15s',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 5,
            }}
          >
            <span>{label}</span>
            <span style={{
              fontSize: 11,
              fontWeight: 700,
              color: isActive ? 'var(--accent)' :
                     isEmpty ? 'var(--text-tertiary)' : 'var(--text)',
              opacity: isEmpty ? 0.6 : 1,
            }}>
              {count}
            </span>
          </button>
        );
      })}
    </div>
  );
}
