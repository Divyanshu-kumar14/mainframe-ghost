import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// `npm run dev` proxies /api to the cockpit engine (python3 -m cockpit.server).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8737' },
  },
});
