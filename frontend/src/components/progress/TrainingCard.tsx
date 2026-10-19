import { TrendingUp } from 'lucide-react'
import type { DerivedMetrics } from '../../types'

interface TrainingCardProps {
  derived: DerivedMetrics | null
  loading: boolean
  /** Active range caption, e.g. "Last 30 days". */
  rangeLabel: string
}

/**
 * Training totals from /progress/derived, requested for the active range, so the
 * card only describes the same window the chart and summary are showing.
 */
export function TrainingCard({ derived, loading, rangeLabel }: TrainingCardProps) {
  const plannedRate = derived?.planned_sessions
    ? Math.round((derived.planned_completion_rate ?? 0) * 100)
    : null

  return (
    <section className="card card--training" aria-label="Training">
      <h2 className="card__title">
        <TrendingUp size={16} />
        Training
        <span className="card__subtitle">{rangeLabel}</span>
      </h2>
      {loading ? (
        <div className="training-grid" aria-hidden="true">
          {[0, 1, 2, 3, 4, 5].map((index) => (
            <div key={index} className="training-cell">
              <div className="skeleton skeleton--label" />
              <div className="skeleton skeleton--value" />
            </div>
          ))}
        </div>
      ) : (
        derived && (
          <>
            <div className="training-grid">
              <div className="training-cell">
                <span className="stat__label">Sessions</span>
                <span className="stat__value">{derived.sessions_completed}</span>
                <span className="stat__caption">completed</span>
              </div>
              <div className="training-cell">
                <span className="stat__label">Active days</span>
                <span className="stat__value">{derived.active_days}</span>
                <span className="stat__caption">with a session</span>
              </div>
              <div className="training-cell">
                <span className="stat__label">Volume</span>
                <span className="stat__value">{derived.total_volume_kg.toLocaleString()} kg</span>
                <span className="stat__caption">lifted</span>
              </div>
              <div className="training-cell">
                <span className="stat__label">Planned done</span>
                <span className="stat__value">{plannedRate === null ? '—' : `${plannedRate}%`}</span>
                <span className="stat__caption">
                  {derived.planned_sessions === 0
                    ? 'nothing planned'
                    : `${derived.planned_completed} of ${derived.planned_sessions}`}
                </span>
                {plannedRate !== null && (
                  <span className="progress-bar" aria-hidden="true">
                    <span className="progress-bar__fill" style={{ width: `${Math.min(plannedRate, 100)}%` }} />
                  </span>
                )}
              </div>
              <div className="training-cell">
                <span className="stat__label">Current streak</span>
                <span className="stat__value">{derived.current_streak_days} d</span>
                <span className="stat__caption">consecutive days</span>
              </div>
              <div className="training-cell">
                <span className="stat__label">Longest streak</span>
                <span className="stat__value">{derived.longest_streak_days} d</span>
                <span className="stat__caption">best run</span>
              </div>
            </div>
            <WeeklySessions weeks={derived.weekly_sessions} />
          </>
        )
      )}
    </section>
  )
}

/** Existing weekly_sessions, drawn as a compact strip: one bar per recorded week. */
function WeeklySessions({ weeks }: { weeks: DerivedMetrics['weekly_sessions'] }) {
  const recent = weeks.slice(-8)
  if (recent.length < 2) return null
  const max = Math.max(...recent.map((week) => week.sessions), 1)
  return (
    <div className="training-weeks">
      <span className="stat__label">Sessions per week</span>
      <div className="training-weeks__bars" role="img" aria-label={describeWeeks(recent)}>
        {recent.map((week) => (
          <span key={week.week_of} className="training-week" title={`Week of ${week.week_of}: ${week.sessions}`}>
            <span
              className="training-week__bar"
              style={{ height: `${Math.max((week.sessions / max) * 28, 3)}px` }}
            />
            <span className="training-week__value">{week.sessions}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

const describeWeeks = (weeks: DerivedMetrics['weekly_sessions']): string =>
  `Sessions per week: ${weeks.map((week) => `${week.sessions} in the week of ${week.week_of}`).join(', ')}`