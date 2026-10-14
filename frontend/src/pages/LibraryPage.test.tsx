import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from '../services/api'
import { LibraryPage } from './LibraryPage'
import type { Document } from '../types'

vi.mock('../services/api', async () => {
  const actual = await vi.importActual<typeof import('../services/api')>('../services/api')
  return {
    ...actual,
    api: {
      ...actual.api,
      listDocuments: vi.fn(),
      uploadDocument: vi.fn(),
      deleteDocument: vi.fn(),
      retryDocument: vi.fn(),
      renameDocument: vi.fn(),
    },
  }
})

const queued: Document = {
  id: 'doc-1',
  filename: 'plan.txt',
  content_type: 'text/plain',
  size_bytes: 2048,
  status: 'failed',
  failure_reason: 'Unsupported file type.',
  created_at: '2026-10-01T10:00:00Z',
}

function page(docs: Document[]) {
  return { items: docs, total: docs.length, limit: 50, offset: 0 }
}

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

/** Give every api method a sane default so a test only overrides what it cares about. */
function applyDefaults() {
  const listDocuments = vi.mocked(api.listDocuments)
  const uploadDocument = vi.mocked(api.uploadDocument)
  const deleteDocument = vi.mocked(api.deleteDocument)
  const retryDocument = vi.mocked(api.retryDocument)
  const renameDocument = vi.mocked(api.renameDocument)

  listDocuments.mockResolvedValue(page([queued]))
  uploadDocument.mockResolvedValue({ document: queued, duplicate: false })
  deleteDocument.mockResolvedValue(undefined)
  retryDocument.mockResolvedValue({ ...queued, status: 'indexed', failure_reason: null })
  renameDocument.mockImplementation(async (id: string, filename: string) => ({
    ...queued,
    id,
    filename,
  }))

  return { listDocuments, uploadDocument, deleteDocument, retryDocument, renameDocument }
}

async function renderLoaded() {
  const spies = applyDefaults()
  render(<LibraryPage />)
  await waitFor(() => expect(screen.getByText('plan.txt')).toBeInTheDocument())
  return spies
}

afterEach(() => {
  vi.clearAllMocks()
})

describe('LibraryPage', () => {
  it('shows a readable failure reason and offers retry', async () => {
    const spies = await renderLoaded()
    const user = userEvent.setup()

    expect(screen.getByText('Failed')).toBeInTheDocument()
    expect(screen.getByText('Unsupported file type.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(spies.retryDocument).toHaveBeenCalledWith('doc-1'))
  })

  it('maps a server error to calm copy instead of raw JSON', async () => {
    const { uploadDocument } = applyDefaults()
    uploadDocument.mockRejectedValue(
      new ApiError(
        500,
        '{"error":{"code":"INTERNAL_ERROR","message":"The activity event could not be recorded."}}',
      ),
    )
    render(<LibraryPage />)
    await waitFor(() => expect(screen.getByText('plan.txt')).toBeInTheDocument())

    const user = userEvent.setup()
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, new File(['data'], 'broken.txt', { type: 'text/plain' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Something went wrong on our side. Please try again.')
    expect(alert).not.toHaveTextContent('{')
  })

  it('lets the user dismiss the error banner', async () => {
    const { listDocuments } = applyDefaults()
    listDocuments.mockRejectedValue(new ApiError(500, '{}'))
    render(<LibraryPage />)

    const alert = await screen.findByRole('alert')
    const user = userEvent.setup()
    await user.click(screen.getByLabelText('Dismiss'))
    await waitFor(() => expect(alert).not.toBeInTheDocument())
  })

  it('shows a friendly type instead of a raw MIME string', async () => {
    await renderLoaded()
    expect(screen.getByText(/Document · TXT/)).toBeInTheDocument()
  })

  it('says "Already in your library" for identical bytes', async () => {
    const { uploadDocument } = applyDefaults()
    uploadDocument.mockResolvedValue({ document: queued, duplicate: true })
    render(<LibraryPage />)
    await waitFor(() => expect(screen.getByText('plan.txt')).toBeInTheDocument())

    const user = userEvent.setup()
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, new File(['x'], 'plan.txt', { type: 'text/plain' }))
    expect(await screen.findByText(/Already in your library/)).toBeInTheDocument()
  })

  it('renames an item', async () => {
    const spies = await renderLoaded()
    const user = userEvent.setup()

    await user.click(screen.getByLabelText('Rename plan.txt'))
    const input = screen.getByDisplayValue('plan.txt')
    await user.clear(input)
    await user.type(input, 'Squat plan.txt')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(spies.renameDocument).toHaveBeenCalledWith('doc-1', 'Squat plan.txt'))
  })

  it('deletes an item', async () => {
    const spies = await renderLoaded()
    const user = userEvent.setup()

    vi.spyOn(window, 'confirm').mockReturnValue(true)
    await user.click(screen.getByLabelText('Delete plan.txt'))
    await waitFor(() => expect(spies.deleteDocument).toHaveBeenCalledWith('doc-1'))
  })
})

describe('LibraryPage polling', () => {
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
