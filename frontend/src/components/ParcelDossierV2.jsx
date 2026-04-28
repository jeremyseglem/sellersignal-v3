import { useState, useEffect, useMemo } from 'react';
import {
  parcels as parcelsApi,
  map as mapApi,
  deepSignal as deepSignalApi,
  leadInteractions,
} from '../api/client.js';
import { useAuth } from '../lib/AuthContext.jsx';
import { ownerTypeLabel, isSellerTargetType } from '../lib/ownerType.js';
import {
  ARCHETYPES,
  detectArchetype,
  computeEquity,
  formatEquity,
  isWithinWaitWindow,
  waitWindowOpensDate,
} from '../lib/archetypePlaybooks.js';
import SixLettersModal from './SixLettersModal.jsx';
import ClaimZipModal from './briefing/ClaimZipModal.jsx';

/**
 * ParcelDossierV2 — the v4 spec dossier.
 *
 * Renders five sections (WHY / NEXT STEP / CONTACT / WHAT TO SAY /
 * EVIDENCE) with content that shifts by archetype. Replaces the
 * 2,352-line ParcelDossier.jsx but ships side-by-side with it
 * during Slice C — BriefingPage's import determines which renders.
 * One-line revert if anything blows up.
 *
 * Lead Memory is wired through:
 *   - Status pill at top when status === working
 *   - Three-tier action buttons: primary Send, secondary Export to CRM,
 *     tertiary text-buttons (Mark as working / Not relevant)
 *   - Archetype-specific outcome dropdown when status === working
 *   - History line at bottom with all events newest-first
 *
 * Cold-visitor mode (no auth):
 *   - Action buttons are visible but every click opens ClaimZipModal
 *   - Same dossier content otherwise — the demo is the conversion
 *
 * Six Letters: kept as a secondary action button (per Jeremy's
 * direction). Fires the same modal as before.
 *
 * Send-letter and Get-contact-info actions: V1 placeholder behavior.
 * Both buttons render and fire toasts indicating Slice 1.5 will wire
 * them to real PDF/Lob/skip-trace integrations.
 *
 * Props:
 *   dossier   — full dossier response from /api/parcels/:pin
 *   onClose   — handler for the X button
 */
export default function ParcelDossierV2({ dossier, onClose }) {
  const { session } = useAuth();
  const isColdVisitor = !session;

  const [streetViewUrl, setStreetViewUrl] = useState(null);
  const [streetViewOk, setStreetViewOk] = useState(true);

  const [deepSignal, setDeepSignal] = useState(null);
  const [deepSignalLoading, setDeepSignalLoading] = useState(false);
  const [deepSignalError, setDeepSignalError] = useState(null);

  const [sixLettersOpen, setSixLettersOpen] = useState(false);
  const [claimModalOpen, setClaimModalOpen] = useState(false);

  // Lead Memory state
  const [events, setEvents] = useState([]);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [actionPending, setActionPending] = useState(false);

  // Lightweight UI hint banner (e.g. "Coming in V1.5 — skip-trace")
  const [hintMessage, setHintMessage] = useState(null);

  // ── Loaders ───────────────────────────────────────────────────

  // Street View
  useEffect(() => {
    if (!dossier?.pin) return;
    setStreetViewUrl(null);
    setStreetViewOk(true);
    mapApi.streetView(dossier.pin)
      .then((r) => setStreetViewUrl(r.url))
      .catch(() => setStreetViewUrl(null));
  }, [dossier?.pin]);

  // Deep Signal cache lookup
  useEffect(() => {
    if (!dossier?.pin) return;
    setDeepSignal(null);
    setDeepSignalError(null);
    setSixLettersOpen(false);
    deepSignalApi.get(dossier.pin)
      .then(setDeepSignal)
      .catch(() => setDeepSignal(null));
  }, [dossier?.pin]);

  // Lead Memory — load this agent's event history for this parcel
  useEffect(() => {
    if (!dossier?.pin || isColdVisitor) {
      setEvents([]);
      return;
    }
    setEventsLoading(true);
    leadInteractions.byPin(dossier.pin)
      .then((r) => setEvents(r.events || []))
      .catch(() => setEvents([]))
      .finally(() => setEventsLoading(false));
  }, [dossier?.pin, isColdVisitor]);

  // Auto-clear hint banner after 4s
  useEffect(() => {
    if (!hintMessage) return;
    const t = setTimeout(() => setHintMessage(null), 4000);
    return () => clearTimeout(t);
  }, [hintMessage]);

  // ── Derived ───────────────────────────────────────────────────

  const parcel = dossier?.parcel || {};
  const harvesterMatches = dossier?.harvester_matches || [];

  const archetype = useMemo(() => detectArchetype(dossier), [dossier]);
  const equityDollars = useMemo(() => computeEquity(dossier), [dossier]);
  const inWaitWindow = useMemo(
    () => isWithinWaitWindow(dossier, archetype),
    [dossier, archetype]
  );
  const waitOpens = useMemo(
    () => waitWindowOpensDate(dossier, archetype),
    [dossier, archetype]
  );

  // Probate contact_status — drives the WHY section's "Wait — no
  // decision-maker yet" rendering when the case has no actionable PR.
  // Only set for archetype === 'probate'.
  const probateMatch = harvesterMatches.find((m) => m.signal_type === 'probate');
  const contactStatus = probateMatch?.contact_status || null;
  const personalRep = probateMatch?.personal_representative || null;

  // Current Lead Memory status — most recent status-changing event.
  // Outcome events (got_response, etc.) don't change status.
  const STATUS_EVENTS = new Set(['working', 'not_relevant', 'sent_to_crm', 'reactivated']);
  const currentStatus = useMemo(() => {
    for (const ev of events) {
      if (STATUS_EVENTS.has(ev.event_type)) {
        // Treat 'reactivated' as no-status (lead is active again)
        return ev.event_type === 'reactivated' ? null : ev.event_type;
      }
    }
    return null;
  }, [events]);

  const statusDate = useMemo(() => {
    if (!currentStatus) return null;
    const ev = events.find((e) => e.event_type === currentStatus);
    return ev ? new Date(ev.created_at) : null;
  }, [events, currentStatus]);

  const canGenerateDeepSignal =
    Boolean((dossier?.investigation?.signals || []).length)
    || harvesterMatches.length > 0;
  const canGenerateSixLetters = isSellerTargetType(parcel.owner_type);

  // ── Action handlers ───────────────────────────────────────────

  const showHint = (msg) => setHintMessage(msg);

  const handleGenerateDeepSignal = async () => {
    if (!dossier?.pin) return;
    setDeepSignalLoading(true);
    setDeepSignalError(null);
    try {
      const r = await deepSignalApi.generate(dossier.pin);
      setDeepSignal(r);
    } catch (e) {
      setDeepSignalError(e?.detail?.message || e?.message || 'Generation failed');
    } finally {
      setDeepSignalLoading(false);
    }
  };

  // Cold-visitor gate: every Lead Memory action triggers the modal.
  // For everything else (Deep Signal, Six Letters), cold visitors
  // are allowed — those don't write anything to the agent's history.
  const guardCold = (fn) => (...args) => {
    if (isColdVisitor) {
      setClaimModalOpen(true);
      return;
    }
    return fn(...args);
  };

  const logEvent = async (event_type, event_data = {}) => {
    if (!dossier?.pin || !parcel?.zip_code) return;
    setActionPending(true);
    try {
      await leadInteractions.log({
        pin:        dossier.pin,
        zip_code:   parcel.zip_code,
        event_type,
        event_data,
      });
      // Refresh event log
      const r = await leadInteractions.byPin(dossier.pin);
      setEvents(r.events || []);
    } catch (e) {
      showHint(`Failed to log event: ${e?.detail?.message || e?.message || 'unknown error'}`);
    } finally {
      setActionPending(false);
    }
  };

  const handleSendLetter = guardCold(() => {
    showHint(
      'Coming in V1.5 — letter generation will produce a printable PDF '
      + 'and mark the lead as letter-sent. Lob mail integration after.'
    );
    // We still log the intent so future migrations to real send have
    // a complete history. But not in V1 — wait until letters are real.
  });

  const handleGetContactInfo = guardCold(() => {
    showHint(
      'Coming in V1.5 — contact info retrieval will run skip-trace and '
      + 'populate the address inline.'
    );
  });

  const handleMarkWorking = guardCold(() => logEvent('working'));
  const handleNotRelevant = guardCold(() => logEvent('not_relevant'));
  const handleReactivate = guardCold(() => logEvent('reactivated'));
  const handleExportCrm = guardCold(() => logEvent('sent_to_crm'));
  const handleOutcome = guardCold((outcome) => {
    // Map UI outcome label to event_type
    const mapping = {
      'Got response':        'got_response',
      'No response':         'no_response',
      'Listing discussion':  'listing_discussion',
      'Closed':              'closed',
      'Interested':          'got_response',
      'Not interested':      'no_response',
      'Considering sale':    'listing_discussion',
      'Open to conversation':'got_response',
      'Future follow-up':    'no_response',
      'Staying long-term':   'no_response',
    };
    const ev = mapping[outcome];
    if (!ev) return;
    return logEvent(ev, { label: outcome });
  });

  // ── Render ────────────────────────────────────────────────────

  return (
    <div style={{
      position: 'absolute',
      top: 0,
      right: 0,
      height: '100vh',
      width: 460,
      background: 'var(--bg-card)',
      borderLeft: '1px solid var(--border)',
      boxShadow: 'var(--shadow-lg)',
      overflow: 'auto',
      zIndex: 1000,
    }}>
      <CloseButton onClose={onClose} />

      <div style={{ padding: 'var(--space-lg)', paddingTop: 'var(--space-md)' }}>
        <DossierHeader
          parcel={parcel}
          archetype={archetype}
          equityDollars={equityDollars}
        />

        {currentStatus && (
          <StatusPill
            status={currentStatus}
            date={statusDate}
            onUndo={currentStatus === 'not_relevant' ? handleReactivate : null}
          />
        )}

        {streetViewUrl && streetViewOk && (
          <img
            src={streetViewUrl}
            alt={`Street View of ${parcel.address || 'property'}`}
            onError={() => setStreetViewOk(false)}
            style={{
              width: '100%',
              marginTop: 'var(--space-md)',
              borderRadius: 'var(--radius-md)',
              display: 'block',
            }}
          />
        )}

        {hintMessage && (
          <div style={{
            marginTop: 'var(--space-md)',
            padding: '10px 14px',
            background: 'rgba(139, 105, 20, 0.08)',
            borderLeft: '3px solid var(--accent)',
            borderRadius: 'var(--radius-md)',
            fontFamily: 'var(--font-serif)',
            fontStyle: 'italic',
            fontSize: 12,
            color: 'var(--text)',
            lineHeight: 1.5,
          }}>
            {hintMessage}
          </div>
        )}

        {/* ── Five archetype-driven sections ─────────────────── */}
        <WhySection
          dossier={dossier}
          archetype={archetype}
          contactStatus={contactStatus}
          personalRep={personalRep}
        />

        <NextStepSection
          archetype={archetype}
          contactStatus={contactStatus}
          inWaitWindow={inWaitWindow}
          waitOpens={waitOpens}
        />

        <ContactSection
          parcel={parcel}
          archetype={archetype}
          equityDollars={equityDollars}
          personalRep={personalRep}
          onGetContactInfo={handleGetContactInfo}
        />

        <WhatToSaySection
          deepSignal={deepSignal}
          deepSignalLoading={deepSignalLoading}
          deepSignalError={deepSignalError}
          archetype={archetype}
          inWaitWindow={inWaitWindow}
          waitOpens={waitOpens}
          canGenerateDeepSignal={canGenerateDeepSignal}
          onGenerateDeepSignal={handleGenerateDeepSignal}
        />

        <EvidenceSection dossier={dossier} />

        {/* ── Outcome dropdown when working ──────────────────── */}
        {currentStatus === 'working' && !isColdVisitor && (
          <OutcomeDropdown
            archetype={archetype}
            events={events}
            onSelect={handleOutcome}
            disabled={actionPending}
          />
        )}

        {/* ── Action buttons ─────────────────────────────────── */}
        <ActionButtons
          archetype={archetype}
          inWaitWindow={inWaitWindow}
          currentStatus={currentStatus}
          isColdVisitor={isColdVisitor}
          actionPending={actionPending}
          canGenerateSixLetters={canGenerateSixLetters}
          onSendLetter={handleSendLetter}
          onExportCrm={handleExportCrm}
          onMarkWorking={handleMarkWorking}
          onNotRelevant={handleNotRelevant}
          onSixLetters={() => setSixLettersOpen(true)}
        />

        {/* ── History ────────────────────────────────────────── */}
        {events.length > 0 && !isColdVisitor && (
          <HistorySection events={events} />
        )}
      </div>

      {sixLettersOpen && (
        <SixLettersModal
          parcel={parcel}
          onClose={() => setSixLettersOpen(false)}
        />
      )}

      {claimModalOpen && (
        <ClaimZipModal
          zip={parcel.zip_code}
          onClose={() => setClaimModalOpen(false)}
        />
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════
//  Sub-components — each is self-contained for readability.
// ═══════════════════════════════════════════════════════════════

function CloseButton({ onClose }) {
  return (
    <button
      onClick={onClose}
      aria-label="Close"
      style={{
        position: 'absolute',
        top: 'var(--space-md)',
        right: 'var(--space-md)',
        width: 30,
        height: 30,
        borderRadius: '50%',
        background: 'var(--bg)',
        color: 'var(--text-secondary)',
        fontSize: 18,
        lineHeight: 1,
        zIndex: 10,
        border: 'none',
        cursor: 'pointer',
      }}
    >
      ×
    </button>
  );
}


function DossierHeader({ parcel, archetype, equityDollars }) {
  const ownerType = ownerTypeLabel(parcel.owner_type);
  return (
    <div style={{ paddingRight: 40 }}>
      {archetype.headlineHint && (
        <div style={{
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: 'var(--accent)',
          fontFamily: 'var(--font-sans)',
        }}>
          {archetype.headlineHint}
        </div>
      )}
      <h2 style={{
        fontFamily: 'var(--font-display)',
        fontSize: 22,
        fontWeight: 600,
        color: 'var(--text)',
        marginTop: 4,
        lineHeight: 1.2,
      }}>
        {parcel.owner_name || 'Owner unknown'}
      </h2>
      <div style={{
        fontFamily: 'var(--font-serif)',
        fontSize: 13,
        color: 'var(--text-secondary)',
        marginTop: 4,
        lineHeight: 1.5,
      }}>
        {parcel.city}, {parcel.state}
        {parcel.total_value && (
          <>
            {' · '}
            <span style={{
              fontFamily: 'var(--font-display)',
              color: 'var(--accent)',
              fontWeight: 600,
              fontStyle: 'normal',
            }}>
              {formatValue(parcel.total_value)}
            </span>
          </>
        )}
        {' · '}{parcel.address || `Parcel ${parcel.pin}`}
      </div>
      {ownerType && (
        <div style={{
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          color: 'var(--text-tertiary)',
          marginTop: 6,
          fontFamily: 'var(--font-sans)',
        }}>
          {ownerType}
          {parcel.tenure_years != null && (
            <> · {Math.round(parcel.tenure_years)}-yr tenure</>
          )}
        </div>
      )}
    </div>
  );
}


function StatusPill({ status, date, onUndo }) {
  const labels = {
    working:      'Working',
    not_relevant: 'Marked not relevant',
    sent_to_crm:  'Exported to CRM',
  };
  const colors = {
    working:      'var(--accent)',
    not_relevant: 'var(--text-tertiary)',
    sent_to_crm:  'var(--hold)',
  };
  const label = labels[status] || status;
  const color = colors[status] || 'var(--text-secondary)';
  const dateStr = date
    ? date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
    : '';
  return (
    <div style={{
      marginTop: 'var(--space-md)',
      padding: '8px 12px',
      background: 'rgba(139, 105, 20, 0.06)',
      borderLeft: `3px solid ${color}`,
      borderRadius: 'var(--radius-sm)',
      fontFamily: 'var(--font-sans)',
      fontSize: 12,
      color: 'var(--text)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 8,
    }}>
      <span>
        <strong style={{ fontWeight: 600 }}>{label}</strong>
        {dateStr && <span style={{ color: 'var(--text-tertiary)' }}> · {dateStr}</span>}
      </span>
      {onUndo && (
        <button
          onClick={onUndo}
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--accent)',
            fontSize: 11,
            fontWeight: 500,
            cursor: 'pointer',
            textDecoration: 'underline',
            fontFamily: 'var(--font-sans)',
          }}
        >
          Undo
        </button>
      )}
    </div>
  );
}


function WhySection({ dossier, archetype, contactStatus, personalRep }) {
  // Special handling for probate with non-actionable contact_status:
  // the dossier honestly says "wait — no decision-maker yet" rather
  // than fabricating a primary contact.
  if (archetype.key === 'probate' && contactStatus
      && contactStatus !== 'family_pr_identified') {
    return (
      <Section label="Why this person">
        <p>
          This is an active probate filing — the deceased owner's
          estate will need to make a decision on this property. {' '}
          <em style={{ color: 'var(--text-secondary)' }}>
            {contactStatus === 'no_pr_yet' && (
              'No personal representative has been appointed yet. '
              + 'A family member typically files this within 2–8 weeks.'
            )}
            {contactStatus === 'parties_not_scraped' && (
              'Case parties have not been fully resolved yet — the '
              + 'personal representative may already be appointed but '
              + 'is not yet in our database.'
            )}
            {contactStatus === 'unworkable_pr' && (
              'Personal representative is a corporate or attorney '
              + 'fiduciary — these usually list through established '
              + 'channels rather than direct outreach.'
            )}
          </em>
        </p>
      </Section>
    );
  }

  // Probate with PR identified
  if (archetype.key === 'probate' && personalRep) {
    return (
      <Section label="Why this person">
        <p>
          {personalRep.name} {personalRep.role_source === 'personal_representative'
            ? 'has been formally appointed as personal representative'
            : 'is the petitioner on the probate filing — typically the incoming personal representative'}
          . They control the estate's decision on this property.
        </p>
      </Section>
    );
  }

  // For all other archetypes, fall back to the dossier's
  // recommended_action.reason or build copy from data.
  return (
    <Section label="Why this person">
      <ArchetypeWhy dossier={dossier} archetype={archetype} />
    </Section>
  );
}


function ArchetypeWhy({ dossier, archetype }) {
  const parcel = dossier?.parcel || {};
  const tenure = parcel.tenure_years;
  const isOOA = parcel.is_out_of_state;

  if (archetype.key === 'investor') {
    return (
      <>
        <p>
          This property has been investor-held{tenure ? ` for ${Math.round(tenure)} years` : ''}.
        </p>
        <p>
          Investor-held single-family properties at the 10–12 year mark
          show elevated disposition rates as long-term capital gains
          thresholds align and depreciation cycles complete.
        </p>
        {isOOA && parcel.owner_state && (
          <p>
            The owner mails to {parcel.owner_state} — out-of-area landlord profile.
          </p>
        )}
      </>
    );
  }

  if (archetype.key === 'longTenure') {
    return (
      <>
        <p>
          This home has been owned{tenure ? ` for ${Math.round(tenure)} years` : ' for a long time'}.
        </p>
        <p>
          Owners at this stage often begin considering downsizing,
          relocation, or estate planning — though the timing is rarely public.
        </p>
      </>
    );
  }

  if (archetype.key === 'estateTransition') {
    return (
      <>
        <p>
          This property shows ownership patterns typical of estate transitions —
          long family hold, multi-generational ownership.
        </p>
        <p>
          No probate or estate filing yet — but this profile typically precedes
          a sale or internal transfer within 2–4 years.
        </p>
      </>
    );
  }

  if (archetype.key === 'divorce') {
    return (
      <p>
        A divorce was filed in King County Superior Court.
        Divorce filings of this kind frequently lead to property sale within
        4–8 months as part of asset division. Initial proceedings typically
        take 60–90 days before property decisions begin.
      </p>
    );
  }

  // General fallback
  const reason = dossier?.recommended_action?.reason
              || dossier?.investigation?.recommended_action?.reason;
  if (reason) {
    return <p>{reason}</p>;
  }
  return (
    <p style={{ color: 'var(--text-tertiary)', fontStyle: 'italic' }}>
      Structural ownership signal — see Evidence below for details.
    </p>
  );
}


function NextStepSection({ archetype, contactStatus, inWaitWindow, waitOpens }) {
  // Wait-window override: divorce within 60 days
  if (inWaitWindow && waitOpens) {
    const dateStr = waitOpens.toLocaleDateString(undefined,
      { month: 'long', day: 'numeric', year: 'numeric' });
    return (
      <Section label="Next step">
        <p>
          <strong>Do not reach out yet.</strong>
        </p>
        <p>
          Revisit this lead after {dateStr} (60 days post-filing), when
          property decisions typically begin. Reaching out earlier reads
          as opportunistic and burns the relationship.
        </p>
      </Section>
    );
  }

  // Probate with non-actionable PR
  if (archetype.key === 'probate' && contactStatus
      && contactStatus !== 'family_pr_identified') {
    return (
      <Section label="Next step">
        <p>
          <strong>Hold for now.</strong> We will surface this lead automatically
          once a personal representative is identified and classified.
        </p>
      </Section>
    );
  }

  // Archetype-specific copy
  if (archetype.key === 'probate') {
    return (
      <Section label="Next step">
        <p>
          Send a handwritten condolence letter this week. Follow up with
          a call in 2–3 weeks if no response.
        </p>
      </Section>
    );
  }

  if (archetype.key === 'investor') {
    return (
      <Section label="Next step">
        <p>
          Reach out this week with an off-market inquiry. Position
          yourself as a buyer source before the property is publicly listed.
        </p>
      </Section>
    );
  }

  if (archetype.key === 'longTenure') {
    return (
      <Section label="Next step">
        <p>
          Send a soft introduction letter this week. Position yourself
          as a local resource — not as someone trying to sell their home.
        </p>
        <p>
          Plan a 6–12 month cultivation cycle. Quarterly check-ins are appropriate.
        </p>
      </Section>
    );
  }

  if (archetype.key === 'estateTransition') {
    return (
      <Section label="Next step">
        <p>
          Cultivate over 6–12 months. Prioritize neighbor introductions
          over direct outreach.
        </p>
      </Section>
    );
  }

  return (
    <Section label="Next step">
      <p>Send an introduction letter this week.</p>
    </Section>
  );
}


function ContactSection({ parcel, archetype, equityDollars, personalRep, onGetContactInfo }) {
  const ownerCity = (parcel.owner_city || '').trim();
  const ownerState = (parcel.owner_state || '').trim();
  const propCity = (parcel.city || '').trim().toUpperCase();
  const propState = (parcel.state || '').trim().toUpperCase();
  const ownerOccupied = ownerCity && ownerState
    && ownerCity.toUpperCase() === propCity
    && ownerState.toUpperCase() === propState;
  const outOfArea = ownerCity && ownerState && !ownerOccupied;

  // PR overrides for probate
  const contactName = personalRep?.name || parcel.owner_name;

  return (
    <Section label="Contact">
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13 }}>
        <div style={{
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          color: 'var(--text-tertiary)',
          marginBottom: 3,
        }}>
          Mailing address
        </div>
        <div style={{ color: 'var(--text)', fontFamily: 'var(--font-serif)', fontSize: 13 }}>
          {contactName && <div>{contactName}</div>}
          {ownerOccupied && (
            <div style={{ color: 'var(--text-secondary)' }}>
              {parcel.address}<br />
              {parcel.city}, {parcel.state} {parcel.owner_zip || ''}
            </div>
          )}
          {outOfArea && (
            <div style={{ color: 'var(--text-secondary)' }}>
              Mails to: {ownerCity}, {ownerState}<br />
              <span style={{ color: 'var(--text-tertiary)', fontStyle: 'italic' }}>
                Street: pending resolution
              </span>
            </div>
          )}
          {!ownerOccupied && !outOfArea && (
            <div style={{ color: 'var(--text-tertiary)', fontStyle: 'italic' }}>
              Pending resolution
            </div>
          )}
        </div>

        {archetype.showEquity && equityDollars != null && (
          <div style={{ marginTop: 12 }}>
            <div style={{
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'var(--text-tertiary)',
              marginBottom: 3,
            }}>
              Estimated equity
            </div>
            <div style={{
              fontFamily: 'var(--font-display)',
              fontSize: 16,
              fontWeight: 600,
              color: 'var(--accent)',
            }}>
              {formatEquity(equityDollars)}
            </div>
          </div>
        )}

        {(!ownerOccupied || outOfArea) && (
          <button
            onClick={onGetContactInfo}
            style={{
              marginTop: 12,
              padding: '7px 12px',
              fontSize: 11,
              fontWeight: 500,
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              background: 'transparent',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              fontFamily: 'var(--font-sans)',
            }}
          >
            Get contact info
          </button>
        )}
      </div>
    </Section>
  );
}


function WhatToSaySection({
  deepSignal,
  deepSignalLoading,
  deepSignalError,
  archetype,
  inWaitWindow,
  waitOpens,
  canGenerateDeepSignal,
  onGenerateDeepSignal,
}) {
  // Wait-window: don't show a letter, show a hold message.
  if (inWaitWindow && waitOpens) {
    const dateStr = waitOpens.toLocaleDateString(undefined,
      { month: 'long', day: 'numeric', year: 'numeric' });
    return (
      <Section label="What to say">
        <p style={{
          color: 'var(--text-secondary)',
          fontStyle: 'italic',
          padding: '12px',
          background: 'var(--bg)',
          borderRadius: 'var(--radius-md)',
        }}>
          Outreach window opens {dateStr}. Drafting and copy will appear
          here when the wait period clears.
        </p>
      </Section>
    );
  }

  // Have a Deep Signal — render its content
  if (deepSignal && (deepSignal.motivation || deepSignal.call_script || deepSignal.mail_script)) {
    return (
      <Section label="What to say">
        <DeepSignalContent ds={deepSignal} />
      </Section>
    );
  }

  // No Deep Signal yet — offer generation if eligible, otherwise a
  // generic archetype-specific intro.
  return (
    <Section label="What to say">
      {canGenerateDeepSignal ? (
        <>
          <p style={{ color: 'var(--text-secondary)', marginBottom: 10 }}>
            Generate a {archetype.tone}-tone outreach script tailored to
            this lead's signals.
          </p>
          <button
            onClick={onGenerateDeepSignal}
            disabled={deepSignalLoading}
            style={{
              padding: '8px 14px',
              fontSize: 12,
              fontWeight: 600,
              border: 'none',
              borderRadius: 'var(--radius-md)',
              background: 'var(--text)',
              color: 'var(--bg-card)',
              cursor: deepSignalLoading ? 'wait' : 'pointer',
              opacity: deepSignalLoading ? 0.6 : 1,
              fontFamily: 'var(--font-sans)',
              letterSpacing: '0.03em',
            }}
          >
            {deepSignalLoading ? 'Generating…' : 'Generate Deep Signal'}
          </button>
          {deepSignalError && (
            <div style={{
              marginTop: 8,
              fontSize: 12,
              color: 'var(--call-now)',
              fontStyle: 'italic',
              fontFamily: 'var(--font-serif)',
            }}>
              {deepSignalError}
            </div>
          )}
        </>
      ) : (
        <ArchetypeIntroLetter archetype={archetype} />
      )}
    </Section>
  );
}


function ArchetypeIntroLetter({ archetype }) {
  // Generic placeholder copy for each archetype, used when Deep Signal
  // isn't available. Plain prose, no fake personalization.
  const text = {
    probate: (
      <>
        Open with condolences. Acknowledge the family's loss directly
        but without dwelling. Offer help understanding options — not
        pushing a sale. Make clear there's no pressure. Sign off warmly.
      </>
    ),
    divorce: (
      <>
        Acknowledge that life transitions create property questions.
        Offer to help understand the current market without obligation.
        Keep it brief and neutral.
      </>
    ),
    estateTransition: (
      <>
        Position as a local resource for long-held properties. Offer
        a low-pressure conversation. Lean on neighbor introductions
        when possible.
      </>
    ),
    investor: (
      <>
        Lead with an off-market opportunity. Mention current buyer
        demand for properties like theirs. Frame it as a deal-flow
        inquiry, not a relationship pitch.
      </>
    ),
    longTenure: (
      <>
        Introduce yourself as a local resource. Mention you came across
        their home and wanted to make contact. Frame it as a "no
        expectations" introduction — staying, updating, or eventually
        selling are all fine outcomes.
      </>
    ),
    general: (
      <>
        A neutral introduction noting your local market focus and offering
        a low-pressure conversation about the property.
      </>
    ),
  };
  return (
    <p style={{
      color: 'var(--text-secondary)',
      fontStyle: 'italic',
      fontFamily: 'var(--font-serif)',
      lineHeight: 1.6,
    }}>
      {text[archetype.key] || text.general}
    </p>
  );
}


function DeepSignalContent({ ds }) {
  const [tab, setTab] = useState(
    ds.best_channel === 'mail' ? 'mail' :
    ds.best_channel === 'door' ? 'door' : 'call'
  );
  const tabs = [
    { key: 'call', label: 'Phone',  content: ds.call_script },
    { key: 'mail', label: 'Letter', content: ds.mail_script },
    { key: 'door', label: 'Door',   content: ds.door_script },
  ].filter((t) => t.content);
  const active = tabs.find((t) => t.key === tab) || tabs[0];

  return (
    <>
      {ds.motivation && (
        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 14,
          color: 'var(--text)',
          lineHeight: 1.55,
        }}>
          {ds.motivation}
        </p>
      )}
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
          fontFamily: 'var(--font-sans)',
        }}>
          {ds.timeline && <div>Timeline: {ds.timeline}</div>}
          {ds.best_channel && <div>Lead with: {ds.best_channel}</div>}
        </div>
      )}
      {tabs.length > 1 && (
        <div style={{
          marginTop: 'var(--space-sm)',
          display: 'flex',
          gap: 4,
          borderBottom: '1px solid var(--border)',
        }}>
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              style={{
                padding: '6px 10px',
                fontSize: 11,
                fontWeight: 600,
                letterSpacing: '0.03em',
                border: 'none',
                borderBottom: `2px solid ${tab === t.key ? 'var(--accent)' : 'transparent'}`,
                background: 'transparent',
                color: tab === t.key ? 'var(--text)' : 'var(--text-tertiary)',
                cursor: 'pointer',
                fontFamily: 'var(--font-sans)',
              }}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}
      {active?.content && (
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
      {ds.what_not_to_say && (
        <div style={{
          marginTop: 'var(--space-md)',
          padding: 'var(--space-sm) var(--space-md)',
          background: 'rgba(158, 75, 60, 0.06)',
          borderLeft: '2px solid rgba(158, 75, 60, 0.4)',
          borderRadius: 'var(--radius-sm)',
        }}>
          <div style={{
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: 'var(--call-now)',
            marginBottom: 4,
            fontFamily: 'var(--font-sans)',
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
    </>
  );
}


function EvidenceSection({ dossier }) {
  const matches = dossier?.harvester_matches || [];
  const tags = dossier?.parcel_state_tags || [];
  const sales = dossier?.sales_history || [];
  const parcel = dossier?.parcel || {};

  const items = [];

  // Harvester matches
  for (const m of matches) {
    const label = signalLabel(m.signal_type);
    const date = m.event_date || m.matched_at;
    const dateStr = formatDate(date);
    items.push({
      key: `m-${m.signal_type}-${m.document_ref || date}`,
      label,
      detail: dateStr,
      ref: m.document_ref,
      strict: m.match_strength === 'strict',
    });
  }

  // Parcel state tags
  for (const t of tags) {
    items.push({
      key: `t-${t.kind}`,
      label: t.label,
      detail: t.description,
      strict: false,
    });
  }

  // Tenure
  if (parcel.tenure_years != null) {
    items.push({
      key: 'tenure',
      label: 'KC Assessor Record',
      detail: `${Math.round(parcel.tenure_years)} years owner-occupied`,
      strict: false,
    });
  }

  // Last arms-length
  const lastPrice = dossier?.last_arms_length_price || parcel.last_transfer_price;
  const lastDate = dossier?.last_arms_length_date || parcel.last_transfer_date;
  if (lastPrice && lastPrice > 0 && lastDate) {
    items.push({
      key: 'last-sale',
      label: 'Last arms-length sale',
      detail: `${formatDate(lastDate)} · ${formatValue(lastPrice)}`,
      strict: false,
    });
  }

  // Sales history badge if there were notable transitions
  for (const s of sales.slice(0, 3)) {
    const reason = (s.sale_reason || '').toUpperCase();
    if (reason.includes('PROPERTY SETTLEMENT')) {
      items.push({
        key: `s-divorce-${s.sale_date}`,
        label: 'Sales history: divorce settlement',
        detail: formatDate(s.sale_date),
        strict: false,
      });
    } else if (reason.includes('ESTATE')) {
      items.push({
        key: `s-estate-${s.sale_date}`,
        label: 'Sales history: estate transfer',
        detail: formatDate(s.sale_date),
        strict: false,
      });
    }
  }

  if (items.length === 0) {
    return (
      <Section label="Evidence">
        <p style={{ color: 'var(--text-tertiary)', fontStyle: 'italic' }}>
          Structural pattern only — no court filings or harvester matches yet.
        </p>
      </Section>
    );
  }

  return (
    <Section label="Evidence">
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {items.map((item) => (
          <li
            key={item.key}
            style={{
              padding: '8px 0',
              borderBottom: '0.5px solid var(--border)',
              fontSize: 12,
              fontFamily: 'var(--font-sans)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'baseline' }}>
              <span style={{ color: 'var(--text)', fontWeight: 600 }}>{item.label}</span>
              {item.strict && (
                <span style={{
                  fontSize: 9,
                  fontWeight: 700,
                  letterSpacing: '0.06em',
                  padding: '1px 5px',
                  background: 'var(--accent)',
                  color: 'white',
                  borderRadius: 3,
                }}>
                  STRICT
                </span>
              )}
            </div>
            {item.detail && (
              <div style={{
                color: 'var(--text-secondary)',
                marginTop: 2,
                fontFamily: 'var(--font-serif)',
                fontStyle: 'italic',
                lineHeight: 1.4,
              }}>
                {item.detail}
              </div>
            )}
            {item.ref && (
              <div style={{
                color: 'var(--text-tertiary)',
                marginTop: 2,
                fontSize: 10,
                fontFamily: 'monospace',
              }}>
                {item.ref}
              </div>
            )}
          </li>
        ))}
      </ul>
    </Section>
  );
}


function OutcomeDropdown({ archetype, events, onSelect, disabled }) {
  // Show the dropdown with archetype-specific options. If the agent
  // has already logged an outcome, surface it; otherwise show
  // "Select outcome…" as the placeholder.
  const lastOutcomeEvent = events.find((e) =>
    ['got_response', 'no_response', 'listing_discussion', 'closed'].includes(e.event_type)
  );
  const lastLabel = lastOutcomeEvent?.event_data?.label;

  return (
    <div style={{
      marginTop: 'var(--space-md)',
      padding: '12px',
      background: 'var(--bg)',
      borderRadius: 'var(--radius-md)',
    }}>
      <div style={{
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        color: 'var(--text-tertiary)',
        marginBottom: 6,
        fontFamily: 'var(--font-sans)',
      }}>
        Outcome
      </div>
      <select
        value={lastLabel || ''}
        onChange={(e) => e.target.value && onSelect(e.target.value)}
        disabled={disabled}
        style={{
          width: '100%',
          padding: '8px 10px',
          fontSize: 13,
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          background: 'var(--bg-card)',
          color: 'var(--text)',
          fontFamily: 'var(--font-sans)',
          cursor: disabled ? 'wait' : 'pointer',
        }}
      >
        <option value="">Select…</option>
        {archetype.outcomes.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </div>
  );
}


function ActionButtons({
  archetype,
  inWaitWindow,
  currentStatus,
  isColdVisitor,
  actionPending,
  canGenerateSixLetters,
  onSendLetter,
  onExportCrm,
  onMarkWorking,
  onNotRelevant,
  onSixLetters,
}) {
  // Suppress primary send during wait window
  const showSend = !inWaitWindow;

  return (
    <div style={{
      marginTop: 'var(--space-lg)',
      paddingTop: 'var(--space-md)',
      borderTop: '1px solid var(--border)',
    }}>
      {showSend && (
        <button
          onClick={onSendLetter}
          disabled={actionPending}
          style={{
            width: '100%',
            padding: '14px',
            fontSize: 14,
            fontWeight: 600,
            background: 'var(--accent)',
            color: 'var(--text-inverse)',
            border: 'none',
            borderRadius: 'var(--radius-md)',
            cursor: actionPending ? 'wait' : 'pointer',
            fontFamily: 'var(--font-sans)',
            letterSpacing: '0.02em',
            marginBottom: 10,
            opacity: actionPending ? 0.6 : 1,
          }}
        >
          {archetype.primaryAction.label}
        </button>
      )}

      <div style={{
        display: 'flex',
        gap: 8,
        marginBottom: 12,
      }}>
        <button
          onClick={onExportCrm}
          disabled={actionPending}
          style={{
            padding: '7px 14px',
            fontSize: 11,
            fontWeight: 400,
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            background: 'transparent',
            color: 'var(--text-secondary)',
            cursor: actionPending ? 'wait' : 'pointer',
            fontFamily: 'var(--font-sans)',
            minWidth: 130,
          }}
        >
          Export to CRM
        </button>
        {canGenerateSixLetters && (
          <button
            onClick={onSixLetters}
            style={{
              padding: '7px 14px',
              fontSize: 11,
              fontWeight: 400,
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              background: 'transparent',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              fontFamily: 'var(--font-sans)',
              minWidth: 130,
            }}
          >
            Six Letters
          </button>
        )}
      </div>

      <div style={{
        display: 'flex',
        gap: 0,
        alignItems: 'center',
        paddingTop: 8,
        borderTop: '0.5px dashed var(--border)',
      }}>
        {currentStatus !== 'working' && (
          <button
            onClick={onMarkWorking}
            disabled={actionPending}
            style={quietButtonStyle('var(--accent)')}
          >
            Mark as working
          </button>
        )}
        {currentStatus === 'working' && (
          <span style={{
            ...quietButtonStyle('var(--text-tertiary)'),
            cursor: 'default',
          }}>
            Working
          </span>
        )}
        <span style={{
          width: 1,
          height: 12,
          background: 'var(--border)',
          margin: '0 4px',
        }} />
        {currentStatus !== 'not_relevant' && (
          <button
            onClick={onNotRelevant}
            disabled={actionPending}
            style={quietButtonStyle('var(--call-now)')}
          >
            Not relevant
          </button>
        )}
      </div>

      {isColdVisitor && (
        <div style={{
          marginTop: 12,
          fontSize: 11,
          color: 'var(--text-tertiary)',
          fontStyle: 'italic',
          fontFamily: 'var(--font-serif)',
          textAlign: 'center',
        }}>
          Sign in to track this lead
        </div>
      )}
    </div>
  );
}


function quietButtonStyle(hoverColor) {
  return {
    background: 'transparent',
    border: 'none',
    padding: '6px 10px',
    fontSize: 11,
    color: 'var(--text-tertiary)',
    cursor: 'pointer',
    fontFamily: 'var(--font-sans)',
    transition: 'color var(--transition)',
  };
}


function HistorySection({ events }) {
  return (
    <div style={{
      marginTop: 'var(--space-lg)',
      paddingTop: 'var(--space-md)',
      borderTop: '0.5px dashed var(--border)',
    }}>
      <div style={{
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        color: 'var(--text-tertiary)',
        marginBottom: 6,
        fontFamily: 'var(--font-sans)',
      }}>
        History
      </div>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {events.map((ev) => (
          <li key={ev.id} style={{
            fontSize: 11,
            color: 'var(--text-secondary)',
            fontFamily: 'var(--font-sans)',
            padding: '3px 0',
          }}>
            • {humanEventLabel(ev)} — {formatShortDate(ev.created_at)}
          </li>
        ))}
      </ul>
    </div>
  );
}


// ── Section shell ────────────────────────────────────────────────

function Section({ label, children }) {
  return (
    <section style={{ marginTop: 'var(--space-lg)' }}>
      <div style={{
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        color: 'var(--accent)',
        marginBottom: 6,
        fontFamily: 'var(--font-sans)',
      }}>
        {label}
      </div>
      <div style={{
        fontFamily: 'var(--font-serif)',
        fontSize: 14,
        color: 'var(--text)',
        lineHeight: 1.55,
      }}>
        {/* Each <p> child gets a small bottom margin via this style. */}
        <div className="ss-prose">
          {children}
        </div>
      </div>
      <style>{`
        .ss-prose p { margin-bottom: 8px; }
        .ss-prose p:last-child { margin-bottom: 0; }
      `}</style>
    </section>
  );
}


// ── Helpers ──────────────────────────────────────────────────────

function formatValue(v) {
  if (!v) return '—';
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000)     return `$${Math.round(v / 1_000)}K`;
  return `$${v}`;
}

function formatDate(iso) {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleDateString(undefined,
      { year: 'numeric', month: 'short', day: 'numeric' });
  } catch {
    return iso;
  }
}

function formatShortDate(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleDateString(undefined,
      { month: 'short', day: 'numeric' });
  } catch {
    return iso;
  }
}

function signalLabel(t) {
  const labels = {
    probate:        'King County Probate Filing',
    obituary:       'Obituary match',
    divorce:        'King County Divorce Filing',
    tax_foreclosure:'Tax foreclosure filing',
  };
  return labels[t] || (t ? t.replace(/_/g, ' ') : 'Signal');
}

function humanEventLabel(ev) {
  const labels = {
    working:             'Marked working',
    not_relevant:        'Marked not relevant',
    sent_to_crm:         'Exported to CRM',
    got_response:        'Logged response',
    no_response:         'Logged no response',
    listing_discussion:  'Listing discussion',
    closed:              'Closed',
    reactivated:         'Reactivated',
  };
  const base = labels[ev.event_type] || ev.event_type;
  if (ev.event_data?.label) return `${base}: ${ev.event_data.label}`;
  return base;
}
