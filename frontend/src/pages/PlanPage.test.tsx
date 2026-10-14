import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const summary = (from: string, to: string) =>
  Array.from({ length: 2 }, (_, index) => ({
    date: index === 0 ? from : to,
    planned_count: index === 0 ? 1 : 0,
    completed_count: index === 0 ? 1 : 0,
    day_type: index === 0 ? 'workout' : 'rest',
    has_meals: false,
  }))

function mockApi(overrides: Record<string, unknown> = {}) {
  const calls: string[] = []
  const base: Record<string, unknown> = {
    getPlanSummary: vi.fn(async (from: string, to: string) => {
      calls.push(`summary:${from}:${to}`)
      return summary(from, to)
    }),
    getPlanWeek: vi.fn(async () => [] as unknown[]),
    listAllWorkouts: vi.fn(async () => [
      {
        id: 'ws-1',
        name: 'hjkfb',
        performed_at: new Date().toISOString(),
        duration_minutes: null,
        notes: null,
        created_at: '',
        sets: [
          {
            id: 's1',
            position: 0,
            exercise_name: 'slknlc',
            reps: 3,
            weight: null,
            weight_unit: null,
            duration_seconds: null,
            distance_meters: null,
            notes: null,
          },
        ],
      },
    ]),
    listAllExercises: vi.fn(async () => [] as unknown[]),
    getPlanTemplates: vi.fn(async () => [
      { key: 'upper_lower', name: 'Upper Lower', days: [] },
    ]),
    createWorkout: vi.fn(async () => ({ id: 'new' })),
    deleteWorkout: vi.fn(async () => undefined),
    createPlannedSession: vi.fn(async () => ({ id: 'ps-1' })),
    updatePlannedSession: vi.fn(async () => ({ id: 'ps-1' })),
    completePlannedSession: vi.fn(async () => ({ id: 'ps-1' })),
    deletePlannedSession: vi.fn(async () => undefined),
    applyPlanTemplate: vi.fn(async () => [] as unknown[]),
    retryDocument: vi.fn(),
    ...overrides,
  }
  return { api: base as never, calls, spies: base }
}

describe('PlanPage', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  async function renderPlan(overrides: Record<string, unknown> = {}) {
    const mocked = mockApi(overrides)
    vi.doMock('../services/api', async () => {
      const actual = await vi.importActual<typeof import('../services/api')>('../services/api')
      return { ...actual, api: mocked.api }
    })
    const module = await import('./PlanPage')
    const user = userEvent.setup()
    render(<module.PlanPage />)
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Month' })).toBeInTheDocument())
    return { ...mocked, user }
  }

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

  it('requests the summary once per view change', async () => {
    const { spies, user } = await renderPlan()
    const before = (spies.getPlanSummary as ReturnType<typeof vi.fn>).mock.calls.length

    await user.click(screen.getByRole('tab', { name: 'Year' }))
    await waitFor(() =>
      expect((spies.getPlanSummary as ReturnType<typeof vi.fn>).mock.calls.length).toBe(before + 1),
    )
  })

  it('shows existing logged sessions for the selected day', async () => {
    await renderPlan()
    expect(screen.getByText('hjkfb')).toBeInTheDocument()
    expect(screen.getByText('slknlc')).toBeInTheDocument()
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

  it('keeps errors dismissible and calm', async () => {
    const { user } = await renderPlan({
      getPlanSummary: vi.fn(async () => {
        throw new Error('The plan could not be loaded.')
      }),
    })

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/could not be loaded/i)
    await user.click(screen.getByLabelText('Dismiss'))
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
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
})
