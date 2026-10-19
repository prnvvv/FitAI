import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import type { Range, SeriesPoint } from './metrics'
import { chartVariantFor, formatMetricValue, metricLabel } from './metrics'

const PAD = { top: 18, right: 14, bottom: 22, left: 46 }
const SINGLE_HEIGHT = 160
const GAP_FACTOR = 3

interface ProgressChartProps {
  points: SeriesPoint[]
  metric: Parameters<typeof formatMetricValue>[0]
  units: 'metric' | 'imperial'
  range: Range
  height: number
  /** True when entries exist outside the selected range (enables "Show all"). */
  showAllAvailable: boolean
  onShowAll: () => void
  onLog: () => void
}

/** Measures the container so every coordinate is a real pixel value. */
function useMeasuredWidth(ref: React.RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const node = ref.current
    if (!node) return
    const measure = () => setWidth(node.clientWidth)
    measure()
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure)
      return () => window.removeEventListener('resize', measure)
    }
    const observer = new ResizeObserver(measure)
    observer.observe(node)
    return () => observer.disconnect()
  }, [ref])
  return width
}

const time = (point: SeriesPoint) => new Date(point.measured_at).getTime()

interface Tick {
  at: number
  label: string
}

/** Round x ticks inside the plotted domain: daily, weekly, monthly or yearly. */
export function xTicks(range: Range, from: number, to: number): Tick[] {
  const start = new Date(from)
  const end = new Date(to)
  const days = (to - from) / 86_400_000
  const push = (date: Date, label: string) => {
    const at = date.getTime()
    if (at < from || at > to) return
    ticks.push({ at, label })
  }
  const ticks: Tick[] = []

  if (range === '7d' || days <= 10) {
    const cursor = new Date(start.getFullYear(), start.getMonth(), start.getDate())
    while (cursor.getTime() <= to && ticks.length < 8) {
      push(
        new Date(cursor),
        cursor.toLocaleDateString(undefined, { weekday: 'short' }).slice(0, 3),
      )
      cursor.setDate(cursor.getDate() + 1)
    }
    return ticks
  }

  if (range === '30d' || days <= 45) {
    const cursor = new Date(start.getFullYear(), start.getMonth(), start.getDate())
    cursor.setDate(cursor.getDate() + ((7 - cursor.getDay()) % 7))
    while (cursor.getTime() <= to && ticks.length < 8) {
      push(new Date(cursor), cursor.toLocaleDateString(undefined, { day: 'numeric', month: 'short' }))
      cursor.setDate(cursor.getDate() + 7)
    }
    return ticks
  }

  if (days > 1100) {
    for (let year = start.getFullYear(); year <= end.getFullYear(); year += 1) {
      push(new Date(year, 0, 1), String(year))
    }
    return ticks
  }

  const cursor = new Date(start.getFullYear(), start.getMonth(), 1)
  while (cursor.getTime() <= to && ticks.length < 14) {
    push(new Date(cursor), cursor.toLocaleDateString(undefined, { month: 'short' }))
    cursor.setMonth(cursor.getMonth() + 1)
  }
  return ticks
}

/** Median gap between entries; segments longer than 3x it signal missing data. */
export function gapThreshold(times: number[]): number {
  if (times.length < 2) return Number.POSITIVE_INFINITY
  const deltas: number[] = []
  for (let i = 1; i < times.length; i += 1) deltas.push(times[i] - times[i - 1])
  const sorted = [...deltas].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  const median = sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid]
  return median > 0 ? median * GAP_FACTOR : Number.POSITIVE_INFINITY
}

/** Pads the data by 10% of its span, with a floor so flat series stay centred. */
export function yDomain(values: number[]): { min: number; max: number } {
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min
  const floor = Math.abs(max || 1) * 0.05 || 1
  const pad = Math.max(span * 0.1, floor)
  return { min: min - pad, max: max + pad }
}

export function ProgressChart({
  points,
  metric,
  units,
  range,
  height,
  showAllAvailable,
  onShowAll,
  onLog,
}: ProgressChartProps) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const width = useMeasuredWidth(wrapRef)
  const [active, setActive] = useState<number | null>(null)

  const sorted = useMemo(() => [...points].sort((a, b) => time(a) - time(b)), [points])
  const format = useCallback((value: number) => formatMetricValue(metric, value, units), [metric, units])
  const label = metricLabel(metric)

  useEffect(() => {
    setActive(null)
  }, [metric, range, units, points])

  if (sorted.length === 0) {
    return (
      <div className="chart chart--empty" role="status" style={{ height: 140 }}>
        <p className="chart__empty-text">No {label.toLowerCase()} entries in this range.</p>
        <div className="chart__empty-actions">
          {showAllAvailable ? (
            <button type="button" className="chart__empty-button" onClick={onShowAll}>
              Show all
            </button>
          ) : (
            <button type="button" className="chart__empty-button" onClick={onLog}>
              Log {label.toLowerCase()}
            </button>
          )}
        </div>
      </div>
    )
  }

  const single = sorted.length === 1
  const boxHeight = single ? SINGLE_HEIGHT : height
  const times = sorted.map(time)
  const domain = yDomain(sorted.map((point) => point.value))
  const from = times[0]
  const to = times[times.length - 1]
  const span = to - from
  const plotWidth = Math.max(width - PAD.left - PAD.right, 1)
  const plotHeight = Math.max(boxHeight - PAD.top - PAD.bottom, 1)
  const x = (at: number) => (span === 0 ? PAD.left + plotWidth / 2 : PAD.left + ((at - from) / span) * plotWidth)
  const y = (value: number) => PAD.top + (1 - (value - domain.min) / (domain.max - domain.min)) * plotHeight
  const ticks = xTicks(range, from, to)
  const threshold = gapThreshold(times)
  const unit = sorted[0].unit === 'BMI' ? '' : sorted[0].unit

  const description = single
    ? `One entry: ${format(sorted[0].value)} ${unit} on ${new Date(sorted[0].measured_at).toLocaleDateString()}`
    : `${sorted.length} entries from ${format(sorted[0].value)} to ${format(sorted[sorted.length - 1].value)} ${unit}`

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (sorted.length === 0) return
    const last = sorted.length - 1
    if (event.key === 'ArrowRight') {
      event.preventDefault()
      setActive((prev) => Math.min((prev ?? -1) + 1, last))
      return
    }
    if (event.key === 'ArrowLeft') {
      event.preventDefault()
      setActive((prev) => Math.max((prev ?? 1) - 1, 0))
      return
    }
    if (event.key === 'Home') {
      event.preventDefault()
      setActive(0)
      return
    }
    if (event.key === 'End') {
      event.preventDefault()
      setActive(last)
      return
    }
    if (event.key === 'Escape') setActive(null)
  }

  if (width === 0) {
    // Nothing is drawn until the container has a real width; never guess pixels.
    return <div className="chart" ref={wrapRef} style={{ height: boxHeight }} />
  }

  if (single) {
    const point = sorted[0]
    return (
      <div className="chart chart--single" ref={wrapRef} style={{ height: SINGLE_HEIGHT }}>
        <svg
          width={width}
          height={SINGLE_HEIGHT}
          role="img"
          aria-label={`${label} chart. ${description}`}
          className="chart__svg"
        >
          <circle
            cx={width / 2}
            cy={SINGLE_HEIGHT / 2}
            r={12}
            fill="var(--accent)"
            opacity={0.18}
            data-testid="chart-single-ring"
          />
          <circle cx={width / 2} cy={SINGLE_HEIGHT / 2} r={6} fill="var(--accent)" />
          <text className="chart__value-label" x={width / 2} y={SINGLE_HEIGHT / 2 - 26} textAnchor="middle">
            {format(point.value)} {unit}
          </text>
          <text className="chart__tick-label" x={width / 2} y={SINGLE_HEIGHT / 2 + 30} textAnchor="middle">
            {new Date(point.measured_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
          </text>
        </svg>
        <p className="chart__caption">Log one more entry to see a trend.</p>
      </div>
    )
  }

  const variant = chartVariantFor(metric, sorted.length)
  const showMarkers = sorted.length <= 40
  const gridValues = [0, 1, 2, 3].map((step) => domain.min + ((domain.max - domain.min) * step) / 3)
  const latest = sorted.length - 1
  const activePoint = active === null ? null : sorted[active]

  return (
    <div
      className="chart"
      ref={wrapRef}
      style={{ height }}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      onBlur={() => setActive(null)}
      role="img"
      aria-label={`${label} chart. ${description}`}
    >
      <svg width={width} height={height} className="chart__svg" aria-hidden="true">
        {gridValues.map((value, index) => (
          <g key={value}>
            <line
              className="chart__grid"
              x1={PAD.left}
              x2={PAD.left + plotWidth}
              y1={y(value)}
              y2={y(value)}
            />
            <text className="chart__axis-label" x={PAD.left - 8} y={y(value) + 4} textAnchor="end">
              {format(value)}
              {index === 0 && unit ? ` ${unit}` : ''}
            </text>
          </g>
        ))}

        {variant === 'bar' ? (
          sorted.map((point, index) => {
            const slot = plotWidth / sorted.length
            const barWidth = Math.max(Math.min(slot * 0.6, 24), 2)
            const zero = y(domain.min)
            const top = y(point.value)
            return (
              <rect
                key={point.id}
                className={`chart__bar${active === index ? ' chart__bar--active' : ''}`}
                x={x(time(point)) - barWidth / 2}
                y={Math.min(top, zero)}
                width={barWidth}
                height={Math.max(Math.abs(zero - top), 1)}
                rx={2}
                onMouseEnter={() => setActive(index)}
              />
            )
          })
        ) : (
          <>
            {sorted.map((point, index) => {
              if (index === 0) return null
              const gap = times[index] - times[index - 1]
              const dashed = gap > threshold
              return (
                <line
                  key={`seg-${point.id}`}
                  className={dashed ? 'chart__line chart__line--dashed' : 'chart__line'}
                  x1={x(times[index - 1])}
                  y1={y(sorted[index - 1].value)}
                  x2={x(times[index])}
                  y2={y(point.value)}
                />
              )
            })}
            {(showMarkers ? sorted : [sorted[latest]]).map((point) => {
              const index = sorted.indexOf(point)
              const isLatest = index === latest
              return (
                <circle
                  key={point.id}
                  className={`chart__marker${isLatest ? ' chart__marker--latest' : ''}${
                    active === index ? ' chart__marker--active' : ''
                  }`}
                  cx={x(time(point))}
                  cy={y(point.value)}
                  r={isLatest ? 4 : 3}
                  onMouseEnter={() => setActive(index)}
                />
              )
            })}
            {showMarkers && (() => {
              const index = active ?? latest
              const at = x(times[index])
              return (
                <text
                  className="chart__value-label"
                  x={at}
                  y={y(sorted[index].value) - 12}
                  textAnchor={at > width - 60 ? 'end' : at < 60 ? 'start' : 'middle'}
                >
                  {format(sorted[index].value)}
                </text>
              )
            })()}
          </>
        )}

        {ticks.map((tick) => (
          <text key={tick.at} className="chart__tick-label" x={x(tick.at)} y={height - 6} textAnchor="middle">
            {tick.label}
          </text>
        ))}
      </svg>

      {activePoint && (
        <div
          className="chart__tooltip"
          role="status"
          style={{
            left: Math.min(Math.max(x(time(activePoint)), 70), Math.max(width - 70, 70)),
            top: Math.max(y(activePoint.value) - 54, 0),
          }}
        >
          <span className="chart__tooltip-date">
            {new Date(activePoint.measured_at).toLocaleDateString(undefined, {
              month: 'short',
              day: 'numeric',
              year: 'numeric',
            })}
          </span>
          <strong>
            {format(activePoint.value)} {unit}
          </strong>
          {activePoint.notes && <span className="chart__tooltip-note">{activePoint.notes}</span>}
        </div>
      )}
    </div>
  )
}