import { useState } from 'react';

/**
 * MapExplorePanel — exploration-mode controls attached to the map.
 *
 * Spec rule: filtering and sorting belong to exploration mode, not
 * above the action list. The action list is closed and directive;
 * filtering it would defeat the "here are five sellers, pick one"
 * frame. The map is open-world — agents who want to dig in find
 * these controls here.
 *
 * Visual treatment: a slim translucent strip pinned to the top
 * of the map. Doesn't compete with the action list to its left.
 * Blurred backdrop so the underlying map remains visible.
 *
 * The panel collapses to a single search input by default. The
 * Filter button reveals filter chips below it. Keeps the chrome
 * minimal until the agent asks for it.
 *
 * Props match the prior BriefingPage state hooks 1:1 so we can
 * lift this component in without changing call sites.
 *
 * Props:
 *   searchQuery, onSearchChange — controlled input for free-text search
 *   filterKey, onFilterChange   — current category filter chip + setter
 *   sortKey, onSortChange       — current sort + setter
 *   filterOptions, sortOptions  — option arrays from BriefingPage
 *   availableTags               — [{tag, count}, ...] this agent's tags
 *                                  for this ZIP. Empty array hides the
 *                                  tag row entirely (no tags yet).
 *   selectedTags                — array of currently-active tag strings
 *                                  (multi-select; union semantics)
 *   onToggleTag(tag)            — toggle one tag in/out of selection
 */
export default function MapExplorePanel({
  searchQuery,
  onSearchChange,
  filterKey,
  onFilterChange,
  sortKey,
  onSortChange,
  filterOptions,
  sortOptions,
  availableTags = [],
  selectedTags = [],
  onToggleTag,
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div style={{
      position: 'absolute',
      top: 16,
      left: 16,
      right: 16,
      zIndex: 400,
      pointerEvents: 'none',
    }}>
      <div style={{
        display: 'flex',
        gap: 8,
        alignItems: 'flex-start',
        pointerEvents: 'auto',
      }}>
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search by address, owner, or PIN"
          style={{
            flex: 1,
            maxWidth: 380,
            padding: '9px 12px',
            fontSize: 13,
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            background: 'rgba(255, 255, 255, 0.96)',
            backdropFilter: 'blur(6px)',
            color: 'var(--text)',
            fontFamily: 'var(--font-sans)',
            boxShadow: 'var(--shadow-sm)',
          }}
        />
        <button
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          style={{
            padding: '9px 14px',
            fontSize: 12,
            fontWeight: 500,
            border: `1px solid ${expanded ? 'var(--accent)' : 'var(--border)'}`,
            borderRadius: 'var(--radius-md)',
            background: 'rgba(255, 255, 255, 0.96)',
            backdropFilter: 'blur(6px)',
            color: expanded ? 'var(--accent)' : 'var(--text-secondary)',
            cursor: 'pointer',
            fontFamily: 'var(--font-sans)',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          Filter & sort
        </button>
      </div>

      {expanded && (
        <div style={{
          marginTop: 8,
          padding: '10px 12px',
          background: 'rgba(255, 255, 255, 0.96)',
          backdropFilter: 'blur(6px)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          maxWidth: 480,
          pointerEvents: 'auto',
          boxShadow: 'var(--shadow-sm)',
        }}>
          <div style={{
            display: 'flex',
            gap: 6,
            flexWrap: 'wrap',
          }}>
            {filterOptions.map((f) => (
              <button
                key={f.key}
                onClick={() => onFilterChange(f.key)}
                style={{
                  padding: '4px 10px',
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: '0.03em',
                  borderRadius: 999,
                  border: `1px solid ${filterKey === f.key ? 'var(--accent)' : 'var(--border)'}`,
                  background: filterKey === f.key ? 'var(--accent)' : 'transparent',
                  color: filterKey === f.key ? 'var(--bg-card)' : 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontFamily: 'var(--font-sans)',
                }}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Tag filter row — only renders when this agent has at
              least one tag in this ZIP. Multi-select with union
              semantics: showing any lead matching any selected tag. */}
          {availableTags.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <div style={{
                fontSize: 9,
                fontWeight: 700,
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
                color: 'var(--text-tertiary)',
                marginBottom: 6,
                fontFamily: 'var(--font-sans)',
              }}>
                Your tags
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {availableTags.map((t) => {
                  const active = selectedTags.includes(t.tag);
                  return (
                    <button
                      key={t.tag}
                      onClick={() => onToggleTag && onToggleTag(t.tag)}
                      style={{
                        padding: '3px 8px',
                        fontSize: 11,
                        fontFamily: 'var(--font-sans)',
                        borderRadius: 999,
                        border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
                        background: active ? 'var(--accent-dim)' : 'transparent',
                        color: active ? 'var(--accent)' : 'var(--text-secondary)',
                        cursor: 'pointer',
                      }}
                    >
                      {t.tag}
                      <span style={{
                        marginLeft: 4,
                        opacity: 0.6,
                        fontSize: 9,
                      }}>
                        {t.count}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          <select
            value={sortKey}
            onChange={(e) => onSortChange(e.target.value)}
            style={{
              marginTop: 8,
              width: '100%',
              padding: '6px 8px',
              fontSize: 12,
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg-card)',
              color: 'var(--text-secondary)',
              fontFamily: 'var(--font-sans)',
            }}
          >
            {sortOptions.map((s) => (
              <option key={s.key} value={s.key}>{s.label}</option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}
