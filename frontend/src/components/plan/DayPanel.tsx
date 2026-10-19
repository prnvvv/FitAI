import { CheckCircle2, LayoutTemplate, Loader2, MoreHorizontal, Plus, Trash2 } from 'lucide-react'
import { useRef, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { Exercise, PlannedSession, Template, WorkoutSession } from '../../types'
import { PanelMenu } from './PanelMenu'
import { SegmentedControl } from './SegmentedControl'
import { SessionEditor } from './SessionEditor'
import type { LoggedSet } from './SessionEditor'
import { TemplatePopover } from './TemplatePopover'

export type { LoggedSet } from './SessionEditor'
export { emptyLoggedSet, Stepper } from './SessionEditor'

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
  onClearLogDraft: () => void
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
  /** Days in the template window that already carry a plan, for the warning. */
  plannedDays: string[]
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

const MODE_HINTS: Record<PanelTab, string> = {
  plan: 'Schedule a session for this day',
  log: 'Record what you did',
}

/**
 * Selected-day workspace: sticky header, scrollable body, sticky footer.
 *
 * Plan and Log are two mounted panels behind one explicit switch, so typed text,
 * chosen exercises and counter values survive mode and day changes exactly as
 * before. Only the footer action changes with the mode, so the user can never
 * see a "Log session" button while planning.
 */
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
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({})
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

  const body =
    loading ? (
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
    ) : split ? (
      <div className="workspace__cols">
        <PlanBody {...props} expanded={expandedPlan} onToggleExpand={toggle(setExpandedPlan)} />
        <LogBody
          {...props}
          collapsed={collapsedLog}
          onToggleCollapse={toggle(setCollapsedLog)}
        />
      </div>
    ) : (
      <>
        <div id="workspace-panel-plan" role="tabpanel" aria-labelledby="workspace-tab-plan" aria-label="Plan" hidden={tab !== 'plan'}>
          <PlanBody {...props} expanded={expandedPlan} onToggleExpand={toggle(setExpandedPlan)} />
        </div>
        <div id="workspace-panel-log" role="tabpanel" aria-labelledby="workspace-tab-log" aria-label="Log" hidden={tab !== 'log'}>
          <LogBody {...props} collapsed={collapsedLog} onToggleCollapse={toggle(setCollapsedLog)} />
        </div>
      </>
    )

  return (
    <section className="workspace" aria-label="Day details">
      <header className="workspace__header">
        <div className="workspace__headline">
          <span className="workspace__date">{shortDayLabel(selected)}</span>
          {selected === today && <span className="plan__badge workspace__today-chip">Today</span>}
          <span className="plan__badge plan__badge--type">{statusText}</span>
        </div>
        <PanelMenu triggerLabel="Day options" trigger={<MoreHorizontal size={18} />} items={menuItems} />
      </header>

      {!loading && !error && (
        <div className="workspace__modes">
          {split ? (
            <p className="workspace__hint">{MODE_HINTS[tab]}</p>
          ) : (
            <>
              <div className="workspace__tabs" role="tablist" aria-label="Day mode">
                {(['plan', 'log'] as const).map((value) => (
                  <button
                    key={value}
                    type="button"
                    role="tab"
                    id={`workspace-tab-${value}`}
                    aria-selected={tab === value}
                    aria-controls={`workspace-panel-${value}`}
                    tabIndex={tab === value ? 0 : -1}
                    className={`workspace__tab${tab === value ? ' workspace__tab--active' : ''}`}
                    ref={(el) => {
                      tabRefs.current[value] = el
                    }}
                    onClick={() => onTabChange(value)}
                    onKeyDown={(event) => {
                      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
                      event.preventDefault()
                      const next = value === 'plan' ? 'log' : 'plan'
                      onTabChange(next)
                      // Arrow keys move focus with selection, as a tablist must.
                      tabRefs.current[next]?.focus()
                    }}
                  >
                    {value === 'plan' ? 'Plan' : 'Log'}
                  </button>
                ))}
              </div>
              <p className="workspace__hint">{MODE_HINTS[tab]}</p>
            </>
          )}
          <div className="workspace__tools">
            {savedAt && <span className="plan__saved">Saved</span>}
            <button type="button" className="plan__text-btn" onClick={() => setTemplateOpen(true)}>
              <LayoutTemplate size={14} />
              Template
            </button>
          </div>
        </div>
      )}

      <div className="workspace__body">{body}</div>

      {!loading && !error && (
        <footer className="workspace__footer">
          {split || tab === 'log' ? (
            <>
              <button type="button" className="plan__text-btn" onClick={props.onClearLogDraft}>
                Clear
              </button>
              <button
                type="button"
                className="profile__save workspace__primary"
                onClick={props.onLogSession}
                disabled={props.saving}
              >
                {props.saving ? <Loader2 className="page__spinner" size={16} /> : 'Log session'}
              </button>
            </>
          ) : (
            <button
              type="button"
              className="profile__save workspace__primary"
              onClick={props.onCreatePlan}
              disabled={props.planning}
            >
              {props.planning ? <Loader2 className="page__spinner" size={16} /> : <Plus size={16} />}
              Plan session
            </button>
          )}
        </footer>
      )}

      <div className="workspace__templates">
        <TemplatePopover
          open={templateOpen}
          templates={props.templates}
          templateKey={props.templateKey}
          templateDate={props.templateDate}
          applying={props.applyingTemplate}
          plannedDays={props.plannedDays}
          onKeyChange={props.onTemplateKey}
          onDateChange={props.onTemplateDate}
          onApply={props.onApplyTemplate}
          onClose={() => setTemplateOpen(false)}
        />
      </div>
    </section>
  )
}

/** Expand/collapse toggle factory, one per list. */
function toggle(setter: Dispatch<SetStateAction<Record<string, boolean>>>) {
  return (id: string) => setter((prev) => ({ ...prev, [id]: !prev[id] }))
}

function PlanBody({
  split,
  planning,
  onCreatePlan,
  planTitle,
  onPlanTitle,
  planDayType,
  onPlanDayType,
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
      <div className="composer">
        <label className="field composer__title">
          <span className="field__label">Session title</span>
          <input
            type="text"
            className="plan__input"
            placeholder="Optional"
            aria-label="Session title"
            value={planTitle}
            onChange={(event) => onPlanTitle(event.target.value)}
          />
        </label>
        <div className="composer__type">
          <span className="editor__field-label">Day type</span>
          <SegmentedControl
            label="Day type"
            name="plan-day-type"
            options={DAY_TYPE_OPTIONS}
            value={planDayType}
            onChange={onPlanDayType}
          />
        </div>
        {split && (
          <button
            type="button"
            className="composer__submit"
            onClick={onCreatePlan}
            disabled={planning}
          >
            <Plus size={16} />
            Plan session
          </button>
        )}
      </div>

      {planned.length === 0 ? (
        <p className="plan__hint">Nothing planned for this day.</p>
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
                  {/* Definition list instead of a six-column table: it never needs
                      horizontal scrolling, whatever the panel width is. */}
                  {session.exercises.length === 0 ? (
                    <p className="plan__hint">No exercises yet.</p>
                  ) : (
                    <dl className="detail">
                      {session.exercises.map((exercise) => (
                        <div className="detail__pair" key={exercise.id}>
                          <dt className="detail__key">{exercise.exercise_name}</dt>
                          <dd className="detail__value">
                            {[
                              exercise.target_sets != null ? `${exercise.target_sets} sets` : null,
                              exercise.target_reps != null ? `${exercise.target_reps} reps` : null,
                              exercise.target_weight != null
                                ? `${exercise.target_weight} ${exercise.target_weight_unit ?? ''}`.trim()
                                : exercise.duration_seconds != null
                                  ? `${exercise.duration_seconds}s`
                                  : exercise.distance_meters != null
                                    ? `${exercise.distance_meters} m`
                                    : null,
                            ]
                              .filter(Boolean)
                              .join(' · ') || 'No target set'}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  )}
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

function LogBody({
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
      {logged.length === 0 ? (
        <p className="plan__hint">Nothing logged yet.</p>
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

      <SessionEditor
        loggedName={loggedName}
        onLoggedName={onLoggedName}
        loggedSets={loggedSets}
        setLoggedSets={setLoggedSets}
        library={library}
        recent={recent}
        onLibraryExercise={onLibraryExercise}
        error={logError}
      />
    </section>
  )
}