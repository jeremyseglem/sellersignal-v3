/*
 * SkipTracePanel.jsx — in-dossier skip-trace UI.
 *
 * Renders inside ContactSection. Three modes:
 *   1. Idle (no result yet): "Find owner contact info" button + monthly remaining
 *   2. Loading: spinner + "Running skip-trace…"
 *   3. Results: persons with phones (DNC pills, litigator banner), emails,
 *      mailing addresses. Cached results show a "last refreshed N days ago" hint.
 *
 * Pre-flight checks:
 *   - On mount, calls skipTrace.status() to know ack state and remaining cap.
 *   - If not acked, clicking the trace button opens TCPAComplianceModal first;
 *     after ack, runs the trace.
 *
 * Probate handling:
 *   - Deceased persons in results are shown but de-prioritized with a
 *     "deceased" label and dimmed styling. For probate leads the deceased
 *     IS the property owner, so they appear; the living PR's contact
 *     info is what the agent actually wants.
 *
 * Compliance:
 *   - Each phone displays a DNC pill if dnc=true.
 *   - Each person with litigator=true shows a prominent red warning banner.
 */

import { useEffect, useState } from 'react';
import { skipTrace, leadInteractions, safeErrorMessage } from '../api/client.js';
import TCPAComplianceModal from './TCPAComplianceModal.jsx';

export default function SkipTracePanel({ pin, onAfterTrace }) {
  const [status, setStatus]   = useState(null);   // {acked, monthly_used, monthly_cap, ...}
  const [result, setResult]   = useState(null);   // {source, hit, persons, ...} | null
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);
  const [showAckModal, setShowAckModal] = useState(false);

  // Initial load: status + check for any existing cached result.
  // Both fire in parallel — if a cached result exists, we render it
  // immediately so the agent doesn't have to re-click "Find owner
  // contact info" every time they re-open a dossier they've already
  // traced.
  useEffect(() => {
    let cancelled = false;
    skipTrace.status()
      .then((s) => { if (!cancelled) setStatus(s); })
      .catch(() => { /* show idle state with no remaining count */ });
    skipTrace.cached(pin)
      .then((r) => {
        if (cancelled) return;
        if (r && r.cached) {
          // Reshape into the same form runTrace() produces, so
          // ResultsDisplay handles both identically.
          setResult({
            source:       'cache',
            hit:          r.hit,
            persons:      r.persons,
            retrieved_at: r.retrieved_at,
            expires_at:   r.expires_at,
          });
        }
      })
      .catch(() => { /* no cache; agent will see idle button */ });
    return () => { cancelled = true; };
  }, [pin]);

  // Reset result when pin changes (different parcel = different trace).
  // The effect above will then re-fetch any cache for the new pin.
  useEffect(() => {
    setResult(null);
    setError(null);
  }, [pin]);

  const runTrace = async ({ force_refresh = false } = {}) => {
    setError(null);
    setLoading(true);
    try {
      const r = await skipTrace.lookup(pin, { force_refresh });
      setResult(r);
      // Refresh status so monthly remaining updates after a fresh trace.
      skipTrace.status().then(setStatus).catch(() => {});
      // Tell the parent dossier so it can refresh the history line.
      onAfterTrace && onAfterTrace();
    } catch (e) {
      const detail = e?.detail;
      if (detail?.code === 'compliance_not_acked') {
        // Server says we need ack — open modal and stop here.
        setShowAckModal(true);
        setLoading(false);
        return;
      }
      if (detail?.code === 'monthly_cap_reached') {
        setError(
          `You've used your ${detail.monthly_cap} skip-traces for this `
          + `month. The cap resets at the start of next month.`
        );
      } else if (detail?.code === 'provider_error') {
        setError(detail.retryable
          ? `${detail.message} (try again)`
          : detail.message);
      } else {
        setError(safeErrorMessage(e, 'Skip-trace failed'));
      }
    } finally {
      setLoading(false);
    }
  };

  const handleTraceClick = () => {
    // Quick local check: if status says not acked, open modal first.
    // (The server also enforces this — local check is for fewer round trips.)
    if (status && !status.acked) {
      setShowAckModal(true);
      return;
    }
    runTrace();
  };

  const handleAcked = () => {
    setShowAckModal(false);
    // Refresh status so the UI reflects the ack, then run the trace
    // the agent was about to run.
    skipTrace.status().then((s) => {
      setStatus(s);
      runTrace();
    }).catch(() => {
      // Status refresh failed but ack succeeded — run anyway.
      runTrace();
    });
  };

  // Display text for the monthly counter. Operators get null cap
  // from the server; show "unlimited" rather than a count.
  let monthlyText = null;
  if (status) {
    if (status.is_operator || status.monthly_cap == null) {
      monthlyText = 'Unlimited skip-traces (operator)';
    } else {
      monthlyText = `${status.monthly_remaining} of ${status.monthly_cap} skip-traces left this month`;
    }
  }

  // Disable the button only when a real cap exists and is reached.
  const capReached = status
    && !status.is_operator
    && status.monthly_remaining === 0;

  return (
    <div style={containerStyle}>
      {!result && (
        <>
          <button
            type="button"
            onClick={handleTraceClick}
            disabled={loading || capReached}
            style={traceButtonStyle(loading)}
          >
            {loading ? 'Running skip-trace…' : 'Find owner contact info'}
          </button>
          {monthlyText && (
            <div style={monthlyTextStyle}>{monthlyText}</div>
          )}
        </>
      )}

      {error && (
        <div style={errorStyle}>{error}</div>
      )}

      {result && (
        <ResultsDisplay
          result={result}
          onRetry={() => runTrace({ force_refresh: true })}
        />
      )}

      {showAckModal && (
        <TCPAComplianceModal
          onAcked={handleAcked}
          onCancel={() => setShowAckModal(false)}
        />
      )}
    </div>
  );
}


function ResultsDisplay({ result, onRetry }) {
  const { hit, persons, source, retrieved_at, expires_at } = result;

  if (!hit || !persons.length) {
    // Build a helpful miss message. If we searched for a specific
    // named PR (search_mode='person'), the miss almost certainly
    // means the PR doesn't live at the property — common for
    // probate cases where the PR is an adult child living elsewhere.
    const searchedFor = result.searched_for;
    const isPersonSearch = result.search_mode === 'person' && searchedFor;
    return (
      <div style={missStyle}>
        <div style={missTitleStyle}>
          {isPersonSearch
            ? `${searchedFor} not found at this address`
            : 'No contact data found'}
        </div>
        <div style={missBodyStyle}>
          {isPersonSearch ? (
            <>
              The personal representative likely lives at a different
              address — common in probate cases. Search probate court
              records for the PR&rsquo;s home address, or try a
              handwritten letter to the property address (often
              forwarded to the PR by family members at the home).
            </>
          ) : (
            <>
              Skip-trace returned no matches for this address. This
              can happen for vacant properties, recently transferred
              ownership, or addresses where the resident&rsquo;s
              identity isn&rsquo;t public. Try again in 30 days, or
              contact this lead by mail to the property address.
            </>
          )}
        </div>
        {source === 'cache' && retrieved_at && (
          <div style={cacheNoteStyle}>
            Cached {timeAgo(retrieved_at)}. Fresh trace available {expiresIn(expires_at)}.
          </div>
        )}
      </div>
    );
  }

  // Litigator warning: any person flagged → big red banner.
  const anyLitigator = persons.some((p) => p.litigator);

  // Sort: living non-deceased property owners first, then living
  // non-owners, then deceased last (probate use case — the deceased
  // homeowner is expected to appear).
  const sorted = [...persons].sort((a, b) => {
    if (a.deceased && !b.deceased) return 1;
    if (!a.deceased && b.deceased) return -1;
    if (a.property_owner && !b.property_owner) return -1;
    if (!a.property_owner && b.property_owner) return 1;
    return 0;
  });

  return (
    <div>
      {anyLitigator && (
        <div style={litigatorBannerStyle}>
          <strong>TCPA LITIGATOR FLAGGED.</strong> One or more numbers
          below are linked to a known TCPA litigator. Do not call or
          text these numbers.
        </div>
      )}

      {sorted.map((p, i) => (
        <PersonCard key={`${p.full_name}-${i}`} person={p} />
      ))}

      <div style={metaRowStyle}>
        <span>
          {source === 'fresh' ? 'Fresh trace' : `Cached ${timeAgo(retrieved_at)}`}
          {source === 'cache' && ` · fresh trace available ${expiresIn(expires_at)}`}
        </span>
        {source === 'cache' && (
          <button type="button" onClick={onRetry} style={retryButtonStyle}>
            Refresh
          </button>
        )}
      </div>
    </div>
  );
}


function PersonCard({ person }) {
  const dim = person.deceased;
  return (
    <div style={personCardStyle(dim)}>
      <div style={personHeaderStyle}>
        <span style={personNameStyle}>
          {person.full_name || `${person.first_name || ''} ${person.last_name || ''}`.trim()}
        </span>
        <span style={personFlagsStyle}>
          {person.property_owner && (
            <Pill color="var(--accent)" bg="var(--accent-dim)">Property owner</Pill>
          )}
          {person.deceased && (
            <Pill color="var(--text-tertiary)" bg="var(--bg-input)">Deceased</Pill>
          )}
          {person.litigator && (
            <Pill color="var(--call-now)" bg="var(--call-now-bg)">Litigator</Pill>
          )}
          {person.age && !person.deceased && (
            <span style={personAgeStyle}>age {person.age}</span>
          )}
        </span>
      </div>

      {person.mailing_address && (person.mailing_address.street || person.mailing_address.city) && (
        <div style={mailingAddressStyle}>
          {[
            person.mailing_address.street,
            [person.mailing_address.city, person.mailing_address.state, person.mailing_address.zip]
              .filter(Boolean).join(', '),
          ].filter(Boolean).join(' · ')}
        </div>
      )}

      {(person.phones || []).length > 0 && (
        <div style={fieldGroupStyle}>
          <div style={fieldLabelStyle}>Phones</div>
          {person.phones.map((ph, i) => (
            <div key={i} style={phoneRowStyle}>
              <a href={`tel:${ph.number}`} style={phoneNumberStyle}>
                {formatPhone(ph.number)}
              </a>
              <span style={phoneMetaStyle}>
                {ph.type}{ph.carrier ? ` · ${ph.carrier}` : ''}
              </span>
              {ph.dnc && (
                <Pill color="var(--call-now)" bg="var(--call-now-bg)" tight>DNC</Pill>
              )}
            </div>
          ))}
        </div>
      )}

      {(person.emails || []).length > 0 && (
        <div style={fieldGroupStyle}>
          <div style={fieldLabelStyle}>Emails</div>
          {person.emails.map((em, i) => (
            <div key={i} style={emailRowStyle}>
              <a href={`mailto:${em.email}`} style={emailLinkStyle}>
                {em.email}
              </a>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


function Pill({ children, color, bg, tight }) {
  return (
    <span style={{
      display: 'inline-block',
      padding: tight ? '1px 6px' : '2px 8px',
      fontSize: 9,
      fontWeight: 700,
      letterSpacing: '0.06em',
      textTransform: 'uppercase',
      color,
      background: bg,
      borderRadius: 10,
      fontFamily: 'var(--font-sans)',
    }}>
      {children}
    </span>
  );
}


function formatPhone(num) {
  if (!num) return '';
  const digits = num.replace(/\D/g, '');
  if (digits.length === 10) {
    return `(${digits.slice(0,3)}) ${digits.slice(3,6)}-${digits.slice(6)}`;
  }
  if (digits.length === 11 && digits[0] === '1') {
    return `(${digits.slice(1,4)}) ${digits.slice(4,7)}-${digits.slice(7)}`;
  }
  return num;
}


function timeAgo(iso) {
  if (!iso) return '';
  const ms = Date.now() - new Date(iso).getTime();
  const days = Math.floor(ms / 86400000);
  if (days === 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 30)  return `${days} days ago`;
  return new Date(iso).toLocaleDateString();
}


function expiresIn(iso) {
  if (!iso) return '';
  const ms = new Date(iso).getTime() - Date.now();
  const days = Math.max(0, Math.ceil(ms / 86400000));
  if (days === 0) return 'now';
  if (days === 1) return 'in 1 day';
  return `in ${days} days`;
}


// ── Styles ────────────────────────────────────────────────────────

const containerStyle = {
  marginTop: 12,
};

const traceButtonStyle = (loading) => ({
  width: '100%',
  padding: '10px 14px',
  fontSize: 13,
  fontWeight: 600,
  background: 'var(--bg-input)',
  color: 'var(--text)',
  border: '1px solid var(--border-strong)',
  borderRadius: 'var(--radius-md, 6px)',
  cursor: loading ? 'wait' : 'pointer',
  fontFamily: 'var(--font-sans)',
  letterSpacing: '0.01em',
  opacity: loading ? 0.6 : 1,
});

const monthlyTextStyle = {
  marginTop: 4,
  fontSize: 10,
  color: 'var(--text-tertiary)',
  fontFamily: 'var(--font-sans)',
  textAlign: 'center',
};

const errorStyle = {
  marginTop: 8,
  padding: '8px 10px',
  background: 'var(--call-now-bg, #fff0f0)',
  border: '1px solid var(--call-now)',
  color: 'var(--call-now)',
  fontSize: 12,
  borderRadius: 'var(--radius-md, 6px)',
  fontFamily: 'var(--font-sans)',
};

const litigatorBannerStyle = {
  padding: '10px 12px',
  background: 'var(--call-now)',
  color: '#fff',
  fontSize: 12,
  fontFamily: 'var(--font-sans)',
  borderRadius: 'var(--radius-md, 6px)',
  marginBottom: 10,
  lineHeight: 1.5,
};

const personCardStyle = (dim) => ({
  padding: '10px 12px',
  marginBottom: 8,
  background: 'var(--bg-card-hover, var(--bg-input))',
  border: '0.5px solid var(--border)',
  borderRadius: 'var(--radius-md, 6px)',
  opacity: dim ? 0.55 : 1,
});

const personHeaderStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'flex-start',
  gap: 8,
  flexWrap: 'wrap',
  marginBottom: 6,
};

const personNameStyle = {
  fontFamily: 'var(--font-serif)',
  fontSize: 15,
  fontWeight: 600,
  color: 'var(--text)',
};

const personFlagsStyle = {
  display: 'inline-flex',
  gap: 4,
  flexWrap: 'wrap',
  alignItems: 'center',
};

const personAgeStyle = {
  fontSize: 10,
  color: 'var(--text-tertiary)',
  fontFamily: 'var(--font-sans)',
};

const mailingAddressStyle = {
  fontSize: 12,
  color: 'var(--text-secondary)',
  fontFamily: 'var(--font-serif)',
  marginBottom: 8,
  paddingBottom: 6,
  borderBottom: '0.5px dashed var(--border)',
};

const fieldGroupStyle = {
  marginTop: 6,
};

const fieldLabelStyle = {
  fontSize: 9,
  fontWeight: 700,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  color: 'var(--text-tertiary)',
  marginBottom: 3,
  fontFamily: 'var(--font-sans)',
};

const phoneRowStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  marginBottom: 2,
  flexWrap: 'wrap',
};

const phoneNumberStyle = {
  fontFamily: 'var(--font-sans)',
  fontSize: 13,
  fontWeight: 600,
  color: 'var(--accent)',
  textDecoration: 'none',
};

const phoneMetaStyle = {
  fontSize: 10,
  color: 'var(--text-tertiary)',
  fontFamily: 'var(--font-sans)',
};

const emailRowStyle = {
  marginBottom: 2,
};

const emailLinkStyle = {
  fontFamily: 'var(--font-sans)',
  fontSize: 12,
  color: 'var(--accent)',
  textDecoration: 'none',
};

const metaRowStyle = {
  marginTop: 4,
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  fontSize: 10,
  color: 'var(--text-tertiary)',
  fontFamily: 'var(--font-sans)',
};

const retryButtonStyle = {
  background: 'transparent',
  border: 'none',
  color: 'var(--accent)',
  fontSize: 10,
  cursor: 'pointer',
  textDecoration: 'underline',
  fontFamily: 'var(--font-sans)',
  padding: 0,
};

const missStyle = {
  padding: 12,
  background: 'var(--bg-input)',
  border: '0.5px dashed var(--border)',
  borderRadius: 'var(--radius-md, 6px)',
};

const missTitleStyle = {
  fontFamily: 'var(--font-sans)',
  fontSize: 12,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  letterSpacing: '0.04em',
  marginBottom: 4,
};

const missBodyStyle = {
  fontFamily: 'var(--font-serif)',
  fontSize: 12,
  lineHeight: 1.5,
  color: 'var(--text-secondary)',
};

const cacheNoteStyle = {
  marginTop: 6,
  fontSize: 10,
  color: 'var(--text-tertiary)',
  fontFamily: 'var(--font-sans)',
  fontStyle: 'italic',
};
