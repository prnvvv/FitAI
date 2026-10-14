/**
 * Network baseline for the Plan page redesign (frontend only).
 *
 * These tests pin the exact API calls the current UI makes for each user
 * scenario: method surrogate (api client fn), arguments (bodies), and call
 * counts. The redesign must keep every one of these identical — same
 * endpoints, same payload fields/values, same number of writes.
 *
 * Interaction steps follow the CURRENT DOM. If the redesign moves a control
 * (e.g. template picker into a popover), only the steps change; the body and
 * call-count assertions below are the baseline and must not change.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PageErrorBoundary } from '../components/layout/PageErrorBoundary'
import { startOfWeek, toDateKey } from '../utils/dates'

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

function mockApi(overrides: Record<string, unknown> = {}) {
  const today = new Date()
  const todayKey = toDateKey(today)
  const base: Record<string, unknown> = {
    getPlanSummary: vi.fn(async () => [daySummary(todayKey)]),
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
  return { api: base as never, spies: base, todayKey }
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

type Spy = ReturnType<typeof vi.fn>
const callsOf = (spies: Record<string, unknown>, name: string) => (spies[name] as Spy).mock.calls
const spiesOf = (spies: Record<string, unknown>): Spy[] =>
  Object.values(spies).map((spy) => spy as Spy)
const totalCalls = (spies: Record<string, unknown>) =>
  spiesOf(spies).reduce((n, spy) => n + spy.mock.calls.length, 0)

const WRITE_FNS = [
  'createWorkout',
  'deleteWorkout',
  'createPlannedSession',
  'updatePlannedSession',
  'completePlannedSession',
  'deletePlannedSession',
  'applyPlanTemplate',
] as const
const writeCalls = (spies: Record<string, unknown>) =>
  WRITE_FNS.reduce((n, name) => n + callsOf(spies, name).length, 0)

describe('PlanPage network baseline', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('selecting a day fires zero requests', async () => {
    const { spies, user } = await renderPlan()
    const grid = screen.getByRole('grid')
    const before = totalCalls(spies)

    await user.click(within(grid).getAllByRole('gridcell')[10])

    await waitFor(() => expect(screen.getByText(/Nothing logged for this day yet/)).toBeInTheDocument())
    expect(totalCalls(spies)).toBe(before)
  })

  it('switching views and navigating fires reads only, with the same ranges', async () => {
    const { spies, user, todayKey } = await renderPlan()
    expect(writeCalls(spies)).toBe(0)

    await user.click(screen.getByRole('tab', { name: 'Week' }))
    await waitFor(() => expect(screen.getByRole('group', { name: 'Week' })).toBeInTheDocument())

    const monday = startOfWeek(new Date())
    const from = toDateKey(monday)
    const to = toDateKey(new Date(monday.getTime() + 6 * 24 * 60 * 60 * 1000))
    expect(callsOf(spies, 'getPlanSummary')).toContainEqual([from, to, expect.anything()])
    expect(writeCalls(spies)).toBe(0)

    await user.click(screen.getByRole('button', { name: 'Next week' }))
    await waitFor(() => {
      expect(callsOf(spies, 'getPlanSummary').length).toBeGreaterThanOrEqual(3)
    })
    expect(writeCalls(spies)).toBe(0)
    expect(todayKey).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })

  it('planning a session posts the exact body once', async () => {
    const { spies, user, todayKey } = await renderPlan()

    await user.click(await screen.findByRole('tab', { name: 'Plan' }))
    await user.click(await screen.findByRole('button', { name: /Plan session/ }))

    await waitFor(() => expect(callsOf(spies, 'createPlannedSession').length).toBe(1))
    expect(callsOf(spies, 'createPlannedSession')[0][0]).toEqual({
      planned_date: todayKey,
      title: null,
      day_type: 'workout',
      notes: null,
      exercises: [],
    })
  })

  it('marking a rest day posts the exact body once', async () => {
    const { spies, user, todayKey } = await renderPlan()

    await user.click(await screen.findByRole('button', { name: 'Day options' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Mark as rest day' }))

    await waitFor(() => expect(callsOf(spies, 'createPlannedSession').length).toBe(1))
    expect(callsOf(spies, 'createPlannedSession')[0][0]).toEqual({
      planned_date: todayKey,
      title: 'Rest',
      day_type: 'rest',
      notes: null,
      exercises: [],
    })
  })

  it('unmarking a rest day deletes that planned session once', async () => {
    const todayKey = toDateKey(new Date())
    const { spies, user } = await renderPlan({
      getPlanSummary: vi.fn(async () => [daySummary(todayKey, { planned_count: 1, day_type: 'rest' })]),
      getAllPlannedSessions: vi.fn(async () => [
        plannedSession('ps-rest', todayKey, { title: 'Rest', day_type: 'rest' }),
      ]),
    })

    expect(screen.queryByRole('button', { name: 'Mark as rest day' })).not.toBeInTheDocument()
    await screen.findByDisplayValue('Rest')
    await user.click(await screen.findByRole('button', { name: 'Day options' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Unmark rest day' }))

    await waitFor(() => expect(callsOf(spies, 'deletePlannedSession').length).toBe(1))
    expect(callsOf(spies, 'deletePlannedSession')[0]).toEqual(['ps-rest'])
  })

  it('logging a session with two exercises posts the exact body once', async () => {
    const { spies, user, todayKey } = await renderPlan()

    await user.click(screen.getByRole('button', { name: /Add exercise/ }))
    const inputs = screen.getAllByLabelText('Exercise')
    expect(inputs).toHaveLength(2)
    await user.type(inputs[0], 'Squat')
    await user.type(inputs[1], 'Bench')
    await user.click(screen.getAllByLabelText('Increase Reps')[0])
    await user.click(screen.getByRole('button', { name: 'Log session' }))

    await waitFor(() => expect(callsOf(spies, 'createWorkout').length).toBe(1))
    expect(callsOf(spies, 'createWorkout')[0][0]).toEqual({
      name: null,
      performed_at: new Date(`${todayKey}T10:00:00`).toISOString(),
      sets: [
        { exercise_name: 'Squat', reps: 1, weight: null, weight_unit: null },
        { exercise_name: 'Bench', reps: null, weight: null, weight_unit: null },
      ],
    })
  })

  it('a double click on Log session sends exactly one request', async () => {
    let resolveCreate: (value: unknown) => void = () => {}
    const { spies, user } = await renderPlan({
      createWorkout: vi.fn(
        () =>
          new Promise((resolve) => {
            resolveCreate = resolve
          }).then(() => ({ id: 'new' })),
      ),
    })

    await user.type(screen.getByLabelText('Exercise'), 'Squat')
    const pending = user.dblClick(screen.getByRole('button', { name: 'Log session' }))
    await waitFor(() => expect(callsOf(spies, 'createWorkout').length).toBe(1))
    resolveCreate(undefined)
    await pending
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(callsOf(spies, 'createWorkout').length).toBe(1)
  })

  it('applying a template posts the key and start date once', async () => {
    const { spies, user, todayKey } = await renderPlan()

    await user.click(await screen.findByRole('button', { name: 'Day options' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Start from a template…' }))
    const select = screen.getByLabelText('Template') as HTMLSelectElement
    await user.selectOptions(select, 'upper_lower')
    await user.click(screen.getByRole('button', { name: 'Apply' }))

    await waitFor(() => expect(callsOf(spies, 'applyPlanTemplate').length).toBe(1))
    expect(callsOf(spies, 'applyPlanTemplate')[0]).toEqual(['upper_lower', todayKey])
  })

  it('deleting a logged session with undo writes delete once then create once', async () => {
    const { spies, user } = await renderPlan()

    await user.click(screen.getByRole('button', { name: 'Delete hjkfb' }))
    await waitFor(() => expect(callsOf(spies, 'deleteWorkout').length).toBe(1))
    expect(callsOf(spies, 'deleteWorkout')[0]).toEqual(['ws-1'])

    await user.click(await screen.findByRole('button', { name: 'Undo' }))
    await waitFor(() => expect(callsOf(spies, 'createWorkout').length).toBe(1))
    const restore = callsOf(spies, 'createWorkout')[0][0]
    expect(restore.name).toBe('hjkfb')
    expect(restore.sets).toHaveLength(1)
    expect(restore.sets[0].exercise_name).toBe('slknlc')
    expect(restore.sets[0].reps).toBe(3)
  })
})
