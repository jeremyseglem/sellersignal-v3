import { useState, useMemo } from 'react';
import { generateSixLetters } from '../lib/sixLetters.js';
import { useAuth } from '../lib/AuthContext.jsx';

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
          {letters.map((L, i) => (
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
              }}>{L.dayLabel}</div>
              <div style={{
                fontFamily: 'var(--font-display)',
                fontSize: 13,
                fontWeight: 600,
                marginTop: 2,
              }}>{L.name}</div>
            </button>
          ))}
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

        {/* Footer with copy action */}
        <div style={{
          padding: 'var(--space-md) var(--space-lg)',
          borderTop: '1px solid var(--border)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 'var(--space-md)',
        }}>
          <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
            {usingAgentVoice
              ? 'Letters in your voice. Lead-specific details substituted automatically.'
              : 'Templates are personalized from parcel data. No AI, no cost.'}
          </div>
          <button
            onClick={() => {
              navigator.clipboard?.writeText(letter.body).catch(() => {});
            }}
            style={{
              padding: '8px 16px',
              fontSize: 12,
              fontWeight: 600,
              background: 'var(--text)',
              color: 'var(--bg-card)',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              cursor: 'pointer',
            }}
          >
            Copy letter
          </button>
        </div>
      </div>
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
  // {num, name, dayLabel, trigger, body} shape.
  return block.letter_sequence
    .filter(L => L && (L.body || L.title))
    .map((L, idx) => ({
      num:      idx + 1,
      name:     L.title || `Letter ${idx + 1}`,
      dayLabel: `Day ${L.day || (idx === 0 ? 1 : idx === 1 ? 30 : idx === 2 ? 60 : idx === 3 ? 90 : idx === 4 ? 135 : 180)}`,
      trigger:  '',  // not used in agent-voice mode (the LLM doesn't emit a trigger field)
      body:     fill(L.body || ''),
    }));
}
