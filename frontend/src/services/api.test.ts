import { describe, expect, it, vi } from 'vitest'
import { ApiError } from './api'

vi.mock('./supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
    },
  },
}))

describe('ApiError', () => {
  it('stores status and body', () => {
    const err = new ApiError(404, 'Not found')
    expect(err.status).toBe(404)
    expect(err.body).toBe('Not found')
    expect(err.message).toContain('404')
  })
})
