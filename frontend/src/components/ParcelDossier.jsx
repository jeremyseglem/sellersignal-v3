import { useEffect, useState } from 'react';
import { map as mapApi } from '../api/client.js';

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

  useEffect(() => {
    if (!dossier?.pin) return;
    setStreetViewUrl(null); setStreetViewOk(true);
    mapApi.streetView(dossier.pin)
      .then((r) => setStreetViewUrl(r.url))
      .catch(() => setStreetViewUrl(null));
  }, [dossier?.pin]);

  const p   = dossier.parcel || {};
  const inv = dossier.investigation || {};
  const rec = dossier.recommended_action;
  const why = dossier.why_not_selling;

  const ownerTag = ownerTypeLabel(p.owner_type);
  const signalLabel = p.signal_family ? p.signal_family.replace(/_/g, ' ') : null;

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
