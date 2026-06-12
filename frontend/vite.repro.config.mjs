import { defineConfig } from 'vite';
export default defineConfig({
  resolve: { alias: [
    { find: /.*lib\/AuthContext\.jsx$/, replacement: '/tmp/repro/authshim.jsx' },
  ]},
});
