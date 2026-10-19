/**
 * Derived, honest analytics for the Progress page.
 *
 * Every function works on rows that were actually persisted: nothing here
 * interpolates a missing day, treats a gap as zero, or predicts a future value.
 * Aggregations are computed over the records that exist and always report how
 * many records they are based on.
 */
import type { SeriesPoint } from './metrics'

const DAY_MS = 86_400_000

export const dayKey = (iso: string): string => iso.slice(0, 10)

export function average(values: number[]): number | null {
  if (values.length === 0) return null
  const total = values.reduce((sum, value) => sum + value, 0)
  return total / values.length
}

/** Mean of the recorded values, rounded to one decimal like the other metrics. */
export const meanOf = (values: number[]): number | null => {
  const mean = average(values)
  return mean === null ? null : Number(mean.toFixed(1))
}

/** Difference between the last two recorded entries, plus when it happened. */
export function changeSincePrevious(points: SeriesPoint[]): {
  delta: number
  since: string
} | null {
  if (points.length < 2) return null
  const previous = points[points.length - 2]
  const latest = points[points.length - 1]
  return {
    delta: Number((latest.value - previous.value).toFixed(1)),
    since: latest.measured_at,
  }
}

export interface DailyBucket {
  /** Local YYYY-MM-DD of the day. */
  day: string
  value: number
  entries: number
}

/**
 * One bucket per day that actually has records. Days without records are absent
 * from the result — they are never materialised as zero.
 *
 * `sum` aggregates the day (used for daily totals such as steps); `mean` averages
 * it (used for metrics that are already a per-day quantity, such as sleep).
 */
export function bucketByDay(points: SeriesPoint[], mode: 'sum' | 'mean'): DailyBucket[] {
  const groups = new Map<string, { values: number[]; entries: number }>()
  for (const point of points) {
    const key = dayKey(point.measured_at)
    const group = groups.get(key) ?? { values: [], entries: 0 }
    group.values.push(point.value)
    group.entries += 1
    groups.set(key, group)
  }
  return [...groups.entries()]
    .sort((a, b) => (a[0] < b[0] ? -1 : 1))
    .map(([day, group]) => ({
      day,
      value:
        mode === 'sum'
          ? group.values.reduce((sum, value) => sum + value, 0)
          : (group.values.reduce((sum, value) => sum + value, 0) / group.values.length),
      entries: group.entries,
    }))
}

export interface StepsAnalytics {
  /** Days that have at least one steps record. */
  recordedDays: number
  total: number
  /** Mean per day *with records*, never divided by calendar days without data. */
  averagePerRecordedDay: number | null
  bestDay: { day: string; value: number } | null
}

export function stepsAnalytics(points: SeriesPoint[]): StepsAnalytics {
  const days = bucketByDay(points, 'sum')
  const total = days.reduce((sum, day) => sum + day.value, 0)
  const best = days.reduce<{ day: string; value: number } | null>(
    (top, day) => (top === null || day.value > top.value ? { day: day.day, value: day.value } : top),
    null,
  )
  return {
    recordedDays: days.length,
    total: Math.round(total),
    averagePerRecordedDay: meanOf(days.map((day) => day.value)),
    bestDay: best,
  }
}

export interface SleepWeek {
  /** Monday of the week, as YYYY-MM-DD. */
  weekOf: string
  average: number
  nights: number
}

/** Mean sleep per recorded night, grouped into Monday-anchored weeks. */
export function weeklySleep(points: SeriesPoint[]): SleepWeek[] {
  const byWeek = new Map<string, number[]>()
  for (const point of points) {
    const weekOf = startOfWeekKey(point.measured_at)
    const values = byWeek.get(weekOf) ?? []
    values.push(point.value)
    byWeek.set(weekOf, values)
  }
  return [...byWeek.entries()]
    .sort((a, b) => (a[0] < b[0] ? -1 : 1))
    .map(([weekOf, values]) => ({ weekOf, average: meanOf(values) ?? 0, nights: values.length }))
}

/** Monday-anchored week key for an ISO timestamp, in local time. */
export function startOfWeekKey(iso: string): string {
  const date = new Date(iso)
  const offset = (date.getDay() + 6) % 7
  return dayKey(new Date(date.getTime() - offset * DAY_MS).toISOString())
}

export interface SleepAnalytics {
  recordedNights: number
  average: number | null
  weeks: SleepWeek[]
}

export function sleepAnalytics(points: SeriesPoint[]): SleepAnalytics {
  return {
    recordedNights: points.length,
    average: meanOf(points.map((point) => point.value)),
    weeks: weeklySleep(points),
  }
}

/**
 * Gaps longer than this multiple of the median interval are rendered dashed so
 * missing data reads as missing rather than as a smooth change.
 */
export function gapFactor(times: number[]): number {
  if (times.length < 3) return Number.POSITIVE_INFINITY
  const deltas: number[] = []
  for (let i = 1; i < times.length; i += 1) deltas.push(times[i] - times[i - 1])
  const sorted = [...deltas].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  const median = sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid]
  return median > 0 ? median * 3 : Number.POSITIVE_INFINITY
}