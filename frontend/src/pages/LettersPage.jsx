/**
 * Letters page (route: /letters).
 *
 * Agent-wide aggregated view of every letter sequence and standalone
 * single-send. Companion to My Leads — where My Leads is the
 * pipeline view ("what leads am I working"), this is the outreach
 * activity view ("what mail did I send and what's happening with it").
 *
 * Backed by GET /api/letters/sequences-by-agent — one round-trip,
 * server returns pre-aggregated rows + filter counts + summary totals.
 *
 * Behavior:
 *   - One row per sequence (or per standalone single-send).
 *   - Sorted newest-started first by default.
 *   - Filter chips for status (active/completed/cancelled) and
 *     activity (has delivered / has returned / has failed / has
 *     scheduled pending). Multi-select within group, AND across
 *     groups. Chips with zero hits are hidden.
 *   - Per-row: progress bar (X of N sent), latest event with
 *     relative timestamp, next scheduled date, view + cancel actions.
 *   - Click row → navigate to the parcel briefing with the dossier
 *     pre-opened, same pattern as My Leads.
 *
 * Cancel flow: confirm dialog → POST /api/letters/cancel-sequence/{id}
 * → optimistic local update (mark cancelled) + refetch to get the
 * server-side refund amount and updated counts.
 */
import { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';

import SiteLayout from '../components/shell/SiteLayout.jsx';
import { letters as lettersApi, safeErrorMessage } from '../api/client.js';
import { useAuth } from '../lib/AuthContext.jsx';


// Filter chips. Order is intentional: most-actionable signals first
// (returned/failed), then high-signal (delivered), then routine
// (active, scheduled, completed, cancelled). Tone drives the active-
// chip color via the same _TONE_* maps as My Leads.
const STATUS_FILTERS = [
  { key: 'has_returned',      label: 'Has returned',      tone: 'alert'   },
  { key: 'has_failed',        label: 'Has failed',        tone: 'alert'   },
  { key: 'has_delivered',     label: 'Has delivered',     tone: 'success' },
  { key: 'active',            label: 'Active',            tone: 'accent'  },
  { key: 'scheduled_pending', label: 'Scheduled pending', tone: 'neutral' },
  { key: 'completed',         label: 'Completed',         tone: 'neutral' },
  { key: 'cancelled',         label: 'Cancelled',         tone: 'neutral' },
];


export default function LettersPage() {
  const { profile, signOut } = useAuth();
  const navigate = useNavigate();

  const [data, setData]         = useState(null);
  const [error, setError]       = useState(null);
  const [search, setSearch]     = useState('');
  const [selectedFilters, setSelectedFilters] = useState([]);
  const [cancellingId, setCancellingId] = useState(null);

  const refresh = () => {
    lettersApi.sequencesByAgent()
      .then(setData)
      .catch((e) => setError(safeErrorMessage(e, 'Failed to load letters')));
  };

  useEffect(() => {
    refresh();
  }, []);

  const handleToggleFilter = (key) => {
    setSelectedFilters((prev) => (
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    ));
  };

  const handleCancel = async (sequence_id, label) => {
    if (!sequence_id) return; // standalone single-sends can't be cancelled
    const ok = window.confirm(
      `Cancel sequence for ${label}?\n\nUnmailed letters will not be sent. ` +
      `You'll be refunded proportionally for letters that haven't gone out yet. ` +
      `Letters already in the mail can't be recalled.`
    );
    if (!ok) return;
    setCancellingId(sequence_id);
    try {
      await lettersApi.cancelSequence(sequence_id);
      // Refresh so we see server-confirmed status + refund.
      refresh();
    } catch (e) {
      alert(safeErrorMessage(e, 'Cancel failed'));
    } finally {
      setCancellingId(null);
    }
  };

  // Filter + search applied client-side; server already sorts by
  // started_at desc.
  const visibleSequences = useMemo(() => {
    if (!data?.sequences) return [];
    const q = search.trim().toLowerCase();

    const matchesFilter = (s, key) => {
      switch (key) {
        case 'active':            return s.status === 'active';
        case 'completed':         return s.status === 'completed';
        case 'cancelled':         return s.status === 'cancelled';
        case 'has_delivered':     return (s.letters_delivered || 0) > 0;
        case 'has_returned':      return (s.letters_returned  || 0) > 0;
        case 'has_failed':        return (s.letters_failed    || 0) > 0;
        case 'scheduled_pending': return (s.letters_scheduled || 0) > 0;
        default: return false;
      }
    };

    return data.sequences.filter((s) => {
      if (q) {
        const hay = [s.address, s.owner_name, s.pin, s.city]
          .filter(Boolean).join(' ').toLowerCase();
        if (!hay.includes(q)) return false;
      }
      if (selectedFilters.length > 0) {
        if (!selectedFilters.some((k) => matchesFilter(s, k))) {
          return false;
        }
      }
      return true;
    });
  }, [data, search, selectedFilters]);

  return (
    <SiteLayout agent={profile} onSignOut={signOut} showFooter={false}>
      <div style={containerStyle}>
        <div style={pageHeaderStyle}>
          <div>
            <h1 style={titleStyle}>Letters</h1>
            {data && (
              <div style={subtitleStyle}>
                {data.totals.total_sequences === 0
                  ? 'No letters sent yet — start a sequence from any parcel dossier.'
                  : `${data.totals.total_sequences} sequence${data.totals.total_sequences === 1 ? '' : 's'} · ${data.totals.total_sent} letter${data.totals.total_sent === 1 ? '' : 's'} sent`}
                {data.totals.total_delivered > 0 && (
                  <>{' · '}<span style={{ color: 'var(--success, #5C7A3B)' }}>{data.totals.total_delivered} delivered</span></>
                )}
                {data.totals.total_scheduled > 0 && (
                  <>{' · '}<span style={{ color: 'var(--text-tertiary)' }}>{data.totals.total_scheduled} scheduled</span></>
                )}
                {data.totals.total_returned > 0 && (
                  <>{' · '}<span style={{ color: 'var(--alert, #B6442C)' }}>{data.totals.total_returned} returned</span></>
                )}
              </div>
            )}
          </div>

          {data?.sequences?.length > 0 && (
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search address or owner"
              style={searchInputStyle}
            />
          )}
        </div>

        {error && <div style={errorStyle}>{error}</div>}

        {/* Filter chips — only render chips that would match >0 rows */}
        {data && data.filter_counts && (() => {
          const visible = STATUS_FILTERS.filter((f) => (data.filter_counts[f.key] || 0) > 0);
          if (visible.length === 0) return null;
          return (
            <div style={filterRowStyle}>
              <span style={filterRowLabelStyle}>Filter:</span>
              {visible.map((f) => {
                const active = selectedFilters.includes(f.key);
                return (
                  <button
                    key={f.key}
                    onClick={() => handleToggleFilter(f.key)}
                    style={filterChipStyle(active, f.tone)}
                  >
                    {f.label}
                    <span style={filterCountStyle}>{data.filter_counts[f.key]}</span>
                  </button>
                );
              })}
              {selectedFilters.length > 0 && (
                <button
                  onClick={() => setSelectedFilters([])}
                  style={clearButtonStyle}
                >
                  Clear
                </button>
              )}
            </div>
          );
        })()}

        {/* Table */}
        {visibleSequences.length > 0 ? (
          <div style={tableWrapStyle}>
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th style={thStyle}>Parcel</th>
                  <th style={thStyle}>Owner</th>
                  <th style={thStyle}>Started</th>
                  <th style={thStyle}>Progress</th>
                  <th style={thStyle}>Latest event</th>
                  <th style={thStyle}>Next scheduled</th>
                  <th style={thActionsStyle}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {visibleSequences.map((s) => (
                  <SequenceRow
                    key={s.sequence_id || `standalone-${s.pin}-${s.started_at}`}
                    seq={s}
                    cancelling={cancellingId === s.sequence_id}
                    onView={() => navigate(`/zip/${s.zip_code}?pin=${s.pin}`)}
                    onCancel={() => handleCancel(s.sequence_id, s.address || s.owner_name || s.pin)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          data?.sequences?.length > 0 ? (
            <div style={emptyFilterStyle}>
              No sequences match the current filter.
            </div>
          ) : data ? (
            <div style={emptyFilterStyle}>
              No letter activity yet. Open a parcel from your briefing and start a 6-letter sequence to see it here.
            </div>
          ) : null
        )}
      </div>
    </SiteLayout>
  );
}


function SequenceRow({ seq, cancelling, onView, onCancel }) {
  const total = seq.letters_total || 6;
  const sent  = seq.letters_sent  || 0;

  // Latest-event display — color-coded by status type.
  const latest = seq.latest_event_status;
  const latestColor =
    latest === 'returned' || latest === 'failed' ? 'var(--alert, #B6442C)' :
    latest === 'delivered'                       ? 'var(--success, #5C7A3B)' :
    latest === 'mailed' || latest === 'created'  ? 'var(--accent, #8B6914)' :
    'var(--text-tertiary)';

  // Address line — fall back to PIN if address is missing.
  const addressLine = seq.address || seq.pin;
  const subLine = [seq.city, seq.state].filter(Boolean).join(', ');

  // Status pill (top-right within the row)
  const statusLabel =
    seq.status === 'active'    ? (seq.is_standalone ? 'Single send' : 'Active') :
    seq.status === 'completed' ? 'Completed' :
    seq.status === 'cancelled' ? 'Cancelled' :
    seq.status === 'failed'    ? 'Failed' : seq.status;

  return (
    <tr style={trStyle}>
      <td style={tdStyle}>
        <div style={parcelAddressStyle}>{addressLine}</div>
        {subLine && <div style={parcelSubStyle}>{subLine}</div>}
        <span style={statusPillStyle(seq.status)}>{statusLabel}</span>
      </td>
      <td style={tdStyle}>
        <div style={ownerStyle}>{seq.owner_name || '—'}</div>
      </td>
      <td style={tdStyle}>
        <div style={metaStyle}>{formatRelative(seq.started_at)}</div>
        <div style={metaSubStyle}>{formatDate(seq.started_at)}</div>
      </td>
      <td style={tdStyle}>
        <ProgressDots sent={sent} delivered={seq.letters_delivered} total={total}
                      returned={seq.letters_returned} failed={seq.letters_failed} />
        <div style={metaSubStyle}>
          {sent} of {total} sent
          {seq.letters_delivered > 0 && ` · ${seq.letters_delivered} delivered`}
        </div>
      </td>
      <td style={tdStyle}>
        {latest ? (
          <>
            <div style={{ ...metaStyle, color: latestColor, fontWeight: 600 }}>
              {capitalize(latest)}
            </div>
            <div style={metaSubStyle}>{formatRelative(seq.latest_event_at)}</div>
          </>
        ) : (
          <div style={{ ...metaStyle, color: 'var(--text-tertiary)' }}>—</div>
        )}
      </td>
      <td style={tdStyle}>
        {seq.next_scheduled_at ? (
          <>
            <div style={metaStyle}>{formatDate(seq.next_scheduled_at)}</div>
            <div style={metaSubStyle}>{formatRelative(seq.next_scheduled_at, /*future*/ true)}</div>
          </>
        ) : (
          <div style={{ ...metaStyle, color: 'var(--text-tertiary)' }}>—</div>
        )}
      </td>
      <td style={tdActionsStyle}>
        <button onClick={onView} style={actionBtnStyle}>View</button>
        {seq.status === 'active' && !seq.is_standalone && (
          <button
            onClick={onCancel}
            disabled={cancelling}
            style={{
              ...actionBtnStyle,
              ...cancelBtnStyle,
              opacity: cancelling ? 0.5 : 1,
            }}
          >
            {cancelling ? 'Cancelling…' : 'Cancel'}
          </button>
        )}
      </td>
    </tr>
  );
}


/**
 * Six-dot progress indicator. Filled = sent. Green-filled = delivered.
 * Red-filled = returned/failed. Empty = scheduled.
 */
function ProgressDots({ sent, delivered, total, returned, failed }) {
  const dots = [];
  // First, render delivered (highest priority — they're done)
  for (let i = 0; i < (delivered || 0) && dots.length < total; i++) {
    dots.push({ tone: 'success', filled: true });
  }
  // Then returned/failed
  for (let i = 0; i < ((returned || 0) + (failed || 0)) && dots.length < total; i++) {
    dots.push({ tone: 'alert', filled: true });
  }
  // Then sent-but-not-yet-delivered
  const inTransit = Math.max(0, (sent || 0) - (delivered || 0));
  for (let i = 0; i < inTransit && dots.length < total; i++) {
    dots.push({ tone: 'accent', filled: true });
  }
  // Pad with empty (scheduled / not yet sent)
  while (dots.length < total) {
    dots.push({ tone: 'neutral', filled: false });
  }
  return (
    <div style={{ display: 'flex', gap: 3 }}>
      {dots.map((d, i) => (
        <span key={i} style={progressDotStyle(d.tone, d.filled)}>●</span>
      ))}
    </div>
  );
}


function formatRelative(iso, future = false) {
  if (!iso) return '';
  const ts = new Date(iso).getTime();
  const now = Date.now();
  const diffSec = future ? Math.max(0, Math.floor((ts - now) / 1000))
                         : Math.max(0, Math.floor((now - ts) / 1000));
  const prefix = future ? 'in ' : '';
  const suffix = future ? '' : ' ago';
  if (diffSec < 60)        return future ? 'soon' : 'just now';
  if (diffSec < 3600)      return `${prefix}${Math.floor(diffSec / 60)}m${suffix}`;
  if (diffSec < 86400)     return `${prefix}${Math.floor(diffSec / 3600)}h${suffix}`;
  if (diffSec < 86400 * 7) return `${prefix}${Math.floor(diffSec / 86400)}d${suffix}`;
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function formatDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function capitalize(s) {
  if (!s) return '';
  return s.charAt(0).toUpperCase() + s.slice(1);
}


// ─── Styles ────────────────────────────────────────────────────────

const _TONE_COLOR = {
  alert:   'var(--alert, #B6442C)',
  success: 'var(--success, #5C7A3B)',
  accent:  'var(--accent, #8B6914)',
  neutral: 'var(--text-tertiary)',
};

const containerStyle = {
  maxWidth: 1200,
  margin: '0 auto',
  padding: '32px 24px',
};

const pageHeaderStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'flex-start',
  gap: 16,
  flexWrap: 'wrap',
  marginBottom: 24,
};

const titleStyle = {
  margin: 0,
  fontFamily: 'var(--font-display)',
  fontSize: 32,
  fontWeight: 400,
  color: 'var(--text-primary)',
  letterSpacing: '-0.01em',
};

const subtitleStyle = {
  marginTop: 6,
  fontFamily: 'var(--font-sans)',
  fontSize: 13,
  color: 'var(--text-secondary)',
};

const searchInputStyle = {
  padding: '8px 12px',
  fontSize: 13,
  fontFamily: 'var(--font-sans)',
  background: 'var(--bg-secondary, #ffffff)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  width: 260,
  color: 'var(--text-primary)',
};

const errorStyle = {
  padding: '12px 16px',
  marginBottom: 16,
  background: 'rgba(182, 68, 44, 0.08)',
  border: '1px solid rgba(182, 68, 44, 0.25)',
  borderRadius: 6,
  fontFamily: 'var(--font-sans)',
  fontSize: 13,
  color: 'var(--alert, #B6442C)',
};

const filterRowStyle = {
  display: 'flex',
  flexWrap: 'wrap',
  alignItems: 'center',
  gap: 8,
  marginBottom: 20,
  padding: '10px 0',
  borderTop: '1px solid var(--border)',
  borderBottom: '1px solid var(--border)',
};

const filterRowLabelStyle = {
  fontFamily: 'var(--font-sans)',
  fontSize: 11,
  fontWeight: 500,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  color: 'var(--text-tertiary)',
  marginRight: 4,
};

const _TONE_BG_ACTIVE = {
  alert:   'var(--alert, #B6442C)',
  success: 'var(--success, #5C7A3B)',
  accent:  'var(--accent, #8B6914)',
  neutral: 'var(--text-secondary)',
};

const filterChipStyle = (active, tone) => ({
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  padding: '4px 10px',
  fontSize: 11,
  fontFamily: 'var(--font-sans)',
  fontWeight: 500,
  letterSpacing: '0.02em',
  borderRadius: 999,
  border: `1px solid ${active ? _TONE_BG_ACTIVE[tone] : 'var(--border)'}`,
  background: active ? _TONE_BG_ACTIVE[tone] : 'transparent',
  color: active ? 'var(--bg-primary, #F5F0EB)' : _TONE_COLOR[tone] || 'var(--text-secondary)',
  cursor: 'pointer',
  transition: 'background 120ms, color 120ms, border-color 120ms',
});

const filterCountStyle = {
  fontSize: 10,
  opacity: 0.7,
  marginLeft: 2,
};

const clearButtonStyle = {
  padding: '4px 10px',
  fontSize: 11,
  fontFamily: 'var(--font-sans)',
  background: 'transparent',
  border: 'none',
  color: 'var(--text-tertiary)',
  cursor: 'pointer',
  textDecoration: 'underline',
};

const tableWrapStyle = {
  background: 'var(--bg-secondary, #ffffff)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  overflow: 'auto',
};

const tableStyle = {
  width: '100%',
  borderCollapse: 'collapse',
  fontFamily: 'var(--font-sans)',
  fontSize: 13,
};

const thStyle = {
  textAlign: 'left',
  padding: '12px 14px',
  fontSize: 11,
  fontWeight: 500,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  color: 'var(--text-tertiary)',
  borderBottom: '1px solid var(--border)',
  background: 'var(--bg-tertiary, rgba(0,0,0,0.02))',
  whiteSpace: 'nowrap',
};

const thActionsStyle = { ...thStyle, textAlign: 'right' };

const trStyle = {
  borderBottom: '1px solid var(--border)',
};

const tdStyle = {
  padding: '14px',
  verticalAlign: 'top',
};

const tdActionsStyle = {
  ...tdStyle,
  textAlign: 'right',
  whiteSpace: 'nowrap',
};

const parcelAddressStyle = {
  fontFamily: 'var(--font-serif)',
  fontSize: 14,
  fontWeight: 500,
  color: 'var(--text-primary)',
  marginBottom: 2,
};

const parcelSubStyle = {
  fontSize: 11,
  color: 'var(--text-tertiary)',
  marginBottom: 4,
};

const ownerStyle = {
  fontSize: 13,
  color: 'var(--text-secondary)',
};

const metaStyle = {
  fontSize: 13,
  color: 'var(--text-primary)',
};

const metaSubStyle = {
  fontSize: 11,
  color: 'var(--text-tertiary)',
  marginTop: 2,
};

const statusPillStyle = (status) => {
  const bg =
    status === 'active'    ? 'rgba(139, 105, 20, 0.12)' :
    status === 'completed' ? 'rgba(92, 122, 59, 0.12)'  :
    status === 'cancelled' ? 'rgba(0, 0, 0, 0.06)'      :
    status === 'failed'    ? 'rgba(182, 68, 44, 0.10)'  :
    'rgba(0, 0, 0, 0.04)';
  const fg =
    status === 'active'    ? 'var(--accent, #8B6914)'  :
    status === 'completed' ? 'var(--success, #5C7A3B)' :
    status === 'cancelled' ? 'var(--text-tertiary)'    :
    status === 'failed'    ? 'var(--alert, #B6442C)'   :
    'var(--text-secondary)';
  return {
    display: 'inline-block',
    marginTop: 4,
    padding: '2px 8px',
    fontSize: 10,
    fontWeight: 500,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    borderRadius: 3,
    background: bg,
    color: fg,
  };
};

const actionBtnStyle = {
  padding: '6px 12px',
  fontSize: 12,
  fontFamily: 'var(--font-sans)',
  fontWeight: 500,
  background: 'transparent',
  border: '1px solid var(--border)',
  borderRadius: 4,
  color: 'var(--text-primary)',
  cursor: 'pointer',
  marginLeft: 6,
  transition: 'background 120ms, border-color 120ms',
};

const cancelBtnStyle = {
  borderColor: 'rgba(182, 68, 44, 0.4)',
  color: 'var(--alert, #B6442C)',
};

const progressDotStyle = (tone, filled) => ({
  fontSize: 11,
  lineHeight: 1,
  color: filled ? _TONE_COLOR[tone] : 'var(--border)',
});

const emptyFilterStyle = {
  marginTop: 32,
  padding: 32,
  textAlign: 'center',
  fontFamily: 'var(--font-serif)',
  fontSize: 14,
  fontStyle: 'italic',
  color: 'var(--text-tertiary)',
  background: 'var(--bg-secondary, #ffffff)',
  border: '1px solid var(--border)',
  borderRadius: 8,
};
