/*
 * LeadTagChips.jsx — tag chip row for a single parcel.
 *
 * Renders inside ParcelDossierV2 just under the StatusPill. Lets the
 * agent see, add, and remove their tags on this parcel. Tags are
 * per-agent (your "Hot lead" is invisible to other agents).
 *
 * Behavior:
 *  - On mount: loads existing tags via leadTags.byPin(pin)
 *  - Click + to open inline input. Enter to submit, Escape to cancel.
 *  - Click × on a chip to remove.
 *  - Optimistic UI: chips appear/disappear immediately; rolls back
 *    on API error and surfaces a hint via onError prop.
 *  - When disabled (cold-visitor gate), renders read-only with no
 *    add/remove affordances.
 */

import { useEffect, useState, useRef } from 'react';
import { leadTags, safeErrorMessage } from '../api/client.js';

export default function LeadTagChips({ pin, zip_code, disabled, onError }) {
  const [tags, setTags]       = useState([]);  // [{id, tag, ...}, ...]
  const [loading, setLoading] = useState(true);
  const [adding, setAdding]   = useState(false);
  const [draft, setDraft]     = useState('');
  const [pending, setPending] = useState(false);
  const inputRef = useRef(null);

  // Load on mount / when pin changes
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    leadTags.byPin(pin)
      .then((r) => {
        if (cancelled) return;
        setTags(r.tags || []);
      })
      .catch(() => { /* swallow; show empty state */ })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [pin]);

  // Focus the input when entering add mode
  useEffect(() => {
    if (adding && inputRef.current) inputRef.current.focus();
  }, [adding]);

  const handleAdd = async () => {
    const trimmed = draft.trim();
    if (!trimmed) {
      setAdding(false);
      setDraft('');
      return;
    }
    if (trimmed.length > 40) {
      onError?.('Tag too long (max 40 chars)');
      return;
    }
    setPending(true);
    try {
      const row = await leadTags.create({ pin, zip_code, tag: trimmed });
      // Dedupe in case server returned an existing row
      setTags((prev) => {
        if (prev.some((t) => t.id === row.id)) return prev;
        return [...prev, row];
      });
      setDraft('');
      setAdding(false);
    } catch (e) {
      onError?.(`Couldn't add tag: ${safeErrorMessage(e)}`);
    } finally {
      setPending(false);
    }
  };

  const handleRemove = async (id) => {
    // Optimistic remove
    const prev = tags;
    setTags(tags.filter((t) => t.id !== id));
    try {
      await leadTags.remove(id);
    } catch (e) {
      setTags(prev);  // rollback
      onError?.(`Couldn't remove tag: ${safeErrorMessage(e)}`);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAdd();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setAdding(false);
      setDraft('');
    }
  };

  if (loading) return null;
  if (tags.length === 0 && disabled) return null;

  return (
    <div style={{
      marginTop: 'var(--space-md)',
      display: 'flex',
      flexWrap: 'wrap',
      gap: 6,
      alignItems: 'center',
    }}>
      {tags.map((t) => (
        <Chip key={t.id} label={t.tag} onRemove={disabled ? null : () => handleRemove(t.id)} />
      ))}

      {!disabled && !adding && (
        <button
          type="button"
          onClick={() => setAdding(true)}
          style={addButtonStyle}
          aria-label="Add tag"
        >
          + tag
        </button>
      )}

      {!disabled && adding && (
        <input
          ref={inputRef}
          type="text"
          value={draft}
          maxLength={40}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={handleAdd}
          disabled={pending}
          placeholder="tag name"
          style={inputStyle}
        />
      )}
    </div>
  );
}


function Chip({ label, onRemove }) {
  return (
    <span style={chipStyle}>
      {label}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove tag ${label}`}
          style={chipRemoveStyle}
        >
          ×
        </button>
      )}
    </span>
  );
}


const chipStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  padding: '3px 8px',
  fontSize: 11,
  fontFamily: 'var(--font-sans)',
  color: 'var(--accent)',
  background: 'var(--accent-dim)',
  border: '0.5px solid rgba(139, 105, 20, 0.25)',
  borderRadius: 11,
  lineHeight: 1.3,
};

const chipRemoveStyle = {
  background: 'transparent',
  border: 'none',
  color: 'var(--accent)',
  fontSize: 13,
  lineHeight: 1,
  cursor: 'pointer',
  padding: '0 0 0 2px',
  opacity: 0.65,
};

const addButtonStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  padding: '3px 8px',
  fontSize: 11,
  fontFamily: 'var(--font-sans)',
  color: 'var(--text-secondary)',
  background: 'transparent',
  border: '0.5px dashed var(--border-strong)',
  borderRadius: 11,
  cursor: 'pointer',
  lineHeight: 1.3,
};

const inputStyle = {
  padding: '3px 8px',
  fontSize: 11,
  fontFamily: 'var(--font-sans)',
  color: 'var(--text)',
  background: 'var(--bg-card)',
  border: '0.5px solid var(--accent)',
  borderRadius: 11,
  outline: 'none',
  width: 120,
};
