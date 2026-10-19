import SiteHeader from './SiteHeader.jsx';
import SiteFooter from './SiteFooter.jsx';

// SiteLayout — wraps a page with the SellerSignal header and
// (optionally) footer. Designed to be rendered around <Outlet />
// at the route level OR around individual page bodies.
//
// Props:
//   agent           — current agent profile or null. Drives auth nav.
//   onSignOut       — callback for the Sign Out button.
//   mode            — 'auto' | 'public' | 'authenticated'. Forces
//                     header mode regardless of agent presence.
//                     Default 'auto'.
//   showFooter      — whether to render SiteFooter. Default true.
//                     App surfaces (briefing, territories) usually
//                     pass false — they take the full viewport.
//   contentMaxWidth — when set, wraps children in a centered container
//                     of this width. Marketing/profile pages want
//                     this; full-bleed app surfaces don't.
export default function SiteLayout({
  children,
  agent = null,
  onSignOut = null,
  mode = 'auto',
  showFooter = true,
  contentMaxWidth = null,
}) {
  return (
    <div style={{
      // 100dvh tracks the visible viewport on iOS Safari (the URL
      // bar's show/hide changes effective viewport height). 100vh on
      // iOS measures against the URL-bar-hidden viewport, which
      // makes the layout taller than what's actually visible and
      // pushes the sticky header above the visible area when the
      // URL bar is showing.
      minHeight: '100dvh',
      background: 'var(--bg)',
      display: 'flex',
      flexDirection: 'column',
    }}>
      <SiteHeader agent={agent} onSignOut={onSignOut} mode={mode} />

      <main style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
      }}>
        {contentMaxWidth ? (
          <div style={{
            maxWidth: contentMaxWidth,
            width: '100%',
            margin: '0 auto',
            padding: 'var(--space-xl) var(--space-lg)',
          }}>
            {children}
          </div>
        ) : (
          children
        )}
      </main>

      {showFooter && <SiteFooter />}
    </div>
  );
}
