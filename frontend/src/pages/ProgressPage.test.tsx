import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { restoreChartWidth, stubChartWidth } from '../test/chartGeometry'
import { toDateKey } from '../utils/dates'
import { summarise } from '../components/progress/metrics'

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
  stubChartWidth()
  const spies: Record<string, unknown> = {
    getProfile: vi.fn(async () => profile),
    weightSeries: vi.fn(async () => [] as unknown[]),
    heightSeries: vi.fn(async () => [] as unknown[]),
    bmiSeries: vi.fn(async () => [] as unknown[]),
    derivedMetrics: vi.fn(async () => derived),
    createMeasurement: vi.fn(async () => ({})),
    deleteMeasurement: vi.fn(async () => undefined),
    metricSeries: vi.fn(async () => [] as unknown[]),
    ...overrides,
  }
  vi.doMock('../services/api', async () => {
    const actual = await vi.importActual<typeof import('../services/api')>('../services/api')
    return { ...actual, api: spies }
  })
  const module = await import('./ProgressPage')
  const user = userEvent.setup()
  render(<module.ProgressPage />)
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

const daysAgo = (days: number) => {
  const date = new Date()
  date.setDate(date.getDate() - days)
  return date
}

const statCell = (label: string) => screen.getByText(label).closest('.stat') as HTMLElement

beforeEach(() => {
  stubChartWidth()
})

afterEach(() => {
  restoreChartWidth()
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
    await renderProgress({ weightSeries: vi.fn(async () => [measurement(70, daysAgo(1).toISOString())]) })
    const chart = await screen.findByRole('img', { name: /Weight chart/ })
    expect(chart).toHaveAccessibleName(/One entry: 70.0 kg/)
    expect(screen.getByText('Log one more weight entry to see a trend.')).toBeInTheDocument()
  })

  it('renders a line with gridlines for several entries', async () => {
    await renderProgress({
      weightSeries: vi.fn(async () => [
        { ...measurement(80, daysAgo(10).toISOString()), measured_at: daysAgo(10).toISOString() },
        { ...measurement(75, daysAgo(6).toISOString()), measured_at: daysAgo(6).toISOString() },
        { ...measurement(70, daysAgo(2).toISOString()), measured_at: daysAgo(2).toISOString() },
      ]),
    })
    const chart = await screen.findByRole('img', { name: /Weight chart/ })
    expect(chart).toHaveAccessibleName(/3 entries from 80.0 to 70.0 kg/)
    expect(document.querySelectorAll('.chart__grid')).toHaveLength(4)
  })

  it('shows an empty state with no entries', async () => {
    await renderProgress()
    expect(await screen.findByText('No weight entries in this range.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Log weight' })).toBeInTheDocument()
  })

  it('validates the log dialog before sending', async () => {
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
    expect(screen.getByLabelText('Weight')).toHaveAttribute('aria-invalid', 'true')

    await user.clear(screen.getByLabelText('Weight'))
    await user.type(screen.getByLabelText('Weight'), '70')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(spies.createMeasurement).toHaveBeenCalledTimes(2))
    const calls = (spies.createMeasurement as ReturnType<typeof vi.fn>).mock.calls.map((call) => call[0])
    expect(calls.map((call) => call.type).sort()).toEqual(['height', 'weight'])
  })

  it('toggles units for display', async () => {
    const { user } = await renderProgress({ weightSeries: vi.fn(async () => [measurement(70, daysAgo(1).toISOString())]) })
    // Two responsive copies exist (header on desktop, toolbar below 768px);
    // CSS hides whichever does not apply.
    await user.click(screen.getAllByRole('button', { name: 'Toggle units' })[0])
    await waitFor(() => expect(screen.getAllByText(/lb/).length).toBeGreaterThan(0))
  })

  it('moves between metric chips with the arrow keys', async () => {
    const { user } = await renderProgress()
    const weight = screen.getByRole('tab', { name: 'Weight' })
    weight.focus()
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: 'Height' })).toHaveAttribute('aria-selected', 'true')
    await user.keyboard('{ArrowLeft}')
    expect(screen.getByRole('tab', { name: 'Weight' })).toHaveAttribute('aria-selected', 'true')
  })

  it('filters by range from the chart toolbar', async () => {
    await renderProgress({
      weightSeries: vi.fn(async () => [
        measurement(70, daysAgo(60).toISOString()),
        measurement(71, daysAgo(1).toISOString()),
      ]),
    })
    expect(statCell('Latest')).toHaveTextContent('71.0 kg')
    await userEvent.click(screen.getByRole('tab', { name: '7D' }))
    expect(statCell('Entries')).toHaveTextContent('1')
    expect(screen.getByText('Last 7 days')).toBeInTheDocument()
  })

  it('swaps the chart for the table without changing the data', async () => {
    await renderProgress({
      weightSeries: vi.fn(async () => [measurement(70, daysAgo(1).toISOString()), measurement(71, daysAgo(2).toISOString())]),
    })
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Table view' }))
    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('row')).toHaveLength(3)
    expect(within(table).getByText('70.0 kg')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Chart view' }))
    expect(screen.getByRole('img', { name: /Weight chart/ })).toBeInTheDocument()
  })

  it('shows Change as a dash and Range as one value for a single entry', async () => {
    await renderProgress({ weightSeries: vi.fn(async () => [measurement(70, daysAgo(1).toISOString())]) })
    const stat = statCell
    expect(stat('Change')).toHaveTextContent('—')
    expect(stat('Range')).toHaveTextContent('70.0 kg')
    expect(stat('Entries')).toHaveTextContent('1')
  })

  it('shows the min–max range across many entries', async () => {
    await renderProgress({
      weightSeries: vi.fn(async () => [
        measurement(80, daysAgo(20).toISOString()),
        measurement(75, daysAgo(10).toISOString()),
        measurement(70, daysAgo(1).toISOString()),
      ]),
    })
    const range = statCell('Range')
    expect(range).toHaveTextContent('70.0–80.0 kg')
  })

  it('lists only the metrics missing from the add-metric menu', async () => {
    const { user } = await renderProgress()
    await user.click(screen.getByRole('button', { name: 'Log' }))
    await user.click(screen.getByRole('button', { name: 'Add metric' }))
    const menu = await screen.findByRole('menu')
    expect(within(menu).getAllByRole('menuitem').map((item) => item.textContent)).toEqual([
      'Body fat',
      'Waist',
      'Sleep',
      'Steps',
    ])

    await user.click(within(menu).getByRole('menuitem', { name: 'Steps' }))
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove Steps' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Add metric' }))
    const reopened = await screen.findByRole('menu')
    expect(within(reopened).queryByRole('menuitem', { name: 'Steps' })).not.toBeInTheDocument()
    expect(within(reopened).queryByRole('menuitem', { name: 'BMI' })).not.toBeInTheDocument()
  })

  it('removes an added row without touching the default rows', async () => {
    const { user } = await renderProgress()
    await user.click(screen.getByRole('button', { name: 'Log' }))
    await user.click(screen.getByRole('button', { name: 'Add metric' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Waist' }))
    await user.click(screen.getByRole('button', { name: 'Remove Waist' }))
    expect(screen.queryByLabelText('Waist')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Weight')).toBeInTheDocument()
    expect(screen.getByLabelText('Height')).toBeInTheDocument()
  })

  it('switches the unit of a metric row from kg to lb', async () => {
    const { spies, user } = await renderProgress()
    await user.click(screen.getByRole('button', { name: 'Log' }))
    const weightUnits = screen.getByRole('group', { name: 'Weight unit' })
    await user.click(within(weightUnits).getByRole('button', { name: 'lb' }))
    await user.type(screen.getByLabelText('Weight'), '154')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(spies.createMeasurement).toHaveBeenCalledTimes(1))
    expect((spies.createMeasurement as ReturnType<typeof vi.fn>).mock.calls[0][0]).toMatchObject({
      type: 'weight',
      unit: 'kg',
    })
  })

  it('asks before discarding a dirty form and keeps the values when editing', async () => {
    const { user } = await renderProgress()
    await user.click(screen.getByRole('button', { name: 'Log' }))
    await user.type(screen.getByLabelText('Weight'), '70')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(await screen.findByText('Discard changes?')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Keep editing' }))
    expect(screen.getByLabelText('Weight')).toHaveValue('70')

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await user.click(await screen.findByRole('button', { name: 'Discard' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('closes on Escape when the form is pristine', async () => {
    const { user } = await renderProgress()
    await user.click(screen.getByRole('button', { name: 'Log' }))
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('keeps the dialog and the values when saving fails, and retries', async () => {
    const { spies, user } = await renderProgress({
      createMeasurement: vi.fn(async () => {
        throw new Error('boom')
      }),
    })
    await user.click(screen.getByRole('button', { name: 'Log' }))
    await user.type(screen.getByLabelText('Weight'), '70')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/boom/)
    expect(screen.getByLabelText('Weight')).toHaveValue('70')

    await user.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(spies.createMeasurement).toHaveBeenCalledTimes(2))
  })

  it('deletes a history entry through the row button', async () => {
    const { spies, user } = await renderProgress({
      weightSeries: vi.fn(async () => [measurement(70, daysAgo(1).toISOString())]),
    })
    await user.click(await screen.findByRole('button', { name: 'Delete entry' }))
    await waitFor(() => expect(spies.deleteMeasurement).toHaveBeenCalledTimes(1))
  })
  it('loads a metric without a dedicated endpoint on demand and charts it', async () => {
    const steps = [7000, 9000, 11000].map((value, index) => ({
      ...measurement(value, daysAgo(index + 1).toISOString()),
      type: 'steps',
      unit: 'steps',
    }))
    const { spies, user } = await renderProgress({ metricSeries: vi.fn(async () => steps) })

    await user.click(screen.getByRole('tab', { name: 'Steps' }))
    expect(await screen.findByRole('img', { name: /Steps chart/ })).toBeInTheDocument()
    expect(spies.metricSeries).toHaveBeenCalledWith('steps')
    // Daily bars for a daily total.
    expect(document.querySelectorAll('.chart__bar')).toHaveLength(3)
    // Derived from the recorded days only, never from missing calendar days.
    expect(screen.getByText(/average per recorded day/i).parentElement).toHaveTextContent('9,000')
  })

  it('explains a single height reading instead of drawing a trend', async () => {
    const { user } = await renderProgress({
      heightSeries: vi.fn(async () => [
        { ...measurement(180, daysAgo(2).toISOString()), type: 'height', unit: 'cm' },
      ]),
    })
    await user.click(screen.getByRole('tab', { name: 'Height' }))
    expect(await screen.findByRole('img', { name: /Height chart/ })).toBeInTheDocument()
    expect(screen.getByText(/Height changes rarely/)).toBeInTheDocument()
    expect(document.querySelectorAll('.chart__line')).toHaveLength(0)
  })

  it('draws height readings as discrete points even with several entries', async () => {
    await renderProgress({
      heightSeries: vi.fn(async () => [
        { ...measurement(181, daysAgo(40).toISOString()), type: 'height', unit: 'cm' },
        { ...measurement(180, daysAgo(20).toISOString()), type: 'height', unit: 'cm' },
        { ...measurement(180, daysAgo(3).toISOString()), type: 'height', unit: 'cm' },
      ]),
    })
    await userEvent.click(screen.getByRole('tab', { name: 'Height' }))
    await screen.findByRole('img', { name: /Height chart/ })
    expect(document.querySelectorAll('.chart__marker')).toHaveLength(2)
    expect(document.querySelectorAll('.chart__line')).toHaveLength(0)
  })

  it('reports the change since the previous entry and the range average', async () => {
    await renderProgress({
      weightSeries: vi.fn(async () => [
        measurement(80, daysAgo(10).toISOString()),
        measurement(76, daysAgo(5).toISOString()),
        measurement(75, daysAgo(1).toISOString()),
      ]),
    })
    const insight = await screen.findByText(/Since the previous entry/)
    expect(insight.parentElement).toHaveTextContent('Since the previous entry -1.0 kg')
    expect(insight.parentElement).toHaveTextContent('Average 77.0 kg')
  })

  it('groups sleep nights into weekly averages', async () => {
    const nights = [7, 8, 6].map((value, index) => ({
      ...measurement(value, daysAgo(index + 1).toISOString()),
      type: 'sleep_hours',
      unit: 'h',
    }))
    await renderProgress({ metricSeries: vi.fn(async () => nights) })
    await userEvent.click(screen.getByRole('tab', { name: 'Sleep' }))
    expect(await screen.findByText(/average per recorded night/i)).toBeInTheDocument()
    expect(screen.getByText(/nights recorded/)).toBeInTheDocument()
    expect(screen.getByText(/Latest week/)).toBeInTheDocument()
  })

  it('asks the training summary for the active range', async () => {
    const { spies, user } = await renderProgress()
    await waitFor(() => expect(spies.derivedMetrics).toHaveBeenCalledTimes(1))
    const today = toDateKey(new Date())
    const from = new Date()
    from.setDate(from.getDate() - 30)
    expect(spies.derivedMetrics).toHaveBeenCalledWith({ from: toDateKey(from), to: today })

    await user.click(screen.getByRole('tab', { name: '7D' }))
    await waitFor(() => expect(spies.derivedMetrics).toHaveBeenCalledTimes(2))
    expect(screen.getByText('Last 7 days')).toBeInTheDocument()
  })

  it('shows the planned-versus-completed counts behind the percentage', async () => {
    await renderProgress({
      derivedMetrics: vi.fn(async () => ({ ...derived, planned_sessions: 8, planned_completed: 2, planned_completion_rate: 0.25 })),
    })
    expect(await screen.findByText('2 of 8')).toBeInTheDocument()
    expect(screen.getByText('25%')).toBeInTheDocument()
  })

  it('keeps the history list on the raw entries while the chart uses recorded days', async () => {
    const first = daysAgo(3)
    const second = daysAgo(1)
    await renderProgress({
      metricSeries: vi.fn(async () => [
        { ...measurement(4000, first.toISOString()), type: 'steps', unit: 'steps' },
        { ...measurement(6000, second.toISOString()), type: 'steps', unit: 'steps' },
        { ...measurement(2000, second.toISOString()), type: 'steps', unit: 'steps' },
      ]),
    })
    await userEvent.click(screen.getByRole('tab', { name: 'Steps' }))
    await screen.findByRole('img', { name: /Steps chart/ })
    // Two recorded days collapse into two bars; the history keeps all three rows.
    expect(document.querySelectorAll('.chart__bar')).toHaveLength(2)
    expect(screen.getAllByRole('button', { name: 'Delete entry' })).toHaveLength(3)
  })
})
