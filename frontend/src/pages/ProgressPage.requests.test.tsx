/**
 * Network baseline for the Progress page redesign (frontend only).
 *
 * These tests pin the exact API calls the page makes for each scenario:
 * client fn (== HTTP method + path), bodies and call counts. The redesign may
 * move controls around (inline log panel -> dialog, table disclosure ->
 * toggle) but every call below must stay byte-identical.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { toDateKey } from '../utils/dates'

const derived = {
  window: { from: '2026-01-01', to: '2026-10-14' },
  sessions_completed: 3,
  active_days: 3,
  sessions_per_week: 1.5,
  weekly_sessions: [],
  total_volume_kg: 1234.5,
  personal_records: [],
  current_streak_days: 2,
  longest_streak_days: 5,
  planned_sessions: 4,
  planned_completed: 1,
  planned_completion_rate: 0.25,
  source: 'derived',
}

const profile = {
  id: 'p',
  user_id: 'u',
  created_at: '',
  updated_at: '',
  preferences: { units: 'metric' as const },
  age: 30,
}

const measurement = (value: number, date: string, type = 'weight', unit = 'kg') => ({
  id: `m-${type}-${date}`,
  type,
  value,
  unit,
  measured_at: new Date(date).toISOString(),
  notes: null,
  created_at: new Date(date).toISOString(),
})

const READ_FNS = ['getProfile', 'weightSeries', 'heightSeries', 'bmiSeries', 'derivedMetrics'] as const

function mockApi(overrides: Record<string, unknown> = {}) {
  const base: Record<string, unknown> = {
    getProfile: vi.fn(async () => profile),
    weightSeries: vi.fn(async () => [] as unknown[]),
    heightSeries: vi.fn(async () => [] as unknown[]),
    bmiSeries: vi.fn(async () => [] as unknown[]),
    derivedMetrics: vi.fn(async () => derived),
    createMeasurement: vi.fn(async () => ({})),
    deleteMeasurement: vi.fn(async () => undefined),
    ...overrides,
  }
  return { api: base as never, spies: base }
}

async function renderProgress(overrides: Record<string, unknown> = {}) {
  const mocked = mockApi(overrides)
  vi.doMock('../services/api', async () => {
    const actual = await vi.importActual<typeof import('../services/api')>('../services/api')
    return { ...actual, api: mocked.api }
  })
  const module = await import('./ProgressPage')
  const user = userEvent.setup()
  render(<module.ProgressPage />)
  await waitFor(() => expect(screen.getByRole('heading', { name: 'Progress' })).toBeInTheDocument())
  return { ...mocked, user }
}

type Spy = ReturnType<typeof vi.fn>
const callsOf = (spies: Record<string, unknown>, name: string) => (spies[name] as Spy).mock.calls
const readCalls = (spies: Record<string, unknown>) =>
  READ_FNS.reduce((n, name) => n + callsOf(spies, name).length, 0)
const writeCalls = (spies: Record<string, unknown>) =>
  callsOf(spies, 'createMeasurement').length + callsOf(spies, 'deleteMeasurement').length

const twoDaysAgo = () => {
  const date = new Date()
  date.setDate(date.getDate() - 2)
  date.setHours(8, 0, 0, 0)
  return date.toISOString()
}

describe('ProgressPage network baseline', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('loads the page with exactly five reads and no writes', async () => {
    const { spies } = await renderProgress()
    await waitFor(() => expect(readCalls(spies)).toBe(5))
    for (const name of READ_FNS) expect(callsOf(spies, name)).toHaveLength(1)
    expect(writeCalls(spies)).toBe(0)
  })

  it('switching metric or range, or toggling units, fires no requests', async () => {
    const { spies, user } = await renderProgress({ weightSeries: vi.fn(async () => [measurement(70, '2026-10-01')]) })
    const before = readCalls(spies)

    for (const name of ['Height', 'Body fat', 'Waist', 'Sleep', 'Steps', 'BMI', 'Weight']) {
      await user.click(screen.getByRole('tab', { name }))
    }
    for (const name of ['7D', '90D', '1Y', 'All', '30D']) {
      await user.click(screen.getByRole('tab', { name }))
    }
    await user.click(screen.getByRole('button', { name: 'Toggle units' }))
    await user.click(screen.getByRole('button', { name: 'Toggle units' }))

    expect(readCalls(spies)).toBe(before)
    expect(writeCalls(spies)).toBe(0)
  })

  it('saving a weight and a height posts two exact bodies, then re-reads once', async () => {
    const { spies, user } = await renderProgress()

    await user.click(screen.getByRole('button', { name: 'Log' }))
    await user.type(screen.getByLabelText('Weight'), '70')
    await user.type(screen.getByLabelText('Height'), '175')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(callsOf(spies, 'createMeasurement')).toHaveLength(2))
    const today = toDateKey(new Date())
    expect(callsOf(spies, 'createMeasurement').map((call) => call[0])).toEqual([
      {
        type: 'weight',
        value: 70,
        unit: 'kg',
        measured_at: new Date(`${today}T08:00:00`).toISOString(),
        notes: undefined,
      },
      {
        type: 'height',
        value: 175,
        unit: 'cm',
        measured_at: new Date(`${today}T08:00:00`).toISOString(),
        notes: undefined,
      },
    ])
    await waitFor(() => expect(readCalls(spies)).toBe(10))
    expect(callsOf(spies, 'weightSeries')).toHaveLength(2)
  })

  it('deleting a history entry writes one delete, then re-reads once', async () => {
    const { spies, user } = await renderProgress({ weightSeries: vi.fn(async () => [measurement(70, '2026-10-01')]) })
    await user.click(await screen.findByRole('button', { name: 'Delete entry' }))

    await waitFor(() => expect(callsOf(spies, 'deleteMeasurement')).toHaveLength(1))
    expect(callsOf(spies, 'deleteMeasurement')[0]).toEqual(['m-weight-2026-10-01'])
    await waitFor(() => expect(readCalls(spies)).toBe(10))
  })

  it('a double click on Save sends exactly one request set', async () => {
    let resolveCreate: (value: unknown) => void = () => {}
    const { spies, user } = await renderProgress({
      createMeasurement: vi.fn(
        () =>
          new Promise((resolve) => {
            resolveCreate = resolve
          }).then(() => ({})),
      ),
    })

    await user.click(screen.getByRole('button', { name: 'Log' }))
    await user.type(screen.getByLabelText('Weight'), '70')
    const pending = user.dblClick(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(callsOf(spies, 'createMeasurement')).toHaveLength(1))
    resolveCreate(undefined)
    await pending
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(callsOf(spies, 'createMeasurement')).toHaveLength(1)
  })

  it('opening the log form sends no requests', async () => {
    const { spies, user } = await renderProgress()
    const before = readCalls(spies)
    await user.click(screen.getByRole('button', { name: 'Log' }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(readCalls(spies)).toBe(before)
    expect(writeCalls(spies)).toBe(0)
  })

  it('the derived training payload is loaded once and never re-fetched per range', async () => {
    const { spies, user } = await renderProgress()
    for (const name of ['7D', '1Y', 'All']) {
      await user.click(screen.getByRole('tab', { name }))
    }
    expect(callsOf(spies, 'derivedMetrics')).toHaveLength(1)
  })

  it('saves a note exactly as typed and keeps the two-day-ago entry untouched', async () => {
    const { spies, user } = await renderProgress()
    await user.click(screen.getByRole('button', { name: 'Log' }))
    await user.type(screen.getByLabelText('Note (optional)'), 'post gym')
    await user.type(screen.getByLabelText('Weight'), '70')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(callsOf(spies, 'createMeasurement')).toHaveLength(1))
    const today = toDateKey(new Date())
    expect(callsOf(spies, 'createMeasurement')[0][0]).toEqual({
      type: 'weight',
      value: 70,
      unit: 'kg',
      measured_at: new Date(`${today}T08:00:00`).toISOString(),
      notes: 'post gym',
    })
    expect(twoDaysAgo()).toMatch(/Z$/)
  })
})