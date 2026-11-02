/**
 * Calendar date-state styling and template panel placement.
 *
 * These assertions guard the colour system (normal / outside / today /
 * selected), the activity indicators (planned, logged, both, rest) and the
 * template panel being anchored inside the workspace instead of floating over
 * it, where an ancestor used to clip it.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PageErrorBoundary } from '../components/layout/PageErrorBoundary'
import { toDateKey } from '../utils/dates'

const daySummary = (date: string, overrides: Record<string, unknown> = {}) => ({
  date,
  planned_count: 0,
  completed_count: 0,
  day_type: 'none',
  has_meals: false,
  ...overrides,
})

function mockApi(overrides: Record<string, unknown> = {}) {
  const base: Record<string, unknown> = {
    getPlanSummary: vi.fn(async () => [] as unknown[]),
    getAllPlannedSessions: vi.fn(async () => [] as unknown[]),
    listAllWorkouts: vi.fn(async () => [] as unknown[]),
    listAllExercises: vi.fn(async () => [] as unknown[]),
    getPlanTemplates: vi.fn(async () => [
      {
        key: 'upper_lower',
        name: 'Upper Lower',
        days: [
          { title: 'Upper', exercises: [{ exercise_name: 'Bench press' }] },
          { title: 'Lower', exercises: [{ exercise_name: 'Squat' }] },
        ],
      },
      { key: 'rest_day', name: 'Rest day', days: [{ title: 'Rest', exercises: [] }] },
    ]),
    createWorkout: vi.fn(async () => ({ id: 'new' })),
    deleteWorkout: vi.fn(async () => undefined),
    createPlannedSession: vi.fn(async () => ({}) as unknown),
    updatePlannedSession: vi.fn(async () => ({}) as unknown),
    completePlannedSession: vi.fn(async () => ({}) as unknown),
    deletePlannedSession: vi.fn(async () => undefined),
    applyPlanTemplate: vi.fn(async () => [] as unknown[]),
    ...overrides,
  }
  return { api: base as never, spies: base }
}

async function renderPlan(overrides: Record<string, unknown> = {}) {
  const mocked = mockApi(overrides)
  vi.doMock('../services/api', async () => {
    const actual = await vi.importActual<typeof import('../services/api')>('../services/api')
    return { ...actual, api: mocked.api }
  })
  const module = await import('./PlanPage')
  const user = userEvent.setup()
  const view = render(
    <PageErrorBoundary name="Plan">
      <module.PlanPage />
    </PageErrorBoundary>,
  )
  await waitFor(() => expect(screen.getByRole('tab', { name: 'Month' })).toBeInTheDocument())
  return { ...mocked, user, view }
}

const cellFor = (day: number, monthOffset = 0) => {
  const date = new Date()
  date.setMonth(date.getMonth() + monthOffset)
  const key = toDateKey(new Date(date.getFullYear(), date.getMonth(), day))
  return document.querySelector(`.plan__month-day[data-key="${key}"]`) as HTMLElement | null
}

beforeEach(() => {
  vi.resetModules()
  // Pin "today" to mid-month. The calendar shows neighbouring-month days as
  // outside days, so a real clock near a month boundary made "today" appear in
  // the next month's grid and broke these assertions. Only Date is faked so
  // waitFor and user-event keep using real timers.
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(2026, 9, 15, 12, 0, 0))
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('calendar date states', () => {
  it('keeps today, selected and outside days distinguishable', async () => {
    const today = new Date().getDate()
    const { user } = await renderPlan()

    // Today is selected on first render, so it carries both states.
    const todayCell = cellFor(today)
    expect(todayCell).toHaveClass('plan__month-day--today', 'plan__month-day--selected')

    // A different date becomes selected while today keeps only its own state.
    await user.click(cellFor(today === 1 ? 2 : 1) as HTMLElement)
    expect(cellFor(today)).toHaveClass('plan__month-day--today')
    expect(cellFor(today)).not.toHaveClass('plan__month-day--selected')
    const other = cellFor(today === 1 ? 2 : 1)
    expect(other).toHaveClass('plan__month-day--selected')
    expect(other).not.toHaveClass('plan__month-day--today')

    // Outside days are muted but stay selectable.
    const outside = document.querySelector('.plan__month-day--outside') as HTMLElement
    expect(outside).toBeInstanceOf(HTMLButtonElement)
    expect((outside as HTMLButtonElement).disabled).toBe(false)
  })

  it('renders planned, logged, both and rest indicators from persisted rows', async () => {
    const now = new Date()
    const planned = toDateKey(new Date(now.getFullYear(), now.getMonth(), 5))
    const logged = toDateKey(new Date(now.getFullYear(), now.getMonth(), 6))
    const both = toDateKey(new Date(now.getFullYear(), now.getMonth(), 7))
    const rest = toDateKey(new Date(now.getFullYear(), now.getMonth(), 8))
    await renderPlan({
      getPlanSummary: vi.fn(async () => [
        daySummary(planned, { planned_count: 1 }),
        daySummary(logged, { completed_count: 1 }),
        daySummary(both, { planned_count: 2, completed_count: 1 }),
        daySummary(rest, { day_type: 'rest' }),
      ]),
    })

    const dotsOf = (key: string) =>
      [...(document.querySelector(`.plan__month-day[data-key="${key}"] .plan__cell-dots`)?.children ?? [])].map(
        (child) => child.className.trim(),
      )

    // Planned is outlined, logged is solid, and both appear side by side.
    expect(dotsOf(planned)).toEqual(['plan__cell-dot'])
    expect(dotsOf(logged)).toEqual(['plan__cell-dot plan__cell-dot--filled'])
    expect(dotsOf(both)).toEqual(['plan__cell-dot', 'plan__cell-dot plan__cell-dot--filled'])
    // A rest day uses the neutral dash instead of a colour.
    expect(dotsOf(rest)).toEqual(['plan__cell-rest'])

    // The legend explains the same three indicators.
    const legend = document.querySelector('.plan__legend') as HTMLElement
    expect(within(legend).getByText(/Planned/)).toBeInTheDocument()
    expect(within(legend).getByText(/Logged/)).toBeInTheDocument()
    expect(within(legend).getByText(/Rest/)).toBeInTheDocument()
  })

  it('updates outside days when another month is opened', async () => {
    const { user } = await renderPlan()
    const outsideBefore = [...document.querySelectorAll('.plan__month-day--outside')].map((cell) =>
      cell.getAttribute('data-key'),
    )

    await user.click(screen.getByRole('button', { name: 'Next month' }))
    await waitFor(() =>
      expect(
        [...document.querySelectorAll('.plan__month-day--outside')].map((cell) => cell.getAttribute('data-key')),
      ).not.toEqual(outsideBefore),
    )

    const outsideAfter = [...document.querySelectorAll('.plan__month-day--outside')].map((cell) =>
      cell.getAttribute('data-key'),
    )
    expect(outsideAfter).not.toEqual(outsideBefore)
    // Today is only marked while its own month is open.
    expect(document.querySelector('.plan__month-day--today')).toBeNull()
    // No outside day pretends to be selected.
    expect(document.querySelector('.plan__month-day--outside.plan__month-day--selected')).toBeNull()
  })
})

describe('template panel placement', () => {
  it('anchors the panel to the workspace toolbar, outside the scrolling body', async () => {
    const { user } = await renderPlan()
    await user.click(screen.getByRole('button', { name: 'Template' }))
    const dialog = await screen.findByRole('dialog', { name: 'Start from a template' })

    const anchor = dialog.closest('.workspace__templates')
    expect(anchor).not.toBeNull()
    expect(anchor?.parentElement).toHaveClass('workspace__modes')
    // Inside the scrolling body it would be clipped and scroll with the rows.
    expect(document.querySelector('.workspace__body .templates')).toBeNull()
    expect(dialog.querySelector('.templates__list')).not.toBeNull()
  })

  it('marks the selected template and closes without a request', async () => {
    const { spies, user } = await renderPlan()
    await user.click(screen.getByRole('button', { name: 'Template' }))
    const dialog = await screen.findByRole('dialog', { name: 'Start from a template' })

    const options = within(dialog).getAllByRole('radio')
    expect(options.every((option) => option.getAttribute('aria-checked') === 'false')).toBe(true)

    await user.click(within(dialog).getByRole('radio', { name: /Upper Lower/ }))
    const selectedRow = within(dialog).getByRole('radio', { name: /Upper Lower/ })
    expect(selectedRow).toHaveAttribute('aria-checked', 'true')
    expect(selectedRow.className).toContain('templates__row--active')

    await user.click(within(dialog).getByRole('button', { name: 'Close' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(spies.applyPlanTemplate).not.toHaveBeenCalled()
  })
})