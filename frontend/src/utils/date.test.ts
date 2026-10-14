import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { formatDateKey, parseDateKey } from './date'

const ORIGINAL_TZ = process.env.TZ

describe('date helpers use the local calendar day', () => {
  beforeEach(() => {
    // A positive UTC offset is where a UTC-based implementation shifts a
    // local-midnight date back by one day.
    process.env.TZ = 'Asia/Kolkata'
  })

  afterEach(() => {
    process.env.TZ = ORIGINAL_TZ
  })

  it('formatDateKey keeps the local day for a local-midnight date', () => {
    expect(formatDateKey(new Date(2026, 9, 14, 0, 0, 0))).toBe('2026-10-14')
  })

  it('formatDateKey pads single-digit months and days', () => {
    expect(formatDateKey(new Date(2026, 0, 5, 0, 0, 0))).toBe('2026-01-05')
  })

  it('parseDateKey returns local midnight of the same day', () => {
    const d = parseDateKey('2026-10-14')
    expect(d.getFullYear()).toBe(2026)
    expect(d.getMonth()).toBe(9)
    expect(d.getDate()).toBe(14)
    expect(d.getHours()).toBe(0)
  })

  it('round-trips a date key through parse and format', () => {
    expect(formatDateKey(parseDateKey('2026-10-14'))).toBe('2026-10-14')
  })

  it('does not shift a local date across the UTC boundary', () => {
    // 10:00 local on the 14th must keep the 14th as its calendar day.
    const performedAt = parseDateKey('2026-10-14')
    performedAt.setHours(10, 0, 0, 0)
    expect(formatDateKey(performedAt)).toBe('2026-10-14')
    expect(performedAt.getTimezoneOffset()).toBe(-330)
  })
})
