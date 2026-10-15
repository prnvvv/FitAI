import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { summarise } from './ProgressPage'

const derived = {
  window: { from: '2026-01-01', to: '2026-10-14' },
  sessions_completed: 0,
  active_days: 0,
  sessions_per_week: 0,
  weekly_sessions: [],
  total_volume_kg: 0,
  personal_records: [],
  current_streak_days: 0,
  longest_streak_days: 0,
  planned_sessions: 0,
  planned_completed: 0,
  planned_completion_rate: null,
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

async function renderProgress(overrides: Record<string, unknown> = {}) {
  const spies: Record<string, unknown> = {
    getProfile: vi.fn(async () => profile),
    weightSeries: vi.fn(async () => [] as unknown[]),
    heightSeries: vi.fn(async () => [] as unknown[]),
    bmiSeries: vi.fn(async () => [] as unknown[]),
    derivedMetrics: vi.fn(async () => derived),
    createMeasurement: vi.fn(async () => ({})),
    deleteMeasurement: vi.fn(async () => undefined),
    ...overrides,
  }
  vi.doMock('../services/api', async () => {
    const actual = await vi.importActual<typeof import('../services/api')>('../services/api')
    return { ...actual, api: spies }
  })
  const module = await import('./ProgressPage')
  const user = userEvent.setup()
  render(
    <MemoryRouter>
      <module.ProgressPage />
    </MemoryRouter>,
  )
  await waitFor(() => expect(screen.getByRole('heading', { name: 'Progress' })).toBeInTheDocument())
  return { spies, user }
}

const measurement = (value: number, date: string) => ({
  id: `m-${date}`,
  type: 'weight',
  value,
  unit: 'kg',
  measured_at: new Date(date).toISOString(),
  notes: null,
  created_at: new Date(date).toISOString(),
})

afterEach(() => {
  vi.resetModules()
  vi.restoreAllMocks()
})

describe('summarise', () => {
  it('handles zero entries', () => {
    expect(summarise([])).toEqual({ latest: null, change: null, rangeLabel: '—', entries: 0 })
  })

  it('shows no change for a single entry', () => {
    expect(summarise([100])).toEqual({ latest: 100, change: null, rangeLabel: '100', entries: 1 })
  })

  it('collapses the range when min equals max', () => {
    expect(summarise([100, 100]).rangeLabel).toBe('100')
  })

  it('computes change across many entries', () => {
    expect(summarise([80, 78, 75])).toEqual({ latest: 75, change: -5, rangeLabel: '75–80', entries: 3 })
  })
})

describe('ProgressPage', () => {
  it('prompts for height when there is none', async () => {
    const { user } = await renderProgress()
    await user.click(screen.getByRole('tab', { name: 'BMI' }))
    expect(await screen.findByText('Add your height to see BMI.')).toBeInTheDocument()
    expect(screen.queryByText(/Healthy range/)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Log height/ }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })

  it('shows the BMI value with a category and disclaimer', async () => {
    await renderProgress({
      heightSeries: vi.fn(async () => [{ ...measurement(175, '2026-01-01'), type: 'height', unit: 'cm' }]),
      bmiSeries: vi.fn(async () => [
        {
          measured_at: new Date('2026-01-05').toISOString(),
          value: 22.9,
          unit: 'bmi',
          source: 'derived',
          weight_kg: 70,
          height_cm: 175,
        },
      ]),
    })

    await userEvent.click(screen.getByRole('tab', { name: 'BMI' }))
    expect(await screen.findByText('22.9')).toBeInTheDocument()
    expect(screen.getByText('Healthy range')).toBeInTheDocument()
    expect(screen.getByText(/rough screening measure/i)).toBeInTheDocument()
  })

  it('hides the category label for users under 18', async () => {
    await renderProgress({
      getProfile: vi.fn(async () => ({ ...profile, age: 16 })),
      heightSeries: vi.fn(async () => [{ ...measurement(160, '2026-01-01'), type: 'height', unit: 'cm' }]),
      bmiSeries: vi.fn(async () => [
        {
          measured_at: new Date('2026-01-05').toISOString(),
          value: 17.2,
          unit: 'bmi',
          source: 'derived',
          weight_kg: 44,
          height_cm: 160,
        },
      ]),
    })

    await userEvent.click(screen.getByRole('tab', { name: 'BMI' }))
    expect(await screen.findByText('17.2')).toBeInTheDocument()
    expect(screen.queryByText('Underweight')).not.toBeInTheDocument()
  })

  it('renders a labelled point for a single entry', async () => {
    await renderProgress({ weightSeries: vi.fn(async () => [measurement(70, '2026-10-01')]) })
    const chart = await screen.findByRole('img', { name: /Weight chart/ })
    expect(chart).toHaveAccessibleName(/One entry: 70.0 kg/)
  })

  it('renders a line and tooltip for several entries', async () => {
    await renderProgress({
      weightSeries: vi.fn(async () => {
        const now = new Date()
        const first = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 10)
        const second = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 2)
        return [
          { ...measurement(80, first.toISOString()), measured_at: first.toISOString() },
          { ...measurement(70, second.toISOString()), measured_at: second.toISOString() },
        ]
      }),
    })
    const chart = await screen.findByRole('img', { name: /Weight chart/ })
    expect(chart).toHaveAccessibleName(/2 entries from 80.0 to 70.0 kg/)
    expect(await screen.findByText('View as table')).toBeInTheDocument()
  })

  it('shows an empty state with no entries', async () => {
    await renderProgress()
    expect(await screen.findByText(/No weight entries yet/i)).toBeInTheDocument()
  })

  it('validates the log sheet before sending', async () => {
    const { spies, user } = await renderProgress()
    await user.click(screen.getByRole('button', { name: 'Log' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('Enter at least one measurement.')).toBeInTheDocument()
    expect(spies.createMeasurement).not.toHaveBeenCalled()
  })

  it('logs weight and height together with inline range errors', async () => {
    const { spies, user } = await renderProgress()
    await user.click(screen.getByRole('button', { name: 'Log' }))

    await user.type(screen.getByLabelText('Weight'), '5')
    await user.type(screen.getByLabelText('Height'), '175')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText(/Weight must be between 20 and 500 kg/)).toBeInTheDocument()

    await user.clear(screen.getByLabelText('Weight'))
    await user.type(screen.getByLabelText('Weight'), '70')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(spies.createMeasurement).toHaveBeenCalledTimes(2))
    const calls = (spies.createMeasurement as ReturnType<typeof vi.fn>).mock.calls.map((call) => call[0])
    expect(calls.map((call) => call.type).sort()).toEqual(['height', 'weight'])
  })

  it('toggles units for display', async () => {
    const { user } = await renderProgress({ weightSeries: vi.fn(async () => [measurement(70, '2026-10-01')]) })
    await user.click(screen.getByRole('button', { name: 'Toggle units' }))
    await waitFor(() => expect(screen.getAllByText(/lb/).length).toBeGreaterThan(0))
  })
})
