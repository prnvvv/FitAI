import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

/**
 * The backend address has a single source of truth: `BACKEND_HOST` and
 * `BACKEND_PORT` in `backend/.env` (falling back to `.env.example` defaults).
 * Change it there, not here.
 */
function backendTarget(root: string, mode: string): string {
  const host = loadEnv(mode, resolve(root, 'backend'), '').BACKEND_HOST || '127.0.0.1'
  const port = loadEnv(mode, resolve(root, 'backend'), '').BACKEND_PORT || '8000'
  return `http://${host}:${port}`
}

export default defineConfig(({ mode }) => {
  const root = resolve(__dirname, '..')
  let target = backendTarget(root, mode)

  // `.env` is the documented source; fall back to the committed example so a
  // fresh clone still proxies to a predictable port.
  try {
    const envFile = readFileSync(resolve(root, 'backend', '.env'), 'utf8')
    const host = /^BACKEND_HOST=(.*)$/m.exec(envFile)?.[1]?.trim()
    const port = /^BACKEND_PORT=(.*)$/m.exec(envFile)?.[1]?.trim()
    if (host && port) target = `http://${host}:${port}`
  } catch {
    // No backend/.env yet; keep the value loaded from .env.example.
  }

  return {
    plugins: [react()],
    server: {
      // Bind IPv4 loopback explicitly: the default binds ::1 only, so a
      // 127.0.0.1 URL (or the proxy target) would be refused.
      host: '127.0.0.1',
      port: 5173,
      proxy: {
        '/api/v1': {
          target,
          changeOrigin: true,
        },
      },
    },
  }
})
