import { AlertCircle, Loader2, Plus, Ruler, Scale, Trash2, TrendingUp, Undo2, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api, toMessage, validationIssues } from '../services/api'
import type { BmiPoint, DerivedMetrics, Measurement, Profile } from '../types'
import {
  BMI_CATEGORY_LABELS,
  bmiCategory,
  formatHeight,
  formatWeight,
  kgToLb,
  lbToKg,
  parseHeightInput,
  toDateKey,
} from '../utils/dates'

type Range = '7d' | '30d' | '90d' | '1y' | 'all'
type MetricKey = 'weight' | 'height' | 'body_fat_percent' | 'waist' | 'sleep_hours' | 'steps' | 'bmi'

const RANGE_OPTIONS: { value: Range; label: string }[] = [
  { value: '7d', label: '7D' },
  { value: '30d', label: '30D' },
  { value: '90d', label: '90D' },
  { value: '1y', label: '1Y' },
  { value: 'all', label: 'All' },
]

interface MetricDef {
  key: MetricKey
  label: string
  canonicalUnit: string
  altUnit: string | null
  min: number
  max: number
  step: number
}

const METRICS: MetricDef[] = [
  { key: 'weight', label: 'Weight', canonicalUnit: 'kg', altUnit: 'lb', min: 20, max: 500, step: 0.1 },
  { key: 'height', label: 'Height', canonicalUnit: 'cm', altUnit: 'in', min: 50, max: 260, step: 0.5 },
  { key: 'body_fat_percent', label: 'Body fat', canonicalUnit: '%', altUnit: null, min: 1, max: 70, step: 0.1 },
  { key: 'waist', label: 'Waist', canonicalUnit: 'cm', altUnit: 'in', min: 30, max: 250, step: 0.5 },
  { key: 'sleep_hours', label: 'Sleep', canonicalUnit: 'h', altUnit: null, min: 0, max: 24, step: 0.1 },
  { key: 'steps', label: 'Steps', canonicalUnit: 'steps', altUnit: null, min: 0, max: 200000, step: 100 },
]

const METRIC_BY_KEY = Object.fromEntries(METRICS.map((metric) => [metric.key, metric])) as Record<
  MetricKey,
  MetricDef
>

interface SeriesPoint {
  id: string
  value: number
  measured_at: string
  unit: string
}

function toPoints(measurements: Measurement[]): SeriesPoint[] {
  return measurements.map((m) => ({
    id: m.id,
    value: Number(m.value),
    measured_at: m.measured_at,
    unit: m.unit,
  }))
}

function bmiToPoints(points: BmiPoint[]): SeriesPoint[] {
  return points.map((point) => ({
    id: `bmi-${point.measured_at}`,
    value: Number(point.value),
    measured_at: point.measured_at,
    unit: 'BMI',
  }))
}

/** "Change" is meaningless for a single entry; range collapses when min == max. */
export function summarise(values: number[]): {
  latest: number | null
  change: number | null
  rangeLabel: string
  entries: number
} {
  if (values.length === 0) return { latest: null, change: null, rangeLabel: '—', entries: 0 }
  const min = Math.min(...values)
  const max = Math.max(...values)
  const trim = (value: number) => Number(value.toFixed(1))
  return {
    latest: trim(values[values.length - 1]),
    change: values.length > 1 ? trim(values[values.length - 1] - values[0]) : null,
    rangeLabel: min === max ? String(trim(min)) : `${trim(min)}–${trim(max)}`,
    entries: values.length,
  }
}

function ProgressChart({
  points,
  unit,
  label,
}: {
  points: SeriesPoint[]
  unit: string
  label: string
}) {
  if (points.length === 0) {
    return (
      <div className="progress__chart-empty" role="status">
        <p>No {label.toLowerCase()} entries in this range yet.</p>
      </div>
    )
  }

  const data = points.map((point) => ({
    date: new Date(point.measured_at).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
    }),
    fullDate: new Date(point.measured_at).toLocaleDateString(undefined, {
      weekday: 'short',
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    }),
    value: point.value,
  }))

  const values = points.map((point) => point.value)
  const description =
    points.length === 1
      ? `One entry: ${values[0].toFixed(1)} ${unit} on ${new Date(points[0].measured_at).toLocaleDateString()}`
      : `${points.length} entries from ${values[0].toFixed(1)} to ${values[values.length - 1].toFixed(1)} ${unit}`

  return (
    <div className="progress__chart-wrap">
      <div
        className="progress__chart"
        role="img"
        aria-label={`${label} chart. ${description}`}
      >
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id={`gradient-${label}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.2} />
                <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--divider)" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
              axisLine={{ stroke: 'var(--divider)' }}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
              axisLine={false}
              tickLine={false}
              domain={['auto', 'auto']}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--bg-popover)',
                border: '1px solid var(--popover-border)',
                borderRadius: '8px',
                boxShadow: 'var(--shadow-md)',
                fontSize: '0.8125rem',
              }}
              labelStyle={{ color: 'var(--text-secondary)', marginBottom: '4px' }}
              formatter={(value) => [`${Number(value).toFixed(1)} ${unit}`, label]}
              labelFormatter={(_, payload) => {
                if (payload && payload.length > 0) {
                  return (payload[0].payload as { fullDate: string }).fullDate
                }
                return ''
              }}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke="var(--accent)"
              strokeWidth={2}
              fill={`url(#gradient-${label})`}
              dot={{ r: 3, fill: 'var(--accent)', strokeWidth: 0 }}
              activeDot={{ r: 5, fill: 'var(--accent)', strokeWidth: 0 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <details className="progress__chart-table">
        <summary>View as table</summary>
        <table>
          <caption className="visually-hidden">{label} entries</caption>
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">{label}</th>
            </tr>
          </thead>
          <tbody>
            {[...points].reverse().map((point) => (
              <tr key={point.id}>
                <td>{new Date(point.measured_at).toLocaleDateString()}</td>
                <td>
                  {point.value.toFixed(1)} {unit}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  )
}

interface DraftMetric {
  key: MetricKey
  value: string
  unit: string
}

export function ProgressPage() {
  const [metric, setMetric] = useState<MetricKey>('weight')
  const [range, setRange] = useState<Range>('30d')
  const [units, setUnits] = useState<'metric' | 'imperial'>('metric')
  const [age, setAge] = useState<number | null>(null)

  const [series, setSeries] = useState<Record<string, SeriesPoint[]>>({})
  const [bmiPoints, setBmiPoints] = useState<SeriesPoint[]>([])
  const [hasHeight, setHasHeight] = useState(false)
  const [latestBmi, setLatestBmi] = useState<number | null>(null)
  const [derived, setDerived] = useState<DerivedMetrics | null>(null)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showLog, setShowLog] = useState(false)
  const [focusMetric, setFocusMetric] = useState<MetricKey>('weight')
  const [logDate, setLogDate] = useState(() => toDateKey(new Date()))
  const [logNote, setLogNote] = useState('')
  const [drafts, setDrafts] = useState<DraftMetric[]>([])
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [savedNote, setSavedNote] = useState<string | null>(null)
  const [undo, setUndo] = useState<(() => void) | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [profile, weights, heights, bmi, derivedMetrics] = await Promise.all([
        api.getProfile(),
        api.weightSeries(),
        api.heightSeries(),
        api.bmiSeries(),
        api.derivedMetrics(),
      ])
      applyProfile(profile)
      setSeries({ weight: toPoints(weights), height: toPoints(heights) })
      setHasHeight(heights.length > 0)
      const bmiSeries = bmiToPoints(bmi)
      setBmiPoints(bmiSeries)
      setLatestBmi(bmiSeries.length ? bmiSeries[bmiSeries.length - 1].value : null)
      setDerived(derivedMetrics)
    } catch (err) {
      setError(toMessage(err, 'Your progress could not be loaded.'))
    } finally {
      setLoading(false)
    }
  }, [])

  const applyProfile = (profile: Profile) => {
    if (profile.preferences?.units === 'imperial') setUnits('imperial')
    if (profile.age) setAge(profile.age)
    else if (profile.date_of_birth) {
      const dob = new Date(profile.date_of_birth)
      const now = new Date()
      let years = now.getFullYear() - dob.getFullYear()
      const hadBirthday =
        now.getMonth() > dob.getMonth() ||
        (now.getMonth() === dob.getMonth() && now.getDate() >= dob.getDate())
      if (!hadBirthday) years -= 1
      setAge(years)
    }
  }

  useEffect(() => {
    void load()
  }, [load])

  const points = useMemo(() => (metric === 'bmi' ? bmiPoints : series[metric] ?? []), [bmiPoints, metric, series])

  const filtered = useMemo(() => {
    if (range === 'all') return points
    const days = range === '7d' ? 7 : range === '30d' ? 30 : range === '90d' ? 90 : 365
    const cutoff = new Date()
    cutoff.setDate(cutoff.getDate() - days)
    return points.filter((point) => new Date(point.measured_at) >= cutoff)
  }, [points, range])

  const definition = metric === 'bmi' ? null : METRIC_BY_KEY[metric]
  const summary = useMemo(() => summarise(filtered.map((point) => point.value)), [filtered])
  const displayUnit =
    metric === 'bmi'
      ? ''
      : units === 'imperial' && definition?.altUnit
        ? definition.altUnit
        : definition?.canonicalUnit ?? ''

  const convertForDisplay = (value: number): number => {
    if (units !== 'imperial' || !definition?.altUnit) return value
    if (metric === 'weight') return kgToLb(value)
    if (metric === 'height') return value / 2.54
    return value
  }

  const displayPoints = useMemo(
    () => filtered.map((point) => ({ ...point, value: convertForDisplay(point.value) })),
    [filtered, units, metric],
  )

  const openLog = (target: MetricKey) => {
    setFocusMetric(target)
    setDrafts([
      { key: 'weight', value: '', unit: units === 'imperial' ? 'lb' : 'kg' },
      { key: 'height', value: '', unit: units === 'imperial' ? 'in' : 'cm' },
    ])
    setFieldErrors({})
    setLogDate(toDateKey(new Date()))
    setLogNote('')
    setShowLog(true)
  }

  const validateDrafts = (): { ok: boolean; entries: { type: string; value: number; unit: string }[]; errors: Record<string, string> } => {
    const entries: { type: string; value: number; unit: string }[] = []
    const errors: Record<string, string> = {}
    for (const draft of drafts) {
      if (draft.value.trim() === '') continue
      const def = METRIC_BY_KEY[draft.key]
      const raw = Number(draft.value)
      if (!Number.isFinite(raw)) {
        errors[draft.key] = 'Enter a number.'
        continue
      }
      const canonical = draft.key === 'height' ? parseHeightInput(draft.value, draft.unit) : draft.key === 'weight' && draft.unit === 'lb' ? lbToKg(raw) : raw
      if (canonical === null) {
        errors[draft.key] = 'Enter a number.'
        continue
      }
      if (canonical < def.min || canonical > def.max) {
        errors[draft.key] = `${def.label} must be between ${def.min} and ${def.max} ${def.canonicalUnit}.`
        continue
      }
      entries.push({
        type: draft.key,
        value: canonical,
        unit: draft.key === 'height' ? 'cm' : def.canonicalUnit,
      })
    }
    if (entries.length === 0 && Object.keys(errors).length === 0) {
      errors.form = 'Enter at least one measurement.'
    }
    // Any invalid field blocks the whole save so nothing is silently dropped.
    return { ok: entries.length > 0 && Object.keys(errors).length === 0, entries, errors }
  }

  const handleLog = async () => {
    const { ok, entries, errors } = validateDrafts()
    setFieldErrors(errors)
    if (!ok) return
    setSaving(true)
    try {
      for (const entry of entries) {
        await api.createMeasurement({
          type: entry.type,
          value: Number(entry.value.toFixed(2)),
          unit: entry.unit,
          measured_at: new Date(`${logDate}T08:00:00`).toISOString(),
          notes: logNote.trim() || undefined,
        })
      }
      setShowLog(false)
      setSavedNote('Saved')
      await load()
    } catch (err) {
      const issues = validationIssues(err)
      if (issues.length) {
        setFieldErrors({ form: issues.map((issue) => issue.message).join(' ') })
      } else {
        setFieldErrors({ form: toMessage(err, 'That entry could not be saved.') })
      }
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await api.deleteMeasurement(id)
      setUndo(() => () => void load())
      await load()
    } catch (err) {
      setError(toMessage(err, 'That entry could not be deleted.'))
    }
  }

  const bmiLabel = latestBmi === null ? null : age !== null && age < 18 ? null : BMI_CATEGORY_LABELS[bmiCategory(latestBmi)]

  return (
    <div className="page page--progress">
      <header className="page__header page__header--row">
        <div>
          <h1>Progress</h1>
          <p>Track how you're doing over time.</p>
        </div>
        <div className="progress__header-actions">
          <div className="progress__range" role="tablist" aria-label="Range">
            {RANGE_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                role="tab"
                aria-selected={range === option.value}
                className={range === option.value ? 'progress__range--active' : ''}
                onClick={() => setRange(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="progress__unit-toggle"
            onClick={() => setUnits((value) => (value === 'metric' ? 'imperial' : 'metric'))}
            aria-label="Toggle units"
          >
            {units === 'metric' ? 'kg / cm' : 'lb / in'}
          </button>
          <button type="button" className="profile__save" onClick={() => openLog(metric === 'bmi' ? 'weight' : metric)}>
            <Plus size={16} />
            Log
          </button>
        </div>
      </header>

      <div className="progress__tabs" role="tablist" aria-label="Metric">
        {[...METRICS.map((item) => item.key), 'bmi' as const].map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={metric === key}
            className={metric === key ? 'progress__tabs--active' : ''}
            onClick={() => setMetric(key)}
          >
            {key === 'bmi' ? 'BMI' : METRIC_BY_KEY[key].label}
          </button>
        ))}
      </div>

      {error && (
        <div className="page__alert page__alert--error" role="alert">
          <AlertCircle size={18} />
          <span>{error}</span>
          <button type="button" className="page__alert-action" onClick={() => void load()}>
            Retry
          </button>
          <button type="button" className="page__alert-close" onClick={() => setError(null)} aria-label="Dismiss">
            <X size={16} />
          </button>
        </div>
      )}

      {showLog && (
        <div className="progress__log-sheet" role="dialog" aria-label="Log measurements">
          <div className="progress__log-head">
            <h3 className="plan__section-label">Log measurements</h3>
            <button type="button" className="plan__nav-btn" onClick={() => setShowLog(false)} aria-label="Close">
              <X size={16} />
            </button>
          </div>
          <div className="progress__log-row">
            <label className="field">
              <span className="field__label">Date</span>
              <input
                type="date"
                className="plan__input"
                value={logDate}
                onChange={(event) => setLogDate(event.target.value)}
              />
            </label>
            <label className="field">
              <span className="field__label">Note (optional)</span>
              <input
                type="text"
                className="plan__input"
                value={logNote}
                onChange={(event) => setLogNote(event.target.value)}
              />
            </label>
          </div>
          {drafts.map((draft) => {
            const def = METRIC_BY_KEY[draft.key]
            const unitOptions =
              draft.key === 'height'
                ? units === 'imperial'
                  ? ['in', 'ft_in', 'cm']
                  : ['cm', 'in']
                : draft.key === 'weight'
                  ? ['kg', 'lb']
                  : [def.canonicalUnit]
            return (
              <div key={draft.key} className="progress__log-row">
                <label className="field">
                  <span className="field__label">{def.label}</span>
                  <input
                    type="text"
                    inputMode="decimal"
                    className="plan__input"
                    autoFocus={draft.key === focusMetric}
                    aria-label={def.label}
                    value={draft.value}
                    onChange={(event) =>
                      setDrafts((prev) =>
                        prev.map((item) => (item.key === draft.key ? { ...item, value: event.target.value } : item)),
                      )
                    }
                  />
                </label>
                <select
                  className="plan__input plan__input--unit"
                  aria-label={`${def.label} unit`}
                  value={draft.unit}
                  onChange={(event) =>
                    setDrafts((prev) =>
                      prev.map((item) => (item.key === draft.key ? { ...item, unit: event.target.value } : item)),
                    )
                  }
                >
                  {unitOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
                {fieldErrors[draft.key] && (
                  <p className="field__error" role="alert">
                    {fieldErrors[draft.key]}
                  </p>
                )}
              </div>
            )
          })}
          <div className="progress__log-row progress__log-row--more">
            <select
              className="plan__input"
              aria-label="Add another metric"
              value=""
              onChange={(event) => {
                const key = event.target.value as MetricKey
                if (!key) return
                const def = METRIC_BY_KEY[key]
                setDrafts((prev) => [
                  ...prev.filter((item) => item.key !== key),
                  { key, value: '', unit: def.canonicalUnit },
                ])
              }}
            >
              <option value="">Add another metric…</option>
              {METRICS.filter((def) => !drafts.some((item) => item.key === def.key)).map((def) => (
                <option key={def.key} value={def.key}>
                  {def.label}
                </option>
              ))}
            </select>
            <button type="button" className="profile__save" onClick={handleLog} disabled={saving}>
              {saving ? <Loader2 className="page__spinner" size={16} /> : 'Save'}
            </button>
          </div>
          {fieldErrors.form && (
            <p className="field__error" role="alert">
              {fieldErrors.form}
            </p>
          )}
        </div>
      )}

      {loading ? (
        <div className="page__loading">
          <Loader2 className="page__spinner" size={24} />
        </div>
      ) : (
        <>
          {metric === 'bmi' && (
            <div className="progress__bmi-card">
              {hasHeight ? (
                <>
                  <div className="progress__label">BMI</div>
                  <div className="progress__value">
                    {latestBmi !== null ? latestBmi.toFixed(1) : '—'}
                    {bmiLabel && <span className="progress__bmi-label">{bmiLabel}</span>}
                  </div>
                  <p className="progress__note">
                    BMI is a rough screening measure. It doesn't account for muscle mass or age, and it
                    isn't a diagnosis.
                  </p>
                </>
              ) : (
                <div className="progress__bmi-empty">
                  <p>Add your height to see BMI.</p>
                  <button type="button" className="profile__save" onClick={() => openLog('height')}>
                    <Ruler size={16} />
                    Log height
                  </button>
                </div>
              )}
            </div>
          )}

          <div className="progress__stats">
            <div className="progress__card">
              <div className="progress__label">Latest</div>
              <div className="progress__value">
                {summary.latest ?? '—'} {summary.latest !== null && displayUnit && <span className="progress__unit">{displayUnit}</span>}
              </div>
            </div>
            <div className="progress__card">
              <div className="progress__label">Change</div>
              <div
                className={`progress__value ${
                  summary.change != null && summary.change > 0
                    ? 'progress__value--up'
                    : summary.change != null && summary.change < 0
                      ? 'progress__value--down'
                      : ''
                }`}
              >
                {summary.change != null
                  ? `${summary.change > 0 ? '+' : ''}${summary.change} ${displayUnit}`
                  : '—'}
              </div>
            </div>
            <div className="progress__card">
              <div className="progress__label">Range</div>
              <div className="progress__value">{summary.rangeLabel}</div>
            </div>
            <div className="progress__card">
              <div className="progress__label">Entries</div>
              <div className="progress__value">{summary.entries}</div>
            </div>
          </div>

          <ProgressChart
            points={displayPoints}
            unit={displayUnit}
            label={metric === 'bmi' ? 'BMI' : (METRIC_BY_KEY[metric].label ?? metric)}
          />

          {derived && (
            <div className="progress__derived">
              <h3 className="plan__section-label">
                <TrendingUp size={14} />
                Training
              </h3>
              <div className="progress__derived-grid">
                <div className="progress__card">
                  <div className="progress__label">Sessions</div>
                  <div className="progress__value">{derived.sessions_completed}</div>
                </div>
                <div className="progress__card">
                  <div className="progress__label">Active days</div>
                  <div className="progress__value">{derived.active_days}</div>
                </div>
                <div className="progress__card">
                  <div className="progress__label">Volume</div>
                  <div className="progress__value">{derived.total_volume_kg.toLocaleString()} kg</div>
                </div>
                <div className="progress__card">
                  <div className="progress__label">Current streak</div>
                  <div className="progress__value">{derived.current_streak_days} d</div>
                </div>
                <div className="progress__card">
                  <div className="progress__label">Longest streak</div>
                  <div className="progress__value">{derived.longest_streak_days} d</div>
                </div>
                <div className="progress__card">
                  <div className="progress__label">Planned done</div>
                  <div className="progress__value">
                    {derived.planned_sessions === 0
                      ? '—'
                      : `${Math.round((derived.planned_completion_rate ?? 0) * 100)}%`}
                  </div>
                </div>
              </div>
            </div>
          )}

          <h3 className="plan__section-label">History</h3>
          {filtered.length === 0 ? (
            <div className="page__empty page__empty--compact">
              {metric === 'height' ? <Ruler size={32} /> : <Scale size={32} />}
              <p>No {metric === 'bmi' ? 'BMI' : METRIC_BY_KEY[metric].label.toLowerCase()} entries yet.</p>
              <button type="button" className="profile__save" onClick={() => openLog(metric === 'bmi' ? 'weight' : metric)}>
                Log your first entry
              </button>
            </div>
          ) : (
            <ul className="library__list">
              {[...filtered].reverse().map((point) => (
                <li key={point.id} className="library__item">
                  <div className="library__icon">
                    <TrendingUp size={18} />
                  </div>
                  <div className="library__info">
                    <div className="library__name">
                      {metric === 'height' && units === 'imperial'
                        ? formatHeight(point.value, units)
                        : metric === 'weight'
                          ? formatWeight(point.value, units)
                          : `${convertForDisplay(point.value).toFixed(1)} ${displayUnit}`}
                    </div>
                    <div className="library__meta">
                      {new Date(point.measured_at).toLocaleDateString(undefined, {
                        weekday: 'short',
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                      })}
                    </div>
                  </div>
                  {metric !== 'bmi' && (
                    <button
                      type="button"
                      className="library__delete"
                      onClick={() => void handleDelete(point.id)}
                      aria-label="Delete entry"
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {undo && (
        <div className="toast" role="status">
          <span>Entry deleted.</span>
          <button
            type="button"
            className="toast__action"
            onClick={() => {
              undo()
              setUndo(null)
            }}
          >
            <Undo2 size={14} />
            Refresh
          </button>
          <button type="button" className="toast__close" onClick={() => setUndo(null)} aria-label="Dismiss">
            <X size={14} />
          </button>
        </div>
      )}
      {savedNote && (
        <span className="visually-hidden" role="status">
          {savedNote}
        </span>
      )}
    </div>
  )
}
