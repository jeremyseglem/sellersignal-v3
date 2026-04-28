/**
 * ClaimZipModal — the cold-visitor conversion gate.
 *
 * Fired when a non-authenticated user clicks any Lead Memory action
 * button in the dossier (Mark as working, Not relevant, Export to CRM,
 * Send letter, Get contact info). The dossier itself renders fully
 * for cold visitors — they can read the WHY, NEXT STEP, CONTACT,
 * WHAT TO SAY, and EVIDENCE sections. The modal only fires on
 * actions that require auth.
 *
 * Per the v4 spec, the conversion happens AFTER engagement, not
 * before. The visitor has already read a real lead and decided it's
 * valuable. The modal asks them to commit at the moment of highest
 * intent.
 *
 * V1 routing: "Claim {ZIP}" sends them to /signup with the ZIP as
 * a query param so signup can pre-fill territory selection. "Maybe
 * later" closes the modal — they keep browsing.
 *
 * Props:
 *   zip      — the ZIP being claimed (rendered in the headline)
 *   onClose  — handler for the X button and "Maybe later"
 */
export default function ClaimZipModal({ zip, onClose }) {
  const headline = zip ? `Claim ${zip} to track this lead` : 'Claim your territory to track this lead';
  const body = zip
    ? `You're looking at one of the active sellers in ${zip} this week. Claim this ZIP to track your outreach, save your progress, and get next week's sellers automatically.`
    : `Claim a territory to track your outreach, save your progress, and get next week's sellers automatically.`;

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
          maxWidth: 480,
          width: '100%',
          padding: 'var(--space-xl)',
          fontFamily: 'var(--font-sans)',
        }}
      >
        <h2 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 22,
          fontWeight: 600,
          color: 'var(--text)',
          lineHeight: 1.2,
          letterSpacing: '-0.005em',
        }}>
          {headline}
        </h2>
        <p style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 14,
          color: 'var(--text-secondary)',
          lineHeight: 1.6,
          marginTop: 'var(--space-md)',
        }}>
          {body}
        </p>
        {zip && (
          <p style={{
            fontFamily: 'var(--font-serif)',
            fontSize: 13,
            color: 'var(--text-tertiary)',
            fontStyle: 'italic',
            marginTop: 'var(--space-sm)',
          }}>
            {zip} is currently unclaimed.
          </p>
        )}
        <div style={{
          marginTop: 'var(--space-lg)',
          padding: '12px',
          background: 'var(--bg)',
          borderRadius: 'var(--radius-md)',
          fontSize: 12,
          color: 'var(--text)',
          fontFamily: 'var(--font-sans)',
          textAlign: 'center',
          letterSpacing: '0.02em',
        }}>
          $299/month · One agent per ZIP · Cancel anytime
        </div>
        <div style={{
          marginTop: 'var(--space-lg)',
          display: 'flex',
          gap: 8,
        }}>
          <a
            href={zip ? `/signup?zip=${encodeURIComponent(zip)}` : '/signup'}
            style={{
              flex: 1,
              padding: '12px',
              fontSize: 13,
              fontWeight: 600,
              background: 'var(--accent)',
              color: 'var(--text-inverse)',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              cursor: 'pointer',
              fontFamily: 'var(--font-sans)',
              textDecoration: 'none',
              textAlign: 'center',
              letterSpacing: '0.02em',
            }}
          >
            {zip ? `Claim ${zip}` : 'Claim a territory'}
          </a>
          <button
            onClick={onClose}
            style={{
              flex: 1,
              padding: '12px',
              fontSize: 13,
              fontWeight: 500,
              background: 'transparent',
              color: 'var(--text-secondary)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              cursor: 'pointer',
              fontFamily: 'var(--font-sans)',
            }}
          >
            Maybe later
          </button>
        </div>
      </div>
    </div>
  );
}
