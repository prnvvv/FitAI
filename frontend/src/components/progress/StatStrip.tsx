import type { MetricKey, SeriesPoint } from './metrics'
import { changeSincePrevious, meanOf, sleepAnalytics, stepsAnalytics } from './analytics'
import { formatMetricValue } from './metrics'

interface StatStripProps {
  metric: MetricKey
  /** Recorded entries in the selected range, in chronological order. */
  points: SeriesPoint[]
  /** Same entries collapsed to one reading per recorded day. */
  daily: SeriesPoint[]
  entries: number
  rangeLabel: string
  unit: string
  latestDate: string | null
  loading?: boolean
}

/**
 * Latest / Change / Range / Entries plus one plain-language line of derived
 * context. Everything here is computed from recorded rows only.
 */
export function StatStrip({
  metric,
  points,
  daily,
  entries,
  rangeLabel,
  unit,
  latestDate,
  loading,
}: StatStripProps) {
  if (loading) {
    return (
      <div className="stat-strip" aria-hidden="true">
        {[0, 1, 2, 3].map((index) => (
          <div key={index} className="stat">
            <div className="skeleton skeleton--label" />
            <div className="skeleton skeleton--value" />
          </div>
        ))}
      </div>
    )
  }

  const format = (value: number) => formatMetricValue(metric, value, 'metric')
  const values = points.map((point) => point.value)
  const latest = values.length ? values[values.length - 1] : null
  const rangeChange =
    values.length > 1 ? Number((values[values.length - 1] - values[0]).toFixed(1)) : null
  const previous = changeSincePrevious(points)
  const average = meanOf(values)

  const rangeText =
    rangeLabel === '—'
      ? '—'
      : `${rangeLabel.includes('–') ? rangeLabel.split('–').map((part) => format(Number(part))).join('–') : format(Number(rangeLabel))}${unit ? ` ${unit}` : ''}`

  return (
    <div className="stat-block">
      <div className="stat-strip">
        <div className="stat stat--primary">
          <span className="stat__label">Latest</span>
          <span className="stat__value stat__value--large">
            {latest === null ? '—' : format(latest)}
            {latest !== null && unit && <span className="stat__unit"> {unit}</span>}
          </span>
          {latestDate && <span className="stat__caption">{latestDate}</span>}
        </div>
        <div className="stat">
          <span className="stat__label">Change</span>
          <span className="stat__value">
            {rangeChange !== null
              ? `${rangeChange > 0 ? '+' : ''}${format(rangeChange)}${unit ? ` ${unit}` : ''}`
              : '—'}
          </span>
          <span className="stat__caption">in this range</span>
        </div>
        <div className="stat">
          <span className="stat__label">Range</span>
          <span className="stat__value">{rangeText}</span>
          <span className="stat__caption">lowest–highest</span>
        </div>
        <div className="stat">
          <span className="stat__label">Entries</span>
          <span className="stat__value">{entries}</span>
          <span className="stat__caption">{daily.length} recorded days</span>
        </div>
      </div>
      <InsightLine
        metric={metric}
        points={points}
        daily={daily}
        previousDelta={previous?.delta ?? null}
        average={average}
        format={format}
        unit={unit}
      />
    </div>
  )
}

interface InsightLineProps {
  metric: MetricKey
  points: SeriesPoint[]
  daily: SeriesPoint[]
  previousDelta: number | null
  average: number | null
  format: (value: number) => string
  unit: string
}

/** One secondary line: the delta since the previous entry, plus metric specifics. */
function InsightLine({ metric, points, daily, previousDelta, average, format, unit }: InsightLineProps) {
  if (points.length === 0) return null

  if (metric === 'steps') {
    const stats = stepsAnalytics(points)
    return (
      <p className="stat-insight">
        <span>
          <strong>{stats.averagePerRecordedDay === null ? '—' : Math.round(stats.averagePerRecordedDay).toLocaleString()}</strong>{' '}
          average per recorded day
        </span>
        <span>
          <strong>{stats.total.toLocaleString()}</strong> total across {stats.recordedDays}{' '}
          {stats.recordedDays === 1 ? 'day' : 'days'}
        </span>
        {stats.bestDay && (
          <span>
            Best <strong>{Math.round(stats.bestDay.value).toLocaleString()}</strong> on{' '}
            {new Date(`${stats.bestDay.day}T12:00:00`).toLocaleDateString(undefined, {
              month: 'short',
              day: 'numeric',
            })}
          </span>
        )}
      </p>
    )
  }

  if (metric === 'sleep_hours') {
    const stats = sleepAnalytics(points)
    const lastWeek = stats.weeks[stats.weeks.length - 1]
    return (
      <p className="stat-insight">
        <span>
          <strong>{average === null ? '—' : format(average)}</strong> {unit} average per recorded night
        </span>
        <span>
          <strong>{stats.recordedNights}</strong> nights recorded
        </span>
        {lastWeek && (
          <span>
            Latest week <strong>{format(lastWeek.average)}</strong> {unit} over {lastWeek.nights}{' '}
            {lastWeek.nights === 1 ? 'night' : 'nights'}
          </span>
        )}
      </p>
    )
  }

  const parts: string[] = []
  if (previousDelta !== null) {
    parts.push(
      `Since the previous entry ${previousDelta > 0 ? '+' : ''}${format(previousDelta)}${unit ? ` ${unit}` : ''}`,
    )
  }
  if (average !== null) {
    parts.push(`Average ${format(average)}${unit ? ` ${unit}` : ''}`)
  }
  if (metric === 'height') {
    parts.push(`${daily.length} recorded ${daily.length === 1 ? 'day' : 'days'}`)
  }

  return (
    <p className="stat-insight">
      {parts.map((part) => (
        <span key={part}>{part}</span>
      ))}
    </p>
  )
}