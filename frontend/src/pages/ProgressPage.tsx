import { AlertCircle, Loader2, Plus, Scale, Trash2, TrendingUp } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../services/api'
import type { Measurement } from '../types'

type Range = '7d' | '30d' | '90d' | '1y' | 'all'

const RANGE_OPTIONS: { value: Range; label: string }[] = [
  { value: '7d', label: '7D' },
  { value: '30d', label: '30D' },
  { value: '90d', label: '90D' },
  { value: '1y', label: '1Y' },
  { value: 'all', label: 'All' },
]

function formatDateInput(d: Date): string {
  return d.toISOString().split('T')[0]
}

export function ProgressPage() {
  const [weights, setWeights] = useState<Measurement[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [range, setRange] = useState<Range>('30d')
  const [saving, setSaving] = useState(false)
  const [showLog, setShowLog] = useState(false)
  const [logValue, setLogValue] = useState('')
  const [logDate, setLogDate] = useState(() => formatDateInput(new Date()))

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.weightSeries()
      setWeights(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load progress')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const [now] = useState(() => new Date())
  const filtered = useMemo(() => {
    if (range === 'all') return weights
    const days = range === '7d' ? 7 : range === '30d' ? 30 : range === '90d' ? 90 : 365
    const cutoff = new Date(now.getFullYear(), now.getMonth(), now.getDate() - days)
    return weights.filter((w) => new Date(w.measured_at) >= cutoff)
  }, [weights, range, now])

  const values = useMemo(
    () => filtered.map((m) => Number(m.value)).filter((v) => !Number.isNaN(v)),
    [filtered],
  )
  const latest = values.length ? values[values.length - 1] : null
  const min = values.length ? Math.min(...values) : null
  const max = values.length ? Math.max(...values) : null
  const change =
    values.length > 1 ? Number((values[values.length - 1] - values[0]).toFixed(2)) : null

  const handleLog = async () => {
    const value = Number(logValue)
    if (Number.isNaN(value) || value <= 0) return
    setSaving(true)
    try {
      await api.createMeasurement({
        type: 'weight',
        value,
        unit: 'kg',
        measured_at: new Date(logDate).toISOString(),
      })
      await load()
      setLogValue('')
      setShowLog(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save entry')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this entry?')) return
    try {
      await api.deleteMeasurement(id)
      setWeights((prev) => prev.filter((m) => m.id !== id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete entry')
    }
  }

  return (
    <div className="page page--progress">
      <header className="page__header page__header--row">
        <div>
          <h1>Progress</h1>
          <p>Track how you're doing over time.</p>
        </div>
        <div className="progress__header-actions">
          <div className="progress__range" role="tablist">
            {RANGE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                role="tab"
                aria-selected={range === opt.value}
                className={range === opt.value ? 'progress__range--active' : ''}
                onClick={() => setRange(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <button type="button" className="profile__save" onClick={() => setShowLog((v) => !v)}>
            <Plus size={16} />
            Log
          </button>
        </div>
      </header>

      {error && (
        <div className="page__alert page__alert--error">
          <AlertCircle size={18} />
          {error}
          <button type="button" className="page__alert-action" onClick={load}>
            Retry
          </button>
        </div>
      )}

      {showLog && (
        <div className="progress__log-sheet">
          <h3 className="plan__section-label">Log weight</h3>
          <div className="progress__log-row">
            <input
              type="date"
              className="plan__input"
              value={logDate}
              onChange={(e) => setLogDate(e.target.value)}
            />
            <input
              type="number"
              className="plan__input plan__input--number"
              placeholder="kg"
              min={0}
              step={0.1}
              value={logValue}
              onChange={(e) => setLogValue(e.target.value)}
            />
            <button type="button" className="profile__save" onClick={handleLog} disabled={saving}>
              {saving ? <Loader2 className="page__spinner" size={16} /> : 'Save'}
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="page__loading">
          <Loader2 className="page__spinner" size={24} />
        </div>
      ) : values.length === 0 ? (
        <div className="page__empty page__empty--compact">
          <Scale size={32} />
          <p>No weight entries yet.</p>
          <span>Log your first measurement to start tracking.</span>
        </div>
      ) : (
        <>
          <div className="progress__stats">
            <div className="progress__card">
              <div className="progress__label">Latest</div>
              <div className="progress__value">{latest} <span className="progress__unit">kg</span></div>
            </div>
            <div className="progress__card">
              <div className="progress__label">Change</div>
              <div className={`progress__value ${change != null && change > 0 ? 'progress__value--up' : change != null && change < 0 ? 'progress__value--down' : ''}`}>
                {change != null ? `${change > 0 ? '+' : ''}${change} kg` : '—'}
              </div>
            </div>
            <div className="progress__card">
              <div className="progress__label">Range</div>
              <div className="progress__value">{min}–{max}</div>
            </div>
            <div className="progress__card">
              <div className="progress__label">Entries</div>
              <div className="progress__value">{values.length}</div>
            </div>
          </div>

          <div className="progress__chart">
            <svg viewBox={`0 0 ${Math.max(filtered.length * 12, 200)} 120`} preserveAspectRatio="none">
              {values.length > 1 && (
                <polyline
                  fill="none"
                  stroke="var(--accent)"
                  strokeWidth="2"
                  points={values
                    .map((v, i) => `${i * 12 + 6},${120 - ((v - (min ?? 0)) / ((max ?? 1) - (min ?? 0) || 1)) * 100}`)
                    .join(' ')}
                />
              )}
              {values.map((v, i) => (
                <circle
                  key={i}
                  cx={i * 12 + 6}
                  cy={120 - ((v - (min ?? 0)) / ((max ?? 1) - (min ?? 0) || 1)) * 100}
                  r="3"
                  fill="var(--accent)"
                />
              ))}
            </svg>
          </div>

          <h3 className="plan__section-label">History</h3>
          <ul className="library__list">
            {[...filtered].reverse().map((m) => (
              <li key={m.id} className="library__item">
                <div className="library__icon">
                  <TrendingUp size={18} />
                </div>
                <div className="library__info">
                  <div className="library__name">{Number(m.value).toFixed(2)} kg</div>
                  <div className="library__meta">{new Date(m.measured_at).toLocaleDateString()}</div>
                </div>
                <button
                  type="button"
                  className="library__delete"
                  onClick={() => handleDelete(m.id)}
                  aria-label="Delete entry"
                >
                  <Trash2 size={16} />
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
