import { describe, expect, it } from 'vitest'
import { ApiError, errorMessage, toMessage, validationIssues } from './api'

describe('error copy mapping', () => {
  it('never uses 404 copy for empty data (the API returns 200 with [])', () => {
    // A list endpoint that has no rows must be a 200 with an empty array; the
    // "couldn't find that" copy is reserved for genuinely missing resources.
    const notFound = errorMessage(404, '{"error":{"code":"RESOURCE_NOT_FOUND","message":"Planned session not found."}}')
    expect(notFound).toBe('Planned session not found.')
    expect(new ApiError(200, '[]').status).toBe(200)
  })

  it('maps each failure class to distinct copy', () => {
    const cases: [number, RegExp][] = [
      [401, /session has expired/i],
      [403, /don't have access/i],
      [404, /couldn't find that/i],
      [413, /too large/i],
      [415, /not supported/i],
      [429, /too many requests/i],
      [500, /went wrong on our side/i],
      [503, /unavailable/i],
    ]
    const messages = cases.map(([status]) => errorMessage(status, '{}'))
    for (const [index, [, pattern]] of cases.entries()) {
      expect(messages[index]).toMatch(pattern)
    }
    expect(new Set(messages).size).toBe(cases.length)
  })

  it('never leaks raw JSON', () => {
    const raw = '{"error":{"code":"INTERNAL_ERROR","message":"select * from users failed"}}'
    expect(errorMessage(500, raw)).not.toContain('{')
    expect(errorMessage(500, raw)).not.toContain('select')
  })

  it('surfaces the first field message for a 422', () => {
    const body = JSON.stringify({
      error: { code: 'VALIDATION_ERROR', details: { errors: [{ msg: 'too small' }] } },
      detail: [{ loc: ['body', 'value'], msg: 'Value error, weight must be between 20 and 500 kg.' }],
    })
    expect(errorMessage(422, body)).toBe('weight must be between 20 and 500 kg.')
  })

  it('extracts field-level issues for inline display', () => {
    const err = new ApiError(
      422,
      JSON.stringify({ detail: [{ loc: ['body', 'height'], msg: 'out of range' }] }),
    )
    expect(validationIssues(err)).toEqual([{ field: 'height', message: 'out of range' }])
    expect(validationIssues(new ApiError(500, '{}'))).toEqual([])
  })

  it('has a calm fallback for unknown failures', () => {
    expect(toMessage(new Error(''), 'fallback')).toBe('fallback')
    expect(toMessage(new ApiError(418, '{}'))).toMatch(/could not be completed/i)
  })
})
