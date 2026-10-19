/*
 * TCPAComplianceModal.jsx — one-time acknowledgment before skip-trace.
 *
 * Shows the agent their compliance responsibilities under TCPA, DNC,
 * and CAN-SPAM before they can run their first skip-trace. Posts to
 * /api/skip-trace/ack-compliance on agreement; the server records
 * the ack so this modal won't appear again for this account.
 *
 * Renders as a full-viewport overlay (z-index above the dossier).
 * Cancel closes without ack — the agent can come back and ack later
 * when they're ready to use the feature.
 */

import { useState } from 'react';
import { skipTrace, safeErrorMessage } from '../api/client.js';

export default function TCPAComplianceModal({ onAcked, onCancel }) {
  const [pending, setPending] = useState(false);
  const [error, setError]     = useState(null);

  const handleAck = async () => {
    setPending(true);
    setError(null);
    try {
      const result = await skipTrace.ackCompliance();
      onAcked && onAcked(result);
    } catch (e) {
      setError(safeErrorMessage(e, 'Could not record acknowledgment'));
      setPending(false);
    }
  };

  return (
    <div style={overlayStyle} onClick={onCancel}>
      <div
        style={modalStyle}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tcpa-modal-title"
      >
        <h2 id="tcpa-modal-title" style={titleStyle}>
          Before you skip-trace
        </h2>

        <p style={paragraphStyle}>
          Skip-trace returns phone numbers, emails, and mailing
          addresses for property owners and their associates. The
          data comes from public records, credit headers, and other
          sources, and it&rsquo;s subject to several laws that
          regulate how you can use it.
        </p>

        <div style={listContainerStyle}>
          <div style={bulletStyle}>
            <strong style={bulletLabelStyle}>TCPA.</strong> The
            Telephone Consumer Protection Act regulates cold calls
            and texts. As of January 27, 2025, &ldquo;one-to-one&rdquo;
            consent rules require you to obtain documented consent
            naming you specifically before using auto-dialers to
            contact mobile numbers. Violations carry $500&ndash;$1,500
            per call.
          </div>
          <div style={bulletStyle}>
            <strong style={bulletLabelStyle}>DNC.</strong> You must
            scrub your call lists against the National Do Not Call
            Registry. SellerSignal flags DNC-listed numbers in the
            results, but you remain responsible for verifying and
            honoring the registry, including state-specific DNC lists
            and any internal request to not be contacted.
          </div>
          <div style={bulletStyle}>
            <strong style={bulletLabelStyle}>Litigators.</strong> The
            results flag known TCPA litigators. If you see this flag,
            do not call or text that number.
          </div>
          <div style={bulletStyle}>
            <strong style={bulletLabelStyle}>CAN-SPAM.</strong> Cold
            emails must include an unsubscribe option and your
            physical mailing address.
          </div>
          <div style={bulletStyle}>
            <strong style={bulletLabelStyle}>Your responsibility.</strong>{' '}
            SellerSignal provides data; you are responsible for
            compliant use. Consult a lawyer if you&rsquo;re unsure
            whether your outreach plan complies with all applicable
            laws.
          </div>
        </div>

        {error && (
          <div style={errorStyle}>{error}</div>
        )}

        <div style={buttonRowStyle}>
          <button
            type="button"
            onClick={onCancel}
            disabled={pending}
            style={cancelButtonStyle}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleAck}
            disabled={pending}
            style={agreeButtonStyle(pending)}
          >
            {pending ? 'Recording…' : 'I understand and agree'}
          </button>
        </div>
      </div>
    </div>
  );
}


// ── Styles ────────────────────────────────────────────────────────

const overlayStyle = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(0, 0, 0, 0.5)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 5000,
  padding: 16,
};

const modalStyle = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-lg, 8px)',
  boxShadow: 'var(--shadow-lg)',
  padding: 'var(--space-lg)',
  maxWidth: 540,
  width: '100%',
  maxHeight: '90vh',
  overflowY: 'auto',
};

const titleStyle = {
  fontFamily: 'var(--font-serif)',
  fontSize: 22,
  fontWeight: 700,
  color: 'var(--text)',
  margin: '0 0 12px 0',
};

const paragraphStyle = {
  fontFamily: 'var(--font-serif)',
  fontSize: 14,
  lineHeight: 1.6,
  color: 'var(--text-secondary)',
  margin: '0 0 16px 0',
};

const listContainerStyle = {
  marginBottom: 16,
};

const bulletStyle = {
  fontFamily: 'var(--font-serif)',
  fontSize: 13,
  lineHeight: 1.55,
  color: 'var(--text-secondary)',
  marginBottom: 10,
  paddingLeft: 0,
};

const bulletLabelStyle = {
  color: 'var(--text)',
  fontFamily: 'var(--font-sans)',
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: '0.04em',
  textTransform: 'uppercase',
  marginRight: 4,
};

const errorStyle = {
  padding: '8px 12px',
  background: 'var(--call-now-bg, #fff0f0)',
  border: '1px solid var(--call-now)',
  color: 'var(--call-now)',
  borderRadius: 'var(--radius-md, 6px)',
  fontFamily: 'var(--font-sans)',
  fontSize: 12,
  marginBottom: 12,
};

const buttonRowStyle = {
  display: 'flex',
  justifyContent: 'flex-end',
  gap: 8,
  marginTop: 12,
};

const cancelButtonStyle = {
  padding: '9px 16px',
  fontSize: 13,
  fontFamily: 'var(--font-sans)',
  background: 'transparent',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-md, 6px)',
  color: 'var(--text-secondary)',
  cursor: 'pointer',
};

const agreeButtonStyle = (pending) => ({
  padding: '9px 18px',
  fontSize: 13,
  fontWeight: 600,
  fontFamily: 'var(--font-sans)',
  background: 'var(--accent)',
  border: 'none',
  borderRadius: 'var(--radius-md, 6px)',
  color: 'var(--text-inverse)',
  cursor: pending ? 'wait' : 'pointer',
  opacity: pending ? 0.6 : 1,
});
