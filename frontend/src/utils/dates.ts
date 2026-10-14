/** Date helpers shared by the Plan and Progress views. */

export function toDateKey(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/** True for a well-formed YYYY-MM-DD key that names a real local date. */
export function isDateKey(value: unknown): value is string {
  if (typeof value !== 'string') return false
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const [year, month, day] = value.split('-').map(Number)
  const date = new Date(year, month - 1, day)
  return toDateKey(date) === value
}

/**
 * Local Date for a YYYY-MM-DD key, or null when the key is not a real date.
 *
 * Building the date from local parts (never `new Date("YYYY-MM-DD")`, which is
 * parsed as UTC and shifts the day) keeps a day key on the same local day in
 * every timezone, including IST (UTC+05:30).
 */
export function dateFromKey(key: string): Date | null {
  if (!isDateKey(key)) return null
  const [year, month, day] = key.split('-').map(Number)
  const date = new Date(year, month - 1, day)
  date.setHours(0, 0, 0, 0)
  return date
}

export function fromDateKey(key: string): Date {
  return dateFromKey(key) ?? new Date()
}

export function addDays(date: Date, days: number): Date {
  const next = new Date(date)
  next.setDate(next.getDate() + days)
  return next
}

export function addMonths(date: Date, months: number): Date {
  return new Date(date.getFullYear(), date.getMonth() + months, 1)
}

export function startOfWeek(date: Date): Date {
  // Monday-first.
  const day = date.getDay()
  const diff = day === 0 ? -6 : 1 - day
  const start = new Date(date)
  start.setDate(date.getDate() + diff)
  start.setHours(0, 0, 0, 0)
  return start
}

export function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1)
}

export function startOfYear(date: Date): Date {
  return new Date(date.getFullYear(), 0, 1)
}

export interface CalendarCell {
  key: string
  date: Date
  inMonth: boolean
}

/** Six-week grid (42 cells) for the month view, Monday-first. */
export function monthGrid(anchor: Date): CalendarCell[] {
  const first = startOfMonth(anchor)
  const gridStart = startOfWeek(first)
  return Array.from({ length: 42 }, (_, index) => {
    const date = addDays(gridStart, index)
    return { key: toDateKey(date), date, inMonth: date.getMonth() === first.getMonth() }
  })
}

export interface YearMonth {
  month: number
  anchor: Date
  days: CalendarCell[]
}

/** Twelve compact month grids for the year heatmap. */
export function yearMonths(anchor: Date): YearMonth[] {
  const year = anchor.getFullYear()
  return Array.from({ length: 12 }, (_, month) => {
    const first = new Date(year, month, 1)
    const length = new Date(year, month + 1, 0).getDate()
    return {
      month,
      anchor: first,
      days: Array.from({ length }, (_, index) => {
        const date = new Date(year, month, index + 1)
        return { key: toDateKey(date), date, inMonth: true }
      }),
    }
  })
}

export function weekDays(anchor: Date): Date[] {
  const start = startOfWeek(anchor)
  return Array.from({ length: 7 }, (_, index) => addDays(start, index))
}

export function formatWeekTitle(anchor: Date): string {
  const days = weekDays(anchor)
  const first = days[0]
  const last = days[6]
  const sameMonth = first.getMonth() === last.getMonth()
  if (sameMonth) {
    return `${first.getDate()} – ${last.getDate()} ${first.toLocaleDateString(undefined, { month: 'short' })} ${last.getFullYear()}`
  }
  return `${first.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })} – ${last.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })} ${last.getFullYear()}`
}

export function formatMonthTitle(anchor: Date): string {
  return anchor.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
}

export function formatDayLabel(key: string): string {
  return fromDateKey(key).toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
}

export type BmiCategory = 'underweight' | 'healthy' | 'overweight' | 'obese'

export function bmiCategory(value: number): BmiCategory {
  if (value < 18.5) return 'underweight'
  if (value < 25) return 'healthy'
  if (value < 30) return 'overweight'
  return 'obese'
}

export const BMI_CATEGORY_LABELS: Record<BmiCategory, string> = {
  underweight: 'Underweight',
  healthy: 'Healthy range',
  overweight: 'Overweight',
  obese: 'Obese',
}

/** Feet-and-inches from centimetres, for imperial display. */
export function cmToFeetInches(cm: number): string {
  const totalInches = cm / 2.54
  const feet = Math.floor(totalInches / 12)
  const inches = Math.round(totalInches - feet * 12)
  return `${feet}' ${inches}"`
}

export function kgToLb(kg: number): number {
  return kg * 2.2046226
}

export function lbToKg(lb: number): number {
  return lb / 2.2046226
}

export function cmToInches(cm: number): number {
  return cm / 2.54
}

export function inchesToCm(inches: number): number {
  return inches * 2.54
}

/** Parse "5'11\"" or 71 into centimetres. */
export function parseHeightInput(value: string, unit: string): number | null {
  const trimmed = value.trim()
  if (trimmed === '') return null
  if (unit === 'cm') {
    const cm = Number(trimmed)
    return Number.isFinite(cm) ? cm : null
  }
  if (unit === 'in') {
    const inches = Number(trimmed)
    return Number.isFinite(inches) ? inchesToCm(inches) : null
  }
  const feetMatch = /^(\d+(?:\.\d+)?)\s*(?:'|ft)\s*(\d+(?:\.\d+)?)?\s*(?:"|in)?$/i.exec(trimmed)
  if (!feetMatch) {
    const inches = Number(trimmed)
    return Number.isFinite(inches) && inches > 0 ? inchesToCm(inches) : null
  }
  const feet = Number(feetMatch[1])
  const inches = feetMatch[2] ? Number(feetMatch[2]) : 0
  return inchesToCm(feet * 12 + inches)
}

export function formatWeight(kg: number, units: 'metric' | 'imperial'): string {
  return units === 'imperial' ? `${kgToLb(kg).toFixed(1)} lb` : `${kg.toFixed(1)} kg`
}

export function formatHeight(cm: number, units: 'metric' | 'imperial'): string {
  return units === 'imperial' ? cmToFeetInches(cm) : `${Math.round(cm)} cm`
}
