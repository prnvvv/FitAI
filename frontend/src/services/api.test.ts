import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from './api'
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
