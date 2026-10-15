import { ChevronLeft, ChevronRight, Undo2, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent } from 'react'
import { DayPanel, emptyLoggedSet } from '../components/plan/DayPanel'
import type { LoggedSet, PanelTab } from '../components/plan/DayPanel'
import {
  api,
  isAbortError,
  normalizeDaySummaries,
  normalizePlannedSessions,
  normalizeWorkoutSessions,
  toMessage,
} from '../services/api'
import type { DaySummary, Exercise, PlannedSession, Template, WorkoutSession } from '../types'
import {
  addDays,
  addMonths,
  dateFromKey,
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
import type { CalendarCell } from '../utils/dates'

type View = 'week' | 'month' | 'year'

const VIEWS: { value: View; label: string }[] = [
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
  { value: 'year', label: 'Year' },
]

const WEEKDAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/** Visible range for the current view; one request covers every view. */
export function visibleRange(view: View, anchor: Date): { from: string; to: string } {
  if (view === 'week') {
    const days = weekDays(anchor)
    return { from: toDateKey(days[0]), to: toDateKey(days[6]) }
  }
  if (view === 'month') {
    const cells = monthGrid(anchor)
    return { from: cells[0].key, to: toDateKey(cells[cells.length - 1].date) }
  }
  return {
    from: toDateKey(new Date(anchor.getFullYear(), 0, 1)),
    to: toDateKey(new Date(anchor.getFullYear(), 11, 31)),
  }
}

/**
 * The 42 fetch cells grouped into weeks, keeping only weeks that contain an
 * in-month day (4–6 rows). Render-only: `monthGrid` and `visibleRange` are
 * untouched, so the summary/session request ranges stay byte-identical.
 */
export function monthWeeks(anchor: Date): CalendarCell[][] {
  const cells = monthGrid(anchor)
  const weeks: CalendarCell[][] = []
  for (let index = 0; index < cells.length; index += 7) {
    const week = cells.slice(index, index + 7)
    if (week.some((cell) => cell.inMonth)) weeks.push(week)
  }
  return weeks
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

/** Local YYYY-MM-DD key for an ISO instant, or '' when it cannot be parsed. */
function localDayKey(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return toDateKey(new Date(date.getFullYear(), date.getMonth(), date.getDate()))
}

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false)
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const list = window.matchMedia(query)
    const update = () => setMatches(list.matches)
    update()
    list.addEventListener('change', update)
    return () => list.removeEventListener('change', update)
  }, [query])
  return matches
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
  const [planningSession, setPlanningSession] = useState(false)
  const saveTimer = useRef<number | null>(null)

  // Re-entrant guards: disables cover the re-rendered case, refs cover two
  // clicks that land before React flushes (and StrictMode double effects can
  // never reach these — they only run from event handlers).
  const planningRef = useRef(false)
  const savingRef = useRef(false)
  const applyingRef = useRef(false)
  const restingRef = useRef(false)

  // Day-panel tab: "Log" for today and past days, "Plan" for future days. A
  // manual choice sticks when another day is selected.
  const [panelTab, setPanelTab] = useState<PanelTab>('log')
  const [tabTouched, setTabTouched] = useState(false)
  const tab: PanelTab = tabTouched ? panelTab : selected > today ? 'plan' : 'log'
  const handleTabChange = useCallback((next: PanelTab) => {
    setPanelTab(next)
    setTabTouched(true)
  }, [])

  // Responsive rendering only; network behavior never depends on these.
  const phone = useMediaQuery('(max-width: 767px)')
  const wide = useMediaQuery('(min-width: 1100px)')
  const [sheetOpen, setSheetOpen] = useState(false)
  const [yearDrawerOpen, setYearDrawerOpen] = useState(false)
  const sheetCloseRef = useRef<HTMLButtonElement>(null)
  const drawerCloseRef = useRef<HTMLButtonElement>(null)

  // Bottom sheet: focus the close button, lock body scroll, restore on close.
  useEffect(() => {
    if (!phone || !sheetOpen) return
    const previous = document.activeElement as HTMLElement | null
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    sheetCloseRef.current?.focus()
    return () => {
      document.body.style.overflow = previousOverflow
      previous?.focus?.()
    }
  }, [phone, sheetOpen])

  // Year drawer: same treatment on desktop.
  useEffect(() => {
    if (phone || view !== 'year' || !yearDrawerOpen) return
    const previous = document.activeElement as HTMLElement | null
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    drawerCloseRef.current?.focus()
    return () => {
      document.body.style.overflow = previousOverflow
      previous?.focus?.()
    }
  }, [phone, view, yearDrawerOpen])

  const summaryByDate = useMemo(() => {
    const map: Record<string, DaySummary> = {}
    for (const day of summary) map[day.date] = day
    return map
  }, [summary])

  const loggedByDate = useMemo(() => {
    const map: Record<string, WorkoutSession[]> = {}
    for (const session of workouts) {
      const key = localDayKey(session.performed_at)
      if (!key) continue
      map[key] = [...(map[key] ?? []), session]
    }
    return map
  }, [workouts])

  const plannedByDate = useMemo(() => {
    const map: Record<string, PlannedSession[]> = {}
    for (const session of planned) {
      map[session.planned_date] = [...(map[session.planned_date] ?? []), session]
    }
    return map
  }, [planned])

  const recentExercises = useMemo(() => {
    const names = workouts.flatMap((session) => (session.sets ?? []).map((set) => set.exercise_name))
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

  // Only the newest load may write state: switching views quickly must not let
  // a slow, stale response overwrite a fresh one.
  const requestId = useRef(0)
  const controller = useRef<AbortController | null>(null)

  const loadRange = useCallback(
    async (nextView: View, nextAnchor: Date, signal: AbortSignal) => {
      const { from, to } = visibleRange(nextView, nextAnchor)
      const [days, sessions] = await Promise.all([
        api.getPlanSummary(from, to, signal),
        api.getAllPlannedSessions(from, to, signal),
      ])
      return { summary: normalizeDaySummaries(days), planned: sessions }
    },
    [],
  )

  const loadWorkouts = useCallback(async (signal: AbortSignal) => {
    return api.listAllWorkouts(signal)
  }, [])

  const reload = useCallback(async () => {
    controller.current?.abort()
    const next = new AbortController()
    controller.current = next
    const id = requestId.current + 1
    requestId.current = id
    setLoading(true)
    try {
      const [range, sessions] = await Promise.all([
        loadRange(view, anchor, next.signal),
        loadWorkouts(next.signal),
      ])
      if (requestId.current !== id) return
      setSummary(range.summary)
      setPlanned(normalizePlannedSessions(range.planned))
      setWorkouts(normalizeWorkoutSessions(sessions))
      setError(null)
    } catch (err) {
      if (isAbortError(err) || requestId.current !== id) return
      setError(toMessage(err, 'The plan could not be loaded.'))
    } finally {
      if (requestId.current === id) setLoading(false)
    }
  }, [anchor, loadRange, loadWorkouts, view])

  useEffect(() => {
    void reload()
    return () => controller.current?.abort()
  }, [reload])

  // Reference data (exercise library, templates) is loaded once on mount: it
  // does not depend on the visible range, and re-fetching it per navigation
  // would be a request storm.
  useEffect(() => {
    const ignore = { current: false }
    void (async () => {
      try {
        const [exercises, templateList] = await Promise.all([
          api.listAllExercises(),
          api.getPlanTemplates(),
        ])
        if (ignore.current) return
        setLibrary(Array.isArray(exercises) ? exercises : [])
        setTemplates(Array.isArray(templateList) ? templateList : [])
      } catch {
        // The exercise picker falls back to free text; templates are optional.
        if (ignore.current) return
        setLibrary([])
        setTemplates([])
      }
    })()
    return () => {
      ignore.current = true
    }
  }, [])

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
  const restSession = useMemo(
    () => selectedPlanned.find((session) => session.day_type === 'rest'),
    [selectedPlanned],
  )

  const selectDay = useCallback(
    (key: string) => {
      setFocused(key)
      setSelected(key)
      if (phone) setSheetOpen(true)
    },
    [phone],
  )

  /** The focused day as a Date, falling back to today when it is unusable. */
  const focusedDate = () => dateFromKey(focused) ?? new Date()

  const handleGridKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const deltas: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }
    const delta = deltas[event.key]
    if (delta !== undefined) {
      event.preventDefault()
      const current = dateFromKey(focused)
      if (current) selectDay(toDateKey(addDays(current, delta)))
      return
    }
    if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault()
      const days = weekDays(focusedDate())
      selectDay(toDateKey(event.key === 'Home' ? days[0] : days[6]))
      return
    }
    if (event.key === 'PageUp' || event.key === 'PageDown') {
      event.preventDefault()
      const direction = event.key === 'PageUp' ? -1 : 1
      const next =
        view === 'year' ? new Date(anchor.getFullYear() + direction, 0, 1) : shift(view, anchor, direction)
      setAnchor(next)
      // Keep the focused cell inside the newly shown grid so the roving
      // tabindex always has exactly one tabbable cell.
      const key = view === 'year' ? toDateKey(next) : toDateKey(shift(view, focusedDate(), direction))
      setFocused(key)
      return
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      setSelected(focused)
      if (phone) setSheetOpen(true)
    }
  }

  const handleWeekKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const days = weekDays(anchor)
    const keys = days.map((day) => toDateKey(day))
    const base = keys.includes(focused) ? focused : keys.includes(selected) ? selected : keys[0]
    const at = keys.indexOf(base)
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault()
      const next = event.key === 'ArrowLeft' ? Math.max(0, at - 1) : Math.min(keys.length - 1, at + 1)
      selectDay(keys[next])
      return
    }
    if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault()
      selectDay(event.key === 'Home' ? keys[0] : keys[keys.length - 1])
    }
  }

  const addLibraryExercise = (exercise: Exercise) => {
    setLibrary((prev) => (prev.some((item) => item.id === exercise.id) ? prev : [...prev, exercise]))
  }

  const handleLogSession = async () => {
    if (savingRef.current) return
    savingRef.current = true
    const sets = loggedSets
      .filter((set) => set.exercise_name.trim())
      .map((set) => ({
        exercise_name: set.exercise_name.trim(),
        reps: set.reps === '' ? null : Number(set.reps),
        weight: set.weight === '' ? null : Number(set.weight),
        weight_unit: set.weight === '' ? null : set.weight_unit,
      }))
    if (sets.length === 0) {
      savingRef.current = false
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
      await reload()
    } catch (err) {
      setLogError(toMessage(err, 'That session could not be saved.'))
    } finally {
      savingRef.current = false
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
              sets: (snapshot.sets ?? []).map((set) => ({
                exercise_name: set.exercise_name,
                reps: set.reps,
                weight: set.weight,
                weight_unit: set.weight_unit,
                duration_seconds: set.duration_seconds,
                distance_meters: set.distance_meters,
              })),
            })
            .then(() => reload())
        },
      })
      await reload()
    } catch (err) {
      setError(toMessage(err, 'That session could not be deleted.'))
    }
  }

  const createPlan = async () => {
    if (planningRef.current) return
    planningRef.current = true
    setPlanningSession(true)
    setError(null)
    try {
      await api.createPlannedSession({
        planned_date: selected,
        title: planTitle.trim() || null,
        day_type: planDayType,
        notes: planNotes.trim() || null,
        exercises: [],
      })
      await reload()
    } catch (err) {
      setError(toMessage(err, 'The session could not be planned.'))
    } finally {
      planningRef.current = false
      setPlanningSession(false)
    }
  }

  /**
   * Editable fields write through local drafts.
   *
   * The value used to come straight from the server row while the save was only
   * debounced, so a re-render reverted what the user had just typed. The draft
   * is the source of truth while typing; the server row wins again after the
   * save completes.
   */
  const [drafts, setDrafts] = useState<Record<string, { title?: string; notes?: string }>>({})
  const draftFor = (session: PlannedSession) => drafts[session.id]
  const setDraft = (sessionId: string, patch: { title?: string; notes?: string }) => {
    setDrafts((prev) => ({ ...prev, [sessionId]: { ...prev[sessionId], ...patch } }))
  }

  const scheduleAutosave = (session: PlannedSession, patch: Partial<PlannedSession>) => {
    if (saveTimer.current) window.clearTimeout(saveTimer.current)
    saveTimer.current = window.setTimeout(async () => {
      saveTimer.current = null
      try {
        await api.updatePlannedSession(session.id, patch)
        setSavedAt(Date.now())
        setDrafts((prev) => {
          const next = { ...prev }
          delete next[session.id]
          return next
        })
        await reload()
      } catch (err) {
        setError(toMessage(err, 'Your changes could not be saved.'))
      }
    }, 600)
  }

  const completeSession = async (session: PlannedSession) => {
    try {
      await api.completePlannedSession(session.id)
      await reload()
    } catch (err) {
      setError(toMessage(err, 'That session could not be completed.'))
    }
  }

  const deletePlanned = async (session: PlannedSession) => {
    try {
      await api.deletePlannedSession(session.id)
      setUndo({ message: 'Planned session removed.', restore: () => void reload() })
      await reload()
    } catch (err) {
      setError(toMessage(err, 'That session could not be removed.'))
    }
  }

  const applyTemplate = async () => {
    if (applyingRef.current || !templateKey) return
    applyingRef.current = true
    setApplyingTemplate(true)
    try {
      await api.applyPlanTemplate(templateKey, templateDate)
      setTemplateKey('')
      await reload()
    } catch (err) {
      setError(toMessage(err, 'That template could not be applied.'))
    } finally {
      applyingRef.current = false
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
    if (restingRef.current) return
    restingRef.current = true
    setMarkingRest(true)
    try {
      await api.createPlannedSession({
        planned_date: selected,
        title: 'Rest',
        day_type: 'rest',
        notes: null,
        exercises: [],
      })
      await reload()
    } catch (err) {
      setError(toMessage(err, 'That day could not be updated.'))
    } finally {
      restingRef.current = false
      setMarkingRest(false)
    }
  }

  const cellStatus = (key: string): string => {
    const day = summaryByDate[key]
    if (day?.day_type === 'rest') return 'rest'
    if ((day?.completed_count ?? 0) > 0) return 'logged'
    if ((day?.planned_count ?? 0) > 0) return 'planned'
    return 'no plan'
  }

  const cellBadges = (key: string) => {
    const day = summaryByDate[key]
    const plannedCount = day?.planned_count ?? 0
    const completed = day?.completed_count ?? 0
    const isRest = day?.day_type === 'rest'
    if (plannedCount === 0 && !isRest && !day?.has_meals) return null
    return (
      <span className="plan__cell-badges">
        {plannedCount > 0 && (
          <span
            className={`plan__cell-dot ${completed >= plannedCount ? 'plan__cell-dot--done' : ''}`}
            title={`${completed} of ${plannedCount} sessions completed`}
          />
        )}
        {isRest && <span className="plan__cell-rest">Rest</span>}
        {day?.has_meals && <span className="plan__cell-meal" title="Nutrition logged" />}
      </span>
    )
  }

  const weeks = useMemo(() => (view === 'month' ? monthWeeks(anchor) : []), [view, anchor])
  const weekStripDays = useMemo(() => (view === 'week' ? weekDays(anchor) : []), [view, anchor])
  const weekHours = useMemo(() => {
    // Cover 6am–9pm by default, widening so every logged session has a row.
    let start = 6
    let end = 21
    for (const day of weekStripDays) {
      for (const session of loggedByDate[toDateKey(day)] ?? []) {
        const hour = new Date(session.performed_at).getHours()
        if (Number.isNaN(hour)) continue
        start = Math.min(start, hour)
        end = Math.max(end, hour)
      }
    }
    const hours: number[] = []
    for (let hour = start; hour <= end; hour += 1) hours.push(hour)
    return hours
  }, [weekStripDays, loggedByDate])
  const stripTabbable =
    weekStripDays.map((day) => toDateKey(day)).find((key) => key === focused) ??
    weekStripDays.map((day) => toDateKey(day)).find((key) => key === selected) ??
    (weekStripDays.length > 0 ? toDateKey(weekStripDays[0]) : null)

  const closeSheet = useCallback(() => setSheetOpen(false), [])
  const closeDrawer = useCallback(() => setYearDrawerOpen(false), [])
  const closeOverlays = useCallback(
    (event: ReactKeyboardEvent<HTMLElement>) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        if (phone && sheetOpen) closeSheet()
        else if (!phone && view === 'year' && yearDrawerOpen) closeDrawer()
      }
    },
    [phone, sheetOpen, view, yearDrawerOpen, closeSheet, closeDrawer],
  )

  const dayPanel = (
    <DayPanel
      selected={selected}
      today={today}
      loading={loading}
      error={error && summary.length === 0 ? error : null}
      onRetry={() => {
        setError(null)
        void reload()
      }}
      loadingLabel={`Loading your ${view} plan…`}
      statusText={dayTypeLabel(daySummary)}
      showMarkRest={daySummary?.day_type === 'none'}
      markingRest={markingRest}
      onMarkRest={() => void markRestDay()}
      restSession={restSession}
      onUnmarkRest={(session) => void deletePlanned(session)}
      savedAt={savedAt}
      tab={tab}
      onTabChange={handleTabChange}
      split={view === 'week' && wide && !phone}
      planTitle={planTitle}
      onPlanTitle={setPlanTitle}
      planDayType={planDayType}
      onPlanDayType={setPlanDayType}
      planning={planningSession}
      onCreatePlan={() => void createPlan()}
      planned={selectedPlanned}
      draftFor={draftFor}
      onDraft={setDraft}
      onAutosave={scheduleAutosave}
      onComplete={(session) => void completeSession(session)}
      onDeletePlanned={(session) => void deletePlanned(session)}
      logged={selectedLogged}
      loggedName={loggedName}
      onLoggedName={setLoggedName}
      loggedSets={loggedSets}
      setLoggedSets={setLoggedSets}
      saving={savingSession}
      logError={logError}
      onLogSession={() => void handleLogSession()}
      onDeleteWorkout={(session) => void handleDeleteWorkout(session)}
      library={library}
      recent={recentExercises}
      onLibraryExercise={addLibraryExercise}
      templates={templates}
      templateKey={templateKey}
      templateDate={templateDate}
      applyingTemplate={applyingTemplate}
      onTemplateKey={setTemplateKey}
      onTemplateDate={setTemplateDate}
      onApplyTemplate={() => void applyTemplate()}
    />
  )

  return (
    <div className="page page--plan">
      <header className="page__header page__header--row plan__page-header">
        <div className="plan__title-block">
          <h1>{periodTitle(view, anchor)}</h1>
          <p className="plan__subtitle">Plan sessions and log what you did</p>
        </div>
        {view === 'year' && (
          <div className="plan__year-totals">
            <span>
              <strong>{yearTotals.sessions}</strong> sessions
            </span>
            <span>
              <strong>{yearTotals.activeDays}</strong> active days
            </span>
          </div>
        )}
        <div className="plan__header-actions">
          <div className="plan__views" role="tablist" aria-label="Calendar period">
            {VIEWS.map((option) => (
              <button
                key={option.value}
                type="button"
                role="tab"
                aria-selected={view === option.value}
                className={view === option.value ? 'plan__views--active' : ''}
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

      {error && summary.length > 0 && (
        <div className="page__alert page__alert--error" role="alert">
          {error}
          <button
            type="button"
            className="page__alert-action"
            onClick={() => {
              setError(null)
              void reload()
            }}
          >
            Retry
          </button>
          <button type="button" className="page__alert-close" onClick={() => setError(null)} aria-label="Dismiss">
            <X size={16} />
          </button>
        </div>
      )}

      <div
        className={`plan__content ${view === 'year' ? 'plan__content--year' : ''} ${view === 'week' ? 'plan__content--week' : ''}`}
      >
        <section className="plan__calendar" aria-label={periodTitle(view, anchor)}>
          {view === 'week' && (
            <div className="plan__week" role="group" aria-label="Week" onKeyDown={handleWeekKeyDown}>
              <div className="timetable">
                <div className="timetable__head">
                  <div className="timetable__gutter-head" aria-hidden="true" />
                  {weekStripDays.map((day) => {
                    const key = toDateKey(day)
                    return (
                      <button
                        key={key}
                        type="button"
                        tabIndex={key === stripTabbable ? 0 : -1}
                        className={`timetable__day ${key === selected ? 'is-selected' : ''} ${
                          key === today ? 'is-today' : ''
                        }`}
                        onClick={() => selectDay(key)}
                        onFocus={() => setFocused(key)}
                        aria-pressed={key === selected}
                        aria-label={`${formatDayLabel(key)}, ${cellStatus(key)}`}
                      >
                        <span className="timetable__weekday">
                          {day.toLocaleDateString(undefined, { weekday: 'short' })}
                        </span>
                        <span className="timetable__date">{day.getDate()}</span>
                      </button>
                    )
                  })}
                </div>

                <div className="timetable__allday">
                  <div className="timetable__gutter-label">All day</div>
                  {weekStripDays.map((day) => {
                    const key = toDateKey(day)
                    const sessions = plannedByDate[key] ?? []
                    return (
                      <div key={key} className="timetable__allday-col">
                        {sessions.map((session, index) => {
                          const label = plannedSessionLabel(session)
                          const tone = session.day_type === 'rest' ? 'slate' : timetableTone(label, index)
                          return (
                            <button
                              key={session.id}
                              type="button"
                              className="timetable__chip"
                              data-tone={tone}
                              onClick={() => selectDay(key)}
                              title={label}
                            >
                              {label}
                            </button>
                          )
                        })}
                      </div>
                    )
                  })}
                </div>

                <div className="timetable__body">
                  <div className="timetable__gutter">
                    {weekHours.map((hour) => (
                      <div key={hour} className="timetable__hour">
                        {hourLabel(hour)}
                      </div>
                    ))}
                  </div>
                  {weekStripDays.map((day) => {
                    const key = toDateKey(day)
                    const logged = loggedByDate[key] ?? []
                    return (
                      <div
                        key={key}
                        className={`timetable__col ${key === selected ? 'is-selected' : ''}`}
                      >
                        {weekHours.map((hour) => (
                          <div key={hour} className="timetable__cell">
                            {logged
                              .filter((session) => new Date(session.performed_at).getHours() === hour)
                              .map((session) => {
                                const label = session.name?.trim() || 'Workout'
                                return (
                                  <div
                                    key={session.id}
                                    className="timetable__event"
                                    data-tone={timetableTone(label)}
                                    title={`${label} · ${loggedTimeRange(session)}`}
                                  >
                                    <span className="timetable__event-title">{label}</span>
                                    <span className="timetable__event-time">
                                      {loggedTimeRange(session)}
                                    </span>
                                  </div>
                                )
                              })}
                          </div>
                        ))}
                      </div>
                    )
                  })}
                </div>
              </div>
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
              <div
                className="plan__month-grid"
                role="grid"
                aria-label={formatMonthTitle(anchor)}
                style={{ '--rows': weeks.length } as CSSProperties}
              >
                {weeks.map((week, index) => (
                  <div
                    key={week[0]?.key ?? `week-${index}`}
                    role="row"
                    className="plan__month-week"
                    aria-label={`Week ${index + 1}`}
                  >
                    {week.map((cell) => (
                      <button
                        key={cell.key}
                        type="button"
                        role="gridcell"
                        tabIndex={cell.key === focused ? 0 : -1}
                        className={`plan__month-day ${cell.inMonth ? '' : 'plan__month-day--outside'} ${
                          cell.key === selected ? 'plan__month-day--selected' : ''
                        } ${cell.key === today ? 'plan__month-day--today' : ''}`}
                        onClick={() => selectDay(cell.key)}
                        onFocus={() => setFocused(cell.key)}
                        aria-label={`${formatDayLabel(cell.key)}, ${cellStatus(cell.key)}`}
                        aria-selected={cell.key === selected}
                        aria-current={cell.key === today ? 'date' : undefined}
                        aria-pressed={cell.key === selected}
                      >
                        <span className="plan__month-date">{cell.date.getDate()}</span>
                        {cell.inMonth && cellBadges(cell.key)}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}

          {view === 'year' && (
            <div onKeyDown={handleGridKeyDown}>
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
                            style={{ '--heat': heatLevel(completed) } as CSSProperties}
                            title={`${formatDayLabel(cell.key)}: ${completed} completed`}
                            aria-label={`${formatDayLabel(cell.key)}, ${completed} completed`}
                            onClick={() => {
                              setFocused(cell.key)
                              setSelected(cell.key)
                              if (phone) setSheetOpen(true)
                              else setYearDrawerOpen(true)
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

        {!phone && view !== 'year' && (
          <section className="plan__panel" aria-label="Day details">
            {dayPanel}
          </section>
        )}
      </div>

      {phone && sheetOpen && (
        <>
          <div className="plan__sheet-backdrop" onClick={closeSheet} aria-hidden />
          <section
            className="plan__sheet"
            role="dialog"
            aria-modal="true"
            aria-label="Day details"
            onKeyDown={closeOverlays}
          >
            <div className="plan__sheet-handle" aria-hidden />
            <button
              ref={sheetCloseRef}
              type="button"
              className="plan__sheet-close"
              onClick={closeSheet}
              aria-label="Close day panel"
            >
              <X size={18} />
            </button>
            <div className="plan__panel plan__panel--sheet">{dayPanel}</div>
          </section>
        </>
      )}

      {!phone && view === 'year' && yearDrawerOpen && (
        <>
          <div className="plan__drawer-backdrop" onClick={closeDrawer} aria-hidden />
          <section className="plan__drawer" role="dialog" aria-modal="true" aria-label="Day details" onKeyDown={closeOverlays}>
            <button
              ref={drawerCloseRef}
              type="button"
              className="plan__sheet-close"
              onClick={closeDrawer}
              aria-label="Close day panel"
            >
              <X size={18} />
            </button>
            <div className="plan__panel plan__panel--drawer">{dayPanel}</div>
          </section>
        </>
      )}

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

/** "No plan" unless the user explicitly planned this day. */
export function dayTypeLabel(day: DaySummary | undefined): string {
  const type = day?.day_type ?? 'none'
  if (type === 'none') return 'No plan'
  return type.replace('_', ' ')
}

/**
 * Timetable helpers.
 *
 * Planned sessions only carry a date, so they are shown in an "all day" band;
 * logged workouts carry a time and are placed in their hour row. Colours are
 * chosen deterministically from the session label so a given session keeps the
 * same colour between renders without inventing categories.
 */
const TIMETABLE_TONES = ['blue', 'mint', 'lavender', 'pink', 'amber', 'cyan'] as const

export function timetableTone(label: string, index = 0): string {
  let hash = 0
  for (let i = 0; i < label.length; i += 1) {
    hash = (hash * 31 + label.charCodeAt(i)) >>> 0
  }
  return TIMETABLE_TONES[(hash + index) % TIMETABLE_TONES.length]
}

/** A readable name for a planned session, falling back to its type. */
export function plannedSessionLabel(session: PlannedSession): string {
  const title = session.title?.trim()
  if (title) return title
  if (session.day_type === 'rest') return 'Rest Day'
  if (session.day_type && session.day_type !== 'none') {
    return session.day_type.charAt(0).toUpperCase() + session.day_type.slice(1)
  }
  return 'Workout'
}

/** "7:30 AM" or "7:30 AM – 8:15 AM" when a duration is recorded. */
export function loggedTimeRange(session: WorkoutSession): string {
  const start = new Date(session.performed_at)
  if (Number.isNaN(start.getTime())) return ''
  const fmt = (date: Date) =>
    date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  if (!session.duration_minutes) return fmt(start)
  const end = new Date(start.getTime() + session.duration_minutes * 60_000)
  return `${fmt(start)} – ${fmt(end)}`
}

/** Short hour label such as "6 AM". */
export function hourLabel(hour: number): string {
  const date = new Date()
  date.setHours(hour, 0, 0, 0)
  return date.toLocaleTimeString(undefined, { hour: 'numeric' })
}

/** Shade a year-heatmap day by the number of sessions completed. */
function heatLevel(completed: number): number {
  if (completed <= 0) return 0
  if (completed === 1) return 1
  if (completed === 2) return 2
  return 3
}
