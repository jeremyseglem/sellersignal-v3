import { useEffect, useState } from 'react';
import { useAuth } from '../lib/AuthContext.jsx';
import { getAccessToken } from '../lib/supabase.js';
import { agentVoice, safeErrorMessage } from '../api/client.js';
import SiteLayout from '../components/shell/SiteLayout.jsx';

/**
 * VoiceOnboardingPage — captures the agent's voice sample, 10 stance
 * answers, and bio. On submit, saves to /api/profile, then triggers
 * /api/agent/generate-scripts which runs 6 archetype LLM generations
 * in parallel (30-90 seconds). On success, shows a preview pane with
 * all 6 generated scripts so the agent can read what their actual
 * outreach will look like.
 *
 * Design choices:
 *  - Single screen, scroll-as-you-go. No multi-step wizard. Less
 *    friction; agents can jump around and edit.
 *  - Stance questions as horizontal pills (forced-choice). Better UX
 *    than radios in a column for binary/ternary choices.
 *  - Geographic anchors as repeatable rows with + Add button.
 *  - Generate button locked until voice_sample has at least 100 chars
 *    (soft-gate, not a hard limit — short samples produce poor output).
 *  - Loading state during generation: ~60 seconds is real, not fake.
 *
 * Save model: clicking Generate first PUTs the form to /api/profile
 * (so the inputs are persisted before generation runs), then POSTs
 * to /api/agent/generate-scripts. If the agent navigates away mid-
 * generation, the profile inputs are saved and they can re-run
 * generation later without re-entering data.
 */

// ─── Stance questions (per AGENT_VOICE_V1.md) ─────────────────────────
// Tuple of (id, prompt, options[]) — each option has {value, label,
// short} where short is the label shown on the selected pill (the
// long label is the radio-like description below).
const STANCE_QUESTIONS = [
  {
    id: 'structural_acknowledgment',
    prompt: 'When you reach out to a probate family or a divorce-affected owner, do you mention the situation directly?',
    options: [
      { value: 'direct',     short: 'Direct',     label: 'It\'s fine to say "I came across the probate filing." I prefer being upfront.' },
      { value: 'indirect',   short: 'Indirect',   label: 'I keep the source vague. "I work with families navigating decisions about a home."' },
      { value: 'it_depends', short: 'It depends', label: 'I read the situation. Depends on the family.' },
    ],
  },
  {
    id: 'first_contact_tempo',
    prompt: 'When a new lead surfaces, do you want to be the first letter in their mailbox or come in later?',
    options: [
      { value: 'first', short: 'First',      label: 'I want to be early. Speed matters.' },
      { value: 'late',  short: 'Quiet late', label: 'I\'d rather come in quiet, after the volume of other cold outreach has died down.' },
    ],
  },
  {
    id: 'first_letter_substance',
    prompt: 'Do your early letters lead with substance (market, comps, value) or with relationship (introduction, who I am)?',
    options: [
      { value: 'substance',    short: 'Substance',    label: 'I lead with what I know about their situation and the market.' },
      { value: 'relationship', short: 'Relationship', label: 'I lead with introducing myself. The first letter isn\'t about the deal.' },
    ],
  },
  {
    id: 'preferred_length',
    prompt: 'Do your letters tend to run short and frequent, or longer and rarer?',
    options: [
      { value: 'short_frequent', short: 'Short, frequent', label: 'Brief letters, more often.' },
      { value: 'long_rare',      short: 'Longer, rarer',   label: 'Longer letters, fewer of them.' },
    ],
  },
  {
    id: 'follow_up_posture',
    prompt: 'If you don\'t hear back, do you keep writing on cadence or step away?',
    options: [
      { value: 'cadence',         short: 'Stay on cadence', label: 'I keep writing until the sequence ends, regardless of whether they respond.' },
      { value: 'wait_for_signal', short: 'Step away',       label: 'I write once or twice and stop unless they signal back.' },
    ],
  },
  {
    id: 'price_voice',
    prompt: 'Are you comfortable referencing specific values, comps, or numbers in early letters?',
    options: [
      { value: 'comfortable_early', short: 'Comfortable',    label: 'Yes — naming a number is part of being useful.' },
      { value: 'only_when_asked',   short: 'Only when asked', label: 'I avoid numbers in cold outreach.' },
    ],
  },
  {
    id: 'self_presentation',
    prompt: 'When you talk about your experience, do you reference it directly or let the work speak?',
    options: [
      { value: 'direct',     short: 'Direct',     label: 'I\'ll mention years in the market, notable transactions, my brokerage.' },
      { value: 'understated', short: 'Understated', label: 'I let the substance of the letter do the work. I rarely talk about myself.' },
    ],
  },
  {
    id: 'competitor_acknowledgment',
    prompt: 'Are you willing to acknowledge other agents directly in your letters?',
    options: [
      { value: 'acknowledge',     short: 'Acknowledge',  label: 'Yes. "If you\'ve decided to work with someone else, that\'s fine." Naming the elephant builds trust.' },
      { value: 'dont_reference',  short: 'Don\'t reference', label: 'No. I focus on what I bring; I don\'t reference competitors.' },
    ],
  },
  {
    id: 'door_knock_posture',
    prompt: 'Are you comfortable cold-knocking on doors, or do you only knock after explicit signal?',
    options: [
      { value: 'cold_open',        short: 'Cold knock',     label: 'Yes, I\'ll go to the door cold. It\'s part of the job.' },
      { value: 'signal_required',  short: 'Signal required', label: 'I only knock if I have a real reason. Otherwise leave a card.' },
    ],
  },
  {
    id: 'phone_posture',
    prompt: 'Do you prefer cold-calling or letter-first?',
    options: [
      { value: 'comfortable_cold', short: 'Cold call',    label: 'I\'ll pick up the phone first. More direct.' },
      { value: 'letter_first',     short: 'Letter first', label: 'I prefer to write first and call only after they\'ve responded.' },
    ],
  },
];

// ─── Archetype display labels for the post-generation preview ─────────
const ARCHETYPE_LABELS = {
  probate:           'Probate',
  divorce:           'Divorce',
  investor:          'Investor / LLC',
  trust:             'Trust',
  longTenure:        'Long-tenure homeowner',
  estateTransition:  'Estate transition',
};

// ─── Empty geographic anchor row factory ──────────────────────────────
const newAnchor = () => ({ neighborhood: '', relationship: '' });


// ─────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────
export default function VoiceOnboardingPage() {
  const { profile, refreshProfile, signOut } = useAuth();

  // Form state mirrors the profile's voice fields.
  const [voiceSample, setVoiceSample] = useState('');
  const [stance, setStance]           = useState({});  // {q.id: option.value}
  const [bgText, setBgText]           = useState('');  // bio.background
  const [anchors, setAnchors]         = useState([newAnchor()]);  // bio.geographic_anchors
  const [affText, setAffText]         = useState('');  // bio.affiliations

  // UI state
  const [saving, setSaving]           = useState(false);
  const [generating, setGenerating]   = useState(false);
  const [error, setError]             = useState(null);
  const [genResult, setGenResult]     = useState(null);  // generation response after success

  // Sync form from profile on first load + whenever profile refreshes.
  useEffect(() => {
    if (!profile) return;
    if (profile.voice_sample) setVoiceSample(profile.voice_sample);
    if (profile.stance && typeof profile.stance === 'object') setStance(profile.stance);
    if (profile.bio && typeof profile.bio === 'object') {
      if (profile.bio.background) setBgText(profile.bio.background);
      if (profile.bio.affiliations) setAffText(profile.bio.affiliations);
      if (Array.isArray(profile.bio.geographic_anchors) && profile.bio.geographic_anchors.length > 0) {
        setAnchors(profile.bio.geographic_anchors);
      }
    }
    // If scripts already exist, seed the preview pane so the agent can
    // see their existing output without re-generating.
    if (profile.generated_scripts && Object.keys(profile.generated_scripts).length > 0) {
      setGenResult({
        scripts: profile.generated_scripts,
        voice_onboarding_completed_at: profile.voice_onboarding_completed_at,
        existing: true,
      });
    }
  }, [profile]);

  // ── Anchor row helpers ────────────────────────────────────────────
  function updateAnchor(idx, field, value) {
    setAnchors(prev => prev.map((a, i) => i === idx ? { ...a, [field]: value } : a));
  }
  function addAnchor()  { setAnchors(prev => [...prev, newAnchor()]); }
  function removeAnchor(idx) {
    setAnchors(prev => prev.length === 1 ? [newAnchor()] : prev.filter((_, i) => i !== idx));
  }

  // ── Validation ────────────────────────────────────────────────────
  const voiceLen = voiceSample.trim().length;
  const voiceOK  = voiceLen >= 100;  // soft minimum — below this the LLM has too little to work with

  // ── Save inputs (PUT /api/profile) without triggering generation ──
  async function saveInputs() {
    setError(null);
    setSaving(true);
    try {
      const token = await getAccessToken();
      if (!token) throw new Error('Not signed in');

      const validAnchors = anchors.filter(a => a.neighborhood.trim() || a.relationship.trim());

      const body = {
        voice_sample: voiceSample.trim(),
        stance,
        bio: {
          background: bgText.trim(),
          geographic_anchors: validAnchors,
          affiliations: affText.trim(),
        },
      };

      const res = await fetch('/api/profile', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const t = await res.text().catch(() => '');
        throw new Error(t || `Save failed (${res.status})`);
      }
      await refreshProfile();
    } finally {
      setSaving(false);
    }
  }

  // ── Generate (PUT inputs first, then POST generate-scripts) ───────
  async function handleGenerate() {
    setError(null);
    if (!voiceOK) {
      setError('Voice sample is too short. Aim for at least 100 characters — a paragraph or a real letter.');
      return;
    }
    setGenerating(true);
    try {
      await saveInputs();
      const result = await agentVoice.generateScripts();
      setGenResult(result);
      await refreshProfile();
      // Scroll to results
      setTimeout(() => {
        document.getElementById('voice-results')?.scrollIntoView({ behavior: 'smooth' });
      }, 100);
    } catch (e) {
      setError(safeErrorMessage(e, 'Generation failed.'));
    } finally {
      setGenerating(false);
    }
  }

  // ─────────────────────────────────────────────────────────────────
  return (
    <SiteLayout
      agent={profile}
      onSignOut={signOut}
      mode="authenticated"
      showFooter={false}
      contentMaxWidth={780}
    >
      <header style={{ marginBottom: 'var(--space-xl)' }}>
        <div style={{
          fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase',
          color: 'var(--text-tertiary)', fontWeight: 600,
          marginBottom: 6, fontFamily: 'var(--font-sans)',
        }}>
          Your voice
        </div>
        <h1 style={{
          fontFamily: 'var(--font-display)', fontSize: 36, fontWeight: 600,
          letterSpacing: '-0.01em', color: 'var(--text)',
        }}>
          How do you reach out to sellers?
        </h1>
        <p style={{
          fontFamily: 'var(--font-serif)', color: 'var(--text-secondary)',
          fontSize: 16, lineHeight: 1.6, marginTop: 'var(--space-sm)',
        }}>
          The system generates your phone, letter, and door scripts in your voice.
          What we need from you: how you actually communicate, how you approach
          different situations, and what makes you you. Takes about ten minutes.
        </p>
      </header>

      {/* ── Voice sample ──────────────────────────────────────────── */}
      <Section
        label="VOICE SAMPLE"
        title="How do you sound when you write to a seller?"
        description="Describe your style in your own words, or paste a real letter you've sent. Either is fine. The system reads your cadence and word choice from this."
      >
        <textarea
          value={voiceSample}
          onChange={(e) => setVoiceSample(e.target.value)}
          rows={10}
          placeholder="Paste a real letter you've sent, or describe how you typically write to a seller. Around a paragraph is enough."
          style={inputStyle()}
        />
        <div style={{
          fontSize: 12, color: voiceOK ? 'var(--text-tertiary)' : 'var(--call-now)',
          marginTop: 6, fontFamily: 'var(--font-sans)',
        }}>
          {voiceLen} characters{!voiceOK && voiceLen > 0 && ' — try for at least 100'}
        </div>
      </Section>

      {/* ── Stance questions ──────────────────────────────────────── */}
      <Section
        label="HOW YOU APPROACH"
        title="Ten quick questions about how you work."
        description="Each question is a real choice that affects how your outreach is written. Pick what's actually true for you."
      >
        {STANCE_QUESTIONS.map((q) => (
          <StanceQuestion
            key={q.id}
            q={q}
            value={stance[q.id]}
            onChange={(v) => setStance(prev => ({ ...prev, [q.id]: v }))}
          />
        ))}
      </Section>

      {/* ── Background ────────────────────────────────────────────── */}
      <Section
        label="BACKGROUND"
        title="How did you get here?"
        description="Where you're from, how you got into real estate, what you did before. Used sparingly — only when it connects organically to a lead. Most letters won't reference this; a few will."
      >
        <textarea
          value={bgText}
          onChange={(e) => setBgText(e.target.value)}
          rows={5}
          placeholder='Example: "I came to real estate after years in development and investment in Bozeman..."'
          style={inputStyle()}
        />
      </Section>

      {/* ── Geographic anchors ────────────────────────────────────── */}
      <Section
        label="WHERE YOU WORK"
        title="Neighborhoods you specialize in or live in."
        description="When a lead's parcel is in one of these areas, the system can reference your connection to it. Used only when relevant — not forced into every letter."
      >
        {anchors.map((a, idx) => (
          <div key={idx} style={{
            display: 'grid', gridTemplateColumns: '1fr 1.5fr auto',
            gap: 8, marginBottom: 8, alignItems: 'center',
          }}>
            <input
              type="text"
              value={a.neighborhood}
              onChange={(e) => updateAnchor(idx, 'neighborhood', e.target.value)}
              placeholder="Neighborhood (e.g. Bridle Trails, Bellevue)"
              style={inputStyle({ marginBottom: 0 })}
            />
            <input
              type="text"
              value={a.relationship}
              onChange={(e) => updateAnchor(idx, 'relationship', e.target.value)}
              placeholder="Your relationship to it (e.g. live here since 2019)"
              style={inputStyle({ marginBottom: 0 })}
            />
            <button
              type="button"
              onClick={() => removeAnchor(idx)}
              style={smallBtnStyle()}
              disabled={anchors.length === 1 && !a.neighborhood && !a.relationship}
              title="Remove"
            >
              −
            </button>
          </div>
        ))}
        <button type="button" onClick={addAnchor} style={addBtnStyle()}>
          + Add neighborhood
        </button>
      </Section>

      {/* ── Affiliations ──────────────────────────────────────────── */}
      <Section
        label="BROKERAGE & PROOF"
        title="Where you work, what you bring, who you know."
        description="Your brokerage, notable transactions, boards or community work, press if relevant. Used in later letters when establishing credibility, not in cold first letters."
      >
        <textarea
          value={affText}
          onChange={(e) => setAffText(e.target.value)}
          rows={5}
          placeholder='Example: "I am with The Agency in Bozeman — a global luxury brokerage with offices in..."'
          style={inputStyle()}
        />
      </Section>

      {/* ── Action ────────────────────────────────────────────────── */}
      <div style={{
        marginTop: 'var(--space-xl)', paddingTop: 'var(--space-lg)',
        borderTop: '1px solid var(--border)',
      }}>
        {error && (
          <div style={{
            padding: '12px 14px', marginBottom: 'var(--space-md)',
            background: 'var(--call-now-bg)', color: 'var(--call-now)',
            borderRadius: 'var(--radius-sm)', fontSize: 14, fontFamily: 'var(--font-sans)',
          }}>
            {error}
          </div>
        )}

        <button
          type="button"
          onClick={handleGenerate}
          disabled={!voiceOK || generating || saving}
          style={primaryBtnStyle(generating || saving)}
        >
          {generating ? 'Generating your scripts… (about 60 seconds)' : (genResult ? 'Regenerate scripts' : 'Generate my scripts')}
        </button>

        {generating && (
          <div style={{
            marginTop: 12, fontSize: 13, color: 'var(--text-tertiary)',
            fontFamily: 'var(--font-serif)', fontStyle: 'italic',
          }}>
            Running six archetype generations in parallel — phone, letter, and door for probate, divorce, trust, investor, long-tenure, and estate transition. This takes a minute.
          </div>
        )}

        {!genResult && !generating && (
          <div style={{
            marginTop: 12, fontSize: 12, color: 'var(--text-tertiary)',
            fontFamily: 'var(--font-sans)',
          }}>
            Your inputs save automatically when you generate. You can come back later and regenerate.
          </div>
        )}
      </div>

      {/* ── Results ───────────────────────────────────────────────── */}
      {genResult && genResult.scripts && (
        <ResultsPane
          id="voice-results"
          scripts={genResult.scripts}
          existing={genResult.existing}
        />
      )}
    </SiteLayout>
  );
}


// ─────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────

function Section({ label, title, description, children }) {
  return (
    <section style={{
      marginBottom: 'var(--space-xl)',
      padding: 'var(--space-lg)',
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)',
    }}>
      <div style={{
        fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase',
        color: 'var(--accent)', fontWeight: 700,
        marginBottom: 6, fontFamily: 'var(--font-sans)',
      }}>
        {label}
      </div>
      <h2 style={{
        fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 600,
        color: 'var(--text)', margin: 0, letterSpacing: '-0.005em',
      }}>
        {title}
      </h2>
      {description && (
        <p style={{
          fontFamily: 'var(--font-serif)', fontSize: 14,
          color: 'var(--text-secondary)', lineHeight: 1.55,
          marginTop: 'var(--space-sm)', marginBottom: 'var(--space-md)',
        }}>
          {description}
        </p>
      )}
      {children}
    </section>
  );
}

function StanceQuestion({ q, value, onChange }) {
  return (
    <div style={{ marginBottom: 'var(--space-md)' }}>
      <div style={{
        fontFamily: 'var(--font-serif)', fontSize: 14,
        color: 'var(--text)', lineHeight: 1.5,
        marginBottom: 8,
      }}>
        {q.prompt}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 6 }}>
        {q.options.map((opt) => {
          const selected = value === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => onChange(opt.value)}
              style={pillStyle(selected)}
            >
              {opt.short}
            </button>
          );
        })}
      </div>
      {value && (
        <div style={{
          fontSize: 12, color: 'var(--text-tertiary)',
          fontStyle: 'italic', fontFamily: 'var(--font-serif)',
          paddingLeft: 2,
        }}>
          {q.options.find(o => o.value === value)?.label}
        </div>
      )}
    </div>
  );
}

function ResultsPane({ id, scripts, existing }) {
  const archetypes = Object.keys(scripts);
  const [active, setActive] = useState(archetypes[0] || 'probate');
  const s = scripts[active];

  if (!s) return null;

  return (
    <section id={id} style={{
      marginTop: 'var(--space-2xl)',
      padding: 'var(--space-lg)',
      background: 'var(--bg-card)',
      border: '2px solid var(--accent)',
      borderRadius: 'var(--radius-lg)',
    }}>
      <div style={{
        fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase',
        color: 'var(--accent)', fontWeight: 700, marginBottom: 6,
        fontFamily: 'var(--font-sans)',
      }}>
        {existing ? 'Your scripts (already generated)' : 'Your scripts'}
      </div>
      <h2 style={{
        fontFamily: 'var(--font-display)', fontSize: 24, fontWeight: 600,
        color: 'var(--text)', margin: 0, letterSpacing: '-0.005em',
        marginBottom: 'var(--space-md)',
      }}>
        Here's what the system generated
      </h2>
      <p style={{
        fontFamily: 'var(--font-serif)', fontSize: 14,
        color: 'var(--text-secondary)', lineHeight: 1.55,
        marginBottom: 'var(--space-lg)',
      }}>
        These are the outreach scripts that will appear when you open a lead.
        Lead-specific details (name, address, neighborhood) are substituted at
        view-time. Switch between archetypes below to see each kind.
      </p>

      {/* Archetype tabs */}
      <div style={{
        display: 'flex', flexWrap: 'wrap', gap: 6,
        marginBottom: 'var(--space-md)',
        paddingBottom: 'var(--space-sm)',
        borderBottom: '1px solid var(--border)',
      }}>
        {archetypes.map((arch) => (
          <button
            key={arch}
            type="button"
            onClick={() => setActive(arch)}
            style={pillStyle(arch === active)}
          >
            {ARCHETYPE_LABELS[arch] || arch}
          </button>
        ))}
      </div>

      {/* Letter sequence */}
      {Array.isArray(s.letter_sequence) && s.letter_sequence.map((letter, idx) => (
        <div key={idx} style={{
          marginBottom: 'var(--space-lg)',
          paddingBottom: 'var(--space-md)',
          borderBottom: idx < s.letter_sequence.length - 1 ? '1px dotted var(--border)' : 'none',
        }}>
          <div style={{
            fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase',
            color: 'var(--text-tertiary)', fontWeight: 700,
            fontFamily: 'var(--font-sans)', marginBottom: 4,
          }}>
            Day {letter.day}
          </div>
          <div style={{
            fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 600,
            color: 'var(--text)', marginBottom: 8,
          }}>
            {letter.title}
          </div>
          <div style={{
            fontFamily: 'var(--font-serif)', fontSize: 14,
            color: 'var(--text)', lineHeight: 1.65,
            whiteSpace: 'pre-wrap',
          }}>
            {letter.body}
          </div>
        </div>
      ))}

      {/* Phone */}
      {s.phone_script && (
        <div style={{ marginBottom: 'var(--space-lg)' }}>
          <div style={{
            fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase',
            color: 'var(--text-tertiary)', fontWeight: 700,
            fontFamily: 'var(--font-sans)', marginBottom: 8,
          }}>
            Phone script
          </div>
          <div style={{
            fontFamily: 'var(--font-mono, monospace)', fontSize: 13,
            color: 'var(--text)', lineHeight: 1.6,
            whiteSpace: 'pre-wrap', background: 'var(--bg)',
            padding: 'var(--space-md)', borderRadius: 'var(--radius-md)',
          }}>
            {s.phone_script}
          </div>
        </div>
      )}

      {/* Door */}
      {s.door_script && (
        <div>
          <div style={{
            fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase',
            color: 'var(--text-tertiary)', fontWeight: 700,
            fontFamily: 'var(--font-sans)', marginBottom: 8,
          }}>
            Door script
          </div>
          <div style={{
            fontFamily: 'var(--font-mono, monospace)', fontSize: 13,
            color: 'var(--text)', lineHeight: 1.6,
            whiteSpace: 'pre-wrap', background: 'var(--bg)',
            padding: 'var(--space-md)', borderRadius: 'var(--radius-md)',
          }}>
            {s.door_script}
          </div>
        </div>
      )}
    </section>
  );
}


// ─────────────────────────────────────────────────────────────────────
// Style helpers
// ─────────────────────────────────────────────────────────────────────

function inputStyle(extra = {}) {
  return {
    width: '100%',
    padding: '12px 14px',
    fontSize: 14,
    fontFamily: 'var(--font-serif)',
    color: 'var(--text)',
    background: 'var(--bg-input, var(--bg))',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
    boxSizing: 'border-box',
    outline: 'none',
    transition: 'border-color 0.15s ease',
    marginBottom: 4,
    lineHeight: 1.5,
    ...extra,
  };
}

function pillStyle(selected) {
  return {
    padding: '7px 14px',
    fontSize: 13,
    fontWeight: selected ? 700 : 500,
    fontFamily: 'var(--font-sans)',
    border: selected ? '1px solid var(--accent)' : '1px solid var(--border)',
    background: selected ? 'var(--accent)' : 'transparent',
    color: selected ? 'var(--text-inverse, #fff)' : 'var(--text)',
    borderRadius: 999,
    cursor: 'pointer',
    transition: 'all 0.12s ease',
    letterSpacing: '0.02em',
  };
}

function primaryBtnStyle(disabled) {
  return {
    width: '100%',
    padding: '14px 20px',
    fontSize: 14,
    fontWeight: 600,
    fontFamily: 'var(--font-sans)',
    color: disabled ? 'var(--text-tertiary)' : 'var(--text-inverse, #fff)',
    background: disabled ? 'var(--bg)' : 'var(--accent)',
    border: disabled ? '1px solid var(--border)' : 'none',
    borderRadius: 'var(--radius-md)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    transition: 'background 0.15s ease',
    letterSpacing: '0.02em',
  };
}

function smallBtnStyle() {
  return {
    width: 32, height: 32,
    border: '1px solid var(--border)',
    background: 'transparent',
    color: 'var(--text-secondary)',
    borderRadius: 'var(--radius-md)',
    cursor: 'pointer',
    fontSize: 18, fontWeight: 600,
    fontFamily: 'var(--font-sans)',
  };
}

function addBtnStyle() {
  return {
    padding: '8px 14px',
    fontSize: 12,
    fontWeight: 600,
    fontFamily: 'var(--font-sans)',
    color: 'var(--accent)',
    background: 'transparent',
    border: '1px dashed var(--accent)',
    borderRadius: 'var(--radius-md)',
    cursor: 'pointer',
    letterSpacing: '0.03em',
  };
}
