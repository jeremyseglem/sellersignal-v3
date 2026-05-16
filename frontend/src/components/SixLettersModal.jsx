import { useState, useMemo, useEffect } from 'react';
import { generateSixLetters } from '../lib/sixLetters.js';
import { useAuth } from '../lib/AuthContext.jsx';
import { letters as lettersApi, safeErrorMessage } from '../api/client.js';

/**
 * SixLettersModal — renders the 6-letter sequence for a parcel in a
 * centered modal with a day-tab navigator across the top.
 *
 * Source priority for letter content:
 *   1. Agent's voice-generated sequence from profile.generated_scripts
 *      (set during /profile/voice onboarding) — the agent's own voice,
 *      LLM-produced once and stored. Tokens substituted at render time.
 *   2. Static templated sequence from sixLetters.js — the v1 default
 *      that ships before any agent has voice-onboarded.
 *
 * Props:
 *   parcel:           the parcel object from ParcelDossier (owner_name,
 *                     address, city, owner_type, tenure_years,
 *                     is_absentee, is_out_of_state)
 *   harvesterMatches: optional — harvester_matches array from the dossier;
 *                     used to resolve probate PR / decedent for addressing
 *   archetypeKey:     optional — archetype.key from detectArchetype;
 *                     dispatches to the right 6-letter sequence
 *   onClose:          () => void
 */
export default function SixLettersModal({
  parcel,
  harvesterMatches,
  archetypeKey,
  onClose,
}) {
  const [activeIdx, setActiveIdx] = useState(0);
  const { profile } = useAuth();

  // Send-wiring state. Fetched on mount and refreshed after any send.
  const [balanceCents, setBalanceCents] = useState(null); // null = loading
  const [sentLetters, setSentLetters]   = useState([]);   // letters_sent_v3 rows
  const [sequences, setSequences]       = useState([]);   // letter_sequences_v3 rows
  const [confirmAction, setConfirmAction] = useState(null);
  const [sending, setSending]           = useState(false);
  const [errorMsg, setErrorMsg]         = useState(null);
  const [successMsg, setSuccessMsg]     = useState(null);

  // Refetch helper — used on mount and after any send/cancel.
  const pin = parcel?.pin;
  const refreshLetterData = async () => {
    if (!pin) return;
    try {
      const [bal, byParcel] = await Promise.all([
        lettersApi.balance(),
        lettersApi.byParcel(pin),
      ]);
      setBalanceCents(bal.balance_cents);
      setSentLetters(byParcel.letters || []);
      setSequences(byParcel.sequences || []);
    } catch (e) {
      // Non-fatal on open — balance just won't display
      console.warn('Failed to load letter data:', e);
    }
  };
  useEffect(() => { refreshLetterData(); }, [pin]); // eslint-disable-line

  const letters = useMemo(() => {
    // Try agent's voice-generated sequence first.
    const agentLetters = agentLetterSequence(profile, archetypeKey, parcel, harvesterMatches);
    if (agentLetters && agentLetters.length > 0) return agentLetters;

    // Fall back to static templated sequence.
    return generateSixLetters({
      owner_name:    parcel.owner_name,
      address:       parcel.address,
      city:          parcel.city,
      owner_type:    parcel.owner_type,
      tenure_years:  parcel.tenure_years,
      is_absentee:   parcel.is_absentee,
      is_out_of_state: parcel.is_out_of_state,
      neighborhood:  parcel.city,
    }, harvesterMatches || [], archetypeKey || null);
  }, [profile, parcel, harvesterMatches, archetypeKey]);

  const usingAgentVoice = useMemo(
    () => Boolean(agentLetterSequence(profile, archetypeKey, parcel, harvesterMatches)),
    [profile, parcel, harvesterMatches, archetypeKey]
  );

  const letter = letters[activeIdx];
  const mailAddr = parcel.owner_address
    ? `${parcel.owner_address}${parcel.owner_city ? ', ' + parcel.owner_city : ''}${parcel.owner_state ? ', ' + parcel.owner_state : ''}`
    : parcel.address;

  // ── Derived: status per letter index ──────────────────────────────
  // For each of the 6 positions (1-6), find the most recent letters_sent_v3
  // row from sentLetters. The row carries status (created, mailed,
  // delivered, etc.) — we surface a short label on each tab.
  const statusByIndex = useMemo(() => {
    const map = {};
    for (const row of sentLetters) {
      const idx = row.letter_index;
      if (!map[idx] || new Date(row.created_at) > new Date(map[idx].created_at)) {
        map[idx] = row;
      }
    }
    return map;
  }, [sentLetters]);

  const activeSequence = useMemo(() =>
    sequences.find((s) => s.status === 'active') || null,
    [sequences]
  );

  const SINGLE_COST_CENTS = 299;
  const SEQUENCE_COST_CENTS = 1499;

  const canSendSingle = balanceCents != null && balanceCents >= SINGLE_COST_CENTS && !activeSequence;
  const canStartSeq = balanceCents != null && balanceCents >= SEQUENCE_COST_CENTS && !activeSequence;

  // ── Action handlers (called from confirm dialog) ──────────────────
  const doSendSingle = async () => {
    setSending(true);
    setErrorMsg(null);
    try {
      const result = await lettersApi.send(pin, activeIdx + 1);
      setSuccessMsg(
        `Letter ${activeIdx + 1} accepted by Lob (test mode = ${result.lob_mode}). ` +
        `Status: ${result.status}.`
      );
      await refreshLetterData();
    } catch (e) {
      setErrorMsg(safeErrorMessage(e, 'Send failed'));
    } finally {
      setSending(false);
      setConfirmAction(null);
    }
  };

  const doStartSequence = async () => {
    setSending(true);
    setErrorMsg(null);
    try {
      const result = await lettersApi.startSequence(pin);
      setSuccessMsg(
        `6-letter sequence started (${result.letters_scheduled} letters scheduled, ` +
        `letter 1 sending immediately).`
      );
      await refreshLetterData();
    } catch (e) {
      setErrorMsg(safeErrorMessage(e, 'Sequence start failed'));
    } finally {
      setSending(false);
      setConfirmAction(null);
    }
  };

  const doPrintPdf = async () => {
    setSending(true);
    setErrorMsg(null);
    try {
      const result = await lettersApi.renderPdfUrl(pin, activeIdx + 1);
      // Open the HTML in a new window — user uses browser Cmd+P / Ctrl+P
      // → Save as PDF for the final print-friendly artifact.
      const blob = new Blob([result.html], { type: 'text/html' });
      const url = URL.createObjectURL(blob);
      const win = window.open(url, '_blank');
      if (!win) {
        setErrorMsg('Popup blocked. Allow popups and try again.');
      } else {
        setSuccessMsg(`Letter ${activeIdx + 1} opened in new window. Use Print → Save as PDF.`);
      }
      // Clean up the blob URL after the new window has had time to load
      setTimeout(() => URL.revokeObjectURL(url), 30000);
      await refreshLetterData();
    } catch (e) {
      setErrorMsg(safeErrorMessage(e, 'PDF render failed'));
    } finally {
      setSending(false);
      setConfirmAction(null);
    }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(44, 36, 24, 0.55)',
        zIndex: 2000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 'var(--space-lg)',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--bg-card)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-lg)',
          maxWidth: 820,
          width: '100%',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div style={{
          padding: 'var(--space-lg) var(--space-lg) var(--space-md)',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 'var(--space-md)',
        }}>
          <div>
            <div style={{
              fontSize: 11,
              color: 'var(--text-tertiary)',
              fontWeight: 600,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
            }}>
              The Six Letters
            </div>
            <h2 style={{
              fontFamily: 'var(--font-display)',
              fontSize: 22,
              fontWeight: 600,
              color: 'var(--text)',
              marginTop: 4,
              lineHeight: 1.15,
            }}>
              {parcel.owner_name || 'Property owner'}
            </h2>
            <div style={{
              fontSize: 12,
              color: 'var(--text-secondary)',
              marginTop: 2,
            }}>
              {parcel.address}{parcel.city ? ` · ${parcel.city}, ${parcel.state}` : ''}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              width: 32, height: 32,
              borderRadius: '50%',
              background: 'var(--bg)',
              color: 'var(--text-secondary)',
              fontSize: 18,
              lineHeight: 1,
              flexShrink: 0,
            }}
            aria-label="Close"
          >×</button>
        </div>

        {/* Tab navigator */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(6, 1fr)',
          gap: 8,
          padding: 'var(--space-md) var(--space-lg)',
          background: 'var(--bg)',
          borderBottom: '1px solid var(--border)',
        }}>
          {letters.map((L, i) => {
            const status = statusByIndex[L.num];
            const statusLabel = status ? (
              status.method === 'pdf_download' ? 'PDF' :
              status.status === 'scheduled' || (status.lob_send_date && new Date(status.lob_send_date) > new Date()) ? 'scheduled' :
              status.status === 'delivered' ? 'delivered' :
              status.status === 'mailed' || status.status === 'in_transit' || status.status === 'in_local_area' ? 'mailed' :
              status.status === 'created' ? 'queued' :
              status.status === 'cancelled' ? 'cancelled' :
              status.status === 'failed' ? 'failed' :
              status.status
            ) : null;
            return (
            <button
              key={L.num}
              onClick={() => setActiveIdx(i)}
              style={{
                padding: '10px 8px',
                border: `1px solid ${activeIdx === i ? 'var(--accent)' : 'var(--border)'}`,
                background: activeIdx === i ? 'var(--accent)' : 'var(--bg-card)',
                color: activeIdx === i ? 'var(--bg-card)' : 'var(--text-secondary)',
                borderRadius: 'var(--radius-md)',
                cursor: 'pointer',
                textAlign: 'left',
                transition: 'all var(--transition)',
              }}
            >
              <div style={{
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: '0.05em',
                textTransform: 'uppercase',
                opacity: 0.85,
              }}>{L.dayLabel}{statusLabel && <span style={{
                marginLeft: 6,
                padding: '1px 5px',
                background: activeIdx === i ? 'rgba(255,255,255,0.2)' : 'var(--bg)',
                borderRadius: 'var(--radius-sm)',
                fontSize: 9,
                letterSpacing: '0.02em',
                textTransform: 'none',
                fontWeight: 500,
              }}>{statusLabel}</span>}</div>
              <div style={{
                fontFamily: 'var(--font-display)',
                fontSize: 13,
                fontWeight: 600,
                marginTop: 2,
              }}>{L.name}</div>
            </button>
          );})}
        </div>

        {/* Letter body */}
        <div style={{
          flex: 1,
          overflowY: 'auto',
          padding: 'var(--space-lg)',
          background: '#FDFBF7',
        }}>
          <div style={{
            fontSize: 10,
            color: 'var(--text-tertiary)',
            fontWeight: 600,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            marginBottom: 4,
          }}>
            Letter {letter.num} of 6 · {letter.dayLabel}
          </div>
          <div style={{
            fontFamily: 'var(--font-display)',
            fontSize: 20,
            fontWeight: 600,
            color: 'var(--text)',
            marginBottom: 'var(--space-xs)',
          }}>
            {letter.name}
          </div>
          {letter.trigger && (
            <div style={{
              fontSize: 12,
              color: 'var(--text-tertiary)',
              fontStyle: 'italic',
              marginBottom: 'var(--space-lg)',
              fontFamily: 'var(--font-serif)',
            }}>
              Trigger: {letter.trigger}
            </div>
          )}

          {/* Recipient block */}
          <div style={{
            fontSize: 13,
            color: 'var(--text-secondary)',
            marginBottom: 'var(--space-lg)',
            fontFamily: 'var(--font-serif)',
          }}>
            {parcel.owner_name && <div style={{ color: 'var(--text)' }}>{parcel.owner_name}</div>}
            <div>{mailAddr}</div>
          </div>

          {/* Letter body */}
          <div style={{
            fontFamily: 'var(--font-serif)',
            fontSize: 15,
            color: 'var(--text)',
            lineHeight: 1.7,
            whiteSpace: 'pre-line',
          }}>
            {letter.body}
          </div>
        </div>

        {/* Error / success banners */}
        {(errorMsg || successMsg) && (
          <div style={{
            padding: 'var(--space-sm) var(--space-lg)',
            background: errorMsg ? '#FEF2F2' : '#F0FDF4',
            color: errorMsg ? '#991B1B' : '#166534',
            borderTop: '1px solid var(--border)',
            fontSize: 12,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 'var(--space-md)',
          }}>
            <div>{errorMsg || successMsg}</div>
            <button
              onClick={() => { setErrorMsg(null); setSuccessMsg(null); }}
              style={{
                background: 'transparent', border: 'none', cursor: 'pointer',
                fontSize: 14, color: 'inherit', flexShrink: 0,
              }}
              aria-label="Dismiss"
            >×</button>
          </div>
        )}

        {/* Footer — three send buttons + balance */}
        <div style={{
          padding: 'var(--space-md) var(--space-lg)',
          borderTop: '1px solid var(--border)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 'var(--space-md)',
          flexWrap: 'wrap',
        }}>
          <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
            Balance:&nbsp;
            <span style={{ color: 'var(--text)', fontWeight: 600 }}>
              {balanceCents == null ? '…' : `$${(balanceCents / 100).toFixed(2)}`}
            </span>
            {activeSequence && (
              <>
                &nbsp;·&nbsp;
                <span style={{ color: '#92400E' }}>Sequence active</span>
              </>
            )}
          </div>

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button
              onClick={() => setConfirmAction({
                type: 'pdf',
                label: `Print Letter ${activeIdx + 1} to PDF`,
                cost: 0,
                handler: doPrintPdf,
              })}
              disabled={sending}
              style={{
                padding: '8px 14px', fontSize: 12, fontWeight: 600,
                background: 'var(--bg)', color: 'var(--text)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                cursor: sending ? 'not-allowed' : 'pointer',
                opacity: sending ? 0.5 : 1,
              }}
            >
              Print to PDF
              <span style={{ marginLeft: 6, color: 'var(--text-tertiary)', fontWeight: 400 }}>
                free
              </span>
            </button>

            <button
              onClick={() => setConfirmAction({
                type: 'single',
                label: `Send Letter ${activeIdx + 1}`,
                cost: SINGLE_COST_CENTS,
                handler: doSendSingle,
              })}
              disabled={!canSendSingle || sending}
              title={
                !canSendSingle && balanceCents != null && balanceCents < SINGLE_COST_CENTS
                  ? 'Insufficient balance — top up to send'
                  : activeSequence ? 'Active sequence — cancel it first to send a single letter'
                  : ''
              }
              style={{
                padding: '8px 14px', fontSize: 12, fontWeight: 600,
                background: canSendSingle && !sending ? 'var(--bg)' : 'var(--bg)',
                color: canSendSingle && !sending ? 'var(--text)' : 'var(--text-tertiary)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                cursor: canSendSingle && !sending ? 'pointer' : 'not-allowed',
                opacity: canSendSingle && !sending ? 1 : 0.5,
              }}
            >
              Send Letter {activeIdx + 1}
              <span style={{ marginLeft: 6, color: 'var(--text-tertiary)', fontWeight: 400 }}>
                $2.99
              </span>
            </button>

            <button
              onClick={() => setConfirmAction({
                type: 'sequence',
                label: 'Start Full 6-Letter Sequence',
                cost: SEQUENCE_COST_CENTS,
                handler: doStartSequence,
              })}
              disabled={!canStartSeq || sending}
              title={
                !canStartSeq && balanceCents != null && balanceCents < SEQUENCE_COST_CENTS
                  ? 'Insufficient balance — top up to send'
                  : activeSequence ? 'Sequence already active for this parcel'
                  : ''
              }
              style={{
                padding: '8px 14px', fontSize: 12, fontWeight: 600,
                background: canStartSeq && !sending ? 'var(--accent)' : 'var(--bg)',
                color: canStartSeq && !sending ? 'var(--bg-card)' : 'var(--text-tertiary)',
                border: '1px solid ' + (canStartSeq && !sending ? 'var(--accent)' : 'var(--border)'),
                borderRadius: 'var(--radius-md)',
                cursor: canStartSeq && !sending ? 'pointer' : 'not-allowed',
                opacity: canStartSeq && !sending ? 1 : 0.5,
              }}
            >
              Start Full Sequence
              <span style={{ marginLeft: 6, opacity: 0.85, fontWeight: 400 }}>
                $14.99
              </span>
            </button>
          </div>
        </div>
      </div>

      {/* Confirm dialog — modal-on-modal */}
      {confirmAction && (
        <div
          onClick={(e) => { e.stopPropagation(); if (!sending) setConfirmAction(null); }}
          style={{
            position: 'fixed', inset: 0, zIndex: 2100,
            background: 'rgba(0,0,0,0.45)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: 'var(--space-lg)',
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'var(--bg-card)',
              borderRadius: 'var(--radius-lg)',
              boxShadow: 'var(--shadow-lg)',
              maxWidth: 460, width: '100%',
              padding: 'var(--space-lg)',
            }}
          >
            <h3 style={{
              fontFamily: 'var(--font-display)',
              fontSize: 20, fontWeight: 600,
              color: 'var(--text)', marginBottom: 'var(--space-sm)',
            }}>
              Confirm
            </h3>
            <div style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 'var(--space-md)' }}>
              {confirmAction.type === 'pdf' && (
                <>Render Letter {activeIdx + 1} as HTML and open in a new window for browser print. <strong>No charge.</strong></>
              )}
              {confirmAction.type === 'single' && (
                <>Send Letter {activeIdx + 1} to <strong>{parcel.owner_name || 'the property owner'}</strong> at <strong>{parcel.address}</strong>.
                  &nbsp;Deducts <strong>$2.99</strong> from your balance.</>
              )}
              {confirmAction.type === 'sequence' && (
                <>Start the full 6-letter sequence to <strong>{parcel.owner_name || 'the property owner'}</strong>.
                  &nbsp;Letter 1 sends immediately; letters 2-6 schedule at days 30, 60, 90, 135, 180.
                  &nbsp;Deducts <strong>$14.99</strong> from your balance.</>
              )}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-sm)' }}>
              <button
                onClick={() => setConfirmAction(null)}
                disabled={sending}
                style={{
                  padding: '8px 16px', fontSize: 13, fontWeight: 600,
                  background: 'var(--bg)', color: 'var(--text)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)',
                  cursor: sending ? 'not-allowed' : 'pointer',
                  opacity: sending ? 0.5 : 1,
                }}
              >
                Cancel
              </button>
              <button
                onClick={confirmAction.handler}
                disabled={sending}
                style={{
                  padding: '8px 16px', fontSize: 13, fontWeight: 600,
                  background: 'var(--accent)', color: 'var(--bg-card)',
                  border: '1px solid var(--accent)',
                  borderRadius: 'var(--radius-md)',
                  cursor: sending ? 'not-allowed' : 'pointer',
                  opacity: sending ? 0.7 : 1,
                }}
              >
                {sending ? 'Sending…' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────────
// agentLetterSequence — pulls the agent's voice-generated 6-letter
// sequence for the given archetype, substitutes lead-specific tokens,
// and returns it in the shape SixLettersModal expects:
//   [{ num, name, dayLabel, trigger, body }, ...]
//
// Returns null when:
//   - no profile (not signed in or profile not loaded yet)
//   - profile has no generated_scripts at all
//   - profile has generated_scripts but not for this archetype
//   - the archetype block exists but has no letter_sequence array
//
// Token vocabulary matches the prompt construction in
// backend/agent_voice/prompts.py:
//   [PROPERTY_ADDRESS], [NEIGHBORHOOD], [RECIPIENT_NAME],
//   [DECEDENT_NAME], [AGENT_NAME]
// ─────────────────────────────────────────────────────────────────────
function agentLetterSequence(profile, archetypeKey, parcel, harvesterMatches) {
  if (!profile || !archetypeKey) return null;
  const scripts = profile.generated_scripts;
  if (!scripts || typeof scripts !== 'object') return null;

  const block = scripts[archetypeKey];
  if (!block || typeof block !== 'object') return null;
  if (!Array.isArray(block.letter_sequence) || block.letter_sequence.length === 0) return null;

  // Resolve lead tokens (same logic as agentGeneratedScripts in
  // ParcelDossierV2.jsx — kept duplicated here so the modal works
  // standalone without importing the dossier's helper).
  const matches = harvesterMatches || [];
  let pr = null, decedent = null;
  for (const m of matches) {
    if (!pr && m.personal_representative && m.personal_representative.name_first) {
      pr = m.personal_representative;
    }
    if (!decedent && m.signal_type === 'probate') {
      const parties = m.all_case_parties || [];
      const dec = parties.find((p) => p.role === 'deceased' || p.role === 'decedent');
      if (dec && (dec.name_first || dec.name_last)) decedent = dec;
    }
    if (pr && decedent) break;
  }

  const ownerName = parcel?.owner_name || '';
  const looksLikeEntity = /\b(trust|llc|inc|corp|company|co\.?|partners|llp|lp)\b/i.test(ownerName);
  const ownerFirst = (!looksLikeEntity && ownerName) ? ownerName.trim().split(/\s+/)[0] : null;

  let recipientName;
  if (archetypeKey === 'probate' && pr?.name_first) {
    recipientName = pr.name_first;
  } else if (archetypeKey === 'trust') {
    recipientName = 'Trustees';
  } else if (looksLikeEntity) {
    recipientName = ownerName;
  } else if (ownerFirst) {
    recipientName = ownerFirst;
  } else {
    recipientName = 'Friend';
  }

  const decedentName = decedent
    ? `${decedent.name_first || ''} ${decedent.name_last || ''}`.trim()
    : 'your loved one';

  const tokens = {
    '[PROPERTY_ADDRESS]': parcel?.address || 'this property',
    '[NEIGHBORHOOD]':     parcel?.city || 'the area',
    '[RECIPIENT_NAME]':   recipientName,
    '[DECEDENT_NAME]':    decedentName,
    '[AGENT_NAME]':       profile.full_name || '',
  };

  function fill(s) {
    if (typeof s !== 'string') return s;
    let out = s;
    for (const [tok, val] of Object.entries(tokens)) {
      const esc = tok.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      out = out.replace(new RegExp(esc, 'g'), val);
    }
    return out;
  }

  // Map agent's {day, title, body} shape onto the modal's expected
  // {num, name, dayLabel, trigger, body} shape. Both title and body
  // run through fill() so tokens like [PROPERTY_ADDRESS] in titles
  // (e.g. "Regarding the property at [PROPERTY_ADDRESS]") get
  // substituted, not displayed raw.
  return block.letter_sequence
    .filter(L => L && (L.body || L.title))
    .map((L, idx) => ({
      num:      idx + 1,
      name:     fill(L.title || `Letter ${idx + 1}`),
      dayLabel: `Day ${L.day || (idx === 0 ? 1 : idx === 1 ? 30 : idx === 2 ? 60 : idx === 3 ? 90 : idx === 4 ? 135 : 180)}`,
      trigger:  '',  // not used in agent-voice mode (the LLM doesn't emit a trigger field)
      body:     fill(L.body || ''),
    }));
}
