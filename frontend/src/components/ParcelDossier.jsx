import { useEffect, useState } from 'react';
import { map as mapApi, deepSignal as deepSignalApi } from '../api/client.js';
import SixLettersModal from './SixLettersModal.jsx';
import { ownerTypeLabel, isSellerTargetType } from '../lib/ownerType';

function formatValue(v) {
  if (!v) return '—';
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000)     return `$${Math.round(v / 1_000)}K`;
  return `$${v}`;
}

function formatYears(y) {
  if (y == null) return '—';
  const r = Math.round(y);
  return r === 1 ? '1 yr' : `${r} yr`;
}

function formatDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  } catch { return iso; }
}

// ownerTypeLabel + isSellerTargetType imported from ../lib/ownerType
// (moved out so PlaybookList can share the same conversion and the
// shared helpers can enumerate every backend category: individual,
// trust, llc, estate, gov, nonprofit, unknown).

export default function ParcelDossier({ dossier, onClose }) {
  const [streetViewUrl, setStreetViewUrl] = useState(null);
  const [streetViewOk, setStreetViewOk] = useState(true);

  // Deep Signal state — loads cached on pin change; generation is on-demand
  const [deepSignal, setDeepSignal] = useState(null);
  const [deepSignalLoading, setDeepSignalLoading] = useState(false);
  const [deepSignalError, setDeepSignalError] = useState(null);

  // Six Letters modal
  const [sixLettersOpen, setSixLettersOpen] = useState(false);

  useEffect(() => {
    if (!dossier?.pin) return;
    setStreetViewUrl(null); setStreetViewOk(true);
    mapApi.streetView(dossier.pin)
      .then((r) => setStreetViewUrl(r.url))
      .catch(() => setStreetViewUrl(null));
  }, [dossier?.pin]);

  // Load cached Deep Signal when pin changes — non-blocking, silent on 404
  useEffect(() => {
    if (!dossier?.pin) return;
    setDeepSignal(null); setDeepSignalError(null); setSixLettersOpen(false);
    deepSignalApi.get(dossier.pin)
      .then((r) => setDeepSignal(r))
      .catch(() => setDeepSignal(null));  // 404 is expected when no cache exists
  }, [dossier?.pin]);

  const p   = dossier.parcel || {};
  const inv = dossier.investigation || {};
  const rec = dossier.recommended_action;
  const why = dossier.why_not_selling;
  // Harvester sidecar: per-signal match list (obituary, probate, divorce,
  // tax_foreclosure) from raw_signal_matches_v3. Always an array; empty
  // when the parcel has no harvester matches.
  const harvesterMatches = dossier.harvester_matches || [];
  const hasConvergence   = Boolean(dossier.convergence);
  // Parcel-state tags: HIGH EQUITY / DEEP TENURE / LEGACY HOLD / MATURE
  // LLC. Descriptive situational markers derived at read time from
  // parcels_v3 columns (see backend/selection/parcel_state_tags.py).
  // Each has { label, kind, description, rank }. Empty list when none
  // fire.
  const parcelStateTags = dossier.parcel_state_tags || [];

  const ownerTag = ownerTypeLabel(p.owner_type);
  const signalLabel = p.signal_family ? p.signal_family.replace(/_/g, ' ') : null;

  // Deep Signal availability:
  //   - Legacy path: inv.signals populated by the SerpAPI investigator
  //   - New path: harvester_matches populated by the raw_signal_matches
  //     pipeline (obituary / probate / divorce / tax_foreclosure)
  //   Either qualifies. If neither fires but the backend has an
  //   investigations_v3 row from some other path, Deep Signal will still
  //   try and succeed. If it genuinely has no investigation, we get
  //   409 and surface it as deepSignalError.
  const canGenerateDeepSignal =
    Boolean(inv?.signals?.length) || harvesterMatches.length > 0;

  // Six Letters availability — purely client-side generator, so we show
  // it broadly for anything that's a plausible seller target. Gov and
  // nonprofit owners hide the button (direct mail to fire stations /
  // churches is inappropriate). See isSellerTargetType in lib/ownerType.
  const canGenerateSixLetters = isSellerTargetType(p.owner_type);

  const handleGenerateDeepSignal = async () => {
    if (!dossier?.pin) return;
    setDeepSignalLoading(true); setDeepSignalError(null);
    try {
      const r = await deepSignalApi.generate(dossier.pin);
      setDeepSignal(r);
    } catch (e) {
      setDeepSignalError(e?.detail?.message || e?.message || 'Generation failed');
    } finally {
      setDeepSignalLoading(false);
    }
  };

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        right: 0,
        height: '100vh',
        width: 440,
        background: 'var(--bg-card)',
        borderLeft: '1px solid var(--border)',
        boxShadow: 'var(--shadow-lg)',
        overflow: 'auto',
        zIndex: 1000,
      }}
    >
      <div style={{ padding: 'var(--space-lg)' }}>
        {/* Close button */}
        <button
          onClick={onClose}
          style={{
            position: 'absolute',
            top: 'var(--space-md)',
            right: 'var(--space-md)',
            width: 28, height: 28,
            borderRadius: '50%',
            background: 'var(--bg)',
            color: 'var(--text-secondary)',
            fontSize: 16,
            lineHeight: 1,
          }}
          aria-label="Close"
        >
          ×
        </button>

        {/* Address + value */}
        <div style={{ paddingRight: 40 }}>
          <div style={{
            fontSize: 11,
            color: 'var(--text-tertiary)',
            fontWeight: 600,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}>
            Parcel {p.pin}
          </div>
          <h2 style={{
            fontFamily: 'var(--font-display)',
            fontSize: 22,
            fontWeight: 600,
            color: 'var(--text)',
            marginTop: 'var(--space-xs)',
            lineHeight: 1.2,
          }}>
            {p.address || 'Address unknown'}
          </h2>
          <div style={{
            display: 'flex',
            gap: 'var(--space-md)',
            marginTop: 'var(--space-sm)',
            fontSize: 13,
            color: 'var(--text-secondary)',
            alignItems: 'center',
            flexWrap: 'wrap',
          }}>
            <div>{p.city}, {p.state}</div>
            <div>·</div>
            <div style={{ fontFamily: 'var(--font-display)', color: 'var(--accent)', fontWeight: 600 }}>
              {formatValue(p.total_value)}
            </div>
            {ownerTag && (
              <>
                <div>·</div>
                <div style={{
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  color: 'var(--text-tertiary)',
                }}>
                  {ownerTag}
                </div>
              </>
            )}
            {/* Absentee / Out-of-State badge.
                OOS is the stronger signal (genuine out-of-state ownership
                strongly correlates with disposition intent), so prefer it
                when both fire. Adjacent-city absentee (e.g., Ballmer's
                Hunts Point home with Bellevue taxpayer mailing) is still
                meaningful context but gets the softer ABSENTEE label. */}
            {p.is_out_of_state && (
              <>
                <div>·</div>
                <div style={{
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  color: 'var(--call-now)',
                }}>
                  Out of State
                </div>
              </>
            )}
            {!p.is_out_of_state && p.is_absentee && (
              <>
                <div>·</div>
                <div style={{
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  color: 'var(--accent)',
                }}>
                  Absentee
                </div>
              </>
            )}
          </div>
        </div>

        {/* Owner info */}
        <div style={{
          marginTop: 'var(--space-lg)',
          padding: 'var(--space-md)',
          background: 'var(--bg)',
          borderRadius: 'var(--radius-md)',
        }}>
          <div style={{
            fontSize: 11,
            color: 'var(--text-tertiary)',
            fontWeight: 600,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}>
            Owner
          </div>
          <div style={{
            fontFamily: 'var(--font-serif)',
            fontSize: 15,
            color: 'var(--text)',
            marginTop: 'var(--space-xs)',
          }}>
            {p.owner_name || '(unknown)'}
          </div>
          <div style={{
            fontSize: 12,
            color: 'var(--text-tertiary)',
            marginTop: 2,
          }}>
            {ownerTag || 'unknown'} · {formatYears(p.tenure_years)} tenure
          </div>
          {/* Mailing address — only shown when different from site,
              since it's redundant otherwise. KC assessor filters the
              street-level mailing address out of public data (RCW
              42.56.070(8)) so we only have city/state. Useful context
              for absentee/OOS outreach: an agent can see at a glance
              that the owner gets mail in Covina, CA. */}
          {p.owner_city && (p.owner_city.toUpperCase() !== (p.city || '').toUpperCase()
                            || (p.owner_state || '').toUpperCase() !== (p.state || '').toUpperCase()) && (
            <div style={{
              fontSize: 12,
              color: 'var(--text-tertiary)',
              marginTop: 4,
              paddingTop: 4,
              borderTop: '1px dashed var(--border)',
            }}>
              <span style={{
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                color: 'var(--text-tertiary)',
              }}>
                Mails to:
              </span>
              {' '}
              {p.owner_city}{p.owner_state ? `, ${p.owner_state}` : ''}
            </div>
          )}
        </div>

        {/* Street View — graceful when key isn't configured */}
        {streetViewUrl && streetViewOk && (
          <img
            src={streetViewUrl}
            alt={`Street View of ${p.address}`}
            onError={() => setStreetViewOk(false)}
            style={{
              width: '100%',
              marginTop: 'var(--space-md)',
              borderRadius: 'var(--radius-md)',
              display: 'block',
            }}
          />
        )}

        {/* Recommended action — if investigated. Receives the full
            parcel + harvester match context so it can generate a
            Who/How/Why/What/First-Move operator card instead of a
            one-line analyst summary. */}
        {rec && rec.category && rec.category !== 'hold' && (
          <RecommendedActionBlock
            rec={rec}
            parcel={p}
            harvesterMatches={harvesterMatches}
          />
        )}

        {/* Harvester matches — itemized list of obit / probate / divorce /
            tax_foreclosure signals that fired on this pin. Shown when ANY
            match exists; the block also surfaces a "converged" indicator
            at the top when 2+ strict signals hit the same pin. */}
        {/* Unified Evidence panel — merges harvester_matches (from the
            free authoritative pipelines: KC Superior Court, obituary
            RSS, KC Treasurer) with inv.signals (from the SerpAPI
            investigator, where used for the remaining signal types
            harvesters don't cover yet: listings, LinkedIn, retirement).
            Replaces the previous split HarvesterMatchesBlock + separate
            Evidence (SignalsBlock) that showed overlapping information
            in two places. Ranked: harvester-strict → harvester-weak →
            serp-high → serp-medium → serp-low. Converged badge when
            2+ distinct harvester signal types hit the same pin. */}
        {(harvesterMatches.length > 0 || (inv?.signals?.length ?? 0) > 0) && (
          <EvidenceBlock
            harvesterMatches={harvesterMatches}
            serpSignals={inv?.signals || []}
            convergence={hasConvergence}
          />
        )}

        {/* Parcel-state tags — descriptive markers (HIGH EQUITY, DEEP
            TENURE, LEGACY HOLD, MATURE LLC) derived from the parcel's
            own columns. No promotion/ranking impact — these are
            situational context for the agent. */}
        {parcelStateTags.length > 0 && (
          <ParcelStateTagsBlock tags={parcelStateTags} />
        )}

        {/* Action buttons — Deep Signal + Six Letters are each
            independently shown or hidden. The ActionButtons container
            renders when at least one applies; the individual buttons
            inside are gated by showDeepSignal / showSixLetters props.
            See isSellerTargetType in lib/ownerType for the Six Letters
            guard (gov / nonprofit hidden). Deep Signal is shown
            whenever the parcel has investigation signals OR harvester
            matches (the latter is the modern pipeline — without this,
            harvester-only parcels silently hid both buttons). */}
        {(canGenerateDeepSignal || canGenerateSixLetters) && (
          <ActionButtons
            hasDeepSignal={Boolean(deepSignal)}
            deepSignalLoading={deepSignalLoading}
            onGenerateDeepSignal={handleGenerateDeepSignal}
            onOpenSixLetters={() => setSixLettersOpen(true)}
            showDeepSignal={canGenerateDeepSignal}
            showSixLetters={canGenerateSixLetters}
          />
        )}

        {/* Deep Signal error (only if generation fails) */}
        {deepSignalError && (
          <div style={{
            marginTop: 'var(--space-md)',
            padding: 'var(--space-sm) var(--space-md)',
            background: 'rgba(158,75,60,0.08)',
            borderLeft: '3px solid var(--call-now)',
            borderRadius: 'var(--radius-md)',
            fontSize: 12,
            color: 'var(--text-secondary)',
          }}>
            Deep Signal failed: {deepSignalError}
          </div>
        )}

        {/* Deep Signal content — scripts + what-not-to-say */}
        {deepSignal && (deepSignal.motivation || deepSignal.call_script) && (
          <DeepSignalBlock ds={deepSignal} />
        )}

        {/* Property detail grid — shown for all parcels */}
        <PropertyGrid parcel={p} signalLabel={signalLabel} />

        {/* Transfer history — if we have it. Arms-length fields
            (from sales_history_v3 via the view) are passed separately
            because they live at the dossier top-level, not inside
            the parcels_v3 row. */}
        {(p.last_transfer_date || p.last_transfer_price
          || dossier.last_arms_length_price) && (
          <TransferHistoryBlock
            parcel={p}
            armsLengthPrice={dossier.last_arms_length_price}
            armsLengthDate={dossier.last_arms_length_date}
            armsLengthBuyer={dossier.last_arms_length_buyer}
            armsLengthSeller={dossier.last_arms_length_seller}
          />
        )}

        {/* Full sales history — the itemized list of every recorded
            transfer the eReal Property harvester parsed for this
            parcel. Surfaces divorces (Property Settlement reason),
            estate distributions, trust moves, and arms-length
            purchases. Collapsed by default when there are more than
            3 rows to keep the dossier scan-able. */}
        {(dossier.sales_history || []).length > 0 && (
          <SalesHistoryBlock sales={dossier.sales_history} />
        )}

        {/* Why not selling — auto-generated read for non-actionable parcels */}
        {why && (
          <WhyNotSellingBlock why={why} />
        )}

        {/* (Investigation signals are rendered upstream via the
            unified EvidenceBlock along with harvester matches.) */}
      </div>

      {/* Six Letters modal */}
      {sixLettersOpen && (
        <SixLettersModal
          parcel={p}
          onClose={() => setSixLettersOpen(false)}
        />
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Action buttons (Deep Signal + Six Letters)
// ──────────────────────────────────────────────────────────────────────
function ActionButtons({
  hasDeepSignal,
  deepSignalLoading,
  onGenerateDeepSignal,
  onOpenSixLetters,
  // Each button is independently shown or hidden. Defaults to true
  // preserve backward compatibility if a caller only passes the
  // click handlers.
  showDeepSignal = true,
  showSixLetters = true,
}) {
  return (
    <div style={{
      marginTop: 'var(--space-lg)',
      display: 'flex',
      gap: 'var(--space-sm)',
    }}>
      {showDeepSignal && (
        <button
          onClick={onGenerateDeepSignal}
          disabled={deepSignalLoading}
          style={{
            flex: 1,
            padding: '10px 12px',
            fontFamily: 'var(--font-sans)',
            fontSize: 12,
            fontWeight: 600,
            letterSpacing: '0.03em',
            border: 'none',
            borderRadius: 'var(--radius-md)',
            background: 'var(--text)',
            color: 'var(--bg-card)',
            cursor: deepSignalLoading ? 'wait' : 'pointer',
            opacity: deepSignalLoading ? 0.6 : 1,
          }}
        >
          {deepSignalLoading
            ? 'Generating…'
            : hasDeepSignal
              ? 'Refresh Deep Signal'
              : 'Deep Signal'}
        </button>
      )}
      {showSixLetters && (
        <button
          onClick={onOpenSixLetters}
          style={{
            flex: 1,
            padding: '10px 12px',
            fontFamily: 'var(--font-sans)',
            fontSize: 12,
            fontWeight: 600,
            letterSpacing: '0.03em',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            background: 'transparent',
            color: 'var(--text)',
            cursor: 'pointer',
          }}
        >
          Six Letters
        </button>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Deep Signal display — motivation + 3 scripts + what-not-to-say
// ──────────────────────────────────────────────────────────────────────
function DeepSignalBlock({ ds }) {
  const [activeScript, setActiveScript] = useState(
    ds.best_channel === 'mail' ? 'mail'
    : ds.best_channel === 'door' ? 'door'
    : 'call'
  );

  const tabs = [
    { key: 'call', label: 'Phone script',  content: ds.call_script },
    { key: 'mail', label: 'Letter',        content: ds.mail_script },
    { key: 'door', label: 'Door knock',    content: ds.door_script },
  ];
  const active = tabs.find((t) => t.key === activeScript) || tabs[0];

  return (
    <div style={{
      marginTop: 'var(--space-lg)',
      padding: 'var(--space-md)',
      background: 'var(--bg)',
      borderRadius: 'var(--radius-md)',
      borderLeft: '3px solid var(--build-now)',
    }}>
      <div style={{
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        color: 'var(--build-now)',
      }}>
        Deep Signal
      </div>

      {/* Motivation — why this owner may sell */}
      {ds.motivation && (
        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 14,
          color: 'var(--text)',
          lineHeight: 1.55,
          marginTop: 'var(--space-sm)',
        }}>
          {ds.motivation}
        </p>
      )}

      {/* Meta row: timeline + best channel */}
      {(ds.timeline || ds.best_channel) && (
        <div style={{
          display: 'flex',
          gap: 'var(--space-md)',
          marginTop: 'var(--space-sm)',
          fontSize: 11,
          color: 'var(--text-tertiary)',
          fontWeight: 600,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
        }}>
          {ds.timeline && <div>Timeline: {ds.timeline}</div>}
          {ds.best_channel && <div>Lead with: {ds.best_channel}</div>}
        </div>
      )}

      {/* Script tabs */}
      <div style={{
        marginTop: 'var(--space-md)',
        display: 'flex',
        gap: 4,
        borderBottom: '1px solid var(--border)',
      }}>
        {tabs.filter((t) => t.content).map((t) => (
          <button
            key={t.key}
            onClick={() => setActiveScript(t.key)}
            style={{
              padding: '6px 10px',
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: '0.03em',
              border: 'none',
              borderBottom: `2px solid ${activeScript === t.key ? 'var(--build-now)' : 'transparent'}`,
              background: 'transparent',
              color: activeScript === t.key ? 'var(--text)' : 'var(--text-tertiary)',
              cursor: 'pointer',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Active script body */}
      {active.content && (
        <div style={{
          marginTop: 'var(--space-sm)',
          padding: 'var(--space-sm) 0',
          fontFamily: 'var(--font-serif)',
          fontSize: 13,
          fontStyle: 'italic',
          color: 'var(--text)',
          lineHeight: 1.6,
          whiteSpace: 'pre-line',
        }}>
          “{active.content}”
        </div>
      )}

      {/* What not to say */}
      {ds.what_not_to_say && (
        <div style={{
          marginTop: 'var(--space-md)',
          padding: 'var(--space-sm) var(--space-md)',
          background: 'rgba(158,75,60,0.06)',
          borderLeft: '2px solid rgba(158,75,60,0.4)',
          borderRadius: 'var(--radius-md)',
        }}>
          <div style={{
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: 'var(--call-now)',
            marginBottom: 4,
          }}>
            What not to say
          </div>
          <div style={{
            fontSize: 12,
            color: 'var(--text-secondary)',
            lineHeight: 1.5,
            fontFamily: 'var(--font-serif)',
          }}>
            {ds.what_not_to_say}
          </div>
        </div>
      )}
    </div>
  );
}

function PropertyGrid({ parcel, signalLabel }) {
  // Only include fields that have a value — blanks dilute the grid.
  // Format the "prop_type" single-letter codes into something a user
  // can read.
  //
  // KC Assessor PROPTYPE codes:
  //   R = Residential, C = Commercial, K = Condo / Apartment,
  //   A = Agricultural, I = Industrial
  const propTypeLabel = (code) => {
    if (!code) return null;
    const c = String(code).toUpperCase();
    return {
      R: 'Residential',
      C: 'Commercial',
      K: 'Condo / Apt',
      A: 'Agricultural',
      I: 'Industrial',
    }[c] || code;
  };
  const sqftFmt = (n) =>
    n ? `${Number(n).toLocaleString()} sq ft` : null;
  const acresFmt = (n) => {
    if (n == null) return null;
    return Number(n) < 0.1
      ? `${Number(n).toFixed(2)} acre`
      : `${Number(n).toFixed(2)} acres`;
  };

  const rowsRaw = [
    { label: 'Cohort',         value: signalLabel || null },
    { label: 'County assessed',value: parcel.total_value ? formatValue(parcel.total_value) : null },
    { label: 'Land',           value: parcel.land_value ? formatValue(parcel.land_value) : null },
    { label: 'Improvements',   value: parcel.building_value ? formatValue(parcel.building_value) : null },
    { label: 'Tenure',         value: parcel.tenure_years != null ? formatYears(parcel.tenure_years) : null },
    { label: 'Property type',  value: propTypeLabel(parcel.prop_type) },
    { label: 'Sq ft',          value: sqftFmt(parcel.sqft) },
    { label: 'Year built',     value: parcel.year_built ? String(parcel.year_built) : null },
    { label: 'Lot size',       value: acresFmt(parcel.acres) },
  ];
  const rows = rowsRaw.filter((r) => r.value != null && r.value !== '');

  return (
    <div style={{
      marginTop: 'var(--space-lg)',
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: 'var(--space-md)',
    }}>
      {rows.map((r) => (
        <div key={r.label}>
          <div style={{
            fontSize: 10,
            color: 'var(--text-tertiary)',
            fontWeight: 600,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}>
            {r.label}
          </div>
          <div style={{
            fontFamily: 'var(--font-display)',
            fontSize: 14,
            color: 'var(--text)',
            marginTop: 2,
            textTransform: r.label === 'Cohort' ? 'capitalize' : 'none',
          }}>
            {r.value}
          </div>
        </div>
      ))}
    </div>
  );
}

function TransferHistoryBlock({
  parcel,
  armsLengthPrice,
  armsLengthDate,
  armsLengthBuyer,
  armsLengthSeller,
}) {
  // Decide what the "primary" transfer line should show.
  //
  // If the recorded last_transfer has a real price, display it — that's
  // what happened. If it's 0 (typical for trust transfers and quit-
  // claims) BUT we have arms-length data, promote that to the primary
  // line instead. Otherwise fall back to the recorded transfer with
  // just a date.
  //
  // This mirrors the backend's HIGH EQUITY logic (see
  // parcel_state_tags.derive_tags), so the agent sees the same cost
  // basis the scoring uses.
  const recordedPrice = parcel.last_transfer_price;
  const hasRecordedPrice = recordedPrice && recordedPrice > 0;
  const hasArmsLength = armsLengthPrice && armsLengthPrice > 0;

  let primaryLabel, primaryDate, primaryPrice, subline;
  if (hasArmsLength && !hasRecordedPrice) {
    primaryLabel = 'Last arms-length sale';
    primaryDate = armsLengthDate;
    primaryPrice = armsLengthPrice;
    // Note the recorded transfer as a subline so the agent understands
    // why this differs from what shows on assessor sites
    if (parcel.last_transfer_date) {
      subline = `Most recent recorded transfer ${formatDate(parcel.last_transfer_date)} — no sale price (trust, quit-claim, or family transfer).`;
    }
  } else {
    primaryLabel = 'Last sale';
    primaryDate = parcel.last_transfer_date;
    primaryPrice = hasRecordedPrice ? recordedPrice : null;
    // If we ALSO have arms-length data from a different date, note it
    if (hasArmsLength && armsLengthDate !== parcel.last_transfer_date) {
      subline = `Last arms-length sale ${formatDate(armsLengthDate)} · ${formatValue(armsLengthPrice)}.`;
    }
  }

  const ago = parcel.tenure_years != null
    ? ` (${formatYears(parcel.tenure_years)} ago)`
    : '';

  return (
    <div style={{
      marginTop: 'var(--space-lg)',
      padding: 'var(--space-md)',
      background: 'var(--bg)',
      borderRadius: 'var(--radius-md)',
    }}>
      <div style={{
        fontSize: 11,
        color: 'var(--text-tertiary)',
        fontWeight: 600,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
      }}>
        Transfer history
      </div>
      <div style={{
        fontSize: 13,
        color: 'var(--text)',
        marginTop: 'var(--space-xs)',
        fontFamily: 'var(--font-serif)',
      }}>
        {primaryLabel}: {formatDate(primaryDate)}{ago}
        {primaryPrice && (
          <span style={{ color: 'var(--text-secondary)' }}>
            {' · '}
            {formatValue(primaryPrice)}
          </span>
        )}
      </div>
      {subline && (
        <div style={{
          marginTop: 6,
          fontSize: 12,
          color: 'var(--text-tertiary)',
          fontFamily: 'var(--font-sans)',
          lineHeight: 1.4,
        }}>
          {subline}
        </div>
      )}
      {hasArmsLength && (armsLengthBuyer || armsLengthSeller) && (
        <div style={{
          marginTop: 6,
          fontSize: 12,
          color: 'var(--text-tertiary)',
          fontFamily: 'var(--font-sans)',
          lineHeight: 1.4,
        }}>
          {armsLengthSeller && `Sold by ${armsLengthSeller}`}
          {armsLengthSeller && armsLengthBuyer && ' → '}
          {armsLengthBuyer && `bought by ${armsLengthBuyer}`}
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Full sales history — every recorded transfer from the eReal Property
// harvester, ordered most-recent-first. Each row shows date, price (or
// "—" when $0), seller → buyer, and tags for non-arms-length reasons
// (Property Settlement = divorce, Estate, Trust, Gift).
//
// The block is informational; no action buttons. It's read-only
// narrative context for the agent ("this home changed hands in a
// divorce") rather than a signal queue.
//
// Collapsed to the first 3 rows when there are more than 3; an
// "Show all N transfers" toggle reveals the rest.
// ──────────────────────────────────────────────────────────────────────
function SalesHistoryBlock({ sales }) {
  const [expanded, setExpanded] = useState(false);
  const rows = Array.isArray(sales) ? sales : [];
  if (rows.length === 0) return null;

  const shown = expanded ? rows : rows.slice(0, 3);
  const hiddenCount = rows.length - shown.length;

  // Flag interesting reasons with a short uppercase badge. These are
  // the non-arms-length reasons the parser records in sale_reason.
  // Property Settlement = divorce, Estate Settlement = death transfer,
  // Gift = family transfer, Trust = trust move.
  const reasonBadge = (reason) => {
    if (!reason) return null;
    const r = String(reason).toUpperCase();
    if (r.includes('PROPERTY SETTLEMENT')) return { text: 'DIVORCE',   color: 'var(--tone-sensitive)' };
    if (r.includes('ESTATE'))              return { text: 'ESTATE',    color: 'var(--tone-sensitive)' };
    if (r === 'GIFT')                      return { text: 'GIFT',      color: 'var(--text-tertiary)' };
    if (r === 'TRUST')                     return { text: 'TRUST',     color: 'var(--text-tertiary)' };
    if (r === 'NONE' || r === 'N/A')       return null;
    return { text: r.slice(0, 20), color: 'var(--text-tertiary)' };
  };

  return (
    <div style={{
      marginTop: 'var(--space-lg)',
      padding: 'var(--space-md)',
      background: 'var(--bg)',
      borderRadius: 'var(--radius-md)',
    }}>
      <div style={{
        fontSize: 11,
        color: 'var(--text-tertiary)',
        fontWeight: 600,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        marginBottom: 'var(--space-sm)',
      }}>
        Sales history ({rows.length})
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {shown.map((s) => {
          const badge = reasonBadge(s.sale_reason);
          const hasPrice = s.sale_price && s.sale_price > 0;
          return (
            <div key={s.recording_number || `${s.sale_date}-${s.buyer_name}`}
                 style={{
                   fontSize: 12,
                   fontFamily: 'var(--font-sans)',
                   borderLeft: `2px solid ${s.is_arms_length ? 'var(--accent)' : 'var(--border)'}`,
                   paddingLeft: 'var(--space-sm)',
                 }}>
              {/* Top line: date + price + badges */}
              <div style={{
                display: 'flex',
                alignItems: 'baseline',
                gap: 8,
                flexWrap: 'wrap',
              }}>
                <span style={{ color: 'var(--text)', fontWeight: 600 }}>
                  {formatDate(s.sale_date)}
                </span>
                <span style={{
                  color: hasPrice ? 'var(--text-secondary)' : 'var(--text-tertiary)',
                  fontFamily: 'var(--font-display)',
                }}>
                  {hasPrice ? formatValue(s.sale_price) : '—'}
                </span>
                {badge && (
                  <span style={{
                    fontSize: 9,
                    fontWeight: 700,
                    letterSpacing: '0.08em',
                    padding: '2px 6px',
                    borderRadius: 3,
                    background: badge.color,
                    color: '#fff',
                  }}>
                    {badge.text}
                  </span>
                )}
                {s.is_arms_length && hasPrice && (
                  <span style={{
                    fontSize: 9,
                    fontWeight: 600,
                    letterSpacing: '0.06em',
                    color: 'var(--accent)',
                    textTransform: 'uppercase',
                  }}>
                    Arms-length
                  </span>
                )}
              </div>
              {/* Second line: seller → buyer */}
              {(s.seller_name || s.buyer_name) && (
                <div style={{
                  color: 'var(--text-tertiary)',
                  marginTop: 2,
                  lineHeight: 1.4,
                }}>
                  {s.seller_name && s.seller_name}
                  {s.seller_name && s.buyer_name && ' → '}
                  {s.buyer_name && s.buyer_name}
                </div>
              )}
              {/* Third line (tertiary): instrument */}
              {s.instrument && (
                <div style={{
                  color: 'var(--text-tertiary)',
                  fontSize: 11,
                  marginTop: 1,
                  fontStyle: 'italic',
                }}>
                  {s.instrument}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {hiddenCount > 0 && (
        <button
          onClick={() => setExpanded(true)}
          style={{
            marginTop: 'var(--space-sm)',
            padding: '6px 10px',
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            background: 'transparent',
            color: 'var(--text-secondary)',
            cursor: 'pointer',
          }}
        >
          Show all {rows.length} transfers
        </button>
      )}
      {expanded && rows.length > 3 && (
        <button
          onClick={() => setExpanded(false)}
          style={{
            marginTop: 'var(--space-sm)',
            padding: '6px 10px',
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            background: 'transparent',
            color: 'var(--text-secondary)',
            cursor: 'pointer',
          }}
        >
          Collapse
        </button>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Helpers used by the operator card. Extracted to keep the component
// body focused on layout.
// ──────────────────────────────────────────────────────────────────────

// Title-case a raw uppercase name from court records. 'MATTHEW ARNOLD'
// becomes 'Matthew Arnold'. Leaves initialisms like LLC alone.
function _titleCaseName(raw) {
  if (!raw) return '';
  return String(raw)
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/\b(Llc|Llp|Inc|Corp|Lp|Co)\b/g, (m) => m.toUpperCase());
}

// Normalize a name for comparison — strip punctuation, collapse
// spaces, lowercase. Used to decide whether the parcel owner IS the
// decedent on a probate filing.
function _normalizeName(raw) {
  if (!raw) return '';
  return String(raw)
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

// Whether two name strings describe the same person. Conservative:
// we require first name + last name to both appear in the other
// string. 'Matthew Arnold' and 'Matthew L Arnold' match. 'Matthew
// Arnold' and 'Robert Arnold' do not.
function _samePerson(a, b) {
  const aa = _normalizeName(a);
  const bb = _normalizeName(b);
  if (!aa || !bb) return false;
  const aTokens = aa.split(' ').filter((t) => t.length > 1);
  const bTokens = bb.split(' ').filter((t) => t.length > 1);
  if (aTokens.length < 2 || bTokens.length < 2) return false;
  // First & last of A must both appear in B (or vice versa).
  const aFirst = aTokens[0];
  const aLast  = aTokens[aTokens.length - 1];
  const bFirst = bTokens[0];
  const bLast  = bTokens[bTokens.length - 1];
  return (bb.includes(aFirst) && bb.includes(aLast)) ||
         (aa.includes(bFirst) && aa.includes(bLast));
}

// Months elapsed between an ISO date and now. Negative means future.
function _monthsAgo(isoDate) {
  if (!isoDate) return null;
  const then = new Date(isoDate);
  if (isNaN(then)) return null;
  const now = new Date();
  return Math.round((now - then) / (1000 * 60 * 60 * 24 * 30.4));
}

// Generate the operator card content for a probate lead. Inputs are
// the full harvester match plus the parcel's owner_name so we can
// decide whether the owner IS the decedent (the common case) vs a
// surviving spouse / co-owner scenario.
//
// Uses the enriched fields that the /api/parcels/{pin} endpoint now
// attaches per-match:
//   personal_representative  — the identified heir-in-charge, or null
//   contact_status           — one of family_pr_identified,
//                               unworkable_pr, no_pr_yet,
//                               parties_not_scraped, not_applicable
//   all_case_parties         — full docket party list for context
function _buildProbateCard(match, parcel) {
  const decedentParty = (match.party_names || []).find(
    (p) => (p.role || '').toLowerCase() === 'decedent'
  );
  const decedentRaw = decedentParty?.raw || (match.party_names || [])[0]?.raw;
  const decedentDisplay = _titleCaseName(decedentRaw);
  const ownerName = parcel?.owner_name || parcel?.owner_name_raw;
  const ownerIsDecedent = _samePerson(decedentRaw, ownerName);

  const filed = match.event_date;
  const filedDisplay = filed
    ? new Date(filed).toLocaleDateString(undefined,
        { year: 'numeric', month: 'long', day: 'numeric' })
    : null;
  const caseNum = match.document_ref;
  const caseUrl = caseNum
    ? 'https://dja-prd-ecexap1.kingcounty.gov/node/501'
    : null;

  const monthsElapsed = _monthsAgo(filed);
  let timingPhrase = 'The estate is in the decision window.';
  if (monthsElapsed != null) {
    if (monthsElapsed < 2) {
      timingPhrase = 'Probate just opened. The estate is still appointing the personal representative.';
    } else if (monthsElapsed < 4) {
      timingPhrase = `Probate is ${monthsElapsed} months in — the personal representative is being appointed or has just been appointed.`;
    } else if (monthsElapsed < 10) {
      timingPhrase = `Probate is ${monthsElapsed} months in. Most estates decide on real property within the next 60–90 days.`;
    } else {
      timingPhrase = `Probate has been open ${monthsElapsed} months. The estate must resolve soon — the property decision is imminent or has already been made.`;
    }
  }

  // PR extraction. `personal_representative` is null when no PR has
  // been identified on the docket yet. When present, has name + first
  // name + last name + classification (family / attorney / corporate /
  // unknown) + role_source ('personal_representative' for formal
  // appointment, 'petitioner' for family member who filed to be
  // appointed — typically the incoming PR).
  const pr = match.personal_representative || null;
  const prDisplay = pr ? _titleCaseName(pr.name) : null;
  const prRoleLabel = pr
    ? (pr.role_source === 'personal_representative'
        ? 'Personal representative (appointed)'
        : 'Petitioner (likely incoming personal representative)')
    : null;
  const prClassLabel = pr?.classification === 'family'
    ? 'family member'
    : pr?.classification === 'attorney'
      ? 'attorney'
      : pr?.classification === 'corporate'
        ? 'corporate fiduciary'
        : null;

  // Other named parties on the docket when no PR is appointed yet —
  // filter out the decedent and any already-identified PR.
  const otherParties = (match.all_case_parties || []).filter((p) => {
    if (p.role === 'deceased') return false;
    if (pr && p.name_raw === pr.name) return false;
    return true;
  });

  const contactStatus = match.contact_status || 'parties_not_scraped';

  return {
    kind: 'probate',
    contactStatus,
    ownerIsDecedent,
    decedentDisplay,
    ownerName: _titleCaseName(ownerName),
    filedDisplay,
    caseNum,
    caseUrl,
    timingPhrase,
    pr,
    prDisplay,
    prRoleLabel,
    prClassLabel,
    otherParties,
  };
}

function RecommendedActionBlock({ rec, parcel, harvesterMatches }) {
  const toneColor = {
    urgent:     'var(--tone-urgent)',
    sensitive:  'var(--tone-sensitive)',
    relational: 'var(--tone-relational)',
    neutral:    'var(--tone-neutral)',
  }[rec.tone] || 'var(--accent)';

  // Identify whether we can render the operator card.
  //
  // Prefer a STRICT probate match. When found, the card is built
  // from real harvester data: decedent name, case number, filing
  // date. For non-probate leads or leads without a strict match we
  // fall back to the original one-line analyst summary so we don't
  // regress behavior on divorce / tax-foreclosure cases until those
  // operator cards are built.
  const probateMatch = (harvesterMatches || []).find(
    (m) => m.signal_type === 'probate' && m.match_strength === 'strict'
  );
  const card = probateMatch ? _buildProbateCard(probateMatch, parcel) : null;

  const headerLabel = `Recommended action — ${rec.category.replace('_', ' ')}`;

  return (
    <div style={{
      marginTop: 'var(--space-lg)',
      padding: 'var(--space-md)',
      borderLeft: `3px solid ${toneColor}`,
      background: 'var(--bg)',
    }}>
      <div style={{
        fontSize: 11,
        color: toneColor,
        fontWeight: 700,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
      }}>
        {headerLabel}
      </div>

      {card && card.kind === 'probate' ? (
        <OperatorProbateCard card={card} />
      ) : (
        <>
          {rec.reason && (
            <div style={{
              fontFamily: 'var(--font-serif)',
              fontSize: 13,
              color: 'var(--text-secondary)',
              marginTop: 'var(--space-xs)',
              fontStyle: 'italic',
            }}>
              {rec.reason}
            </div>
          )}
          {rec.next_step && (
            <div style={{
              fontSize: 14,
              color: 'var(--text)',
              marginTop: 'var(--space-sm)',
              fontWeight: 500,
            }}>
              → {rec.next_step}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// Sub-component: operator-format probate card. Branches on
// contact_status so the agent sees a different call-to-action
// depending on whether a workable PR has been identified:
//   family_pr_identified — CALL [PR NAME], full action card
//   no_pr_yet            — docket exists but no PR appointed;
//                          show other named parties, direct agent
//                          to monitor
//   parties_not_scraped  — case exists, parties haven't been
//                          harvested yet; direct agent to docket
//   unworkable_pr        — corporate/attorney PR, acknowledge
//                          limited workability
//   pr_unknown_classification — PR exists but classification wasn't
//                          determinable; treat conservatively
function OperatorProbateCard({ card }) {
  const section = (label, body, key) => (
    <div key={key} style={{ marginTop: 'var(--space-sm)' }}>
      <div style={{
        fontSize: 10,
        color: 'var(--text-tertiary)',
        fontWeight: 700,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        marginBottom: 3,
      }}>
        {label}
      </div>
      <div style={{
        fontSize: 13,
        color: 'var(--text)',
        lineHeight: 1.5,
        fontFamily: 'var(--font-serif)',
      }}>
        {body}
      </div>
    </div>
  );

  // Common context line: probate filed + case number. Used by all
  // status variants below.
  const contextLine = (card.filedDisplay || card.caseNum) && (
    <div style={{
      marginTop: 'var(--space-xs)',
      fontSize: 12,
      color: 'var(--text-tertiary)',
    }}>
      Re: estate of {card.decedentDisplay}
      {card.filedDisplay && <> · Probate filed {card.filedDisplay}</>}
      {card.caseNum && (
        <> · King County Superior Court, case {card.caseNum}</>
      )}
    </div>
  );

  // Urgency badge — top-right of card. Uses the toneColor palette
  // already in use in RecommendedActionBlock.
  const urgencyBadge = (level, color) => (
    <div style={{
      marginTop: 'var(--space-xs)',
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: 3,
      background: color,
      color: 'white',
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: '0.1em',
      textTransform: 'uppercase',
      fontFamily: 'var(--font-sans)',
    }}>
      {level}
    </div>
  );

  // ── Variant A: family_pr_identified — full CALL NOW card ──
  if (card.contactStatus === 'family_pr_identified' && card.pr) {
    return (
      <div style={{ marginTop: 'var(--space-sm)' }}>
        {/* PRIMARY CTA — the thing that can't be missed. */}
        <div style={{
          fontSize: 22,
          color: 'var(--text)',
          fontFamily: 'var(--font-serif)',
          fontWeight: 700,
          lineHeight: 1.2,
          marginTop: 'var(--space-xs)',
        }}>
          Call {card.prDisplay}
        </div>
        <div style={{
          fontSize: 12,
          color: 'var(--text-secondary)',
          marginTop: 2,
          fontStyle: 'italic',
          fontFamily: 'var(--font-serif)',
        }}>
          {card.prRoleLabel}
          {card.prClassLabel && ` · ${card.prClassLabel}`}
        </div>

        {urgencyBadge('High · decision window active', 'var(--tone-sensitive)')}

        {contextLine}

        {section('Contact',
          <div>
            <div style={{ color: 'var(--text-tertiary)' }}>
              Mailing address: not yet resolved
            </div>
            <div style={{
              marginTop: 4,
              fontSize: 11,
              color: 'var(--text-tertiary)',
              fontStyle: 'italic',
            }}>
              Auto-resolution coming in next release · beta
            </div>
          </div>,
          'contact'
        )}

        {section('Why now',
          <>
            {card.prDisplay} controls the estate's decision on this
            property. {card.timingPhrase}
          </>,
          'why'
        )}

        {section('Script',
          <div style={{
            padding: 'var(--space-sm)',
            background: 'var(--bg-card)',
            borderRadius: 'var(--radius-sm)',
            fontStyle: 'italic',
            lineHeight: 1.5,
          }}>
            &ldquo;Hi {card.pr.name_first ? _titleCaseName(card.pr.name_first) : card.prDisplay} — I came across the estate filing for {card.decedentDisplay}. I&rsquo;m very sorry for your loss. I work with families navigating property decisions during probate and wanted to offer help if it&rsquo;s useful — no pressure at all.&rdquo;
          </div>,
          'script'
        )}

        {section('Next step',
          <strong>Send a handwritten condolence letter.</strong>,
          'next'
        )}
      </div>
    );
  }

  // ── Variant B: no_pr_yet — WATCH / PREP card ──
  if (card.contactStatus === 'no_pr_yet') {
    return (
      <div style={{ marginTop: 'var(--space-sm)' }}>
        <div style={{
          fontSize: 18,
          color: 'var(--text)',
          fontFamily: 'var(--font-serif)',
          fontWeight: 600,
          lineHeight: 1.3,
          marginTop: 'var(--space-xs)',
        }}>
          Wait — no decision-maker yet
        </div>
        <div style={{
          fontSize: 12,
          color: 'var(--text-secondary)',
          marginTop: 2,
          fontStyle: 'italic',
          fontFamily: 'var(--font-serif)',
        }}>
          {card.ownerIsDecedent
            ? `${card.ownerName} is deceased. Personal representative not yet appointed.`
            : `${card.decedentDisplay} is deceased. Personal representative not yet appointed.`}
        </div>

        {urgencyBadge('Watch · will convert when PR is appointed', 'var(--accent)')}

        {contextLine}

        {section('Why this still matters',
          <>{card.timingPhrase} A personal representative will be appointed soon — typically a close family member.</>,
          'why'
        )}

        {section('Next step',
          <strong>Hold for now. We will surface this lead automatically once a personal representative is appointed.</strong>,
          'next'
        )}
      </div>
    );
  }

  // ── Variant C: parties_not_scraped — data gap ──
  if (card.contactStatus === 'parties_not_scraped') {
    return (
      <div style={{ marginTop: 'var(--space-sm)' }}>
        <div style={{
          fontSize: 18,
          color: 'var(--text)',
          fontFamily: 'var(--font-serif)',
          fontWeight: 600,
          lineHeight: 1.3,
          marginTop: 'var(--space-xs)',
        }}>
          Lead pending — case parties resolving
        </div>
        <div style={{
          fontSize: 12,
          color: 'var(--text-secondary)',
          marginTop: 2,
          fontStyle: 'italic',
          fontFamily: 'var(--font-serif)',
        }}>
          {card.ownerIsDecedent
            ? `${card.ownerName} is deceased.`
            : `Probate filing active for ${card.decedentDisplay}.`}
        </div>

        {urgencyBadge('Watch · pending data', 'var(--text-tertiary)')}

        {contextLine}

        {section('Why now', card.timingPhrase, 'why')}

        {section('Next step',
          <strong>Hold for now. We will surface this lead automatically once the personal representative is identified.</strong>,
          'next'
        )}
      </div>
    );
  }

  // ── Variant D: unworkable_pr — corporate/attorney PR ──
  if (card.contactStatus === 'unworkable_pr' && card.pr) {
    return (
      <div style={{ marginTop: 'var(--space-sm)' }}>
        <div style={{
          fontSize: 18,
          color: 'var(--text)',
          fontFamily: 'var(--font-serif)',
          fontWeight: 600,
          lineHeight: 1.3,
          marginTop: 'var(--space-xs)',
        }}>
          Monitor — direct outreach unlikely to convert
        </div>
        <div style={{
          fontSize: 12,
          color: 'var(--text-secondary)',
          marginTop: 2,
          fontStyle: 'italic',
          fontFamily: 'var(--font-serif)',
        }}>
          Personal representative is {card.prClassLabel || 'corporate / attorney'} ({card.prDisplay})
        </div>

        {urgencyBadge('Low · track for listing', 'var(--text-tertiary)')}

        {contextLine}

        {section('Why this still matters',
          <>{card.timingPhrase} Corporate fiduciaries and attorney PRs usually list through established channels.</>,
          'why'
        )}

        {section('Next step',
          <strong>Hold. Watch for listing activity on this parcel.</strong>,
          'next'
        )}
      </div>
    );
  }

  // ── Fallback: pr_unknown_classification or anything else ──
  return (
    <div style={{ marginTop: 'var(--space-sm)' }}>
      <div style={{
        fontSize: 18,
        color: 'var(--text)',
        fontFamily: 'var(--font-serif)',
        fontWeight: 600,
        lineHeight: 1.3,
        marginTop: 'var(--space-xs)',
      }}>
        {card.ownerIsDecedent
          ? `${card.ownerName} is deceased. Probate active.`
          : `Probate filing active for ${card.decedentDisplay}.`}
      </div>
      {urgencyBadge('Watch · pending data', 'var(--text-tertiary)')}
      {contextLine}
      {section('Why now', card.timingPhrase, 'why')}
      {section('Next step',
        <strong>Hold. We will surface this lead automatically once the personal representative is identified.</strong>,
        'next'
      )}
    </div>
  );
}

function WhyNotSellingBlock({ why }) {
  return (
    <div style={{
      marginTop: 'var(--space-lg)',
      padding: 'var(--space-md)',
      background: 'var(--bg)',
      borderRadius: 'var(--radius-md)',
    }}>
      <div style={{
        fontSize: 11,
        color: 'var(--text-tertiary)',
        fontWeight: 600,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
      }}>
        Why this isn&rsquo;t a seller yet
      </div>
      <p style={{
        fontFamily: 'var(--font-serif)',
        fontSize: 14,
        color: 'var(--text)',
        lineHeight: 1.5,
        marginTop: 'var(--space-sm)',
      }}>
        {why.why_not_selling}
      </p>

      {why.what_could_change_this?.length > 0 && (
        <div style={{ marginTop: 'var(--space-md)' }}>
          <div style={{
            fontSize: 11,
            color: 'var(--text-tertiary)',
            fontWeight: 600,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}>
            What could change this
          </div>
          <ul style={{
            listStyle: 'none',
            marginTop: 'var(--space-sm)',
          }}>
            {why.what_could_change_this.map((s, i) => (
              <li
                key={i}
                style={{
                  fontFamily: 'var(--font-serif)',
                  fontSize: 13,
                  color: 'var(--text-secondary)',
                  padding: '3px 0',
                  paddingLeft: 'var(--space-md)',
                  position: 'relative',
                }}
              >
                <span style={{
                  position: 'absolute',
                  left: 0,
                  color: 'var(--accent)',
                }}>·</span>
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {why.transition_window && (
        <div style={{
          marginTop: 'var(--space-md)',
          fontSize: 12,
          color: 'var(--text-tertiary)',
          fontStyle: 'italic',
          fontFamily: 'var(--font-serif)',
        }}>
          {why.transition_window}
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// EvidenceBlock — unified panel replacing the old split of
// HarvesterMatchesBlock (harvester_matches) + SignalsBlock (inv.signals).
//
// Sources:
//   - harvesterMatches[]: from the free authoritative pipelines
//     (KC Superior Court probate/divorce, obituary RSS, KC Treasurer
//     tax foreclosure). Has structured party_names, document_ref,
//     event_date, match_strength (strict/weak).
//   - serpSignals[]: from the legacy SerpAPI investigator, only for
//     the signal types harvesters don't cover yet (previously_listed,
//     linkedin_found, retirement, age_found, etc.). Has source_url,
//     source_title, source_snippet, trust (high/medium/low).
//
// Normalization: every row becomes { label, authority, detail, party,
//     when, ref, url, trust } regardless of source pipeline. The UI
//     renders a single consistent list.
//
// Ordering:
//   1. Harvester STRICT matches (authoritative + high-confidence name match)
//   2. Harvester WEAK matches
//   3. SerpAPI HIGH trust
//   4. SerpAPI MEDIUM trust
//   5. SerpAPI LOW trust
//
// Deduplication: serp signals whose type matches a harvester match
// (probate, obituary, divorce, financial_distress) are dropped from
// the serp side — the harvester row is authoritative. Phase 1
// already removed these serp builders at the source; this is
// belt-and-suspenders for any cached legacy signals.
//
// Convergence: when `convergence` is true (2+ distinct harvester
// signal types on the same pin), show a CONVERGED badge at the top.
// Example: probate + obituary for the same decedent is a strong
// converged signal of an imminent sale.
// ──────────────────────────────────────────────────────────────────────
function EvidenceBlock({ harvesterMatches, serpSignals, convergence }) {
  // Harvester signal types that take precedence over their serp
  // equivalents. If a harvester match exists for one of these types,
  // serp signals of the same type are suppressed.
  const HARVESTER_PRIMARY_TYPES = new Set([
    'probate', 'obituary', 'divorce', 'tax_foreclosure', 'financial_distress',
  ]);

  // Map backend signal types to readable labels.
  const harvesterLabel = {
    probate:         'Probate filing',
    obituary:        'Obituary match',
    divorce:         'Divorce filing',
    tax_foreclosure: 'Tax foreclosure',
  };

  // SerpAPI signal types → labels. Deliberately does NOT include the
  // types that harvesters authoritatively cover.
  const serpLabel = (t) => {
    if (!t) return '';
    return String(t).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  };

  // Render the primary party name from a harvester match's
  // party_names array. Role priority: decedent > petitioner > party >
  // parcel_only > first entry.
  const renderHarvesterParty = (parties) => {
    if (!Array.isArray(parties) || parties.length === 0) return null;
    for (const role of ['decedent', 'petitioner', 'party', 'parcel_only']) {
      const hit = parties.find((p) => p && (p.role || '').toLowerCase() === role);
      if (hit && hit.raw) return hit.raw;
    }
    return parties[0]?.raw || null;
  };

  // Format ISO date to a friendly short date.
  const formatWhen = (iso) => {
    if (!iso) return null;
    try {
      const d = new Date(iso);
      if (isNaN(d)) return iso;
      return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    } catch { return iso; }
  };

  // Extract hostname for SerpAPI source links.
  const hostOf = (url) => {
    if (!url) return null;
    try { return new URL(url).hostname.replace(/^www\./, ''); }
    catch { return url; }
  };

  // Normalize both pipelines to a common row shape.
  const harvesterRows = (harvesterMatches || []).map((m) => {
    const strong = m.match_strength === 'strict';
    return {
      source:      'harvester',
      label:       harvesterLabel[m.signal_type] || serpLabel(m.signal_type),
      type:        m.signal_type,
      authority:   strong ? 'STRICT' : 'WEAK',
      authorityColor: strong ? 'var(--accent)' : 'var(--text-tertiary)',
      party:       renderHarvesterParty(m.party_names),
      when:        formatWhen(m.event_date),
      sourceType:  m.source_type,
      ref:         m.document_ref,
      url:         m.source_url,  // when present (e.g., obit RSS link)
      // Sort key: lower = higher priority. Strict = 0, weak = 1.
      sortRank:    strong ? 0 : 1,
      key:         `h-${m.signal_type}-${m.document_ref || m.event_date || Math.random()}`,
    };
  });

  // Keep only serp signals whose types aren't covered by harvesters.
  // Already minimal after Phase 1, but this is a safety net in case
  // old inv.signals rows linger in the DB.
  const dedupedSerpSignals = (serpSignals || []).filter(
    (s) => s?.type && !HARVESTER_PRIMARY_TYPES.has(s.type)
  );

  const serpRows = dedupedSerpSignals.map((s, i) => {
    const trustRank = { high: 2, medium: 3, low: 4 }[s.trust] ?? 4;
    const trustColor = {
      high:   'var(--hold)',
      medium: 'var(--accent)',
      low:    'var(--text-tertiary)',
    }[s.trust] || 'var(--text-tertiary)';
    return {
      source:      'serp',
      label:       serpLabel(s.type),
      type:        s.type,
      authority:   (s.trust || 'LOW').toUpperCase(),
      authorityColor: trustColor,
      // SerpAPI signals carry detail (human-readable explanation) +
      // source_title (actual page title, e.g., obituary headline) +
      // source_snippet (matched text excerpt).
      detail:      s.detail,
      sourceTitle: s.source_title,
      sourceSnippet: s.source_snippet,
      url:         s.source_url,
      sortRank:    trustRank,
      key:         `s-${s.type}-${i}`,
    };
  });

  const rows = [...harvesterRows, ...serpRows].sort(
    (a, b) => a.sortRank - b.sortRank
  );

  if (rows.length === 0) return null;

  return (
    <div style={{
      marginTop: 'var(--space-lg)',
      padding: 'var(--space-md)',
      background: 'var(--bg)',
      borderLeft: `3px solid ${convergence ? 'var(--call-now)' : 'var(--accent)'}`,
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'baseline',
        justifyContent: 'space-between',
        gap: 'var(--space-sm)',
        marginBottom: 'var(--space-sm)',
      }}>
        <div style={{
          fontSize: 11,
          color: 'var(--text-tertiary)',
          fontWeight: 700,
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
        }}>
          Evidence ({rows.length})
        </div>
        {convergence && (
          <span style={{
            fontSize: 9,
            fontWeight: 700,
            letterSpacing: '0.08em',
            padding: '2px 6px',
            borderRadius: 3,
            background: 'var(--call-now)',
            color: 'white',
            fontFamily: 'var(--font-sans)',
          }}>
            CONVERGED
          </span>
        )}
      </div>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {rows.map((r, i) => (
          <li
            key={r.key}
            style={{
              padding: 'var(--space-sm) 0',
              borderBottom: i < rows.length - 1 ? '1px solid var(--border)' : 'none',
              fontSize: 12,
            }}
          >
            {/* Top line: label + authority badge */}
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'baseline',
              gap: 'var(--space-sm)',
            }}>
              <span style={{
                fontWeight: 600,
                color: 'var(--text)',
                letterSpacing: '0.02em',
              }}>
                {r.label}
              </span>
              <span style={{
                fontSize: 9,
                fontWeight: 700,
                letterSpacing: '0.08em',
                padding: '1px 5px',
                borderRadius: 3,
                background: r.source === 'harvester' && r.authority === 'STRICT'
                  ? r.authorityColor : 'transparent',
                color: r.source === 'harvester' && r.authority === 'STRICT'
                  ? 'white' : r.authorityColor,
                border: r.source === 'harvester' && r.authority === 'STRICT'
                  ? 'none' : `1px solid ${r.authorityColor}`,
                fontFamily: 'var(--font-sans)',
              }}>
                {r.authority}
              </span>
            </div>

            {/* Harvester-specific: party name in italic serif */}
            {r.party && (
              <div style={{
                color: 'var(--text-secondary)',
                marginTop: 3,
                fontFamily: 'var(--font-serif)',
                fontStyle: 'italic',
                lineHeight: 1.4,
              }}>
                {r.party}
              </div>
            )}

            {/* Harvester: when + source type */}
            {(r.when || r.sourceType) && (
              <div style={{
                display: 'flex',
                gap: 'var(--space-md)',
                marginTop: 3,
                fontSize: 11,
                color: 'var(--text-tertiary)',
              }}>
                {r.when && <span>{r.when}</span>}
                {r.sourceType && <span>{r.sourceType.replace(/_/g, ' ')}</span>}
              </div>
            )}

            {/* Harvester: case/document reference in monospace */}
            {r.ref && (
              <div style={{
                marginTop: 2,
                fontSize: 10,
                color: 'var(--text-tertiary)',
                fontFamily: 'monospace',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {r.ref}
              </div>
            )}

            {/* SerpAPI-specific: human-readable detail fallback */}
            {r.detail && (
              <div style={{
                color: 'var(--text-secondary)',
                marginTop: 3,
                fontFamily: 'var(--font-serif)',
                lineHeight: 1.4,
              }}>
                {r.detail}
              </div>
            )}

            {/* SerpAPI-specific: matched page title in italic quotes */}
            {r.sourceTitle && (
              <div style={{
                color: 'var(--text)',
                marginTop: 4,
                fontFamily: 'var(--font-serif)',
                fontStyle: 'italic',
                lineHeight: 1.4,
              }}>
                "{r.sourceTitle}"
              </div>
            )}

            {/* SerpAPI-specific: matched snippet text */}
            {r.sourceSnippet && (
              <div style={{
                color: 'var(--text-tertiary)',
                marginTop: 3,
                fontSize: 11,
                lineHeight: 1.4,
              }}>
                {r.sourceSnippet}
              </div>
            )}

            {/* Universal: clickable source link when available */}
            {r.url && (
              <div style={{ marginTop: 4 }}>
                <a
                  href={r.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  style={{
                    color: 'var(--accent)',
                    fontSize: 11,
                    textDecoration: 'none',
                    borderBottom: '1px dotted var(--accent)',
                  }}
                >
                  {hostOf(r.url) || 'view source'} →
                </a>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}


// Dossier block rendering parcel-state tags (HIGH EQUITY, DEEP TENURE,
// LEGACY HOLD, MATURE LLC). These are derived at read time from
// parcels_v3 columns — no harvester match required. Each tag has a
// human-readable description for the hover state + inline body.
function ParcelStateTagsBlock({ tags }) {
  return (
    <div style={{ marginTop: 'var(--space-lg)' }}>
      <div style={{
        fontSize: 11,
        color: 'var(--text-tertiary)',
        fontWeight: 600,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        marginBottom: 'var(--space-sm)',
      }}>
        Parcel State
      </div>
      <ul style={{
        listStyle: 'none',
        padding: 0,
        margin: 0,
      }}>
        {tags.map((t) => (
          <li key={t.kind} style={{
            padding: 'var(--space-sm) 0',
            borderTop: '1px solid var(--border-subtle)',
          }}>
            <div style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: 8,
              marginBottom: 2,
            }}>
              <span style={{
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: '0.08em',
                padding: '2px 6px',
                borderRadius: 3,
                border: '1px solid var(--text-tertiary)',
                color: 'var(--text-tertiary)',
                whiteSpace: 'nowrap',
              }}>
                {t.label}
              </span>
            </div>
            {t.description && (
              <div style={{
                fontSize: 13,
                color: 'var(--text-secondary)',
                lineHeight: 1.4,
                marginLeft: 2,
              }}>
                {t.description}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}


