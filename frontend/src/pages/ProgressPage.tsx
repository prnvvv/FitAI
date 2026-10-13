import { TrendingUp } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../services/api'
import type { Measurement } from '../types'

export function ProgressPage() {
  const [weights, setWeights] = useState<Measurement[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .weightSeries()
      .then(setWeights)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const values = weights.map((m) => Number(m.value)).filter((v) => !Number.isNaN(v))
  const min = values.length ? Math.min(...values) : null
  const max = values.length ? Math.max(...values) : null
  const latest = values.length ? values[values.length - 1] : null

  return (
    <div className="page page--progress">
      <header className="page__header">
        <h1>Progress</h1>
        <p>Your tracked weight measurements over time.</p>
      </header>

      {loading ? (
        <div className="page__loading">Loading…</div>
      ) : values.length === 0 ? (
        <div className="page__empty">
          <TrendingUp size={48} />
          <p>No weight history yet.</p>
          <span>Record measurements to see your trends here.</span>
        </div>
      ) : (
        <>
          <div className="progress__stats">
            <div className="progress__card">
              <div className="progress__label">Latest</div>
              <div className="progress__value">{latest} kg</div>
            </div>
            <div className="progress__card">
              <div className="progress__label">Lowest</div>
              <div className="progress__value">{min} kg</div>
            </div>
            <div className="progress__card">
              <div className="progress__label">Highest</div>
              <div className="progress__value">{max} kg</div>
            </div>
            <div className="progress__card">
              <div className="progress__label">Entries</div>
              <div className="progress__value">{values.length}</div>
            </div>
          </div>

          <ul className="memory__list">
            {weights.map((m) => (
              <li key={m.id} className="memory__item">
                <div className="memory__content">
                  <div className="memory__key">{new Date(m.measured_at).toLocaleDateString()}</div>
                  <div className="memory__value">
                    {m.value} {m.unit}
                  </div>
                  {m.notes && <div className="memory__meta">{m.notes}</div>}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}