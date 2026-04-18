import { Routes, Route, Navigate } from 'react-router-dom';
import BriefingPage from './pages/BriefingPage.jsx';
import CoveragePage from './pages/CoveragePage.jsx';

export default function App() {
  return (
    <Routes>
      {/* Default route — redirect to coverage list */}
      <Route path="/" element={<Navigate to="/coverage" replace />} />

      {/* Coverage list — shows all live ZIPs */}
      <Route path="/coverage" element={<CoveragePage />} />

      {/* Unified briefing + map for a specific ZIP */}
      <Route path="/zip/:zip" element={<BriefingPage />} />
    </Routes>
  );
}
