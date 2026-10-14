import { CheckCircle2, Dumbbell, LayoutTemplate, Loader2, Minus, MoreHorizontal, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { Exercise, PlannedSession, Template, WorkoutSession } from '../../types'
import { ExerciseCombobox } from './ExerciseCombobox'
import { PanelMenu } from './PanelMenu'
import { SegmentedControl } from './SegmentedControl'
import { TemplatePopover } from './TemplatePopover'

export interface LoggedSet {
  exercise_name: string
  reps: number | ''
  weight: number | ''
  weight_unit: 'kg' | 'lb'
}

export function emptyLoggedSet(): LoggedSet {
  return { exercise_name: '', reps: '', weight: '', weight_unit: 'kg' }
}

export type PanelTab = 'plan' | 'log'

export interface PlanDraftPatch {
  title?: string
  notes?: string
}

interface DayPanelProps {
  selected: string
  today: string
  loading: boolean
  /** "Loading your month plan…" — keeps the view-specific skeleton text. */
  loadingLabel: string
  error: string | null
  onRetry: () => void
  /** Verbatim day-type label ("No plan", "rest", ...) — existing logic. */
  statusText: string
  showMarkRest: boolean
  markingRest: boolean
  onMarkRest: () => void
  restSession: PlannedSession | undefined
  onUnmarkRest: (session: PlannedSession) => void
  savedAt: number | null
  tab: PanelTab
  onTabChange: (tab: PanelTab) => void
  /** Week view on wide screens: Plan and Log side by side, no tabs. */
  split: boolean
  planTitle: string
  onPlanTitle: (value: string) => void
  planDayType: string
  onPlanDayType: (value: string) => void
  planning: boolean
  onCreatePlan: () => void
  planned: PlannedSession[]
  draftFor: (session: PlannedSession) => PlanDraftPatch | undefined
  onDraft: (sessionId: string, patch: PlanDraftPatch) => void
  onAutosave: (session: PlannedSession, patch: Partial<PlannedSession>) => void
  onComplete: (session: PlannedSession) => void
  onDeletePlanned: (session: PlannedSession) => void
  logged: WorkoutSession[]
  loggedName: string
  onLoggedName: (value: string) => void
  loggedSets: LoggedSet[]
  setLoggedSets: Dispatch<SetStateAction<LoggedSet[]>>
  saving: boolean
  logError: string | null
  onLogSession: () => void
  onDeleteWorkout: (session: WorkoutSession) => void
  library: Exercise[]
  recent: Exercise[]
  onLibraryExercise: (exercise: Exercise) => void
  templates: Template[]
  templateKey: string
  templateDate: string
  applyingTemplate: boolean
  onTemplateKey: (value: string) => void
  onTemplateDate: (value: string) => void
  onApplyTemplate: () => void
}

/** Short "Wed, 14 Oct" label for the panel header. */
function shortDayLabel(key: string): string {
  const [year, month, day] = key.split('-').map(Number)
  const date = new Date(year, month - 1, day)
  const weekday = date.toLocaleDateString(undefined, { weekday: 'short' })
  const monthDay = date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
  return `${weekday}, ${monthDay}`
}

const DAY_TYPE_OPTIONS = [
  { value: 'workout', label: 'Workout' },
  { value: 'rest', label: 'Rest' },
  { value: 'active_recovery', label: 'Active recovery' },
]

export function DayPanel(props: DayPanelProps) {
  const {
    selected,
    today,
    loading,
    loadingLabel,
    error,
    onRetry,
    statusText,
    showMarkRest,
    markingRest,
    onMarkRest,
    restSession,
    onUnmarkRest,
    savedAt,
    tab,
    onTabChange,
    split,
  } = props
  const [templateOpen, setTemplateOpen] = useState(false)
  const [collapsedLog, setCollapsedLog] = useState<Record<string, boolean>>({})
  const [expandedPlan, setExpandedPlan] = useState<Record<string, boolean>>({})

  const menuItems = [
    ...(restSession
      ? [{ label: 'Unmark rest day', onSelect: () => onUnmarkRest(restSession) }]
      : showMarkRest
        ? [{ label: 'Mark as rest day', disabled: markingRest, onSelect: onMarkRest }]
        : []),
    { label: 'Start from a template…', onSelect: () => setTemplateOpen(true) },
  ]

  return (
    <>
      <div className="daypanel__header">
        <div className="daypanel__title">
          <span className="daypanel__date">{shortDayLabel(selected)}</span>
          {selected === today && <span className="plan__badge daypanel__today-chip">Today</span>}
          <span className="plan__badge plan__badge--type">{statusText}</span>
        </div>
        <PanelMenu triggerLabel="Day options" trigger={<MoreHorizontal size={18} />} items={menuItems} />
      </div>

      {loading ? (
        <div className="plan__skeleton" role="status" aria-busy="true" aria-live="polite">
          <span className="visually-hidden">{loadingLabel}</span>
          <div className="plan__skeleton-line" />
          <div className="plan__skeleton-line" />
          <div className="plan__skeleton-line" />
          <div className="plan__skeleton-line" />
        </div>
      ) : error ? (
        <div className="page__alert page__alert--error" role="alert">
          {error}
          <button type="button" className="page__alert-action" onClick={onRetry}>
            Retry
          </button>
        </div>
      ) : (
        <>
          <div className="daypanel__toolbar">
            {!split && (
              <div className="plan__tabs" role="tablist" aria-label="Day panel">
                {(['plan', 'log'] as const).map((value) => (
                  <button
                    key={value}
                    type="button"
                    role="tab"
                    aria-selected={tab === value}
                    className={tab === value ? 'plan__tabs--active' : ''}
                    onClick={() => onTabChange(value)}
                  >
                    {value === 'plan' ? 'Plan' : 'Log'}
                  </button>
                ))}
              </div>
            )}
            <div className="daypanel__toolbar-right">
              {savedAt && <span className="plan__saved">Saved</span>}
              <button type="button" className="plan__text-btn" onClick={() => setTemplateOpen(true)}>
                <LayoutTemplate size={14} />
                Template
              </button>
            </div>
          </div>

          <div className="daypanel__body">
            {split ? (
              <div className="daypanel__cols">
                <PlanSection {...props} expanded={expandedPlan} onToggleExpand={toggleExpanded(setExpandedPlan)} />
                <LogSection {...props} collapsed={collapsedLog} onToggleCollapse={toggleCollapsed(setCollapsedLog)} />
              </div>
            ) : (
              <>
                <div role="tabpanel" aria-label="Plan" hidden={tab !== 'plan'}>
                  <PlanSection {...props} expanded={expandedPlan} onToggleExpand={toggleExpanded(setExpandedPlan)} />
                </div>
                <div role="tabpanel" aria-label="Log" hidden={tab !== 'log'}>
                  <LogSection {...props} collapsed={collapsedLog} onToggleCollapse={toggleCollapsed(setCollapsedLog)} />
                </div>
              </>
            )}
          </div>

          <div className="daypanel__footer">
            <button
              type="button"
              className="profile__save daypanel__log-btn"
              onClick={props.onLogSession}
              disabled={props.saving}
            >
              {props.saving ? <Loader2 className="page__spinner" size={16} /> : 'Log session'}
            </button>
          </div>
        </>
      )}

      <TemplatePopover
        open={templateOpen}
        templates={props.templates}
        templateKey={props.templateKey}
        templateDate={props.templateDate}
        applying={props.applyingTemplate}
        onKeyChange={props.onTemplateKey}
        onDateChange={props.onTemplateDate}
        onApply={props.onApplyTemplate}
        onClose={() => setTemplateOpen(false)}
      />
    </>
  )
}

function toggleCollapsed(setter: Dispatch<SetStateAction<Record<string, boolean>>>) {
  return (id: string) =>
    setter((prev) => ({ ...prev, [id]: !prev[id] }))
}

function toggleExpanded(setter: Dispatch<SetStateAction<Record<string, boolean>>>) {
  return (id: string) =>
    setter((prev) => ({ ...prev, [id]: !prev[id] }))
}

function PlanSection({
  planTitle,
  onPlanTitle,
  planDayType,
  onPlanDayType,
  planning,
  onCreatePlan,
  planned,
  draftFor,
  onDraft,
  onAutosave,
  onComplete,
  onDeletePlanned,
  expanded,
  onToggleExpand,
}: DayPanelProps & {
  expanded: Record<string, boolean>
  onToggleExpand: (id: string) => void
}) {
  return (
    <section aria-label="Planned sessions">
      <div className="daypanel__plan-row">
        <input
          type="text"
          className="plan__input"
          placeholder="Session title (optional)"
          aria-label="Session title"
          value={planTitle}
          onChange={(event) => onPlanTitle(event.target.value)}
        />
        <SegmentedControl
          label="Day type"
          name="plan-day-type"
          options={DAY_TYPE_OPTIONS}
          value={planDayType}
          onChange={onPlanDayType}
        />
        <button
          type="button"
          className="profile__save daypanel__plan-btn"
          onClick={onCreatePlan}
          disabled={planning}
        >
          <Plus size={16} />
          Plan session
        </button>
      </div>

      {planned.length === 0 ? (
        <p className="plan__hint">Nothing planned.</p>
      ) : (
        <ul className="plan__session-list">
          {planned.map((session) => (
            <li key={session.id} className="plan__session plan__session--slim">
              <div className="plan__session-header">
                <input
                  className="plan__session-title-input"
                  aria-label="Session title"
                  value={draftFor(session)?.title ?? session.title ?? ''}
                  onChange={(event) => {
                    onDraft(session.id, { title: event.target.value })
                    onAutosave(session, { title: event.target.value || null })
                  }}
                />
                <span className="plan__session-type">{session.day_type.replace('_', ' ')}</span>
                {session.status === 'completed' && (
                  <span className="plan__badge plan__badge--done">Done</span>
                )}
                <button
                  type="button"
                  className="plan__text-btn"
                  aria-expanded={!!expanded[session.id]}
                  aria-label={`Details for ${session.title ?? 'session'}`}
                  onClick={() => onToggleExpand(session.id)}
                >
                  {expanded[session.id] ? 'Hide' : 'Details'}
                </button>
                <button
                  type="button"
                  className="plan__icon-btn"
                  onClick={() => onDeletePlanned(session)}
                  aria-label="Delete planned session"
                >
                  <Trash2 size={16} />
                </button>
              </div>
              {expanded[session.id] && (
                <div className="plan__session-detail">
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
                              onChange={() => onComplete(session)}
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
                    value={draftFor(session)?.notes ?? session.notes ?? ''}
                    onChange={(event) => {
                      onDraft(session.id, { notes: event.target.value })
                      onAutosave(session, { notes: event.target.value })
                    }}
                  />
                  {session.status !== 'completed' && (
                    <button
                      type="button"
                      className="plan__text-btn"
                      onClick={() => onComplete(session)}
                    >
                      <CheckCircle2 size={14} />
                      Mark complete
                    </button>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function summarizeSets(session: WorkoutSession): string {
  const sets = session.sets ?? []
  if (sets.length === 0) return 'No exercises'
  const first = sets
    .slice(0, 2)
    .map((set) => `${set.exercise_name} ${set.reps ?? '—'} reps`)
    .join(' · ')
  return `${sets.length} ${sets.length === 1 ? 'exercise' : 'exercises'} — ${first}`
}

function LogSection({
  logged,
  loggedName,
  onLoggedName,
  loggedSets,
  setLoggedSets,
  logError,
  onDeleteWorkout,
  library,
  recent,
  onLibraryExercise,
  collapsed,
  onToggleCollapse,
}: DayPanelProps & {
  collapsed: Record<string, boolean>
  onToggleCollapse: (id: string) => void
}) {
  return (
    <section aria-label="Logged sessions">
      <h3 className="plan__section-label">
        <Dumbbell size={14} />
        Logged
      </h3>
      {logged.length === 0 ? (
        <p className="plan__hint">Nothing logged for this day yet.</p>
      ) : (
        <ul className="plan__session-list">
          {logged.map((session) => (
            <li key={session.id} className="plan__session plan__session--slim">
              <div className="plan__session-header">
                <button
                  type="button"
                  className="plan__session-toggle"
                  aria-expanded={!collapsed[session.id]}
                  onClick={() => onToggleCollapse(session.id)}
                >
                  <span className="plan__session-name">{session.name ?? 'Session'}</span>
                  <span className="plan__session-summary">{summarizeSets(session)}</span>
                </button>
                <button
                  type="button"
                  className="plan__icon-btn"
                  onClick={() => onDeleteWorkout(session)}
                  aria-label={`Delete ${session.name ?? 'session'}`}
                >
                  <Trash2 size={16} />
                </button>
              </div>
              {!collapsed[session.id] && (
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
              )}
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
          onChange={(event) => onLoggedName(event.target.value)}
        />
        {loggedSets.map((set, index) => (
          <div key={index} className="plan__exercise-card">
            <ExerciseCombobox
              value={set.exercise_name}
              library={library}
              recent={recent}
              onLibraryChange={onLibraryExercise}
              onChange={(value) =>
                setLoggedSets((prev) =>
                  prev.map((item, i) => (i === index ? { ...item, exercise_name: value } : item)),
                )
              }
            />
            <div className="plan__exercise-grid">
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
              <SegmentedControl
                label="Weight unit"
                name={`weight-unit-${index}`}
                options={[
                  { value: 'kg', label: 'kg' },
                  { value: 'lb', label: 'lb' },
                ]}
                value={set.weight_unit}
                onChange={(value) =>
                  setLoggedSets((prev) =>
                    prev.map((item, i) =>
                      i === index ? { ...item, weight_unit: value as 'kg' | 'lb' } : item,
                    ),
                  )
                }
              />
              <button
                type="button"
                className="plan__icon-btn"
                onClick={() => setLoggedSets((prev) => prev.filter((_, i) => i !== index))}
                aria-label="Remove set"
              >
                <Trash2 size={16} />
              </button>
            </div>
          </div>
        ))}
        {logError && (
          <p className="field__error" role="alert">
            {logError}
          </p>
        )}
        <button
          type="button"
          className="plan__text-btn"
          onClick={() => setLoggedSets((prev) => [...prev, emptyLoggedSet()])}
        >
          <Plus size={14} />
          Add exercise
        </button>
      </div>
    </section>
  )
}

export function Stepper({
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
