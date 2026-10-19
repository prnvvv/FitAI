import { Trash2 } from 'lucide-react'
import type { SeriesPoint } from './metrics'

interface HistoryCardProps {
  title: string
  points: SeriesPoint[]
  /** Pre-formatted "value unit" per point, computed by the page. */
  renderValue: (point: SeriesPoint) => string
  readOnly: boolean
  onDelete: (id: string) => void
  loading: boolean
}

/** Slim, internally scrolling history list with the existing delete handler. */
export function HistoryCard({ title, points, renderValue, readOnly, onDelete, loading }: HistoryCardProps) {
  return (
    <section className="card card--history" aria-label="History">
      <h2 className="card__title">{title}</h2>
      {loading ? (
        <ul className="history" aria-hidden="true">
          {[0, 1, 2].map((index) => (
            <li key={index} className="history__row">
              <div className="skeleton skeleton--line" />
            </li>
          ))}
        </ul>
      ) : points.length === 0 ? (
        <p className="history__empty">No entries in this range.</p>
      ) : (
        <ul className="history">
          {[...points].reverse().map((point) => (
            <li key={point.id} className="history__row">
              <div className="history__main">
                <span className="history__value">{renderValue(point)}</span>
                <span className="history__date">
                  {new Date(point.measured_at).toLocaleDateString(undefined, {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                  })}
                </span>
                {point.notes && <span className="history__note">{point.notes}</span>}
              </div>
              {!readOnly && (
                <button
                  type="button"
                  className="history__delete"
                  onClick={() => onDelete(point.id)}
                  aria-label="Delete entry"
                >
                  <Trash2 size={16} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}