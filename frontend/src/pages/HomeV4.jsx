import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { availability, notifications } from '../api/client.js';
import '../styles/home-v4.css';

/*
 * HomeV4 — the V4 homepage, ported from the approved demo
 * (sellersignal-premium-v18) per MIGRATION_V4.md Phase 2.
 *
 * Mounted by HomePage.jsx ONLY when the V4 skin is active; V3 users
 * never load this module (React.lazy). The hero video lives at
 * /assets/hero-build.mp4 (committed static asset, not in the bundle).
 *
 * The ZIP checker below is NOT the demo's simplified fetch — it is the
 * live V3 checker's full three-state flow (open → signup route,
 * claimed → release wait list, not_covered → expansion demand), same
 * api client calls, same `source` semantics, restyled. Lose nothing.
 */

// ── hero terminal beats (synced to the build clip) ──
const BEATS = [
  { t: 0.15, html: '<span class="tag">98039 · MEDINA</span><span class="dim"> — 38 SIGNALS UNDER WATCH</span>' },
  { t: 0.85, html: '<span class="tag">SIGNAL DETECTED</span><span class="dim"> — OWNERSHIP IN TRANSITION</span>' },
  { t: 2.05, html: '<span class="tag">CROSS-REFERENCED</span><span class="dim"> — TITLE · TENURE · TAX · OWNERSHIP</span>' },
  { t: 3.35, html: '<span class="tag">DECISION-MAKER IDENTIFIED</span><span class="dim"> — MARGARET ELLISON · FAMILY</span>' },
  { t: 4.35, html: '<span class="tag">CONTACT VERIFIED</span><span class="dim"> · (425) •••-••41 · M•••••••@•••••.COM</span>' },
  { t: 4.85, html: '<span class="tag">THE PLAY →</span> <span class="v">The right letter, today. The call, week two.</span>', cls: 'play-line' },
];

const FEED = [
  ['98177', 'Seattle WA', '76 decision-makers identified'],
  ['06831', 'Greenwich CT', '24 signals corroborated · four layers'],
  ['98012', 'Mill Creek WA', '22 decision-makers identified'],
  ['98026', 'Edmonds WA', '23 signals live this quarter'],
  ['85250', 'Scottsdale AZ', 'trust transfers under watch'],
  ['75013', 'Allen TX', 'signal detected · identity pending'],
  ['98109', 'Seattle WA', '48 decision-makers identified'],
  ['78738', 'Lakeway TX', 'out-of-state owners flagged'],
  ['98011', 'Bothell WA', '54 decision-makers identified'],
  ['06870', 'Old Greenwich CT', 'long-tenure holdings under watch'],
];

const MARKETS = [
  ['Seattle Eastside', '32 territories · 2,150 decision-makers named', 'https://images.unsplash.com/photo-1568605114967-8130f3a36994?w=1000&q=80'],
  ['Scottsdale & Phoenix', '24 territories · deep-layer coverage', 'https://images.unsplash.com/photo-1613977257363-707ba9348227?w=1000&q=80'],
  ['Greenwich', '5 territories · 51 decision-makers named', 'https://images.unsplash.com/photo-1570129477492-45c003edd2be?w=1000&q=80'],
  ['Dallas & Park Cities', '9 territories', 'https://images.unsplash.com/photo-1600585154084-4e5fe7c39198?w=1000&q=80'],
  ['Austin & Lakeway', '9 territories', 'https://images.unsplash.com/photo-1600607687920-4e2a09cf159d?w=1000&q=80'],
  ['Edmonds & Snohomish', '6 territories · 125 signals corroborated', 'https://images.unsplash.com/photo-1499793983690-e29da59ef1c2?w=1000&q=80'],
];

function typeLine(el, html) {
  const full = document.createElement('div');
  full.innerHTML = html;
  const spans = [...full.childNodes];
  el.innerHTML = '';
  el.classList.add('on');
  const caret = document.createElement('span');
  caret.className = 'caret';
  let si = 0, ci = 0;
  const outs = spans.map((n) => { const c = n.cloneNode(false); el.appendChild(c); return c; });
  el.appendChild(caret);
  (function tick() {
    if (!el.isConnected) return;
    if (si >= spans.length) { caret.remove(); return; }
    const src = spans[si].textContent;
    if (ci < src.length) {
      outs[si].textContent = src.slice(0, ++ci);
      setTimeout(tick, 14);
    } else { si++; ci = 0; tick(); }
  })();
}

// ── count-up stat ──
function Stat({ target, label }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver((es) => {
      es.forEach((e) => {
        if (!e.isIntersecting) return;
        io.unobserve(el);
        const t0 = performance.now(), dur = 1600;
        const step = (t) => {
          if (!el.isConnected) return;
          const p = Math.min(1, (t - t0) / dur), ease = 1 - Math.pow(1 - p, 3);
          el.textContent = Math.round(target * ease).toLocaleString();
          if (p < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
      });
    }, { threshold: 0.4 });
    io.observe(el);
    return () => io.disconnect();
  }, [target]);
  return (
    <div className="stat"><b ref={ref}>0</b><span>{label}</span></div>
  );
}

// ── email capture (ported from live ZipChecker, v18 skin) ──
function EmailCapture({ email, setEmail, onSubmit, busy, buttonLabel }) {
  return (
    <div className="checker" style={{ marginTop: 14 }}>
      <input
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') onSubmit(); }}
        placeholder="YOUR EMAIL"
        type="email"
        aria-label="Email address"
      />
      <button className="btn btn-brass" onClick={onSubmit} disabled={busy}>
        {busy ? 'Saving…' : buttonLabel}
      </button>
    </div>
  );
}

// ── the live three-state checker, v18 skin ──
function ZipCheckerV4() {
  const [zip, setZip] = useState('');
  const [result, setResult] = useState(null);
  const [email, setEmail] = useState('');
  const [phase, setPhase] = useState('idle');
  const [errMsg, setErrMsg] = useState('');
  const zipValid = /^\d{5}$/.test(zip);

  async function check() {
    if (!zipValid || phase === 'checking') return;
    setPhase('checking'); setErrMsg(''); setResult(null);
    try {
      const r = await availability.check(zip);
      setResult(r); setPhase('checked');
    } catch {
      setErrMsg('Could not check that ZIP. Try again?'); setPhase('idle');
    }
  }
  async function subscribe() {
    if (!email || phase === 'subscribing' || !result) return;
    setPhase('subscribing'); setErrMsg('');
    const source = result.status === 'claimed' ? 'homepage_checker' : 'expansion_request';
    try {
      await notifications.subscribe(result.zip_code, email, source);
      setPhase('subscribed');
    } catch {
      setErrMsg('Could not save that. Try again?'); setPhase('checked');
    }
  }
  function reset() {
    setZip(''); setResult(null); setEmail(''); setPhase('idle'); setErrMsg('');
  }
  const place = result && result.city ? `${result.city}, ${result.state}` : null;

  return (
    <>
      {phase !== 'subscribed' && (
        <div className="checker">
          <input
            value={zip}
            onChange={(e) => {
              setZip(e.target.value.replace(/\D/g, '').slice(0, 5));
              if (result) { setResult(null); setPhase('idle'); }
            }}
            onKeyDown={(e) => { if (e.key === 'Enter') check(); }}
            placeholder="ENTER YOUR ZIP"
            inputMode="numeric"
            maxLength={5}
            aria-label="ZIP code"
          />
          <button
            className="btn btn-brass"
            onClick={check}
            disabled={!zipValid || phase === 'checking'}
            style={{ opacity: zipValid ? 1 : 0.55 }}
          >
            {phase === 'checking' ? 'Checking…' : 'Check availability'}
          </button>
        </div>
      )}

      <div className="check-result">
        {errMsg && <span style={{ color: 'var(--call-now, #D4705C)' }}>{errMsg}</span>}

        {result && phase !== 'subscribed' && result.status === 'open' && (
          <>
            <b>{result.zip_code}{place ? ` — ${place} —` : ''} is open.</b> One agent will hold it.
            <div style={{ marginTop: 14 }}>
              <Link to="/signup" className="btn btn-brass">Request access</Link>
            </div>
          </>
        )}

        {result && phase !== 'subscribed' && result.status === 'claimed' && (
          <>
            <b>{result.zip_code}{place ? ` — ${place} —` : ''} is held by another agent.</b>{' '}
            {result.queue_size > 0
              ? `${result.queue_size} waiting if it releases.`
              : 'We can tell you if it releases.'}
            <EmailCapture email={email} setEmail={setEmail} onSubmit={subscribe}
              busy={phase === 'subscribing'} buttonLabel="Notify me" />
          </>
        )}

        {result && phase !== 'subscribed' && result.status === 'not_covered' && (
          <>
            We're not in {result.zip_code} yet. Markets open selectively — demand decides where next.
            <EmailCapture email={email} setEmail={setEmail} onSubmit={subscribe}
              busy={phase === 'subscribing'} buttonLabel="Request my market" />
          </>
        )}

        {phase === 'subscribed' && (
          <>
            Noted. You'll hear from us about {result?.zip_code} — nothing else, no list.
            <div style={{ marginTop: 14 }}>
              <button className="btn btn-ghost" onClick={reset}>Check another ZIP</button>
            </div>
          </>
        )}
      </div>
    </>
  );
}

export default function HomeV4() {
  const navRef = useRef(null);
  const vidRef = useRef(null);
  const termRef = useRef(null);
  const replayRef = useRef(null);

  // nav scroll state
  useEffect(() => {
    const onScroll = () => navRef.current &&
      navRef.current.classList.toggle('solid', window.scrollY > 40);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  // hero: beats typed in sync with the build clip; hold the dossier, then loop
  useEffect(() => {
    const vid = vidRef.current, term = termRef.current, replay = replayRef.current;
    if (!vid || !term || !replay) return;
    let raf = 0, loopTimer = 0;
    const typed = new Set();
    const resetTerm = () => {
      typed.clear();
      term.innerHTML = BEATS.map((b, i) =>
        `<div class="term-line ${b.cls || ''}" data-beat="${i}"></div>`).join('');
      replay.classList.remove('on');
    };
    const watch = () => {
      const t = vid.currentTime;
      BEATS.forEach((b, i) => {
        if (t >= b.t && !typed.has(i)) {
          typed.add(i);
          const el = term.querySelector(`[data-beat="${i}"]`);
          if (el) typeLine(el, b.html);
        }
      });
      if (!vid.ended) raf = requestAnimationFrame(watch);
    };
    const run = () => {
      cancelAnimationFrame(raf);
      clearTimeout(loopTimer);
      resetTerm();
      vid.currentTime = 0;
      vid.play().catch(() => {});
      raf = requestAnimationFrame(watch);
    };
    const onEnded = () => {
      replay.classList.add('on');
      loopTimer = setTimeout(() => { if (vid.ended) run(); }, 6000);
    };
    vid.addEventListener('ended', onEnded);
    replay.addEventListener('click', run);
    const io = new IntersectionObserver((es) => {
      es.forEach((e) => {
        if (e.isIntersecting && vid.paused && vid.currentTime === 0) run();
      });
    }, { threshold: 0.35 });
    io.observe(vid);
    resetTerm();
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(loopTimer);
      vid.removeEventListener('ended', onEnded);
      replay.removeEventListener('click', run);
      io.disconnect();
    };
  }, []);

  const tickerItems = [...FEED, ...FEED];

  return (
    <div className="hv4">
      <nav ref={navRef}>
        <div className="wrap">
          <div className="logo">
            <svg width="26" height="26" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ flexShrink: 0, color: 'var(--brass)' }} aria-hidden="true">
              <circle cx="14" cy="14" r="13.07" stroke="currentColor" strokeWidth="1.86" fill="none" />
              <rect x="9.5" y="16" width="2.5" height="4" rx="1" fill="currentColor" />
              <rect x="13" y="13" width="2.5" height="7" rx="1" fill="currentColor" />
              <rect x="16.5" y="9" width="2.5" height="11" rx="1" fill="currentColor" />
            </svg>
            <span className="logo-word">SellerSignal</span>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <Link to="/login" className="btn btn-ghost btn-sm">Sign in</Link>
            <Link to="/signup" className="btn btn-brass btn-sm">Request access</Link>
          </div>
        </div>
      </nav>

      <section className="hero">
        <div className="hero-stage">
          <video className="hero-video" ref={vidRef} muted playsInline preload="auto">
            <source src="/assets/hero-build.mp4" type="video/mp4" />
          </video>
        </div>
        <div className="hero-shade" />
        <div className="term-scrim" />
        <div className="term" ref={termRef} />
        <button className="replay" ref={replayRef}>Replay signal</button>
        <div className="hero-fn">Name illustrative · the signal is real</div>

        <div className="wrap">
          <div className="eyebrow">Pre-market intelligence</div>
          <h1 className="serif">The future of <em>listing generation.</em></h1>
          <p className="hero-sub">Proprietary predictive technology that reveals homeowners most likely to sell — turning hidden opportunity into predictable listings.</p>
          <div className="hero-cta">
            <a href="#claim" className="btn btn-brass">Check your ZIP</a>
            <a href="#markets" className="btn btn-ghost">Territories</a>
          </div>
        </div>
      </section>

      <div className="ticker">
        <div className="ticker-track">
          {tickerItems.map(([z, c, s], i) => (
            <span key={i}>◆ <span className="zip">{z}</span> {c} — <span className="n">{s}</span></span>
          ))}
        </div>
      </div>

      <section className="markets" id="markets">
        <div className="wrap">
          <div className="section-head">
            <div className="section-label">TERRITORIES · 7 MARKETS LIVE</div>
            <h2>Seven markets. One agent per ZIP.</h2>
          </div>
          <div className="tiles">
            {MARKETS.map(([name, meta, img]) => (
              <div className="tile" key={name}>
                <img src={img} alt={name} loading="lazy" />
                <div className="tile-line" />
                <div className="tile-info">
                  <h3 className="serif">{name}</h3>
                  <div className="mono">{meta}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="name-section" id="name">
        <div className="name-bg" />
        <div className="name-shade" />
        <div className="wrap">
          <div className="name-inner">
            <div className="name-eyebrow">FOUR LAYERS ALIGNED — TITLE · TENURE · TAX · CONTACT</div>
            <div className="the-name">Margaret<br />Ellison</div>
            <p className="name-ctx">Surfaced by the intelligence layer four days ago. Decides the property on Evergreen Point Road. Hasn't called an agent. Isn't on a list anyone sells.</p>
            <div className="name-kicker">You would <em>already know her name.</em></div>
            <div className="name-fn">NAME ILLUSTRATIVE · THE SIGNAL IS REAL</div>
          </div>
        </div>
      </section>

      <section className="stats" id="stats">
        <div className="wrap" style={{ marginBottom: 54 }}>
          <div className="section-label">UNDER WATCH · LIVE COUNTS</div>
        </div>
        <div className="wrap">
          <Stat target={855544} label="properties under watch" />
          <Stat target={90} label="exclusive territories" />
          <Stat target={2346} label="decision-makers identified by name" />
        </div>
      </section>

      <section className="founders" id="founders">
        <div className="wrap">
          <div>
            <div className="section-label">THE FOUNDERS</div>
            <h2>Built by the people <em>who use it.</em></h2>
            <p className="body">SellerSignal was built by two top-producing agents who wanted it for themselves — and who run it in their own territories every week. <b>No one else in this space holds a license.</b> Every play, every cadence, every letter in this platform exists because it won a listing first.</p>
            <p className="body" style={{ marginTop: 16 }}>And the incentives run one direction: one agent per ZIP means your territory is never sold twice. We only win when you list.</p>
            <div className="kicker">Your incentives and ours are the same: the listing.</div>
          </div>
          <div className="f-list">
            <div className="f-item">
              <div className="fn2">Jeremy Seglem</div>
              <div className="fr">Co-founder · Licensed agent</div>
              <div className="fd">Built the intelligence methodology this platform runs on, prospecting luxury territories the same way you will.</div>
            </div>
            <div className="f-item">
              <div className="fn2">Brian Hawkins</div>
              <div className="fr">Co-founder · Licensed agent</div>
              <div className="fd">Runs the platform in his own market every week. Every feature ships only after it survives his prospecting.</div>
            </div>
            <a className="f-link" href="mailto:jeremy.seglem@theagencyre.com">Speak with the founders →</a>
          </div>
        </div>
      </section>

      <section className="claim" id="claim">
        <div className="wrap">
          <div className="section-label" style={{ marginBottom: 18 }}>TERRITORY CHECK</div>
          <h2>Your ZIP may <em>still be open.</em></h2>
          <p>One agent per territory. Ever.</p>
          <ZipCheckerV4 />
        </div>
      </section>

      <footer>
        <div className="wrap">
          <span className="mono" style={{ fontSize: 11, letterSpacing: '0.08em' }}>© 2026 SELLERSIGNAL · PRIVATE · BY INVITATION</span>
          <span className="mono" style={{ fontSize: 11, letterSpacing: '0.08em' }}>SELLERSIGNAL.CO</span>
        </div>
      </footer>
    </div>
  );
}
