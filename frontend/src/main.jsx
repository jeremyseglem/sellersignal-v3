import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import { AuthProvider } from './lib/AuthContext.jsx';
import './styles/tokens.css';
import './styles/v4-tokens.css';
import './styles/v4-remap.css';
import { initUiVersion } from './lib/uiVersion';

// V4 UI flag plumbing (MIGRATION_V4.md) — no-op unless UI_V4 or ?v4=1
initUiVersion();

// AuthProvider wraps the entire app so any page or component can
// call useAuth() to read the current session and profile. Provider
// must sit inside BrowserRouter because LoginPage uses
// useSearchParams during its initial render.
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
