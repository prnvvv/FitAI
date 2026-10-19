import { kgToLb } from '../../utils/dates'

export type Range = '7d' | '30d' | '90d' | '1y' | 'all'
export type MetricKey = 'weight' | 'height' | 'body_fat_percent' | 'waist' | 'sleep_hours' | 'steps' | 'bmi'
/** Metrics a user can log. BMI is derived from weight and height. */
export type LoggableMetricKey = Exclude<MetricKey, 'bmi'>

export const RANGE_OPTIONS: { value: Range; label: string; caption: string }[] = [
  { value: '7d', label: '7D', caption: 'Last 7 days' },
  { value: '30d', label: '30D', caption: 'Last 30 days' },
  { value: '90d', label: '90D', caption: 'Last 90 days' },
  { value: '1y', label: '1Y', caption: 'Last year' },
  { value: 'all', label: 'All', caption: 'All time' },
]

export interface MetricDef {
  key: LoggableMetricKey
  label: string
  canonicalUnit: string
  altUnit: string | null
  min: number
  max: number
  step: number
}

/** Metrics that can be logged. BMI is derived and therefore never listed here. */
export const METRICS: MetricDef[] = [
  { key: 'weight', label: 'Weight', canonicalUnit: 'kg', altUnit: 'lb', min: 20, max: 500, step: 0.1 },
  { key: 'height', label: 'Height', canonicalUnit: 'cm', altUnit: 'in', min: 50, max: 260, step: 0.5 },
  { key: 'body_fat_percent', label: 'Body fat', canonicalUnit: '%', altUnit: null, min: 1, max: 70, step: 0.1 },
  { key: 'waist', label: 'Waist', canonicalUnit: 'cm', altUnit: 'in', min: 30, max: 250, step: 0.5 },
  { key: 'sleep_hours', label: 'Sleep', canonicalUnit: 'h', altUnit: null, min: 0, max: 24, step: 0.1 },
  { key: 'steps', label: 'Steps', canonicalUnit: 'steps', altUnit: null, min: 0, max: 200000, step: 100 },
]

/** Chip order: the six loggable metrics, then the derived BMI behind a divider. */
export const CHIP_KEYS: MetricKey[] = [...METRICS.map((metric) => metric.key), 'bmi']

export const METRIC_BY_KEY = Object.fromEntries(METRICS.map((metric) => [metric.key, metric])) as Record<
  LoggableMetricKey,
  MetricDef
>

export const metricLabel = (key: MetricKey): string => (key === 'bmi' ? 'BMI' : METRIC_BY_KEY[key].label)

export const RANGE_DAYS: Record<Exclude<Range, 'all'>, number> = { '7d': 7, '30d': 30, '90d': 90, '1y': 365 }

export const rangeCaption = (range: Range): string =>
  RANGE_OPTIONS.find((option) => option.value === range)?.caption ?? 'All time'

export type ChartKind = 'line' | 'dots' | 'bars'

export interface MetricVisual {
  /**
   * `line` connects readings, `dots` never connects (for metrics that change in
   * discrete steps, such as height) and `bars` plots one bar per recorded day.
   */
  kind: ChartKind
  /** How several entries recorded on the same day collapse into one reading. */
  dayMode: 'sum' | 'mean'
  /** Metrics that cannot be negative are drawn from zero so bars stay honest. */
  zeroBased: boolean
  /** Caption for the average shown in the summary. */
  averageLabel: string
}

const VISUALS: Record<MetricKey, MetricVisual> = {
  weight: { kind: 'line', dayMode: 'mean', zeroBased: false, averageLabel: 'Average' },
  // Height is re-measured rarely: connecting two readings would imply a change
  // that was never recorded, so height is drawn as discrete points only.
  height: { kind: 'dots', dayMode: 'mean', zeroBased: false, averageLabel: 'Average' },
  body_fat_percent: { kind: 'line', dayMode: 'mean', zeroBased: false, averageLabel: 'Average' },
  waist: { kind: 'line', dayMode: 'mean', zeroBased: false, averageLabel: 'Average' },
  sleep_hours: { kind: 'bars', dayMode: 'mean', zeroBased: true, averageLabel: 'Average per night' },
  steps: { kind: 'bars', dayMode: 'sum', zeroBased: true, averageLabel: 'Average per recorded day' },
  bmi: { kind: 'line', dayMode: 'mean', zeroBased: false, averageLabel: 'Average' },
}

export const METRIC_VISUALS = VISUALS

/**
 * Bars are only readable while they are not hair-thin, so very dense daily data
 * falls back to the line once there are more than 31 recorded days.
 */
export function chartKindFor(key: MetricKey, recordedDays: number): ChartKind {
  const visual = VISUALS[key]
  if (visual.kind !== 'bars') return visual.kind
  return recordedDays <= 31 ? 'bars' : 'line'
}

/** Existing per-metric display precision, reused by the chart and the history. */
export function formatMetricValue(key: MetricKey, value: number, units: 'metric' | 'imperial'): string {
  switch (key) {
    case 'weight':
      return (units === 'imperial' ? kgToLb(value) : value).toFixed(1)
    case 'steps':
      return Math.round(value).toLocaleString()
    case 'bmi':
    case 'body_fat_percent':
    case 'sleep_hours':
    case 'waist':
    case 'height':
      return value.toFixed(1)
  }
}

export interface SeriesPoint {
  id: string
  value: number
  measured_at: string
  unit: string
  notes?: string | null
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