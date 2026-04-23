import { useEffect, useState } from 'react';
import { map as mapApi, deepSignal as deepSignalApi } from '../api/client.js';
import SixLettersModal from './SixLettersModal.jsx';

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

function ownerTypeLabel(t) {
  if (!t || t === 'unknown') return null;
  const map = { llc: 'LLC', trust: 'Trust', individual: 'Individual', company: 'Company' };
  return map[t.toLowerCase()] || t;
}

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

  const ownerTag = ownerTypeLabel(p.owner_type);
  const signalLabel = p.signal_family ? p.signal_family.replace(/_/g, ' ') : null;

  // Deep Signal is only available for investigated parcels (those with signals).
  // The endpoint returns 409 for uninvestigated parcels — hide the button rather
  // than letting the user click into an error.
  const canGenerateDeepSignal = Boolean(inv?.signals?.length);

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
            {p.is_absentee && (
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

        {/* Recommended action — if investigated */}
        {rec && rec.category && rec.category !== 'hold' && (
          <RecommendedActionBlock rec={rec} />
        )}

        {/* Harvester matches — itemized list of obit / probate / divorce /
            tax_foreclosure signals that fired on this pin. Shown when ANY
            match exists; the block also surfaces a "converged" indicator
            at the top when 2+ strict signals hit the same pin. */}
        {harvesterMatches.length > 0 && (
          <HarvesterMatchesBlock
            matches={harvesterMatches}
            convergence={hasConvergence}
          />
        )}

        {/* Action buttons — Deep Signal + Six Letters */}
        {canGenerateDeepSignal && (
          <ActionButtons
            hasDeepSignal={Boolean(deepSignal)}
            deepSignalLoading={deepSignalLoading}
            onGenerateDeepSignal={handleGenerateDeepSignal}
            onOpenSixLetters={() => setSixLettersOpen(true)}
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

        {/* Transfer history — if we have it */}
        {(p.last_transfer_date || p.last_transfer_price) && (
          <TransferHistoryBlock parcel={p} />
        )}

        {/* Why not selling — auto-generated read for non-actionable parcels */}
        {why && (
          <WhyNotSellingBlock why={why} />
        )}

        {/* Investigation signals, if present */}
        {inv?.signals?.length > 0 && (
          <SignalsBlock signals={inv.signals} />
        )}
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
function ActionButtons({ hasDeepSignal, deepSignalLoading, onGenerateDeepSignal, onOpenSixLetters }) {
  return (
    <div style={{
      marginTop: 'var(--space-lg)',
      display: 'flex',
      gap: 'var(--space-sm)',
    }}>
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
  const rows = [
    { label: 'Cohort',          value: signalLabel || '—' },
    { label: 'County assessed', value: parcel.total_value ? formatValue(parcel.total_value) : '—' },
    { label: 'Tenure',          value: formatYears(parcel.tenure_years) },
    { label: 'Property type',   value: parcel.prop_type || 'Residential' },
  ];
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

function TransferHistoryBlock({ parcel }) {
  const ago = parcel.tenure_years != null ? ` (${formatYears(parcel.tenure_years)} ago)` : '';
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
        Last sale: {formatDate(parcel.last_transfer_date)}{ago}
        {parcel.last_transfer_price && (
          <span style={{ color: 'var(--text-secondary)' }}>
            {' · '}
            {formatValue(parcel.last_transfer_price)}
          </span>
        )}
      </div>
    </div>
  );
}

function RecommendedActionBlock({ rec }) {
  const toneColor = {
    urgent:     'var(--tone-urgent)',
    sensitive:  'var(--tone-sensitive)',
    relational: 'var(--tone-relational)',
    neutral:    'var(--tone-neutral)',
  }[rec.tone] || 'var(--accent)';

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
        Recommended action — {rec.category.replace('_', ' ')}
      </div>
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

function HarvesterMatchesBlock({ matches, convergence }) {
  // Map backend signal types to readable labels + soft color cues.
  // Keep all four variants here (probate, obituary, divorce, tax_foreclosure).
  const signalMeta = {
    probate:          { label: 'Probate filing',    family: 'death_inheritance' },
    obituary:         { label: 'Obituary match',    family: 'death_inheritance' },
    divorce:          { label: 'Divorce filing',    family: 'divorce_unwinding' },
    tax_foreclosure:  { label: 'Tax foreclosure',   family: 'financial_stress' },
  };

  // Format the primary matched party from the signal's party_names array.
  // Role priority: decedent > petitioner > party > parcel_only > first entry.
  const renderParty = (parties) => {
    if (!Array.isArray(parties) || parties.length === 0) return null;
    const byRolePreference = ['decedent', 'petitioner', 'party', 'parcel_only'];
    for (const role of byRolePreference) {
      const hit = parties.find((p) => p && (p.role || '').toLowerCase() === role);
      if (hit && hit.raw) return hit.raw;
    }
    return parties[0]?.raw || null;
  };

  const formatEventDate = (iso) => {
    if (!iso) return null;
    try {
      const d = new Date(iso);
      if (isNaN(d)) return iso;
      return d.toLocaleDateString(undefined, {
        year: 'numeric', month: 'short', day: 'numeric',
      });
    } catch { return iso; }
  };

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
          Active signals ({matches.length})
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
      <ul style={{ listStyle: 'none' }}>
        {matches.map((m, i) => {
          const meta  = signalMeta[m.signal_type] || { label: m.signal_type, family: null };
          const party = renderParty(m.party_names);
          const when  = formatEventDate(m.event_date);
          const strong = m.match_strength === 'strict';
          return (
            <li
              key={`${m.signal_type}-${m.document_ref || i}`}
              style={{
                padding: 'var(--space-sm) 0',
                borderBottom: i < matches.length - 1 ? '1px solid var(--border)' : 'none',
                fontSize: 12,
              }}
            >
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'baseline',
                gap: 'var(--space-sm)',
              }}>
                <span style={{ fontWeight: 500, color: 'var(--text)' }}>
                  {meta.label}
                </span>
                <span style={{
                  fontSize: 9,
                  fontWeight: 700,
                  letterSpacing: '0.08em',
                  padding: '1px 5px',
                  borderRadius: 3,
                  background: strong ? 'var(--accent)' : 'transparent',
                  color:       strong ? 'white'        : 'var(--text-tertiary)',
                  border:      strong ? 'none'         : '1px solid var(--text-tertiary)',
                  fontFamily: 'var(--font-sans)',
                }}>
                  {strong ? 'STRICT' : 'WEAK'}
                </span>
              </div>
              {party && (
                <div style={{
                  color: 'var(--text-secondary)',
                  marginTop: 2,
                  fontFamily: 'var(--font-serif)',
                  fontStyle: 'italic',
                }}>
                  {party}
                </div>
              )}
              <div style={{
                display: 'flex',
                gap: 'var(--space-md)',
                marginTop: 2,
                fontSize: 11,
                color: 'var(--text-tertiary)',
              }}>
                {when && <span>{when}</span>}
                {m.source_type && <span>{m.source_type.replace(/_/g, ' ')}</span>}
              </div>
              {m.document_ref && (
                <div style={{
                  marginTop: 2,
                  fontSize: 10,
                  color: 'var(--text-tertiary)',
                  fontFamily: 'monospace',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}>
                  {m.document_ref}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}


function SignalsBlock({ signals }) {
  const trustColor = { high: 'var(--hold)', medium: 'var(--accent)', low: 'var(--text-tertiary)' };
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
        Evidence ({signals.length})
      </div>
      <ul style={{ listStyle: 'none' }}>
        {signals.map((s, i) => (
          <li key={i} style={{
            padding: 'var(--space-sm) 0',
            borderBottom: i < signals.length - 1 ? '1px solid var(--border)' : 'none',
            fontSize: 12,
          }}>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'baseline',
              gap: 'var(--space-sm)',
            }}>
              <span style={{ fontWeight: 500, color: 'var(--text)' }}>
                {s.type}
              </span>
              <span style={{
                fontSize: 10,
                color: trustColor[s.trust] || 'var(--text-tertiary)',
                fontWeight: 600,
                letterSpacing: '0.05em',
                textTransform: 'uppercase',
              }}>
                {s.trust}
              </span>
            </div>
            {s.detail && (
              <div style={{
                color: 'var(--text-secondary)',
                marginTop: 2,
                fontFamily: 'var(--font-serif)',
              }}>
                {s.detail}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
