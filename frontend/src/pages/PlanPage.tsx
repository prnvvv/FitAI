import {
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Dumbbell,
  LayoutTemplate,
  Loader2,
  Minus,
  Plus,
  Trash2,
  Undo2,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ExerciseCombobox } from '../components/plan/ExerciseCombobox'
import { api, toMessage } from '../services/api'
import type { DaySummary, Exercise, PlannedSession, Template, WorkoutSession } from '../types'
import {
  addDays,
  addMonths,
  formatDayLabel,
  formatMonthTitle,
  formatWeekTitle,
  monthGrid,
  startOfMonth,
  startOfWeek,
  toDateKey,
  weekDays,
  yearMonths,
} from '../utils/dates'

type View = 'week' | 'month' | 'year'

const VIEWS: { value: View; label: string }[] = [
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
  { value: 'year', label: 'Year' },
]

const WEEKDAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const DAY_TYPES = ['workout', 'rest', 'active_recovery']

interface LoggedSet {
  exercise_name: string
  reps: number | ''
  weight: number | ''
  weight_unit: 'kg' | 'lb'
}

function emptyLoggedSet(): LoggedSet {
  return { exercise_name: '', reps: '', weight: '', weight_unit: 'kg' }
}

/** Visible range for the current view; one request covers every view. */
function visibleRange(view: View, anchor: Date): { from: string; to: string } {
  if (view === 'week') {
    const days = weekDays(anchor)
    return { from: toDateKey(days[0]), to: toDateKey(days[6]) }
  }
  if (view === 'month') {
    const cells = monthGrid(anchor)
    return { from: cells[0].key, to: cells[cells.length - 1].key }
  }
  return { from: toDateKey(new Date(anchor.getFullYear(), 0, 1)), to: toDateKey(new Date(anchor.getFullYear(), 11, 31)) }
}

function shift(view: View, anchor: Date, direction: -1 | 1): Date {
  if (view === 'week') return addDays(startOfWeek(anchor), 7 * direction)
  if (view === 'month') return addMonths(startOfMonth(anchor), direction)
  return new Date(anchor.getFullYear() + direction, 0, 1)
}

function periodTitle(view: View, anchor: Date): string {
  if (view === 'week') return formatWeekTitle(anchor)
  if (view === 'month') return formatMonthTitle(anchor)
  return String(anchor.getFullYear())
}

function localDayKey(iso: string): string {
  const date = new Date(iso)
  return toDateKey(new Date(date.getFullYear(), date.getMonth(), date.getDate()))
}

export function PlanPage() {
  const today = useMemo(() => toDateKey(new Date()), [])
  const [view, setView] = useState<View>('month')
  const [anchor, setAnchor] = useState(() => new Date())
  const [selected, setSelected] = useState(today)
  const [focused, setFocused] = useState(today)

  const [summary, setSummary] = useState<DaySummary[]>([])
  const [planned, setPlanned] = useState<PlannedSession[]>([])
  const [workouts, setWorkouts] = useState<WorkoutSession[]>([])
  const [library, setLibrary] = useState<Exercise[]>([])
  const [templates, setTemplates] = useState<Template[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [savedAt, setSavedAt] = useState<number | null>(null)
  const [undo, setUndo] = useState<{ message: string; restore: () => void } | null>(null)

  const [loggedName, setLoggedName] = useState('')
  const [loggedSets, setLoggedSets] = useState<LoggedSet[]>([emptyLoggedSet()])
  const [savingSession, setSavingSession] = useState(false)
  const [logError, setLogError] = useState<string | null>(null)

  const [templateKey, setTemplateKey] = useState('')
  const [templateDate, setTemplateDate] = useState(today)
  const [applyingTemplate, setApplyingTemplate] = useState(false)
  const [markingRest, setMarkingRest] = useState(false)

  const [planTitle, setPlanTitle] = useState('')
  const [planDayType, setPlanDayType] = useState('workout')
  const [planNotes, setPlanNotes] = useState('')
  const saveTimer = useRef<number | null>(null)

  const summaryByDate = useMemo(() => {
    const map: Record<string, DaySummary> = {}
    for (const day of summary) map[day.date] = day
    return map
  }, [summary])

  const loggedByDate = useMemo(() => {
    const map: Record<string, WorkoutSession[]> = {}
    for (const session of workouts) {
      const key = localDayKey(session.performed_at)
      map[key] = [...(map[key] ?? []), session]
    }
    return map
  }, [workouts])

  const recentExercises = useMemo(() => {
    const names = workouts.flatMap((session) => session.sets.map((set) => set.exercise_name))
    const seen = new Set<string>()
    const result: Exercise[] = []
    for (const name of names) {
      if (seen.has(name)) continue
      seen.add(name)
      const match = library.find((exercise) => exercise.name === name)
      if (match) result.push(match)
    }
    return result.slice(0, 5)
  }, [library, workouts])

  const loadRange = useCallback(async (nextView: View, nextAnchor: Date) => {
    const { from, to } = visibleRange(nextView, nextAnchor)
    try {
      const [days, sessions] = await Promise.all([
        api.getPlanSummary(from, to),
        api.getPlanWeek(from, to),
      ])
      setSummary(days)
      setPlanned(sessions)
    } catch (err) {
      setError(toMessage(err, 'The plan could not be loaded.'))
    }
  }, [])

  const loadWorkouts = useCallback(async () => {
    try {
      setWorkouts(await api.listAllWorkouts())
    } catch (err) {
      setError(toMessage(err, 'Your logged sessions could not be loaded.'))
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    void (async () => {
      await Promise.all([loadRange(view, anchor), loadWorkouts()])
      try {
        const [exercises, templateList] = await Promise.all([
          api.listAllExercises(),
          api.getPlanTemplates(),
        ])
        if (!cancelled) {
          setLibrary(exercises)
          setTemplates(templateList)
        }
      } catch {
        // The exercise picker falls back to free text; templates are optional.
      }
      if (!cancelled) setLoading(false)
    })()
    return () => {
      cancelled = true
    }
  }, [anchor, loadRange, loadWorkouts, view])

  useEffect(() => {
    setTemplateDate(selected)
    setPlanTitle('')
    setPlanDayType('workout')
    setPlanNotes('')
  }, [selected])

  useEffect(() => () => {
    if (saveTimer.current) window.clearTimeout(saveTimer.current)
  }, [])

  const selectedPlanned = useMemo(
    () => planned.filter((session) => session.planned_date === selected),
    [planned, selected],
  )
  const selectedLogged = loggedByDate[selected] ?? []
  const daySummary = summaryByDate[selected]

  const moveFocus = (key: string) => {
    setFocused(key)
    setSelected(key)
  }

  const handleGridKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const deltas: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }
    if (event.key in deltas) {
      event.preventDefault()
      moveFocus(toDateKey(addDays(new Date(`${focused}T00:00:00`), deltas[event.key])))
      return
    }
    if (event.key === 'PageUp' || event.key === 'PageDown') {
      event.preventDefault()
      const direction = event.key === 'PageUp' ? -1 : 1
      const next = view === 'year' ? new Date(anchor.getFullYear() + direction, 0, 1) : shift(view, anchor, direction)
      setAnchor(next)
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      setSelected(focused)
    }
  }

  const addLibraryExercise = (exercise: Exercise) => {
    setLibrary((prev) => (prev.some((item) => item.id === exercise.id) ? prev : [...prev, exercise]))
  }

  const handleLogSession = async () => {
    const sets = loggedSets
      .filter((set) => set.exercise_name.trim())
      .map((set) => ({
        exercise_name: set.exercise_name.trim(),
        reps: set.reps === '' ? null : Number(set.reps),
        weight: set.weight === '' ? null : Number(set.weight),
        weight_unit: set.weight === '' ? null : set.weight_unit,
      }))
    if (sets.length === 0) {
      setLogError('Add at least one exercise.')
      return
    }
    const performedAt = new Date(`${selected}T10:00:00`)
    setSavingSession(true)
    setLogError(null)
    try {
      await api.createWorkout({
        name: loggedName.trim() || null,
        performed_at: performedAt.toISOString(),
        sets,
      })
      setLoggedName('')
      setLoggedSets([emptyLoggedSet()])
      await loadWorkouts()
      await loadRange(view, anchor)
    } catch (err) {
      setLogError(toMessage(err, 'That session could not be saved.'))
    } finally {
      setSavingSession(false)
    }
  }

  const handleDeleteWorkout = async (session: WorkoutSession) => {
    const snapshot = session
    try {
      await api.deleteWorkout(session.id)
      setWorkouts((prev) => prev.filter((item) => item.id !== session.id))
      setUndo({
        message: 'Session deleted.',
        restore: () => {
          void api
            .createWorkout({
              name: snapshot.name,
              performed_at: snapshot.performed_at,
              notes: snapshot.notes,
              sets: snapshot.sets.map((set) => ({
                exercise_name: set.exercise_name,
                reps: set.reps,
                weight: set.weight,
                weight_unit: set.weight_unit,
                duration_seconds: set.duration_seconds,
                distance_meters: set.distance_meters,
              })),
            })
            .then(loadWorkouts)
        },
      })
      await loadRange(view, anchor)
    } catch (err) {
      setError(toMessage(err, 'That session could not be deleted.'))
    }
  }

  const createPlan = async () => {
    setError(null)
    try {
      await api.createPlannedSession({
        planned_date: selected,
        title: planTitle.trim() || null,
        day_type: planDayType,
        notes: planNotes.trim() || null,
        exercises: [],
      })
      await loadRange(view, anchor)
    } catch (err) {
      setError(toMessage(err, 'The session could not be planned.'))
    }
  }

  const scheduleAutosave = (session: PlannedSession, patch: Partial<PlannedSession>) => {
    if (saveTimer.current) window.clearTimeout(saveTimer.current)
    saveTimer.current = window.setTimeout(async () => {
      try {
        await api.updatePlannedSession(session.id, patch)
        setSavedAt(Date.now())
        await loadRange(view, anchor)
      } catch (err) {
        setError(toMessage(err, 'Your changes could not be saved.'))
      }
    }, 600)
  }

  const completeSession = async (session: PlannedSession) => {
    try {
      await api.completePlannedSession(session.id)
      await loadRange(view, anchor)
      await loadWorkouts()
    } catch (err) {
      setError(toMessage(err, 'That session could not be completed.'))
    }
  }

  const deletePlanned = async (session: PlannedSession) => {
    try {
      await api.deletePlannedSession(session.id)
      setUndo({ message: 'Planned session removed.', restore: () => void loadRange(view, anchor) })
      await loadRange(view, anchor)
    } catch (err) {
      setError(toMessage(err, 'That session could not be removed.'))
    }
  }

  const applyTemplate = async () => {
    if (!templateKey) return
    setApplyingTemplate(true)
    try {
      await api.applyPlanTemplate(templateKey, templateDate)
      setTemplateKey('')
      await loadRange(view, anchor)
    } catch (err) {
      setError(toMessage(err, 'That template could not be applied.'))
    } finally {
      setApplyingTemplate(false)
    }
  }

  const year = yearMonths(anchor)
  const yearTotals = useMemo(() => {
    const sessions = summary.reduce((total, day) => total + day.completed_count, 0)
    const activeDays = summary.filter((day) => day.completed_count > 0).length
    return { sessions, activeDays }
  }, [summary])

  const markRestDay = async () => {
    setMarkingRest(true)
    try {
      await api.createPlannedSession({
        planned_date: selected,
        title: 'Rest',
        day_type: 'rest',
        notes: null,
        exercises: [],
      })
      await loadRange(view, anchor)
    } catch (err) {
      setError(toMessage(err, 'That day could not be updated.'))
    } finally {
      setMarkingRest(false)
    }
  }

  const cellBadges = (key: string) => {
    const day = summaryByDate[key]
    const plannedCount = day?.planned_count ?? 0
    const completed = day?.completed_count ?? 0
    return (
      <span className="plan__cell-badges">
        {plannedCount > 0 && (
          <span
            className={`plan__cell-dot ${completed >= plannedCount ? 'plan__cell-dot--done' : ''}`}
            title={`${completed} of ${plannedCount} sessions completed`}
          />
        )}
        {day?.has_meals && <span className="plan__cell-meal" title="Nutrition logged" />}
      </span>
    )
  }

  return (
    <div className="page page--plan">
      <header className="page__header page__header--row">
        <div>
          <h1>Plan</h1>
          <p>Schedule sessions, apply templates, and log what you did.</p>
        </div>
        <div className="plan__header-actions">
          <div className="progress__range" role="tablist" aria-label="Calendar period">
            {VIEWS.map((option) => (
              <button
                key={option.value}
                type="button"
                role="tab"
                aria-selected={view === option.value}
                className={view === option.value ? 'progress__range--active' : ''}
                onClick={() => setView(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="plan__nav-btn"
            onClick={() => setAnchor(shift(view, anchor, -1))}
            aria-label={`Previous ${view}`}
          >
            <ChevronLeft size={18} />
          </button>
          <button
            type="button"
            className="plan__today-btn"
            onClick={() => {
              const now = new Date()
              setAnchor(view === 'year' ? new Date(now.getFullYear(), 0, 1) : startOfMonth(now))
              setSelected(today)
              setFocused(today)
            }}
          >
            Today
          </button>
          <button
            type="button"
            className="plan__nav-btn"
            onClick={() => setAnchor(shift(view, anchor, 1))}
            aria-label={`Next ${view}`}
          >
            <ChevronRight size={18} />
          </button>
        </div>
      </header>

      {error && (
        <div className="page__alert page__alert--error" role="alert">
          {error}
          <button
            type="button"
            className="page__alert-action"
            onClick={() => {
              setError(null)
              void loadRange(view, anchor)
              void loadWorkouts()
            }}
          >
            Retry
          </button>
          <button type="button" className="page__alert-close" onClick={() => setError(null)} aria-label="Dismiss">
            <X size={16} />
          </button>
        </div>
      )}

      <div className="plan__layout">
        <section className="plan__calendar" aria-label={periodTitle(view, anchor)}>
          <div className="plan__calendar-title">{periodTitle(view, anchor)}</div>

          {view === 'week' && (
            <div className="plan__week" role="group" aria-label="Week">
              {weekDays(anchor).map((day) => {
                const key = toDateKey(day)
                const count = summaryByDate[key]?.completed_count ?? 0
                return (
                  <button
                    key={key}
                    type="button"
                    className={`plan__day ${key === selected ? 'plan__day--selected' : ''} ${
                      key === today ? 'plan__day--today' : ''
                    }`}
                    onClick={() => moveFocus(key)}
                    aria-pressed={key === selected}
                  >
                    <span className="plan__day-weekday">
                      {day.toLocaleDateString(undefined, { weekday: 'short' })}
                    </span>
                    <span className="plan__day-date">{day.getDate()}</span>
                    {count > 0 && <span className="plan__day-dot" aria-hidden />}
                  </button>
                )
              })}
            </div>
          )}

          {view === 'month' && (
            <div onKeyDown={handleGridKeyDown}>
              <div className="plan__weekdays" aria-hidden>
                {WEEKDAY_LABELS.map((label) => (
                  <div key={label} className="plan__weekday">
                    {label}
                  </div>
                ))}
              </div>
              <div className="plan__month-grid" role="grid" aria-label={formatMonthTitle(anchor)}>
                {monthGrid(anchor).map((cell) => (
                  <button
                    key={cell.key}
                    type="button"
                    role="gridcell"
                    tabIndex={cell.key === focused ? 0 : -1}
                    className={`plan__month-day ${cell.inMonth ? '' : 'plan__month-day--blank'} ${
                      cell.key === selected ? 'plan__month-day--selected' : ''
                    } ${cell.key === today ? 'plan__month-day--today' : ''}`}
                    onClick={() => moveFocus(cell.key)}
                    onFocus={() => setFocused(cell.key)}
                    aria-label={formatDayLabel(cell.key)}
                    aria-pressed={cell.key === selected}
                  >
                    <span className="plan__month-date">{cell.date.getDate()}</span>
                    {cell.inMonth && cellBadges(cell.key)}
                  </button>
                ))}
              </div>
            </div>
          )}

          {view === 'year' && (
            <div onKeyDown={handleGridKeyDown}>
              <div className="plan__year-totals">
                <span>
                  <strong>{yearTotals.sessions}</strong> sessions
                </span>
                <span>
                  <strong>{yearTotals.activeDays}</strong> active days
                </span>
              </div>
              <div className="plan__year-grid">
                {year.map((entry) => (
                  <div key={entry.month} className="plan__year-month">
                    <button
                      type="button"
                      className="plan__year-month-title"
                      onClick={() => {
                        setAnchor(entry.anchor)
                        setView('month')
                      }}
                    >
                      {entry.anchor.toLocaleDateString(undefined, { month: 'short' })}
                    </button>
                    <div className="plan__year-days">
                      {entry.days.map((cell) => {
                        const completed = summaryByDate[cell.key]?.completed_count ?? 0
                        return (
                          <button
                            key={cell.key}
                            type="button"
                            className={`plan__year-day ${cell.key === selected ? 'plan__year-day--selected' : ''}`}
                            style={{ '--heat': heatLevel(completed) } as React.CSSProperties}
                            title={`${formatDayLabel(cell.key)}: ${completed} completed`}
                            aria-label={`${formatDayLabel(cell.key)}, ${completed} completed`}
                            onClick={() => {
                              setAnchor(entry.anchor)
                              setView('month')
                              moveFocus(cell.key)
                            }}
                          />
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
              <p className="plan__year-legend">
                <span className="plan__year-swatch plan__year-swatch--0" /> none
                <span className="plan__year-swatch plan__year-swatch--1" /> 1
                <span className="plan__year-swatch plan__year-swatch--2" /> 2
                <span className="plan__year-swatch plan__year-swatch--3" /> 3+
              </p>
            </div>
          )}
        </section>

        <section className="plan__panel">
          <h2 className="plan__panel-title">
            <CalendarDays size={16} />
            {formatDayLabel(selected)}
          </h2>

          {loading ? (
            <div className="page__loading">
              <Loader2 className="page__spinner" size={24} />
            </div>
          ) : (
            <>
              <div className="plan__day-meta">
                <span className="plan__badge plan__badge--type">{dayTypeLabel(daySummary)}</span>
                {daySummary?.day_type === 'none' && (
                  <button
                    type="button"
                    className="plan__text-btn"
                    onClick={markRestDay}
                    disabled={markingRest}
                  >
                    Mark as rest day
                  </button>
                )}
                {savedAt && <span className="plan__saved">Saved</span>}
              </div>

              <h3 className="plan__section-label">Planned</h3>
              {selectedPlanned.length === 0 ? (
                <div className="plan__inline-form">
                  <input
                    type="text"
                    className="plan__input"
                    placeholder="Session title (optional)"
                    aria-label="Session title"
                    value={planTitle}
                    onChange={(event) => setPlanTitle(event.target.value)}
                  />
                  <select
                    className="plan__input"
                    aria-label="Day type"
                    value={planDayType}
                    onChange={(event) => setPlanDayType(event.target.value)}
                  >
                    {DAY_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {type.replace('_', ' ')}
                      </option>
                    ))}
                  </select>
                  <button type="button" className="profile__save" onClick={createPlan}>
                    <Plus size={16} />
                    Plan session
                  </button>
                </div>
              ) : (
                <ul className="plan__session-list">
                  {selectedPlanned.map((session) => (
                    <li key={session.id} className="plan__session">
                      <div className="plan__session-header">
                        <input
                          className="plan__session-title-input"
                          aria-label="Session title"
                          value={session.title ?? ''}
                          onChange={(event) =>
                            scheduleAutosave(session, { title: event.target.value || null })
                          }
                        />
                        {session.status === 'completed' && (
                          <span className="plan__badge plan__badge--done">Done</span>
                        )}
                      </div>
                      <table className="plan__set-table">
                        <caption className="visually-hidden">Exercises for {session.title ?? 'session'}</caption>
                        <thead>
                          <tr>
                            <th scope="col">#</th>
                            <th scope="col">Exercise</th>
                            <th scope="col">Sets</th>
                            <th scope="col">Reps</th>
                            <th scope="col">Target</th>
                            <th scope="col">Done</th>
                          </tr>
                        </thead>
                        <tbody>
                          {session.exercises.length === 0 && (
                            <tr>
                              <td colSpan={6} className="plan__set-detail">
                                No exercises yet.
                              </td>
                            </tr>
                          )}
                          {session.exercises.map((exercise) => (
                            <tr key={exercise.id}>
                              <td>{exercise.position + 1}</td>
                              <td>{exercise.exercise_name}</td>
                              <td>{exercise.target_sets ?? '—'}</td>
                              <td>{exercise.target_reps ?? '—'}</td>
                              <td>
                                {exercise.target_weight != null
                                  ? `${exercise.target_weight} ${exercise.target_weight_unit ?? ''}`
                                  : exercise.duration_seconds != null
                                    ? `${exercise.duration_seconds}s`
                                    : '—'}
                              </td>
                              <td>
                                <input
                                  type="checkbox"
                                  aria-label={`${exercise.exercise_name} done`}
                                  checked={session.status === 'completed'}
                                  disabled={session.status === 'completed'}
                                  onChange={() => void completeSession(session)}
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <textarea
                        className="plan__input plan__input--textarea"
                        aria-label="Session notes"
                        placeholder="Notes"
                        value={session.notes ?? ''}
                        onChange={(event) => scheduleAutosave(session, { notes: event.target.value })}
                      />
                      <div className="plan__session-actions">
                        {session.status !== 'completed' && (
                          <button
                            type="button"
                            className="plan__text-btn"
                            onClick={() => void completeSession(session)}
                          >
                            <CheckCircle2 size={14} />
                            Mark complete
                          </button>
                        )}
                        <button
                          type="button"
                          className="plan__icon-btn"
                          onClick={() => void deletePlanned(session)}
                          aria-label="Delete planned session"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}

              <h3 className="plan__section-label">
                <Dumbbell size={14} />
                Logged
              </h3>
              {selectedLogged.length === 0 ? (
                <p className="plan__hint">Nothing logged for this day yet.</p>
              ) : (
                <ul className="plan__session-list">
                  {selectedLogged.map((session) => (
                    <li key={session.id} className="plan__session">
                      <div className="plan__session-header">
                        <span className="plan__session-name">{session.name ?? 'Session'}</span>
                        <button
                          type="button"
                          className="plan__icon-btn"
                          onClick={() => void handleDeleteWorkout(session)}
                          aria-label={`Delete ${session.name ?? 'session'}`}
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                      <div className="plan__session-sets">
                        {session.sets.map((set) => (
                          <div key={set.id} className="plan__set-row">
                            <span className="plan__set-exercise">{set.exercise_name}</span>
                            <span className="plan__set-detail">
                              {set.reps ?? '—'} reps
                              {set.weight != null ? ` @ ${set.weight} ${set.weight_unit ?? ''}` : ''}
                            </span>
                          </div>
                        ))}
                      </div>
                    </li>
                  ))}
                </ul>
              )}

              <div className="plan__add">
                <h3 className="plan__section-label">Log a session</h3>
                <input
                  type="text"
                  className="plan__input"
                  placeholder="Session name (optional)"
                  aria-label="Logged session name"
                  value={loggedName}
                  onChange={(event) => setLoggedName(event.target.value)}
                />
                {loggedSets.map((set, index) => (
                  <div key={index} className="plan__set-editor">
                    <ExerciseCombobox
                      value={set.exercise_name}
                      library={library}
                      recent={recentExercises}
                      onLibraryChange={addLibraryExercise}
                      onChange={(value) =>
                        setLoggedSets((prev) =>
                          prev.map((item, i) => (i === index ? { ...item, exercise_name: value } : item)),
                        )
                      }
                    />
                    <Stepper
                      label="Reps"
                      value={set.reps}
                      onChange={(value) =>
                        setLoggedSets((prev) =>
                          prev.map((item, i) => (i === index ? { ...item, reps: value } : item)),
                        )
                      }
                    />
                    <Stepper
                      label="Weight"
                      value={set.weight}
                      step={2.5}
                      onChange={(value) =>
                        setLoggedSets((prev) =>
                          prev.map((item, i) => (i === index ? { ...item, weight: value } : item)),
                        )
                      }
                    />
                    <select
                      className="plan__input plan__input--unit"
                      aria-label="Weight unit"
                      value={set.weight_unit}
                      onChange={(event) =>
                        setLoggedSets((prev) =>
                          prev.map((item, i) =>
                            i === index ? { ...item, weight_unit: event.target.value as 'kg' | 'lb' } : item,
                          ),
                        )
                      }
                    >
                      <option value="kg">kg</option>
                      <option value="lb">lb</option>
                    </select>
                    <button
                      type="button"
                      className="plan__icon-btn"
                      onClick={() => setLoggedSets((prev) => prev.filter((_, i) => i !== index))}
                      aria-label="Remove set"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
                {logError && (
                  <p className="field__error" role="alert">
                    {logError}
                  </p>
                )}
                <div className="plan__add-actions">
                  <button
                    type="button"
                    className="plan__text-btn"
                    onClick={() => setLoggedSets((prev) => [...prev, emptyLoggedSet()])}
                  >
                    <Plus size={14} />
                    Add exercise
                  </button>
                  <button
                    type="button"
                    className="profile__save"
                    onClick={handleLogSession}
                    disabled={savingSession}
                  >
                    {savingSession ? <Loader2 className="page__spinner" size={16} /> : 'Log session'}
                  </button>
                </div>
              </div>

              <div className="plan__templates">
                <h3 className="plan__section-label">
                  <LayoutTemplate size={14} />
                  Start from a template
                </h3>
                <div className="plan__template-row">
                  <select
                    className="plan__input"
                    aria-label="Template"
                    value={templateKey}
                    onChange={(event) => setTemplateKey(event.target.value)}
                  >
                    <option value="">Choose a template</option>
                    {templates.map((template) => (
                      <option key={template.key} value={template.key}>
                        {template.name.replace(/_/g, ' ')}
                      </option>
                    ))}
                  </select>
                  <input
                    type="date"
                    className="plan__input"
                    aria-label="Template start date"
                    value={templateDate}
                    onChange={(event) => setTemplateDate(event.target.value)}
                  />
                  <button
                    type="button"
                    className="profile__save"
                    onClick={applyTemplate}
                    disabled={applyingTemplate || !templateKey}
                  >
                    {applyingTemplate ? <Loader2 className="page__spinner" size={16} /> : 'Apply'}
                  </button>
                </div>
              </div>
            </>
          )}
        </section>
      </div>

      {undo && (
        <div className="toast" role="status">
          <span>{undo.message}</span>
          <button
            type="button"
            className="toast__action"
            onClick={() => {
              undo.restore()
              setUndo(null)
            }}
          >
            <Undo2 size={14} />
            Undo
          </button>
          <button type="button" className="toast__close" onClick={() => setUndo(null)} aria-label="Dismiss">
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  )
}

/** Shade a year-heatmap day by the number of sessions completed. */
/** "No plan" unless the user explicitly planned this day. */
export function dayTypeLabel(day: DaySummary | undefined): string {
  const type = day?.day_type ?? 'none'
  if (type === 'none') return 'No plan'
  return type.replace('_', ' ')
}

function heatLevel(completed: number): number {
  if (completed <= 0) return 0
  if (completed === 1) return 1
  if (completed === 2) return 2
  return 3
}

function Stepper({
  label,
  value,
  step = 1,
  onChange,
}: {
  label: string
  value: number | ''
  step?: number
  onChange: (value: number | '') => void
}) {
  const decrement = () => {
    const current = value === '' ? 0 : Number(value)
    onChange(Math.max(0, current - step))
  }
  const increment = () => onChange((value === '' ? 0 : Number(value)) + step)
  return (
    <div className="stepper">
      <span className="stepper__label">{label}</span>
      <button type="button" className="stepper__btn" onClick={decrement} aria-label={`Decrease ${label}`}>
        <Minus size={14} />
      </button>
      <input
        type="number"
        className="stepper__input"
        aria-label={label}
        value={value}
        min={0}
        step={step}
        onChange={(event) =>
          onChange(event.target.value === '' ? '' : Number(event.target.value))
        }
      />
      <button type="button" className="stepper__btn" onClick={increment} aria-label={`Increase ${label}`}>
        <Plus size={14} />
      </button>
    </div>
  )
}
