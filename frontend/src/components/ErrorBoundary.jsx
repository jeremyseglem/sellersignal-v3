import React from 'react';

/**
 * Top-level error boundary — 2026-06-12.
 *
 * Before this existed, ANY uncaught render/effect error unmounted the whole
 * React tree and the agent saw a pure blank page with zero information
 * (e.g. the mobile lead-click blank-screen reports). This renders the actual
 * error message on screen so a screenshot from any device is a usable bug
 * report, plus a reload button.
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error) {
    return { error };
  }
  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('ErrorBoundary caught:', error, info?.componentStack);
    this.setState({ stack: (info?.componentStack || '').split('\n').slice(0, 6).join('\n') });
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div style={{
        minHeight: '60vh', display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', gap: 16,
        padding: 24, textAlign: 'center',
        fontFamily: 'var(--font-sans, sans-serif)', color: 'var(--text-primary, #2C2418)',
        background: 'var(--bg-card, #F5F0EB)',
      }}>
        <div style={{ fontFamily: 'var(--font-serif, serif)', fontStyle: 'italic', fontSize: 18 }}>
          Something broke on this screen.
        </div>
        <code style={{
          fontSize: 12, whiteSpace: 'pre-wrap', maxWidth: 640, textAlign: 'left',
          background: 'rgba(44,36,24,0.06)', padding: '12px 14px', borderRadius: 6,
          wordBreak: 'break-word',
        }}>
          {String(this.state.error?.message || this.state.error)}
          {this.state.stack ? `\n${this.state.stack}` : ''}
        </code>
        <button
          onClick={() => window.location.reload()}
          style={{
            padding: '10px 22px', borderRadius: 999, border: 'none',
            background: 'var(--accent, #8B6914)', color: '#fff',
            fontSize: 14, fontWeight: 600, cursor: 'pointer',
          }}
        >
          Reload
        </button>
      </div>
    );
  }
}
