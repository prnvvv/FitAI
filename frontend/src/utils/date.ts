/**
 * Local-time date helpers for calendar UIs.
 *
 * These deliberately use the local calendar (`getFullYear`/`getMonth`/`getDate`)
 * rather than `toISOString()`, so a date selected in the UI maps to the same
 * calendar day regardless of the browser's UTC offset.
 */

/** Format a Date as a `YYYY-MM-DD` key using the local calendar day. */
export function formatDateKey(d: Date): string {
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/** Parse a `YYYY-MM-DD` key into a Date at local midnight. */
export function parseDateKey(key: string): Date {
  const [year, month, day] = key.split('-').map(Number)
  return new Date(year, month - 1, day)
}
