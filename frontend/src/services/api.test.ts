import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, TimeoutError } from './api'
import type { Page, WorkoutSession } from '../types'

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
