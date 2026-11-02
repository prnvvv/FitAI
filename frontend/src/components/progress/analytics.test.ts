import { describe, expect, it } from 'vitest'
import {
  average,
  bucketByDay,
  changeSincePrevious,
  gapFactor,
  meanOf,
  sleepAnalytics,
  startOfWeekKey,
  stepsAnalytics,
  weeklySleep,
} from './analytics'
import type { SeriesPoint } from './metrics'

const point = (id: string, value: number, measured_at: string): SeriesPoint => ({
  id,
  value,
  measured_at,
  unit: 'kg',
})

const on = (daysAgo: number, hour = 8) => {
  const date = new Date()
  date.setDate(date.getDate() - daysAgo)
  date.setHours(hour, 0, 0, 0)
  return date.toISOString()
}

describe('averages', () => {
  it('returns null for no data instead of a misleading zero', () => {
    expect(average([])).toBeNull()
    expect(meanOf([])).toBeNull()
  })

  it('rounds to one decimal like the other metric values', () => {
    expect(meanOf([70, 71, 72])).toBe(71)
    expect(meanOf([1, 1, 2])).toBe(1.3)
  })
})

describe('bucketByDay', () => {
  it('never materialises a day without records', () => {
    const buckets = bucketByDay([point('a', 8000, on(5)), point('b', 9000, on(2))], 'sum')
    expect(buckets).toHaveLength(2)
    expect(buckets.map((bucket) => bucket.value)).toEqual([8000, 9000])
  })

  it('sums repeated entries on one day for daily totals', () => {
    const morning = new Date()
    morning.setHours(8, 0, 0, 0)
    const evening = new Date()
    evening.setHours(20, 0, 0, 0)
    const buckets = bucketByDay(
      [point('a', 4000, morning.toISOString()), point('b', 6000, evening.toISOString())],
      'sum',
    )
    expect(buckets).toHaveLength(1)
    expect(buckets[0].value).toBe(10000)
    expect(buckets[0].entries).toBe(2)
  })

  it('averages repeated entries on one day for per-night metrics', () => {
    const buckets = bucketByDay([point('a', 6, on(3)), point('b', 8, on(3))], 'mean')
    expect(buckets[0].value).toBe(7)
  })

  it('keeps days in chronological order', () => {
    const buckets = bucketByDay([point('a', 1, on(1)), point('b', 1, on(9)), point('c', 1, on(4))], 'sum')
    const days = buckets.map((bucket) => bucket.day)
    expect([...days].sort()).toEqual(days)
  })
})

describe('changeSincePrevious', () => {
  it('is null for a single entry', () => {
    expect(changeSincePrevious([point('a', 70, on(1))])).toBeNull()
  })

  it('compares the last two entries only', () => {
    const change = changeSincePrevious([
      point('a', 80, on(20)),
      point('b', 78, on(10)),
      point('c', 77.5, on(1)),
    ])
    expect(change?.delta).toBe(-0.5)
    expect(change?.since).toBe(on(1))
  })
})

describe('stepsAnalytics', () => {
  it('averages over recorded days, never over calendar days without data', () => {
    const stats = stepsAnalytics([point('a', 8000, on(6)), point('b', 10000, on(2))])
    expect(stats.recordedDays).toBe(2)
    expect(stats.averagePerRecordedDay).toBe(9000)
    expect(stats.total).toBe(18000)
    expect(stats.bestDay?.value).toBe(10000)
  })

  it('reports an empty set honestly', () => {
    const stats = stepsAnalytics([])
    expect(stats).toEqual({
      recordedDays: 0,
      total: 0,
      averagePerRecordedDay: null,
      bestDay: null,
    })
  })
})

describe('sleepAnalytics', () => {
  it('averages nights and groups them into Monday-anchored weeks', () => {
    const stats = sleepAnalytics([
      // Fixed dates: relative dates made this depend on the weekday it ran on.
      point('a', 7, '2026-10-20T08:00:00'), // same Monday-anchored week as the next entry
      point('b', 8, '2026-10-19T08:00:00'),
      point('c', 6, '2026-10-26T08:00:00'),
    ])
    expect(stats.recordedNights).toBe(3)
    expect(stats.average).toBe(7)
    expect(stats.weeks).toHaveLength(2)
    expect(stats.weeks[0]).toEqual({ weekOf: startOfWeekKey('2026-10-20T08:00:00'), average: 7.5, nights: 2 })
    expect(stats.weeks[1].nights).toBe(1)
  })

  it('anchors weeks on Monday', () => {
    // 2026-10-19 is a Monday, so that week key is itself.
    expect(startOfWeekKey('2026-10-19T08:00:00')).toBe('2026-10-19')
    expect(startOfWeekKey('2026-10-21T08:00:00')).toBe('2026-10-19')
    expect(startOfWeekKey('2026-10-25T08:00:00')).toBe('2026-10-19')
    expect(startOfWeekKey('2026-10-26T08:00:00')).toBe('2026-10-26')
  })

  it('needs no weeks to report', () => {
    expect(weeklySleep([])).toEqual([])
    expect(sleepAnalytics([]).average).toBeNull()
  })
})

describe('gapFactor', () => {
  it('needs three readings before it can call something a gap', () => {
    expect(gapFactor([0, 1000])).toBe(Number.POSITIVE_INFINITY)
  })

  it('uses three times the median interval', () => {
    expect(gapFactor([0, 10, 20, 90])).toBe(30)
  })
})