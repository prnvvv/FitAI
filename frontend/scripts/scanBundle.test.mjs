import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { scanDir, scanText } from './scanBundle.mjs'

const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url')
const jwt = (role) => `${b64({ alg: 'HS256' })}.${b64({ role, iss: 'supabase' })}.${'s'.repeat(20)}`

describe('bundle secret scanner', () => {
  it('flags a service_role JWT but not the public anon key', () => {
    expect(scanText(`k="${jwt('service_role')}"`)).toContain('Supabase service_role JWT')
    expect(scanText(`k="${jwt('anon')}"`)).toEqual([])
  })

  it('flags provider keys and database URLs', () => {
    expect(scanText('gsk_' + 'a'.repeat(30))).toContain('Groq API key')
    expect(scanText('hf_' + 'b'.repeat(34))).toContain('Hugging Face token')
    expect(scanText('postgresql+psycopg2://u:pw@db.host:5432/x')).toContain(
      'Database URL with credentials',
    )
  })

  it('flags shipped source maps and passes a clean build', () => {
    const dir = mkdtempSync(join(tmpdir(), 'bundle-'))
    mkdirSync(join(dir, 'assets'))
    writeFileSync(join(dir, 'index.html'), '<html></html>')
    writeFileSync(join(dir, 'assets', 'app.js'), 'console.log(1)')
    expect(scanDir(dir)).toEqual([])
    writeFileSync(join(dir, 'assets', 'app.js.map'), '{}')
    expect(scanDir(dir).join()).toContain('source map shipped')
  })
})
