import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, validationIssues } from './api'
import type { Page, WorkoutSession } from '../types'

vi.mock('./supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
    },
  },
}))

describe('ApiError', () => {
  it('stores status and body and shows human copy', () => {
    const err = new ApiError(404, 'Not found')
    expect(err.status).toBe(404)
    expect(err.body).toBe('Not found')
    expect(err.message).toBe("We couldn't find that.")
  })

  it('never leaks raw JSON to the user', () => {
    const body = JSON.stringify({ error: { code: 'INTERNAL_ERROR', message: 'boom' } })
    const err = new ApiError(500, body)
    expect(err.message).not.toContain('{')
    expect(err.message).toBe('Something went wrong on our side. Please try again.')
  })

  it('maps each failure class to a distinct message', () => {
    expect(new ApiError(401, '').message).toMatch(/session has expired/)
    expect(new ApiError(403, '').message).toMatch(/don't have access/)
    expect(new ApiError(422, JSON.stringify({ detail: [{ loc: ['body', 'value'], msg: 'too small' }] })).message).toBe(
      'too small',
    )
    expect(new ApiError(413, '').message).toMatch(/too large/)
    expect(new ApiError(415, '').message).toMatch(/not supported/)
  })

  it('extracts field-level validation issues', () => {
    const err = new ApiError(
      422,
      JSON.stringify({
        detail: [
          { loc: ['body', 'value'], msg: 'weight must be between 20 and 500 kg.' },
          { loc: ['body', 'unit'], msg: 'wrong unit' },
        ],
      }),
    )
    expect(validationIssues(err)).toEqual([
      { field: 'value', message: 'weight must be between 20 and 500 kg.' },
      { field: 'unit', message: 'wrong unit' },
    ])
  })
})

describe('listAllWorkouts', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('pages through workouts without exceeding the backend limit', async () => {
    const sessions: WorkoutSession[] = Array.from({ length: 150 }, (_, i) => ({
      id: `ws-${i}`,
      name: `Session ${i}`,
      performed_at: '2026-01-01T00:00:00Z',
      duration_minutes: 60,
      notes: null,
      created_at: '',
      updated_at: '',
      sets: [],
    }))
    const firstPage: Page<WorkoutSession> = {
      items: sessions.slice(0, 100),
      total: 150,
      limit: 100,
      offset: 0,
    }
    const secondPage: Page<WorkoutSession> = {
      items: sessions.slice(100),
      total: 150,
      limit: 100,
      offset: 100,
    }

    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify(firstPage), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(secondPage), { status: 200 }))

    const all = await api.listAllWorkouts()

    expect(all).toHaveLength(150)
    expect(fetchSpy).toHaveBeenCalledTimes(2)
    expect(fetchSpy).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining('/workouts?limit=100&offset=0'),
      expect.any(Object),
    )
    expect(fetchSpy).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining('/workouts?limit=100&offset=100'),
      expect.any(Object),
    )
  })
})
