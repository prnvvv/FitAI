import { describe, expect, it } from 'vitest'
import {
  addDays,
  bmiCategory,
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
