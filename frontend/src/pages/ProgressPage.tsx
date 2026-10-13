import { TrendingUp } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../services/api'
import type { Memory } from '../types'

export function ProgressPage() {
  const [weightHistory, setWeightHistory] = useState<Memory[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .listMemory(100)
      .then((page) => {
        const weights = page.items.filter(
          (m) => m.key.toLowerCase().includes('weight') && m.effective_at,
        )
        setWeightHistory(weights)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const values = weightHistory
    .map((m) => Number(m.value))
    .filter((v) => !Number.isNaN(v))

  const min = values.length ? Math.min(...values) : null
  const max = values.length ? Math.max(...values) : null

  return (
    <div className="page page--progress">
      <header className="page__header">
        <h1>Progress</h1>
        <p>A simple view of your tracked metrics.</p>
      </header>

      {loading ? (
        <div className="page__loading">Loading…</div>
      ) : values.length === 0 ? (
        <div className="page__empty">
          <TrendingUp size={48} />
          <p>No weight history yet.</p>
          <span>Tell FitAI your current and past weights to see trends.</span>
        </div>
      ) : (
        <div className="progress__stats">
          <div className="progress__card">
            <div className="progress__label">Latest</div>
            <div className="progress__value">{values[values.length - 1]} kg</div>
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
      )}
    </div>
  )
}
