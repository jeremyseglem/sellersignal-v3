/*
 * LeadNotesSection.jsx — mutable notes panel for a single parcel.
 *
 * Renders inside ParcelDossierV2 between ActionButtons and HistorySection.
 * Lets the agent record context per prospect — call notes, mailer
 * details, anything that helps them remember where they stand. Notes
 * are per-agent (your notes are invisible to other agents).
 *
 * Behavior:
 *  - On mount: loads existing notes via leadNotes.byPin(pin)
 *  - "+ Add note" → expands inline textarea → Save creates a row
 *  - Each existing note has Edit and Delete affordances
 *  - Edit mode: textarea pre-filled, Save updates, Cancel reverts
 *  - When disabled (cold-visitor gate), renders read-only (no
 *    add/edit/delete affordances)
 *
 * Notes are capped at 4000 chars server-side; we enforce 4000 here
 * too with a character counter that turns red as the user approaches
 * the limit.
 */

import { useEffect, useState } from 'react';
import { leadNotes, safeErrorMessage } from '../api/client.js';

const MAX_NOTE_LENGTH = 4000;

export default function LeadNotesSection({ pin, zip_code, disabled, onError }) {
  const [notes, setNotes]     = useState([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding]   = useState(false);
  const [draft, setDraft]     = useState('');
  const [editingId, setEditingId] = useState(null);
  const [editDraft, setEditDraft] = useState('');
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    leadNotes.byPin(pin)
      .then((r) => {
        if (cancelled) return;
        setNotes(r.notes || []);
      })
      .catch(() => { /* swallow */ })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [pin]);

  const handleAdd = async () => {
    const body = draft.trim();
    if (!body) {
      setAdding(false);
      setDraft('');
      return;
    }
    setPending(true);
    try {
      const row = await leadNotes.create({ pin, zip_code, body });
      setNotes((prev) => [row, ...prev]);
      setDraft('');
      setAdding(false);
    } catch (e) {
      onError?.(`Couldn't save note: ${safeErrorMessage(e)}`);
    } finally {
      setPending(false);
    }
  };

  const handleEditStart = (note) => {
    setEditingId(note.id);
    setEditDraft(note.body);
  };

  const handleEditSave = async () => {
    const body = editDraft.trim();
    if (!body) return;
    setPending(true);
    try {
      const updated = await leadNotes.update(editingId, body);
      setNotes((prev) => prev.map((n) => (n.id === updated.id ? updated : n)));
      setEditingId(null);
      setEditDraft('');
    } catch (e) {
      onError?.(`Couldn't update note: ${safeErrorMessage(e)}`);
    } finally {
      setPending(false);
    }
  };

  const handleDelete = async (id) => {
    const prev = notes;
    setNotes(notes.filter((n) => n.id !== id));
    try {
      await leadNotes.remove(id);
    } catch (e) {
      setNotes(prev);
      onError?.(`Couldn't delete note: ${safeErrorMessage(e)}`);
    }
  };

  if (loading) return null;
  // Hide entirely for cold visitors with no notes
  if (notes.length === 0 && disabled) return null;

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>Notes</div>

      {notes.map((n) => (
        editingId === n.id ? (
          <NoteEditor
            key={n.id}
            value={editDraft}
            setValue={setEditDraft}
            onSave={handleEditSave}
            onCancel={() => { setEditingId(null); setEditDraft(''); }}
            pending={pending}
          />
        ) : (
          <NoteCard
            key={n.id}
            note={n}
            disabled={disabled}
            onEdit={() => handleEditStart(n)}
            onDelete={() => handleDelete(n.id)}
          />
        )
      ))}

      {!disabled && (
        adding ? (
          <NoteEditor
            value={draft}
            setValue={setDraft}
            onSave={handleAdd}
            onCancel={() => { setAdding(false); setDraft(''); }}
            pending={pending}
          />
        ) : (
          <button
            type="button"
            onClick={() => setAdding(true)}
            style={addButtonStyle}
          >
            + Add note
          </button>
        )
      )}
    </div>
  );
}


function NoteCard({ note, disabled, onEdit, onDelete }) {
  return (
    <div style={cardStyle}>
      <div style={cardBodyStyle}>{note.body}</div>
      <div style={cardFooterStyle}>
        <span style={cardDateStyle}>
          {formatNoteDate(note.created_at, note.updated_at)}
        </span>
        {!disabled && (
          <span style={{ display: 'inline-flex', gap: 8 }}>
            <button type="button" onClick={onEdit} style={linkButtonStyle}>Edit</button>
            <button type="button" onClick={onDelete} style={linkButtonStyle}>Delete</button>
          </span>
        )}
      </div>
    </div>
  );
}


function NoteEditor({ value, setValue, onSave, onCancel, pending }) {
  const charCount = value.length;
  const overLimit = charCount > MAX_NOTE_LENGTH;
  const approaching = charCount > MAX_NOTE_LENGTH * 0.9;
  return (
    <div style={editorContainerStyle}>
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Write a note (e.g., called, left voicemail with PR, will follow up Tuesday)"
        rows={3}
        maxLength={MAX_NOTE_LENGTH}
        disabled={pending}
        style={textareaStyle}
        autoFocus
      />
      <div style={editorFooterStyle}>
        <span style={{
          fontSize: 10,
          color: overLimit ? 'var(--call-now)' : (approaching ? 'var(--accent)' : 'var(--text-tertiary)'),
          fontFamily: 'var(--font-sans)',
        }}>
          {charCount} / {MAX_NOTE_LENGTH}
        </span>
        <span style={{ display: 'inline-flex', gap: 8 }}>
          <button type="button" onClick={onCancel} style={linkButtonStyle} disabled={pending}>
            Cancel
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={pending || !value.trim() || overLimit}
            style={saveButtonStyle}
          >
            {pending ? 'Saving…' : 'Save'}
          </button>
        </span>
      </div>
    </div>
  );
}


function formatNoteDate(createdAt, updatedAt) {
  const created = new Date(createdAt);
  const updated = new Date(updatedAt);
  const wasEdited = (updated - created) > 2000;  // 2s tolerance
  const base = created.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  });
  if (!wasEdited) return base;
  const editedAt = updated.toLocaleString(undefined, {
    month: 'short', day: 'numeric',
  });
  return `${base} · edited ${editedAt}`;
}


// ── Styles ────────────────────────────────────────────────────────

const containerStyle = {
  marginTop: 'var(--space-lg)',
  paddingTop: 'var(--space-md)',
  borderTop: '0.5px dashed var(--border)',
};

const headerStyle = {
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  color: 'var(--text-tertiary)',
  marginBottom: 8,
  fontFamily: 'var(--font-sans)',
};

const cardStyle = {
  background: 'var(--bg-card-hover)',
  border: '0.5px solid var(--border)',
  borderRadius: 'var(--radius-md, 6px)',
  padding: '8px 10px',
  marginBottom: 8,
};

const cardBodyStyle = {
  fontFamily: 'var(--font-serif)',
  fontSize: 13,
  lineHeight: 1.5,
  color: 'var(--text)',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
};

const cardFooterStyle = {
  marginTop: 6,
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
};

const cardDateStyle = {
  fontSize: 10,
  color: 'var(--text-tertiary)',
  fontFamily: 'var(--font-sans)',
};

const linkButtonStyle = {
  background: 'transparent',
  border: 'none',
  padding: 0,
  fontSize: 10,
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  textDecoration: 'underline',
  fontFamily: 'var(--font-sans)',
};

const editorContainerStyle = {
  marginBottom: 8,
};

const textareaStyle = {
  width: '100%',
  padding: 8,
  fontFamily: 'var(--font-serif)',
  fontSize: 13,
  lineHeight: 1.5,
  color: 'var(--text)',
  background: 'var(--bg-card)',
  border: '0.5px solid var(--accent)',
  borderRadius: 'var(--radius-md, 6px)',
  outline: 'none',
  resize: 'vertical',
  boxSizing: 'border-box',
};

const editorFooterStyle = {
  marginTop: 4,
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
};

const addButtonStyle = {
  background: 'transparent',
  border: '0.5px dashed var(--border-strong)',
  color: 'var(--text-secondary)',
  fontSize: 11,
  fontFamily: 'var(--font-sans)',
  padding: '6px 10px',
  borderRadius: 'var(--radius-md, 6px)',
  cursor: 'pointer',
  width: '100%',
  textAlign: 'left',
};

const saveButtonStyle = {
  background: 'var(--accent)',
  color: 'var(--text-inverse)',
  border: 'none',
  fontSize: 11,
  fontFamily: 'var(--font-sans)',
  padding: '4px 10px',
  borderRadius: 4,
  cursor: 'pointer',
  fontWeight: 600,
};
