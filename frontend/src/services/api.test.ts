import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  api,
  ApiError,
  isAbortError,
  normalizeDaySummaries,
  normalizePlannedSessions,
  normalizeWorkoutSessions,
  TimeoutError,
  validationIssues,
} from './api'
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

describe('request timeout', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('aborts and reports a timeout instead of hanging forever', async () => {
    vi.useFakeTimers()
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      (_input, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          )
        }),
    )

    try {
      const file = new File(['data'], 'plan.txt', { type: 'text/plain' })
      const settled = api.uploadDocument(file).catch((err: unknown) => err)
      await vi.advanceTimersByTimeAsync(30_000)
      await expect(settled).resolves.toBeInstanceOf(TimeoutError)
    } finally {
      vi.useRealTimers()
    }
  })

  it('passes an abort signal so the request can be cancelled', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 }))

    await api.listDocuments()

    const init = fetchSpy.mock.calls[0][1] as RequestInit
    expect(init.signal).toBeInstanceOf(AbortSignal)
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

describe('plan response normalization', () => {
  it('unwraps the Page envelope returned by /plan/sessions', async () => {
    const page = {
      items: [
        {
          id: 'ps-1',
          planned_date: '2026-10-14',
          title: 'Push',
          day_type: 'workout',
          status: 'planned',
          completed_session_id: null,
          notes: null,
          created_at: '',
          updated_at: '',
          exercises: [],
        },
      ],
      total: 1,
      limit: 100,
      offset: 0,
    }
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(page), { status: 200 }),
    )

    const sessions = await api.getAllPlannedSessions('2026-10-12', '2026-10-18')

    expect(sessions).toHaveLength(1)
    expect(sessions[0].planned_date).toBe('2026-10-14')
  })

  it('returns an empty list for a null or malformed envelope', () => {
    expect(normalizePlannedSessions(null)).toEqual([])
    expect(normalizePlannedSessions({ items: null })).toEqual([])
    expect(normalizePlannedSessions([{ id: 1 }])).toEqual([])
    expect(normalizePlannedSessions({ items: [{ id: 'a', planned_date: '2026-01-01' }] })).toEqual([
      { id: 'a', planned_date: '2026-01-01', exercises: [] },
    ])
    expect(normalizeDaySummaries(null)).toEqual([])
    expect(normalizeDaySummaries([{ date: '2026-10-14' }])).toEqual([
      { date: '2026-10-14', planned_count: 0, completed_count: 0, day_type: 'none', has_meals: false },
    ])
    expect(normalizeWorkoutSessions(undefined)).toEqual([])
  })

  it('recognises an aborted request', () => {
    const abort = new DOMException('aborted', 'AbortError')
    expect(isAbortError(abort)).toBe(true)
    expect(isAbortError(new Error('boom'))).toBe(false)
  })
})
