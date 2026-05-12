import { useEffect, useState, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { myLeads, safeErrorMessage } from '../api/client.js';
import { useAuth } from '../lib/AuthContext.jsx';
import SiteLayout from '../components/shell/SiteLayout.jsx';

/*
 * MyLeadsPage — the agent's active pipeline.
 *
 * Shows every parcel the agent has any engagement with (interaction,
 * note, or tag), minus pins they've dismissed via 'not_relevant' or
 * 'closed'. The briefing page is the daily firehose; this is where
 * leads live once an agent has claimed them.
 *
 * Layout:
 *   Header row:    totals + search input
 *   Tag chip row:  filter by tag (multi-select union)
 *   Lead sections: Working → Listing Discussion → Sent to CRM →
 *                  Engaged (touched but no funnel status)
 *
 * Clicking a lead navigates to its briefing page with the dossier
 * auto-opened via ?pin=:pin query param.
 */

const SECTION_ORDER = [
  { key: 'working',            label: 'Working',            color: 'var(--accent)' },
  { key: 'listing_discussion', label: 'Listing discussion', color: 'var(--hold)' },
  { key: 'sent_to_crm',        label: 'Sent to CRM',        color: 'var(--text-secondary)' },
  { key: 'engaged',            label: 'Engaged',            color: 'var(--text-tertiary)' },
];

export default function MyLeadsPage() {
  const { profile, signOut } = useAuth();
  const navigate = useNavigate();

  const [data, setData]         = useState(null);
  const [error, setError]       = useState(null);
  const [search, setSearch]     = useState('');
  const [selectedTags, setSelectedTags] = useState([]);

  useEffect(() => {
    myLeads.list()
      .then(setData)
      .catch((e) => setError(safeErrorMessage(e, 'Failed to load leads')));
  }, []);

  const handleToggleTag = (tag) => {
    setSelectedTags((prev) => (
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    ));
  };

  // Apply search + tag filter, then group by status.
  const grouped = useMemo(() => {
    if (!data?.leads) return null;
    const q = search.trim().toLowerCase();

    const filtered = data.leads.filter((L) => {
      // Search: address / owner / pin / any tag
      if (q) {
        const hay = [
          L.address, L.owner_name, L.pin, L.city, ...(L.tags || []),
        ].filter(Boolean).join(' ').toLowerCase();
        if (!hay.includes(q)) return false;
      }
      // Tag filter: union semantics — match if any selected tag is present
      if (selectedTags.length > 0) {
        const tagSet = new Set(L.tags || []);
        if (!selectedTags.some((t) => tagSet.has(t))) return false;
      }
      return true;
    });

    // Group: status string maps directly to section key; null → 'engaged'
    const out = {
      working:            [],
      listing_discussion: [],
      sent_to_crm:        [],
      engaged:            [],
    };
    for (const L of filtered) {
      const key = L.status || 'engaged';
      if (out[key]) out[key].push(L);
      else out.engaged.push(L);
    }
    return out;
  }, [data, search, selectedTags]);

  return (
    <SiteLayout agent={profile} onSignOut={signOut} showFooter={false}>
      <div style={containerStyle}>
        <div style={pageHeaderStyle}>
          <div>
            <h1 style={titleStyle}>My Leads</h1>
            {data && (
              <div style={subtitleStyle}>
                {data.totals.total === 0
                  ? 'No engaged leads yet — tag, note, or mark a lead from the briefing to start your pipeline.'
                  : `${data.totals.total} active lead${data.totals.total === 1 ? '' : 's'}`}
                {data?.totals?.total > 0 && (
                  <>
                    {' · '}
                    <span style={{ color: 'var(--accent)' }}>{data.totals.working} working</span>
                    {data.totals.listing_discussion > 0 && (
                      <>{' · '}<span style={{ color: 'var(--hold)' }}>{data.totals.listing_discussion} in listing discussion</span></>
                    )}
                    {data.totals.engaged > 0 && (
                      <>{' · '}<span style={{ color: 'var(--text-tertiary)' }}>{data.totals.engaged} engaged</span></>
                    )}
                  </>
                )}
              </div>
            )}
          </div>

          {data?.leads?.length > 0 && (
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search address, owner, or tag"
              style={searchInputStyle}
            />
          )}
        </div>

        {error && (
          <div style={errorStyle}>{error}</div>
        )}

        {data && data.available_tags.length > 0 && (
          <div style={tagRowStyle}>
            <span style={tagRowLabelStyle}>Filter by tag:</span>
            {data.available_tags.map((t) => {
              const active = selectedTags.includes(t.tag);
              return (
                <button
                  key={t.tag}
                  onClick={() => handleToggleTag(t.tag)}
                  style={tagChipStyle(active)}
                >
                  {t.tag}
                  <span style={tagCountStyle}>{t.count}</span>
                </button>
              );
            })}
            {selectedTags.length > 0 && (
              <button
                onClick={() => setSelectedTags([])}
                style={clearButtonStyle}
              >
                Clear filter
              </button>
            )}
          </div>
        )}

        {grouped && SECTION_ORDER.map((sec) => {
          const leads = grouped[sec.key];
          if (!leads || leads.length === 0) return null;
          return (
            <Section key={sec.key} label={sec.label} color={sec.color} count={leads.length}>
              {leads.map((L) => (
                <LeadRow key={L.pin} lead={L} onClick={() => {
                  navigate(`/zip/${L.zip_code}?pin=${L.pin}`);
                }} />
              ))}
            </Section>
          );
        })}

        {grouped && Object.values(grouped).every((arr) => arr.length === 0) && data?.leads?.length > 0 && (
          <div style={emptyFilterStyle}>
            No leads match the current filter.
          </div>
        )}
      </div>
    </SiteLayout>
  );
}


function Section({ label, color, count, children }) {
  return (
    <section style={{ marginTop: 'var(--space-xl, 28px)' }}>
      <div style={{
        display: 'flex',
        alignItems: 'baseline',
        gap: 8,
        marginBottom: 12,
        paddingBottom: 6,
        borderBottom: `1px solid ${color}`,
      }}>
        <h2 style={{
          fontSize: 16,
          fontWeight: 700,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          color,
          fontFamily: 'var(--font-sans)',
          margin: 0,
        }}>
          {label}
        </h2>
        <span style={{
          fontSize: 11,
          color: 'var(--text-tertiary)',
          fontFamily: 'var(--font-sans)',
        }}>
          {count}
        </span>
      </div>
      <div>{children}</div>
    </section>
  );
}


function LeadRow({ lead, onClick }) {
  return (
    <button onClick={onClick} style={leadRowStyle}>
      <div style={leadRowLeftStyle}>
        <div style={leadAddressStyle}>{lead.address || '(no address)'}</div>
        <div style={leadOwnerStyle}>
          {lead.owner_name || '(unknown owner)'}
          {lead.city && <span style={{ color: 'var(--text-tertiary)' }}> · {lead.city}, {lead.state}</span>}
          {lead.total_value && (
            <span style={{ color: 'var(--text-tertiary)' }}> · {formatValue(lead.total_value)}</span>
          )}
        </div>
        {lead.tags.length > 0 && (
          <div style={leadTagsRowStyle}>
            {lead.tags.map((t) => (
              <span key={t} style={leadTagChipStyle}>{t}</span>
            ))}
          </div>
        )}
      </div>
      <div style={leadRowRightStyle}>
        {lead.notes_count > 0 && (
          <div style={leadMetaStyle}>
            {lead.notes_count} note{lead.notes_count === 1 ? '' : 's'}
          </div>
        )}
        <div style={leadMetaStyle}>{formatRelative(lead.last_action_at)}</div>
        <div style={leadZipStyle}>ZIP {lead.zip_code}</div>
      </div>
    </button>
  );
}


function formatValue(v) {
  if (!v) return '';
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000)     return `$${Math.round(v / 1_000)}K`;
  return `$${v}`;
}


function formatRelative(iso) {
  if (!iso) return '';
  const ts = new Date(iso).getTime();
  const now = Date.now();
  const diffSec = Math.max(0, Math.floor((now - ts) / 1000));
  if (diffSec < 60)        return 'just now';
  if (diffSec < 3600)      return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400)     return `${Math.floor(diffSec / 3600)}h ago`;
  if (diffSec < 86400 * 7) return `${Math.floor(diffSec / 86400)}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}


// ── Styles ────────────────────────────────────────────────────────

const containerStyle = {
  maxWidth: 960,
  margin: '0 auto',
  padding: 'var(--space-lg) var(--space-lg) calc(var(--space-lg) * 3)',
};

const pageHeaderStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'flex-start',
  gap: 16,
  flexWrap: 'wrap',
  marginBottom: 16,
};

const titleStyle = {
  fontFamily: 'var(--font-serif)',
  fontSize: 28,
  fontWeight: 700,
  color: 'var(--text)',
  margin: '0 0 4px 0',
};

const subtitleStyle = {
  fontFamily: 'var(--font-sans)',
  fontSize: 13,
  color: 'var(--text-secondary)',
};

const searchInputStyle = {
  padding: '9px 12px',
  fontSize: 13,
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-md)',
  background: 'var(--bg-card)',
  color: 'var(--text)',
  fontFamily: 'var(--font-sans)',
  minWidth: 260,
};

const errorStyle = {
  padding: '12px 16px',
  background: 'var(--call-now-bg)',
  border: '1px solid var(--call-now)',
  color: 'var(--call-now)',
  borderRadius: 'var(--radius-md)',
  fontFamily: 'var(--font-sans)',
  fontSize: 13,
  marginBottom: 16,
};

const tagRowStyle = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 6,
  alignItems: 'center',
  padding: '10px 12px',
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-md)',
  marginBottom: 12,
};

const tagRowLabelStyle = {
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  color: 'var(--text-tertiary)',
  fontFamily: 'var(--font-sans)',
  marginRight: 6,
};

const tagChipStyle = (active) => ({
  padding: '4px 10px',
  fontSize: 11,
  fontFamily: 'var(--font-sans)',
  borderRadius: 999,
  border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
  background: active ? 'var(--accent-dim)' : 'transparent',
  color: active ? 'var(--accent)' : 'var(--text-secondary)',
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
});

const tagCountStyle = {
  opacity: 0.6,
  fontSize: 10,
};

const clearButtonStyle = {
  background: 'transparent',
  border: 'none',
  padding: '4px 8px',
  fontSize: 11,
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  fontFamily: 'var(--font-sans)',
  textDecoration: 'underline',
  marginLeft: 4,
};

const leadRowStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'flex-start',
  width: '100%',
  padding: '12px 14px',
  marginBottom: 8,
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-md)',
  cursor: 'pointer',
  textAlign: 'left',
  fontFamily: 'inherit',
  transition: 'border-color var(--transition), background var(--transition)',
};

const leadRowLeftStyle = {
  flex: 1,
  minWidth: 0,
};

const leadRowRightStyle = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'flex-end',
  gap: 2,
  marginLeft: 16,
  flexShrink: 0,
};

const leadAddressStyle = {
  fontFamily: 'var(--font-serif)',
  fontSize: 15,
  fontWeight: 600,
  color: 'var(--text)',
  marginBottom: 2,
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
};

const leadOwnerStyle = {
  fontFamily: 'var(--font-sans)',
  fontSize: 12,
  color: 'var(--text-secondary)',
};

const leadTagsRowStyle = {
  marginTop: 6,
  display: 'flex',
  flexWrap: 'wrap',
  gap: 4,
};

const leadTagChipStyle = {
  padding: '2px 7px',
  fontSize: 10,
  fontFamily: 'var(--font-sans)',
  color: 'var(--accent)',
  background: 'var(--accent-dim)',
  border: '0.5px solid rgba(139, 105, 20, 0.25)',
  borderRadius: 8,
  lineHeight: 1.3,
};

const leadMetaStyle = {
  fontFamily: 'var(--font-sans)',
  fontSize: 10,
  color: 'var(--text-tertiary)',
};

const leadZipStyle = {
  fontFamily: 'var(--font-sans)',
  fontSize: 10,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  marginTop: 2,
};

const emptyFilterStyle = {
  marginTop: 32,
  padding: 24,
  textAlign: 'center',
  fontFamily: 'var(--font-serif)',
  fontSize: 14,
  fontStyle: 'italic',
  color: 'var(--text-tertiary)',
};
