import { resolve } from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

/**
 * The backend address has a single source of truth: `BACKEND_HOST` and
 * `BACKEND_PORT` in `backend/.env` (falling back to the defaults below).
 * Change it there, not here.
 */
function backendTarget(root: string, mode: string): string {
  const backendEnv = loadEnv(mode, resolve(root, 'backend'), '')
  const host = backendEnv.BACKEND_HOST || '127.0.0.1'
  const port = backendEnv.BACKEND_PORT || '8000'
  return `http://${host}:${port}`
}

export default defineConfig(({ mode }) => {
  const root = resolve(import.meta.dirname, '..')

  return {
    plugins: [react()],
    // Never ship source maps to production: they expose original source to anyone.
    build: { sourcemap: false },
    server: {
      // Bind IPv4 loopback explicitly: the default binds ::1 only, so a
      // 127.0.0.1 URL (or the proxy target) would be refused.
      host: '127.0.0.1',
      port: 5173,
      // Fail loudly instead of silently moving to another port, which would
      // hide a stale dev server holding 5173.
      strictPort: true,
      proxy: {
        '/api/v1': {
          target: backendTarget(root, mode),
          changeOrigin: true,
        },
      },
    },
  }
})
