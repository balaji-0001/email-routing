import path from 'path';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig, loadEnv } from 'vite';

// Local settings come from the repo-root .env (see .env.example).
// Variables set in the shell take precedence over the file.
const workspaceRoot = path.resolve(import.meta.dirname, '..');

function readPort(name: string, raw: string | undefined, fallback: number) {
  if (!raw) return fallback;

  const port = Number(raw);

  if (Number.isNaN(port) || port <= 0) {
    throw new Error(`Invalid ${name} value: "${raw}"`);
  }

  return port;
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, workspaceRoot, '');

  const port = readPort('WEB_PORT', env.WEB_PORT, 5173);
  // PORT is the API server's port; the dev server forwards /api to it so the
  // browser can call the API on the same origin as the app.
  const apiPort = readPort('PORT', env.PORT, 5000);
  const proxy = {
    '/api': { target: `http://localhost:${apiPort}`, changeOrigin: true },
  };

  return {
    base: env.BASE_PATH || '/',
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(import.meta.dirname, 'src'),
      },
      dedupe: ['react', 'react-dom'],
    },
    root: path.resolve(import.meta.dirname),
    build: {
      outDir: path.resolve(import.meta.dirname, 'dist/public'),
      emptyOutDir: true,
    },
    server: {
      port,
      strictPort: true,
      proxy,
      fs: {
        strict: true,
      },
    },
    preview: {
      port,
      proxy,
    },
  };
});
