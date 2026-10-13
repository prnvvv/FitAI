import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LibraryPage } from './LibraryPage'
import { api } from '../services/api'
import type { Document } from '../types'

vi.mock('../services/api', () => ({
  api: {
    listDocuments: vi.fn(),
    uploadDocument: vi.fn(),
    deleteDocument: vi.fn(),
  },
  NetworkError: class NetworkError extends Error {},
  TimeoutError: class TimeoutError extends Error {},
}))

function makeDocument(status: Document['status']): Document {
  return {
    id: 'doc-1',
    filename: 'plan.pdf',
    content_type: 'application/pdf',
    size_bytes: 2048,
    status,
    created_at: '2026-01-01T00:00:00Z',
  }
}

function page(docs: Document[]) {
  return { items: docs, total: docs.length, limit: 50, offset: 0 }
}

describe('LibraryPage', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('polls until a pending document finishes indexing', async () => {
    const listDocuments = vi.mocked(api.listDocuments)
    listDocuments
      .mockResolvedValueOnce(page([makeDocument('pending')]))
      .mockResolvedValueOnce(page([makeDocument('processing')]))
      .mockResolvedValue(page([makeDocument('indexed')]))

    render(<LibraryPage />)

    expect(await screen.findByText('Queued')).toBeTruthy()

    // First poll: still indexing.
    await vi.advanceTimersByTimeAsync(3000)
    await waitFor(() => expect(screen.getByText('Reading')).toBeTruthy())

    // Second poll: indexing finished.
    await vi.advanceTimersByTimeAsync(3000)
    await waitFor(() => expect(screen.getByText('Ready')).toBeTruthy())

    expect(listDocuments.mock.calls.length).toBeGreaterThanOrEqual(3)
  })

  it('does not keep polling once every document is settled', async () => {
    const listDocuments = vi.mocked(api.listDocuments)
    listDocuments.mockResolvedValue(page([makeDocument('indexed')]))

    render(<LibraryPage />)
    expect(await screen.findByText('Ready')).toBeTruthy()

    await vi.advanceTimersByTimeAsync(15000)

    expect(listDocuments).toHaveBeenCalledTimes(1)
  })
})