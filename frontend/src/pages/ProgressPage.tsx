import { AlertCircle, LineChart, Plus, Ruler, Table2, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, toMessage } from '../services/api'
import type { BmiPoint, DerivedMetrics, Measurement, Profile } from '../types'
import {
  BMI_CATEGORY_LABELS,
  bmiCategory,
  formatHeight,
  formatWeight,
  kgToLb,
  parseHeightInput,
} from '../utils/dates'
import { HistoryCard } from '../components/progress/HistoryCard'
import { LogDialog } from '../components/progress/LogDialog'
import type { LogPayload } from '../components/progress/LogDialog'
import { MetricChips } from '../components/progress/MetricChips'
import {
  METRIC_BY_KEY,
  RANGE_DAYS,
  RANGE_OPTIONS,
  metricLabel,
  rangeCaption,
  formatMetricValue,
  summarise,
} from '../components/progress/metrics'
import type { MetricKey, Range, SeriesPoint } from '../components/progress/metrics'
import { ProgressChart } from '../components/progress/ProgressChart'
import { StatStrip } from '../components/progress/StatStrip'
import { TrainingCard } from '../components/progress/TrainingCard'

export { summarise } from '../components/progress/metrics'

function toPoints(measurements: Measurement[]): SeriesPoint[] {
  return measurements.map((m) => ({
    id: m.id,
    value: Number(m.value),
    measured_at: m.measured_at,
    unit: m.unit,
    notes: m.notes,
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

export function ProgressPage() {
  const [metric, setMetric] = useState<MetricKey>('weight')
  const [range, setRange] = useState<Range>('30d')
  const [view, setView] = useState<'chart' | 'table'>('chart')
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
  const [saving, setSaving] = useState(false)
  const [logError, setLogError] = useState<string | null>(null)
  const [savedNote, setSavedNote] = useState<string | null>(null)
  const [undo, setUndo] = useState<(() => void) | null>(null)

  const applyProfile = useCallback((profile: Profile) => {
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
  }, [])

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
  }, [applyProfile])

  useEffect(() => {
    void load()
  }, [load])

  const points = useMemo(() => (metric === 'bmi' ? bmiPoints : series[metric] ?? []), [bmiPoints, metric, series])

  const filtered = useMemo(() => {
    if (range === 'all') return points
    const cutoff = new Date()
    cutoff.setDate(cutoff.getDate() - RANGE_DAYS[range])
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

  const convertForDisplay = useCallback(
    (value: number): number => {
      if (units !== 'imperial' || !definition?.altUnit) return value
      if (metric === 'weight') return kgToLb(value)
      if (metric === 'height') return value / 2.54
      return value
    },
    [definition, metric, units],
  )

  const displayPoints = useMemo(
    () =>
      filtered.map((point) => ({
        ...point,
        value: convertForDisplay(point.value),
        unit: displayUnit,
      })),
    [filtered, convertForDisplay, displayUnit],
  )

  const openLog = (target: MetricKey) => {
    setFocusMetric(target === 'bmi' ? 'weight' : target)
    setLogError(null)
    setShowLog(true)
  }

  const handleLog = async ({ date, note, drafts }: LogPayload) => {
    if (saving) return
    setSaving(true)
    setLogError(null)
    try {
      for (const draft of drafts) {
        if (draft.value.trim() === '') continue
        const def = METRIC_BY_KEY[draft.key]
        const raw = Number(draft.value)
        const canonical =
          draft.key === 'height'
            ? parseHeightInput(draft.value, draft.unit)
            : draft.key === 'weight' && draft.unit === 'lb'
              ? raw / 2.2046226
              : raw
        if (canonical === null) continue
        await api.createMeasurement({
          type: draft.key,
          value: Number(canonical.toFixed(2)),
          unit: draft.key === 'height' ? 'cm' : def.canonicalUnit,
          measured_at: new Date(`${date}T08:00:00`).toISOString(),
          notes: note.trim() || undefined,
        })
      }
      setShowLog(false)
      setSavedNote('Saved')
      await load()
    } catch (err) {
      setLogError(toMessage(err, 'That entry could not be saved.'))
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

  const bmiLabel = latestBmi === null || (age !== null && age < 18) ? null : BMI_CATEGORY_LABELS[bmiCategory(latestBmi)]
  const latestDate = filtered.length
    ? new Date(filtered[filtered.length - 1].measured_at).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : null

  const historyValue = (point: SeriesPoint) => {
    if (metric === 'height' && units === 'imperial') return formatHeight(point.value, units)
    if (metric === 'weight') return formatWeight(point.value, units)
    return `${convertForDisplay(point.value).toFixed(1)} ${displayUnit}`
  }

  return (
    <div className="page page--progress">
      <header className="page__header page__header--row">
        <div>
          <h1>Progress</h1>
          <p>Track how you're doing over time.</p>
        </div>
        <div className="progress__header-actions">
          <button
            type="button"
            className="progress__unit-toggle progress__unit-toggle--header"
            onClick={() => setUnits((value) => (value === 'metric' ? 'imperial' : 'metric'))}
            aria-label="Toggle units"
          >
            {units === 'metric' ? 'kg / cm' : 'lb / in'}
          </button>
          <button type="button" className="profile__save" onClick={() => openLog(metric)}>
            <Plus size={16} />
            Log
          </button>
        </div>
      </header>

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

      <div className="progress__layout">
        <div className="progress__main">
          <section className="card card--measurement" aria-label="Measurement">
            <MetricChips value={metric} onChange={setMetric} />

            <StatStrip
              latest={summary.latest}
              change={summary.change}
              rangeLabel={summary.rangeLabel}
              entries={summary.entries}
              unit={displayUnit}
              latestDate={latestDate}
              format={(value) => formatMetricValue(metric, value, 'metric')}
              loading={loading}
            />

            {metric === 'bmi' && !loading && (
              <div className="progress__bmi-card">
                {hasHeight ? (
                  <>
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
                  <>
                    <p className="progress__note">Add your height to see BMI.</p>
                    <button type="button" className="profile__save" onClick={() => openLog('height')}>
                      <Ruler size={16} />
                      Log height
                    </button>
                  </>
                )}
              </div>
            )}

            <div className="chart-toolbar">
              <span className="chart-toolbar__caption">{rangeCaption(range)}</span>
              {/* Below 768px the header drops the unit toggle and it lives here. */}
              <button
                type="button"
                className="progress__unit-toggle progress__unit-toggle--toolbar"
                onClick={() => setUnits((value) => (value === 'metric' ? 'imperial' : 'metric'))}
                aria-label="Toggle units"
              >
                {units === 'metric' ? 'kg / cm' : 'lb / in'}
              </button>
              <div className="chart-toolbar__controls">
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
                <div className="segmented segmented--view" role="group" aria-label="View">
                  <button
                    type="button"
                    aria-label="Chart view"
                    aria-pressed={view === 'chart'}
                    className={view === 'chart' ? 'segmented__item--active' : undefined}
                    onClick={() => setView('chart')}
                  >
                    <LineChart size={16} />
                  </button>
                  <button
                    type="button"
                    aria-label="Table view"
                    aria-pressed={view === 'table'}
                    className={view === 'table' ? 'segmented__item--active' : undefined}
                    onClick={() => setView('table')}
                  >
                    <Table2 size={16} />
                  </button>
                </div>
              </div>
            </div>

            {loading ? (
              <div className="skeleton skeleton--chart" aria-hidden="true" />
            ) : view === 'table' ? (
              <div className="chart-table">
                <table>
                  <caption className="visually-hidden">{metricLabel(metric)} entries</caption>
                  <thead>
                    <tr>
                      <th scope="col">Date</th>
                      <th scope="col">{metricLabel(metric)}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...displayPoints].reverse().map((point) => (
                      <tr key={point.id}>
                        <td>{new Date(point.measured_at).toLocaleDateString()}</td>
                        <td>
                          {point.value.toFixed(1)} {displayUnit}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <ProgressChart
                points={displayPoints}
                metric={metric}
                units={units}
                range={range}
                height={240}
                showAllAvailable={filtered.length === 0 && points.length > 0}
                onShowAll={() => setRange('all')}
                onLog={() => openLog(metric)}
              />
            )}
          </section>
        </div>

        <div className="progress__side">
          <TrainingCard derived={derived} loading={loading} />

          <HistoryCard
            title={`History${metricLabel(metric) ? ` · ${metricLabel(metric)}` : ''}`}
            points={filtered}
            renderValue={historyValue}
            readOnly={metric === 'bmi'}
            onDelete={(id) => void handleDelete(id)}
            loading={loading}
          />
        </div>
      </div>

      <LogDialog
        open={showLog}
        units={units}
        focusMetric={focusMetric}
        saving={saving}
        error={logError}
        onDismiss={() => setShowLog(false)}
        onSubmit={(payload) => void handleLog(payload)}
      />

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