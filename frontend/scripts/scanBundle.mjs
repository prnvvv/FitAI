// Scan a built frontend for privileged secrets and source maps.
// Usage: node scripts/scanBundle.mjs [distDir]   (exits 1 on any finding)
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const PATTERNS = [
  ['Groq API key', /gsk_[A-Za-z0-9]{20,}/],
  ['Hugging Face token', /hf_[A-Za-z0-9]{30,}/],
  ['Database URL with credentials', /postgres(?:ql)?(?:\+\w+)?:\/\/[^\s:@/]+:[^\s@/]+@/],
  ['Private key block', /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/],
  ['Supabase secret key', /sb_secret_[A-Za-z0-9_-]{16,}/],
  ['Service-role identifier', /SUPABASE_SERVICE_ROLE_KEY/],
]

/** Decode the payload of a JWT-looking string, or null. */
function jwtPayload(token) {
  try {
    const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(Buffer.from(part, 'base64').toString('utf8'))
  } catch {
    return null
  }
}

/** Return human-readable findings for one file's text. */
export function scanText(text) {
  const findings = []
  for (const [label, re] of PATTERNS) if (re.test(text)) findings.push(label)
  for (const token of text.match(/eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/g) ?? []) {
    if (jwtPayload(token)?.role === 'service_role') findings.push('Supabase service_role JWT')
  }
  return findings
}

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? walk(path) : [path]
  })
}

export function scanDir(dir) {
  const problems = []
  for (const file of walk(dir)) {
    if (file.endsWith('.map')) problems.push(`${file}: source map shipped`)
    if (/\.(js|css|html|json|txt|svg)$/.test(file)) {
      for (const f of scanText(readFileSync(file, 'utf8'))) problems.push(`${file}: ${f}`)
    }
  }
  return problems
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const dir = process.argv[2] ?? 'dist'
  const problems = scanDir(dir)
  if (problems.length) {
    console.error(`Bundle scan FAILED (${problems.length}):\n` + problems.join('\n'))
    process.exit(1)
  }
  console.log(`Bundle scan passed: no privileged secrets or source maps in ${dir}`)
}
