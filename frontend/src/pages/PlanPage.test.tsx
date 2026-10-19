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

const rangeSummary = (from: string, to: string) => [daySummary(from), daySummary(to)]

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
  exercises: [],
  ...overrides,
})

const workoutSession = (id: string, performedAt: string, name: string | null, exercise = 'slknlc') => ({
  id,
  name,
  performed_at: performedAt,
  duration_minutes: null,
  notes: null,
  created_at: '',
  sets: [
    {
      id: `${id}-s1`,
      position: 0,
      exercise_name: exercise,
      reps: 3,
      weight: null,
      weight_unit: null,
      duration_seconds: null,
      distance_meters: null,
      notes: null,
    },
  ],
})

/** The default fake: an empty library, empty plan, one logged session today. */
function mockApi(overrides: Record<string, unknown> = {}) {
  const calls: string[] = []
  const today = new Date()
  const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(
    today.getDate(),
  ).padStart(2, '0')}`
  const base: Record<string, unknown> = {
    getPlanSummary: vi.fn(async (from: string, to: string) => {
      calls.push(`summary:${from}:${to}`)
      return rangeSummary(from, to)
    }),
    getAllPlannedSessions: vi.fn(async () => [] as unknown[]),
    listAllWorkouts: vi.fn(async () => [workoutSession('ws-1', new Date().toISOString(), 'hjkfb')]),
    listAllExercises: vi.fn(async () => [] as unknown[]),
    getPlanTemplates: vi.fn(async () => [{ key: 'upper_lower', name: 'Upper Lower', days: [] }]),
    createWorkout: vi.fn(async () => ({ id: 'new' })),
    deleteWorkout: vi.fn(async () => undefined),
    createPlannedSession: vi.fn(async () => plannedSession('ps-1', todayKey)),
    updatePlannedSession: vi.fn(async () => ({ id: 'ps-1' })),
    completePlannedSession: vi.fn(async () => ({ id: 'ps-1' })),
    deletePlannedSession: vi.fn(async () => undefined),
    applyPlanTemplate: vi.fn(async () => [] as unknown[]),
    ...overrides,
  }
  return { api: base as never, calls, spies: base, todayKey }
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

describe('PlanPage', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('switches between week, month and year views', async () => {
    const { user } = await renderPlan()

    expect(screen.getByRole('grid')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Week' }))
    expect(screen.queryByRole('grid')).not.toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Week' })).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Year' }))
    expect(screen.getByText(new Date().getFullYear())).toBeInTheDocument()
    expect(screen.getByText(/active days/)).toBeInTheDocument()
  })

  it('renders week, month and year with empty data', async () => {
    const { user } = await renderPlan({
      listAllWorkouts: vi.fn(async () => [] as unknown[]),
      getPlanSummary: vi.fn(async () => [] as unknown[]),
      getAllPlannedSessions: vi.fn(async () => [] as unknown[]),
    })

    expect(screen.getByText('No plan')).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Plan' }))
    expect(screen.getByRole('button', { name: /Plan session/ })).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Log' }))
    expect(screen.getByText('Nothing logged yet.')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Week' }))
    expect(screen.getByRole('group', { name: 'Week' })).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Year' }))
    expect(screen.getByText(/active days/)).toBeInTheDocument()
  })

  it('requests the summary once per view change', async () => {
    const { spies, user } = await renderPlan()
    const before = (spies.getPlanSummary as ReturnType<typeof vi.fn>).mock.calls.length

    await user.click(screen.getByRole('tab', { name: 'Year' }))
    await waitFor(() =>
      expect((spies.getPlanSummary as ReturnType<typeof vi.fn>).mock.calls.length).toBe(before + 1),
    )
  })

  it('renders planned sessions returned through the paged endpoint', async () => {
    const todayKey = toDateKey(new Date())
    const { user } = await renderPlan({
      getAllPlannedSessions: vi.fn(async () => [plannedSession('ps-9', todayKey)]),
    })

    await user.click(screen.getByRole('tab', { name: 'Plan' }))
    expect(screen.getByDisplayValue('Session ps-9')).toBeInTheDocument()
  })

  it('shows existing logged sessions for the selected day', async () => {
    await renderPlan()
    expect(screen.getByText('hjkfb')).toBeInTheDocument()
    // Exercise appears in the collapsed-row summary and in the set detail.
    expect(screen.getAllByText(/slknlc/)).toHaveLength(2)
  })

  it('logs a session with an exercise chosen from the library', async () => {
    const { spies, user } = await renderPlan({
      listAllExercises: vi.fn(async () => [
        {
          id: 'e1',
          slug: 'barbell_back_squat',
          name: 'Barbell Back Squat',
          primary_muscle_group: 'legs',
          equipment: 'barbell',
          movement_type: 'legs',
          unit_mode: 'reps_weight',
          is_custom: false,
        },
      ]),
    })

    const input = screen.getByLabelText('Exercise')
    await user.type(input, 'squat')
    await user.click(await screen.findByRole('option', { name: /Barbell Back Squat/ }))
    await user.click(screen.getByLabelText('Increase Reps'))
    await user.click(screen.getByRole('button', { name: 'Log session' }))

    await waitFor(() => expect(spies.createWorkout).toHaveBeenCalled())
    const payload = (spies.createWorkout as ReturnType<typeof vi.fn>).mock.calls[0][0]
    expect(payload.sets[0].exercise_name).toBe('Barbell Back Squat')
    expect(payload.sets[0].reps).toBe(1)
  })

  it('keeps what the user types in a planned session title', async () => {
    const todayKey = toDateKey(new Date())
    const { user } = await renderPlan({
      getAllPlannedSessions: vi.fn(async () => [plannedSession('ps-9', todayKey, { title: 'Push' })]),
    })

    await user.click(screen.getByRole('tab', { name: 'Plan' }))
    const input = screen.getByDisplayValue('Push')
    await user.clear(input)
    await user.type(input, 'Push day')

    expect((input as HTMLInputElement).value).toBe('Push day')
  })

  it('supports keyboard navigation in the month grid', async () => {
    const { user } = await renderPlan()
    const focusedDay = document.querySelector('.plan__month-day[tabindex="0"]') as HTMLElement
    expect(focusedDay).toBeTruthy()
    focusedDay.focus()

    const before = focusedDay.getAttribute('aria-label')
    await user.keyboard('{ArrowRight}')

    await waitFor(() => {
      const next = document.querySelector('.plan__month-day--selected')
      expect(next?.getAttribute('aria-label')).not.toBe(before)
    })
  })

  it('keeps exactly one tabbable cell after paging to another month', async () => {
    const { user } = await renderPlan()
    const grid = screen.getByRole('grid')
    within(grid)

    const focused = document.querySelector('.plan__month-day[tabindex="0"]') as HTMLElement
    focused.focus()
    await user.keyboard('{PageDown}')

    await waitFor(() => {
      const tabbable = document.querySelectorAll('.plan__month-day[tabindex="0"]')
      expect(tabbable.length).toBe(1)
    })
  })

  it('ignores a stale response when views are switched quickly', async () => {
    let resolveSlow: (value: unknown) => void = () => {}
    const slow = new Promise((resolve) => {
      resolveSlow = resolve
    })
    let call = 0
    const { user } = await renderPlan({
      getPlanSummary: vi.fn(async (from: string, to: string) => {
        call += 1
        if (call === 1) {
          await slow
          return rangeSummary(from, to)
        }
        return [daySummary(to, { planned_count: 3, day_type: 'workout' })]
      }),
    })

    await user.click(screen.getByRole('tab', { name: 'Week' }))
    await waitFor(() => expect(call).toBeGreaterThan(1))
    resolveSlow(rangeSummary('2000-01-01', '2000-01-07'))

    await waitFor(() => expect(screen.getByRole('tab', { name: 'Week' })).toHaveAttribute('aria-selected', 'true'))
    expect(screen.queryByText(/2000/)).not.toBeInTheDocument()
  })

  it('shows a loading skeleton before the first response arrives', async () => {
    let resolve: (value: unknown) => void = () => {}
    vi.doMock('../services/api', async () => {
      const actual = await vi.importActual<typeof import('../services/api')>('../services/api')
      return {
        ...actual,
        api: {
          ...(mockApi().api as Record<string, unknown>),
          getPlanSummary: vi.fn(
            () =>
              new Promise((r) => {
                resolve = r
              }),
          ),
          getAllPlannedSessions: vi.fn(() => new Promise((r) => setTimeout(() => r([]), 0))),
          listAllWorkouts: vi.fn(() => new Promise((r) => setTimeout(() => r([]), 0))),
        } as never,
      }
    })
    const module = await import('./PlanPage')
    render(<module.PlanPage />)

    expect(await screen.findByRole('status')).toHaveTextContent(/loading your month plan/i)

    resolve(rangeSummary(toDateKey(new Date()), toDateKey(new Date())))
  })

  it('survives a malformed or empty plan response without crashing', async () => {
    await renderPlan({
      getPlanSummary: vi.fn(async () => null as unknown),
      getAllPlannedSessions: vi.fn(async () => ({ items: null }) as unknown),
      listAllWorkouts: vi.fn(async () => undefined as unknown),
    })

    expect(screen.queryByText(/couldn't be displayed/i)).not.toBeInTheDocument()
    expect(screen.getByRole('grid')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Month' })).toBeInTheDocument()
  })

  it('offers a retry when loading fails and recovers afterwards', async () => {
    let failing = true
    const { user } = await renderPlan({
      getPlanSummary: vi.fn(async (from: string, to: string) => {
        if (failing) throw new Error('The plan could not be loaded.')
        return rangeSummary(from, to)
      }),
    })

    const alert = await screen.findAllByRole('alert')
    expect(alert[0]).toHaveTextContent(/could not be loaded/i)

    failing = false
    await user.click(within(alert[0]).getByRole('button', { name: 'Retry' }))

    await waitFor(() => expect(screen.queryByText(/could not be loaded/i)).not.toBeInTheDocument())
  })

  it('shows a rest day only when the day was explicitly set to rest', async () => {
    const todayKey = toDateKey(new Date())
    const { user } = await renderPlan({
      getPlanSummary: vi.fn(async () => [
        daySummary(todayKey, { planned_count: 1, day_type: 'rest' }),
      ]),
      getAllPlannedSessions: vi.fn(async () => [
        plannedSession('ps-rest', todayKey, { title: 'Rest', day_type: 'rest' }),
      ]),
    })

    expect(document.querySelector('.plan__badge--type')).toHaveTextContent('rest')
    await user.click(screen.getByRole('button', { name: 'Day options' }))
    expect(screen.queryByRole('menuitem', { name: 'Mark as rest day' })).not.toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Unmark rest day' })).toBeInTheDocument()
  })

  it('plans and logs a session and keeps it after a refresh', async () => {
    let planned: unknown[] = []
    const { user, spies } = await renderPlan({
      getAllPlannedSessions: vi.fn(async () => planned),
      createPlannedSession: vi.fn(async (payload: { planned_date: string }) => {
        planned = [plannedSession('ps-new', payload.planned_date, { title: 'Leg day' })]
        return planned[0]
      }),
    })

    await user.click(screen.getByRole('tab', { name: 'Plan' }))
    await user.click(screen.getByRole('button', { name: /Plan session/ }))
    await waitFor(() => expect(spies.createPlannedSession).toHaveBeenCalled())

    expect(screen.getByDisplayValue('Leg day')).toBeInTheDocument()
  })
})

describe('PlanPage redesign', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders only as many week rows as the month needs', async () => {
    const module = await import('./PlanPage')
    expect(module.monthWeeks(new Date(2021, 1, 1))).toHaveLength(4)
    expect(module.monthWeeks(new Date(2026, 9, 1))).toHaveLength(5)
    expect(module.monthWeeks(new Date(2026, 7, 1))).toHaveLength(6)
  })

  it('renders one grid row per needed week for the current month', async () => {
    const module = await import('./PlanPage')
    await renderPlan()
    const grid = screen.getByRole('grid')
    expect(within(grid).getAllByRole('row')).toHaveLength(
      module.monthWeeks(new Date()).length,
    )
  })

  it('styles outside-month cells like in-month cells', async () => {
    await renderPlan()
    const cells = Array.from(document.querySelectorAll('.plan__month-day'))
    expect(cells.length).toBeGreaterThan(0)
    expect(document.querySelectorAll('.plan__month-day--blank').length).toBe(0)
    const outside = Array.from(document.querySelectorAll('.plan__month-day--outside'))
    expect(outside.length).toBeGreaterThan(0)
    for (const cell of outside) {
      expect(cell.tagName).toBe('BUTTON')
    }
  })

  it('moves to the week edges with Home and End and selects with Space', async () => {
    const { startOfWeek, addDays } = await import('../utils/dates')
    const { user } = await renderPlan()
    const focused = document.querySelector('.plan__month-day[tabindex="0"]') as HTMLElement
    focused.focus()

    const monday = startOfWeek(new Date())
    await user.keyboard('{End}')
    await waitFor(() => {
      const selected = document.querySelector('.plan__month-day--selected .plan__month-date')
      expect(selected?.textContent).toBe(String(addDays(monday, 6).getDate()))
    })

    await user.keyboard('{Home}')
    await waitFor(() => {
      const selected = document.querySelector('.plan__month-day--selected .plan__month-date')
      expect(selected?.textContent).toBe(String(monday.getDate()))
    })

    const current = document.querySelector('.plan__month-day[tabindex="0"]') as HTMLElement
    const label = current.getAttribute('aria-label')
    current.focus()
    await user.keyboard(' ')
    await waitFor(() => {
      expect(
        document.querySelector('.plan__month-day--selected')?.getAttribute('aria-label'),
      ).toBe(label)
    })
  })

  it('defaults to Log for today and Plan for future days', async () => {
    const { user } = await renderPlan()
    expect(screen.getByRole('tab', { name: 'Log' })).toHaveAttribute('aria-selected', 'true')

    const cells = within(screen.getByRole('grid')).getAllByRole('gridcell')
    await user.click(cells[cells.length - 1])
    expect(screen.getByRole('tab', { name: 'Plan' })).toHaveAttribute('aria-selected', 'true')
  })

  it('keeps typed form text across tab switches', async () => {
    const { user } = await renderPlan()
    const nameInput = screen.getByLabelText('Logged session name')
    await user.type(nameInput, 'Evening lift')

    await user.click(screen.getByRole('tab', { name: 'Plan' }))
    const titleInput = screen.getByLabelText('Session title')
    await user.type(titleInput, 'Push day')

    await user.click(screen.getByRole('tab', { name: 'Log' }))
    expect((screen.getByLabelText('Logged session name') as HTMLInputElement).value).toBe(
      'Evening lift',
    )
    await user.click(screen.getByRole('tab', { name: 'Plan' }))
    expect((screen.getByLabelText('Session title') as HTMLInputElement).value).toBe('Push day')
  })

  it('opens the template popover from the day menu', async () => {
    const { user } = await renderPlan()
    await user.click(screen.getByRole('button', { name: 'Day options' }))
    await user.click(screen.getByRole('menuitem', { name: 'Start from a template…' }))

    expect(screen.getByRole('dialog', { name: 'Start from a template' })).toBeInTheDocument()
    expect(screen.getByLabelText('Template')).toBeInTheDocument()
    expect(screen.getByLabelText('Template start date')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Apply template' })).toBeInTheDocument()
  })

  it('sends one request for a double-clicked Plan session', async () => {
    const todayKey = toDateKey(new Date())
    let resolveCreate: (value: unknown) => void = () => {}
    const { spies, user } = await renderPlan({
      createPlannedSession: vi.fn(
        () =>
          new Promise((resolve) => {
            resolveCreate = resolve
          }).then(() => plannedSession('ps-1', todayKey)),
      ),
    })
    await user.click(screen.getByRole('tab', { name: 'Plan' }))
    const pending = user.dblClick(screen.getByRole('button', { name: /Plan session/ }))
    await waitFor(() =>
      expect((spies.createPlannedSession as ReturnType<typeof vi.fn>).mock.calls.length).toBe(1),
    )
    resolveCreate(undefined)
    await pending
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect((spies.createPlannedSession as ReturnType<typeof vi.fn>).mock.calls.length).toBe(1)
  })

  it('opens the day drawer from the year view and closes it with Escape', async () => {
    const { user } = await renderPlan()
    await user.click(screen.getByRole('tab', { name: 'Year' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    await user.click(document.querySelector('.plan__year-day') as HTMLElement)
    expect(screen.getByRole('dialog', { name: 'Day details' })).toBeInTheDocument()

    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('opens the month view from a year month title', async () => {
    const { user } = await renderPlan()
    await user.click(screen.getByRole('tab', { name: 'Year' }))
    await user.click(document.querySelector('.plan__year-month-title') as HTMLElement)

    expect(screen.getByRole('tab', { name: 'Month' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('grid')).toBeInTheDocument()
  })
})

describe('PlanPage day labelling', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('labels an unplanned day "No plan" and an explicit rest day "rest"', async () => {
    const module = await import('./PlanPage')
    const days = [
      { date: '2026-10-14', planned_count: 0, completed_count: 0, day_type: 'none', has_meals: false },
      { date: '2026-10-15', planned_count: 1, completed_count: 0, day_type: 'rest', has_meals: false },
      {
        date: '2026-10-16',
        planned_count: 1,
        completed_count: 0,
        day_type: 'active_recovery',
        has_meals: false,
      },
    ]
    expect(module.dayTypeLabel(days[0])).toBe('No plan')
    expect(module.dayTypeLabel(days[1])).toBe('rest')
    expect(module.dayTypeLabel(days[2])).toBe('active recovery')
    expect(module.dayTypeLabel(undefined)).toBe('No plan')
  })

  it('covers week, month and year with plain local date ranges', async () => {
    const module = await import('./PlanPage')
    const anchor = new Date(2026, 9, 14) // 14 Oct 2026, a Wednesday, local

    const week = module.visibleRange('week', anchor)
    expect(week).toEqual({ from: '2026-10-12', to: '2026-10-18' }) // Monday-first

    const month = module.visibleRange('month', anchor)
    expect(month.from).toBe('2026-09-28') // six Monday-first rows
    expect(month.to).toBe('2026-11-08')

    expect(module.visibleRange('year', anchor)).toEqual({
      from: '2026-01-01',
      to: '2026-12-31',
    })
  })
})