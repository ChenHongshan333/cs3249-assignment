import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ command, mode }) => ({
  base: '/',
  plugins: [react({
    babel: command === 'serve' && mode !== 'production'
      ? { plugins: [['module:@locator/babel-jsx', { env: 'development' }]] }
      : undefined,
  })],
  // The FastAPI backend runs on port 8000; the browser only talks to Vite, which forwards /api to it.
  server: { host: '127.0.0.1', proxy: { '/api': 'http://127.0.0.1:8000' } },
}));
