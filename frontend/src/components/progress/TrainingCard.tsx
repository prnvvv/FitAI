import { TrendingUp } from 'lucide-react'
import type { DerivedMetrics } from '../../types'

interface TrainingCardProps {
  derived: DerivedMetrics | null
  loading: boolean
}

/**
 * Training totals from /progress/derived. That endpoint carries its own window
 * and is not re-fetched per range, so this card is never labelled with the
 * selected range.
 */
export function TrainingCard({ derived, loading }: TrainingCardProps) {
  const plannedRate = derived?.planned_sessions
    ? Math.round((derived.planned_completion_rate ?? 0) * 100)
    : null

  return (
    <section className="card card--training" aria-label="Training">
      <h2 className="card__title">
        <TrendingUp size={16} />
        Training
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
          <div className="training-grid">
            <div className="training-cell">
              <span className="stat__label">Sessions</span>
              <span className="stat__value">{derived.sessions_completed}</span>
            </div>
            <div className="training-cell">
              <span className="stat__label">Active days</span>
              <span className="stat__value">{derived.active_days}</span>
            </div>
            <div className="training-cell">
              <span className="stat__label">Volume</span>
              <span className="stat__value">{derived.total_volume_kg.toLocaleString()} kg</span>
            </div>
            <div className="training-cell">
              <span className="stat__label">Planned done</span>
              <span className="stat__value">{plannedRate === null ? '—' : `${plannedRate}%`}</span>
              {plannedRate !== null && (
                <span className="progress-bar" aria-hidden="true">
                  <span className="progress-bar__fill" style={{ width: `${Math.min(plannedRate, 100)}%` }} />
                </span>
              )}
            </div>
            <div className="training-cell">
              <span className="stat__label">Current streak</span>
              <span className="stat__value">{derived.current_streak_days} d</span>
            </div>
            <div className="training-cell">
              <span className="stat__label">Longest streak</span>
              <span className="stat__value">{derived.longest_streak_days} d</span>
            </div>
          </div>
        )
      )}
    </section>
  )
}