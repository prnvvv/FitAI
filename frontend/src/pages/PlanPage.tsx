import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Dumbbell,
  Loader2,
  Plus,
  Trash2,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../services/api'
import type { WorkoutSession, WorkoutSessionCreate } from '../types'

function formatDateKey(d: Date): string {
  return d.toISOString().split('T')[0]
}

function startOfWeek(d: Date): Date {
  const date = new Date(d)
  const day = date.getDay()
  const diff = date.getDate() - day + (day === 0 ? -6 : 1)
  date.setDate(diff)
  date.setHours(0, 0, 0, 0)
  return date
}

function addDays(d: Date, n: number): Date {
  const date = new Date(d)
  date.setDate(date.getDate() + n)
  return date
}

interface DraftSet {
  exercise_name: string
  reps: number | ''
  weight: number | ''
}

export function PlanPage() {
  const [sessions, setSessions] = useState<WorkoutSession[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [today] = useState(() => formatDateKey(new Date()))
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()))
  const [selectedDate, setSelectedDate] = useState(() => formatDateKey(new Date()))
  const [saving, setSaving] = useState(false)
  const [draftName, setDraftName] = useState('')
  const [draftSets, setDraftSets] = useState<DraftSet[]>([
    { exercise_name: '', reps: '', weight: '' },
  ])

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const allSessions = await api.listAllWorkouts()
      setSessions(allSessions)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load plan')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const days = useMemo(() => {
    return Array.from({ length: 7 }, (_, i) => addDays(weekStart, i))
  }, [weekStart])

  const sessionsByDate = useMemo(() => {
    const map: Record<string, WorkoutSession[]> = {}
    for (const s of sessions) {
      const key = formatDateKey(new Date(s.performed_at))
      map[key] = map[key] ?? []
      map[key].push(s)
    }
    return map
  }, [sessions])

  const selectedSessions = sessionsByDate[selectedDate] ?? []
  const selectedDateLabel = useMemo(
    () => new Date(selectedDate).toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' }),
    [selectedDate],
  )

  const handleSaveSession = async () => {
    const validSets = draftSets.filter((s) => s.exercise_name.trim())
    if (validSets.length === 0) return
    setSaving(true)
    try {
      const performedAt = new Date(selectedDate)
      performedAt.setHours(10, 0, 0, 0)
      const payload: WorkoutSessionCreate = {
        performed_at: performedAt.toISOString(),
        name: draftName.trim() || undefined,
        sets: validSets.map((s) => ({
          exercise_name: s.exercise_name.trim(),
          reps: s.reps === '' ? undefined : Number(s.reps),
          weight: s.weight === '' ? undefined : Number(s.weight),
          weight_unit: s.weight === '' ? undefined : 'kg',
        })),
      }
      await api.createWorkout(payload)
      await load()
      setDraftName('')
      setDraftSets([{ exercise_name: '', reps: '', weight: '' }])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save session')
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteSession = async (id: string) => {
    if (!confirm('Delete this session?')) return
    try {
      await api.deleteWorkout(id)
      setSessions((prev) => prev.filter((s) => s.id !== id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete session')
    }
  }

  return (
    <div className="page page--plan">
      <header className="page__header page__header--row">
        <div>
          <h1>Plan</h1>
          <p>Schedule and log your sessions.</p>
        </div>
        <div className="plan__header-actions">
          <button
            type="button"
            className="plan__nav-btn"
            onClick={() => setWeekStart((w) => addDays(w, -7))}
            aria-label="Previous week"
          >
            <ChevronLeft size={18} />
          </button>
          <button
            type="button"
            className="plan__today-btn"
            onClick={() => {
              const today = new Date()
              setWeekStart(startOfWeek(today))
              setSelectedDate(formatDateKey(today))
            }}
          >
            Today
          </button>
          <button
            type="button"
            className="plan__nav-btn"
            onClick={() => setWeekStart((w) => addDays(w, 7))}
            aria-label="Next week"
          >
            <ChevronRight size={18} />
          </button>
        </div>
      </header>

      {error && (
        <div className="page__alert page__alert--error">
          {error}
          <button type="button" className="page__alert-action" onClick={load}>
            Retry
          </button>
        </div>
      )}

      <div className="plan__week">
        {days.map((day) => {
          const key = formatDateKey(day)
          const isSelected = key === selectedDate
            const isToday = key === today
          const hasSession = (sessionsByDate[key]?.length ?? 0) > 0
          return (
            <button
              key={key}
              type="button"
              className={`plan__day ${isSelected ? 'plan__day--selected' : ''} ${isToday ? 'plan__day--today' : ''}`}
              onClick={() => setSelectedDate(key)}
              aria-pressed={isSelected}
            >
              <span className="plan__day-weekday">{day.toLocaleDateString(undefined, { weekday: 'narrow' })}</span>
              <span className="plan__day-date">{day.getDate()}</span>
              {hasSession && <span className="plan__day-dot" aria-hidden />}
            </button>
          )
        })}
      </div>

      <div className="plan__panel">
        <h2 className="plan__panel-title">
          <CalendarDays size={16} />
          {selectedDateLabel}
        </h2>

        {loading ? (
          <div className="page__loading">
            <Loader2 className="page__spinner" size={24} />
          </div>
        ) : selectedSessions.length === 0 ? (
          <div className="page__empty page__empty--compact">
            <Dumbbell size={32} />
            <p>No session planned.</p>
          </div>
        ) : (
          <ul className="plan__session-list">
            {selectedSessions.map((session) => (
              <li key={session.id} className="plan__session">
                <div className="plan__session-header">
                  <span className="plan__session-name">{session.name ?? 'Session'}</span>
                  <button
                    type="button"
                    className="plan__icon-btn"
                    onClick={() => handleDeleteSession(session.id)}
                    aria-label="Delete session"
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
            value={draftName}
            onChange={(e) => setDraftName(e.target.value)}
          />
          <div className="plan__sets">
            {draftSets.map((set, i) => (
              <div key={i} className="plan__set-editor">
                <input
                  type="text"
                  className="plan__input"
                  placeholder="Exercise"
                  value={set.exercise_name}
                  onChange={(e) =>
                    setDraftSets((prev) =>
                      prev.map((s, idx) => (idx === i ? { ...s, exercise_name: e.target.value } : s)),
                    )
                  }
                />
                <input
                  type="number"
                  className="plan__input plan__input--number"
                  placeholder="Reps"
                  min={0}
                  value={set.reps}
                  onChange={(e) =>
                    setDraftSets((prev) =>
                      prev.map((s, idx) => (idx === i ? { ...s, reps: e.target.value === '' ? '' : Number(e.target.value) } : s)),
                    )
                  }
                />
                <input
                  type="number"
                  className="plan__input plan__input--number"
                  placeholder="Weight kg"
                  min={0}
                  value={set.weight}
                  onChange={(e) =>
                    setDraftSets((prev) =>
                      prev.map((s, idx) => (idx === i ? { ...s, weight: e.target.value === '' ? '' : Number(e.target.value) } : s)),
                    )
                  }
                />
              </div>
            ))}
          </div>
          <div className="plan__add-actions">
            <button
              type="button"
              className="plan__text-btn"
              onClick={() => setDraftSets((prev) => [...prev, { exercise_name: '', reps: '', weight: '' }])}
            >
              <Plus size={14} />
              Add exercise
            </button>
            <button
              type="button"
              className="profile__save"
              onClick={handleSaveSession}
              disabled={saving || draftSets.every((s) => !s.exercise_name.trim())}
            >
              {saving ? <Loader2 className="page__spinner" size={16} /> : 'Log session'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
