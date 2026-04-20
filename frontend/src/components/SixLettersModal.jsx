import { useState, useMemo } from 'react';
import { generateSixLetters } from '../lib/sixLetters.js';

/**
 * SixLettersModal — renders the 6-letter sequence for a parcel in a
 * centered modal with a day-tab navigator across the top.
 *
 * Props:
 *   parcel:   the parcel object from ParcelDossier (owner_name, address,
 *             city, owner_type, tenure_years, is_absentee, is_out_of_state)
 *   onClose:  () => void
 */
export default function SixLettersModal({ parcel, onClose }) {
  const [activeIdx, setActiveIdx] = useState(0);

  const letters = useMemo(() => generateSixLetters({
    owner_name:    parcel.owner_name,
    address:       parcel.address,
    city:          parcel.city,
    owner_type:    parcel.owner_type,
    tenure_years:  parcel.tenure_years,
    is_absentee:   parcel.is_absentee,
    is_out_of_state: parcel.is_out_of_state,
    neighborhood:  parcel.city,
  }), [parcel]);

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
          <div style={{
            fontSize: 12,
            color: 'var(--text-tertiary)',
            fontStyle: 'italic',
            marginBottom: 'var(--space-lg)',
            fontFamily: 'var(--font-serif)',
          }}>
            Trigger: {letter.trigger}
          </div>

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
            Templates are personalized from parcel data. No AI, no cost.
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
