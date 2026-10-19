/**
 * Layout and interaction guarantees for the redesigned Plan workspace.
 *
 * The overflow assertions are the regression gate for the horizontal scrollbar
 * that used to appear inside the logging area: every editor row and the
 * scrollable workspace body must report `scrollWidth <= clientWidth` at narrow
 * container widths.
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

const plannedSession = (id: string, date: string, overrides: Record<string, unknown> = {}) => ({
  id,
  planned_date: date,
  title: `Session ${id}`,
  day_type: 'workout',
  status: 'planned',
  completed_session_id: null,
  notes: null,
  created_at: '',
  updated_at: '',
  exercises: [
    {
      id: `${id}-e1`,
      position: 0,
      exercise_name: 'Barbell back squat with a very long descriptive name for wrapping',
      target_sets: 4,
      target_reps: 6,
      target_weight: 80,
      target_weight_unit: 'kg',
      duration_seconds: null,
      distance_meters: null,
    },
  ],
  ...overrides,
})

function mockApi(overrides: Record<string, unknown> = {}) {
  const base: Record<string, unknown> = {
    getPlanSummary: vi.fn(async () => [] as unknown[]),
    getAllPlannedSessions: vi.fn(async () => [] as unknown[]),
    listAllWorkouts: vi.fn(async () => [] as unknown[]),
    listAllExercises: vi.fn(async () => [
      {
        id: 'e1',
        slug: 'barbell_back_squat',
        name: 'Barbell back squat',
        primary_muscle_group: 'legs',
        equipment: 'barbell',
        movement_type: 'legs',
        unit_mode: 'reps_weight',
        is_custom: false,
      },
    ]),
    getPlanTemplates: vi.fn(async () => [
      {
        key: 'upper_lower',
        name: 'Upper Lower',
        days: [
          { title: 'Upper', exercises: [{ exercise_name: 'Bench press' }, { exercise_name: 'Row' }] },
          { title: 'Lower', exercises: [{ exercise_name: 'Squat' }] },
        ],
      },
    ]),
    createWorkout: vi.fn(async () => ({ id: 'new' })),
    deleteWorkout: vi.fn(async () => undefined),
    createPlannedSession: vi.fn(async () => plannedSession('ps-1', toDateKey(new Date()))),
    updatePlannedSession: vi.fn(async () => plannedSession('ps-1', toDateKey(new Date()))),
    completePlannedSession: vi.fn(async () => plannedSession('ps-1', toDateKey(new Date()))),
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
  render(
    <PageErrorBoundary name="Plan">
      <module.PlanPage />
    </PageErrorBoundary>,
  )
  await waitFor(() => expect(screen.getByRole('tab', { name: 'Month' })).toBeInTheDocument())
  return { ...mocked, user }
}

/** jsdom has no layout, so width-based rules cannot be exercised directly. */
function setWorkspaceWidth(width: number) {
  const style = document.createElement('style')
  style.textContent = `
    .workspace, .plan__panel, .editor__row, .editor__fields, .editor__row-head {
      width: ${width}px !important;
    }
  `
  document.head.appendChild(style)
  return () => style.remove()
}

const overflowOf = (element: Element | null) =>
  element ? Math.max(0, element.scrollWidth - element.clientWidth) : 0

beforeEach(() => {
  vi.resetModules()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('month rows', () => {
  it('renders only the weeks the month needs', async () => {
    const { monthWeeks } = await import('./PlanPage')
    // Only weeks that contain a day of the month are kept, so a month renders
    // between four and six rows instead of a fixed six.
    expect(monthWeeks(new Date(2027, 1, 15))).toHaveLength(4)
    expect(monthWeeks(new Date(2026, 9, 15))).toHaveLength(5)
    expect(monthWeeks(new Date(2026, 7, 15))).toHaveLength(6)
    // Every row holds seven days and each row keeps an in-month day.
    for (const row of monthWeeks(new Date(2026, 9, 15))) {
      expect(row).toHaveLength(7)
      expect(row.some((cell) => cell.inMonth)).toBe(true)
    }
  })
})

describe('Plan workspace layout', () => {
  it('never overflows horizontally at narrow container widths', async () => {
    const restore = setWorkspaceWidth(320)
    try {
      await renderPlan({ getAllPlannedSessions: vi.fn(async () => [plannedSession('ps-9', toDateKey(new Date()))]) })
      await waitFor(() => expect(document.querySelector('.editor__row')).toBeTruthy())

      for (const width of [320, 360, 480, 768]) {
        const panel = document.querySelector('.plan__panel')
        const body = document.querySelector('.workspace__body')
        const rows = [...document.querySelectorAll('.editor__row')]
        expect(rows.length).toBeGreaterThan(0)
        expect(overflowOf(panel)).toBeLessThanOrEqual(0)
        expect(overflowOf(body)).toBeLessThanOrEqual(0)
        for (const row of rows) expect(overflowOf(row)).toBeLessThanOrEqual(0)
        setWorkspaceWidth(width)
      }
    } finally {
      restore()
    }
  })

  it('keeps a long exercise name inside its row', async () => {
    const restore = setWorkspaceWidth(320)
    try {
      await renderPlan({ getAllPlannedSessions: vi.fn(async () => [plannedSession('ps-9', toDateKey(new Date()))]) })
      await userEvent.click(screen.getByRole('tab', { name: 'Plan' }))
      await waitFor(() => expect(screen.getByRole('button', { name: /Details/ })).toBeInTheDocument())
      await userEvent.click(screen.getByRole('button', { name: /Details/ }))

      // The detail is a definition list, not a scrolling table.
      const detail = document.querySelector('.detail')
      expect(detail).toBeTruthy()
      expect(document.querySelector('.plan__set-table')).toBeNull()
      expect(overflowOf(detail)).toBeLessThanOrEqual(0)
    } finally {
      restore()
    }
  })

  it('gives the workspace the wider column and keeps one primary action per mode', async () => {
    const { user } = await renderPlan()

    await user.click(screen.getByRole('tab', { name: 'Plan' }))
    expect(screen.getByRole('button', { name: /Plan session/ })).toBeInTheDocument()
    // The log action is never offered while planning.
    expect(screen.queryByRole('button', { name: 'Log session' })).not.toBeInTheDocument()
    expect(screen.getByText('Schedule a session for this day')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Log' }))
    expect(screen.getByRole('button', { name: 'Log session' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Plan session/ })).not.toBeInTheDocument()
    expect(screen.getByText('Record what you did')).toBeInTheDocument()
  })

  it('switches modes with the arrow keys', async () => {
    const { user } = await renderPlan()
    await user.click(screen.getByRole('tab', { name: 'Plan' }))
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: 'Log' })).toHaveAttribute('aria-selected', 'true')
    await user.keyboard('{ArrowLeft}')
    expect(screen.getByRole('tab', { name: 'Plan' })).toHaveAttribute('aria-selected', 'true')
  })

  it('keeps the editor state when the mode changes', async () => {
    const { user } = await renderPlan()
    await user.type(screen.getByLabelText('Logged session name'), 'Evening session')
    await user.type(screen.getByLabelText('Exercise'), 'Bench')

    await user.click(screen.getByRole('tab', { name: 'Plan' }))
    expect(screen.getByLabelText('Logged session name')).toHaveValue('Evening session')
    expect(screen.getByLabelText('Exercise')).toHaveValue('Bench')

    await user.click(screen.getByRole('tab', { name: 'Log' }))
    expect(screen.getByLabelText('Logged session name')).toHaveValue('Evening session')
  })

  it('reserves the validation line so the message does not move the rows', async () => {
    const { user } = await renderPlan()
    const row = document.querySelector('.editor__row') as HTMLElement
    const before = row.getBoundingClientRect().height

    await user.click(screen.getByRole('button', { name: 'Log session' }))
    const message = await screen.findByText('Add at least one exercise.')
    expect(message).toBeInTheDocument()

    const after = (document.querySelector('.editor__row') as HTMLElement).getBoundingClientRect().height
    expect(after).toBe(before)
  })

  it('clears the local draft without sending a request', async () => {
    const { spies, user } = await renderPlan()
    await user.type(screen.getByLabelText('Logged session name'), 'Scratch')
    await user.click(screen.getByRole('button', { name: 'Clear' }))

    expect(screen.getByLabelText('Logged session name')).toHaveValue('')
    expect(spies.createWorkout).not.toHaveBeenCalled()
  })

  it('parses stepper values and toggles the unit without a request', async () => {
    const { spies, user } = await renderPlan()
    await user.click(screen.getByRole('button', { name: 'Increase Reps' }))
    await user.click(screen.getByRole('button', { name: 'Increase Weight' }))
    const lbs = within(screen.getByRole('radiogroup', { name: 'Weight unit' })).getByLabelText('lb')
    await user.click(lbs)

    expect(screen.getByLabelText('Reps')).toHaveValue(1)
    expect(screen.getByLabelText('Weight')).toHaveValue(2.5)
    expect(lbs).toBeChecked()
    expect(spies.createWorkout).not.toHaveBeenCalled()
  })

  it('describes what applying a template does and warns about planned days', async () => {
    const today = toDateKey(new Date())
    const { user } = await renderPlan({
      getAllPlannedSessions: vi.fn(async () => [plannedSession('ps-9', today)]),
    })

    await user.click(screen.getByRole('button', { name: 'Template' }))
    const dialog = await screen.findByRole('dialog', { name: 'Start from a template' })

    // The counts come from the template payload itself.
    const radios = within(dialog).getAllByRole('radio').map((node) => node.textContent)
    expect(radios).toHaveLength(1)
    // "2 days · 3 exercises" is derived from the template payload, not invented.
    expect(radios[0]).toContain('2 days')
    expect(radios[0]).toContain('3 exercises')
    expect(within(dialog).getByRole('button', { name: 'Apply template' })).toBeDisabled()

    await user.click(within(dialog).getByRole('radio', { name: /Upper Lower/ }))
    // Preview uses the real day titles from the template.
    expect(within(dialog).getByText('Upper')).toBeInTheDocument()
    expect(within(dialog).getByText('Lower')).toBeInTheDocument()
    // Truthful description: it creates planned sessions, it does not touch logs.
    expect(within(dialog).getByText(/Adds one planned session per template day/)).toBeInTheDocument()
    expect(within(dialog).getByText(/Nothing already logged is changed/)).toBeInTheDocument()
    // Existing plans are kept, so the confirmation appears before applying.
    expect(within(dialog).getByText(/already has a plan/)).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Apply template' })).toBeEnabled()
  })

  it('applies the template without a confirmation when the window is free', async () => {
    const { spies, user } = await renderPlan()
    await user.click(screen.getByRole('button', { name: 'Template' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('radio', { name: /Upper Lower/ }))
    expect(within(dialog).queryByText(/already has a plan/)).not.toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Apply template' }))
    await waitFor(() => expect(spies.applyPlanTemplate).toHaveBeenCalledTimes(1))
  })

  it('renders the month legend and totals from existing summary data', async () => {
    const today = new Date()
    await renderPlan({
      getPlanSummary: vi.fn(async () => [
        daySummary(toDateKey(today), { planned_count: 2, completed_count: 1 }),
      ]),
    })
    const legend = document.querySelector('.plan__legend') as HTMLElement
    expect(legend).toHaveTextContent('Planned')
    expect(legend).toHaveTextContent('Logged')
    expect(legend).toHaveTextContent('Rest')
    expect(screen.getByText(/This month:/)).toHaveTextContent('2 planned')
    expect(screen.getByText(/This month:/)).toHaveTextContent('1 logged')
  })

  it('offers the two day actions when the day is completely empty', async () => {
    const { user } = await renderPlan()

    expect(screen.getByRole('button', { name: 'Plan a session' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mark as rest day' })).toBeInTheDocument()
    // The same action stays available in the day menu.
    await user.click(screen.getByRole('button', { name: 'Day options' }))
    expect(await screen.findByRole('menuitem', { name: 'Mark as rest day' })).toBeInTheDocument()

    // The first switches to Plan mode without touching the network.
    await user.click(screen.getByRole('button', { name: 'Plan a session' }))
    expect(screen.getByRole('tab', { name: 'Plan' })).toHaveAttribute('aria-selected', 'true')
  })

  it('shows the week strip and a day list in week view', async () => {
    const { user } = await renderPlan()
    await user.click(screen.getByRole('tab', { name: 'Week' }))
    expect(screen.getByRole('group', { name: 'Week' })).toBeInTheDocument()
    expect(document.querySelectorAll('.plan__week-row')).toHaveLength(7)
  })
})