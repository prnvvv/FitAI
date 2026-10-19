import { describe, expect, it } from 'vitest'
import {
  addDays,
  bmiCategory,
  conversationDateGroup,
  dateFromKey,
  formatMessageTime,
  isDateKey,
  cmToFeetInches,
  formatMonthTitle,
  formatWeekTitle,
  inchesToCm,
  kgToLb,
  lbToKg,
  monthGrid,
  parseHeightInput,
  startOfWeek,
  toDateKey,
  weekDays,
  yearMonths,
} from './dates'

describe('date helpers', () => {
  it('starts weeks on Monday', () => {
    // 2026-10-14 is a Wednesday.
    const monday = startOfWeek(new Date(2026, 9, 14))
    expect(toDateKey(monday)).toBe('2026-10-12')
    expect(weekDays(monday).map(toDateKey)).toEqual([
      '2026-10-12',
      '2026-10-13',
      '2026-10-14',
      '2026-10-15',
      '2026-10-16',
      '2026-10-17',
      '2026-10-18',
    ])
  })

  it('treats Sunday as the end of the week', () => {
    expect(toDateKey(startOfWeek(new Date(2026, 9, 18)))).toBe('2026-10-12')
  })

  it('builds a six-row month grid', () => {
    const grid = monthGrid(new Date(2026, 9, 1))
    expect(grid).toHaveLength(42)
    expect(grid.filter((cell) => cell.inMonth)).toHaveLength(31)
    expect(grid[0].key).toBe('2026-09-28')
  })

  it('builds twelve year months', () => {
    const months = yearMonths(new Date(2026, 0, 1))
    expect(months).toHaveLength(12)
    expect(months[0].days).toHaveLength(31)
    expect(months[1].days).toHaveLength(28)
  })

  it('formats period titles', () => {
    expect(formatWeekTitle(new Date(2026, 9, 14))).toBe('12 – 18 Oct 2026')
    expect(formatMonthTitle(new Date(2026, 9, 14))).toMatch(/October 2026/)
  })

  it('moves across month boundaries', () => {
    expect(toDateKey(addDays(new Date(2026, 9, 31), 1))).toBe('2026-11-01')
  })
})

describe('bmi helpers', () => {
  it('maps values to WHO adult ranges', () => {
    expect(bmiCategory(17)).toBe('underweight')
    expect(bmiCategory(18.5)).toBe('healthy')
    expect(bmiCategory(24.9)).toBe('healthy')
    expect(bmiCategory(25)).toBe('overweight')
    expect(bmiCategory(29.9)).toBe('overweight')
    expect(bmiCategory(30)).toBe('obese')
  })
})

describe('unit conversion', () => {
  it('converts between kg and lb', () => {
    expect(lbToKg(kgToLb(70))).toBeCloseTo(70, 5)
    expect(kgToLb(70)).toBeCloseTo(154.32, 1)
  })

  it('converts between cm and inches', () => {
    expect(inchesToCm(175 / 2.54)).toBeCloseTo(175, 5)
    expect(cmToFeetInches(175)).toBe("5' 9\"")
  })

  it('parses height in cm, inches and feet+inches', () => {
    expect(parseHeightInput('175', 'cm')).toBe(175)
    expect(parseHeightInput('68.9', 'in')).toBeCloseTo(175, 0)
    expect(parseHeightInput(`5' 9"`, 'ft_in')).toBeCloseTo(175.26, 1)
    expect(parseHeightInput('', 'cm')).toBeNull()
  })
})

describe('local day keys (IST)', () => {
  it('keeps a YYYY-MM-DD key on the same local day', () => {
    const date = dateFromKey('2026-10-14')
    expect(date).not.toBeNull()
    expect(toDateKey(date as Date)).toBe('2026-10-14')
    expect(date?.getDate()).toBe(14)
    expect(date?.getHours()).toBe(0)
  })

  it('never parses a day key as UTC (which would shift the day)', () => {
    // `new Date('2026-10-14')` is midnight UTC and lands on the 13th or 15th
    // depending on the offset; the helper builds local parts instead.
    expect(toDateKey(dateFromKey('2026-10-14') as Date)).toBe('2026-10-14')
    expect(toDateKey(dateFromKey('2026-01-01') as Date)).toBe('2026-01-01')
    expect(toDateKey(dateFromKey('2026-03-29') as Date)).toBe('2026-03-29')
  })

  it('rejects malformed or impossible keys', () => {
    expect(isDateKey('2026-10-14')).toBe(true)
    expect(isDateKey('2026-13-01')).toBe(false)
    expect(isDateKey('2026-02-30')).toBe(false)
    expect(isDateKey('14-10-2026')).toBe(false)
    expect(isDateKey('')).toBe(false)
    expect(isDateKey(undefined)).toBe(false)
    expect(dateFromKey('nonsense')).toBeNull()
  })

  it('round-trips an instant logged at local midnight', () => {
    const logged = new Date(2026, 9, 14, 0, 30)
    expect(toDateKey(logged)).toBe('2026-10-14')
  })

  it('round-trips an instant logged at local 23:45', () => {
    const logged = new Date(2026, 9, 14, 23, 45)
    expect(toDateKey(logged)).toBe('2026-10-14')
  })
})

describe('conversationDateGroup', () => {
  const now = new Date(2026, 9, 14, 9, 0)

  it('groups by local calendar day, not a rolling 24-hour window', () => {
    // 23:50 the previous evening is "Yesterday", not "Today".
    expect(conversationDateGroup(new Date(2026, 9, 14, 8, 30).toISOString(), now)).toBe('Today')
    expect(conversationDateGroup(new Date(2026, 9, 13, 23, 50).toISOString(), now)).toBe('Yesterday')
    expect(conversationDateGroup(new Date(2026, 9, 13, 0, 5).toISOString(), now)).toBe('Yesterday')
    expect(conversationDateGroup(new Date(2026, 9, 10, 12, 0).toISOString(), now)).toBe('Previous 7 days')
    expect(conversationDateGroup(new Date(2026, 9, 1, 12, 0).toISOString(), now)).toBe('Earlier')
  })

  it('keeps unparseable timestamps visible under "Earlier"', () => {
    expect(conversationDateGroup('', now)).toBe('Earlier')
    expect(conversationDateGroup(null, now)).toBe('Earlier')
    expect(conversationDateGroup('not-a-date', now)).toBe('Earlier')
  })

  it('treats a future timestamp as the most recent bucket', () => {
    expect(conversationDateGroup(new Date(2026, 9, 15, 8, 0).toISOString(), now)).toBe('Today')
  })
})

describe('formatMessageTime', () => {
  const now = new Date(2026, 9, 14, 9, 0)

  it('shows only the clock time for today', () => {
    const label = formatMessageTime(new Date(2026, 9, 14, 14, 5).toISOString(), now)
    expect(label).toMatch(/\d{1,2}[:.]05/)
  })

  it('prefixes the day for older messages', () => {
    const label = formatMessageTime(new Date(2026, 8, 30, 14, 5).toISOString(), now)
    expect(label).toMatch(/30/)
    expect(label).toMatch(/05/)
  })

  it('returns an empty string for an unparseable timestamp', () => {
    expect(formatMessageTime('', now)).toBe('')
    expect(formatMessageTime(undefined, now)).toBe('')
    expect(formatMessageTime('not-a-date', now)).toBe('')
  })
})
