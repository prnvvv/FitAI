import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../services/api'
import type { Document } from '../types'

const queued: Document = {
  id: 'doc-1',
  filename: 'plan.jpg',
  content_type: 'image/jpeg',
  size_bytes: 2048,
  status: 'failed',
  failure_reason: "Unsupported file type.",
  created_at: '2026-10-01T10:00:00Z',
}

function mockApi(overrides: Record<string, unknown> = {}) {
  const spies: Record<string, unknown> = {
    listDocuments: vi.fn(async () => ({ items: [queued], total: 1, limit: 50, offset: 0 })),
    uploadDocument: vi.fn(async () => queued),
    deleteDocument: vi.fn(async () => undefined),
    retryDocument: vi.fn(async () => ({ ...queued, status: 'indexed', failure_reason: null })),
    renameDocument: vi.fn(async (id: string, filename: string) => ({ ...queued, id, filename })),
    ...overrides,
  }
  vi.doMock('../services/api', async () => {
    const actual = await vi.importActual<typeof import('../services/api')>('../services/api')
    return { ...actual, api: spies }
  })
  return spies
}

async function renderLibrary(overrides: Record<string, unknown> = {}) {
  const spies = mockApi(overrides)
  vi.resetModules()
  const module = await import('./LibraryPage')
  const user = userEvent.setup()
  const view = render(<module.LibraryPage />)
  if (!('listDocuments' in overrides) || !(overrides.listDocuments instanceof Function)) {
    await waitFor(() => expect(screen.getByText('plan.jpg')).toBeInTheDocument())
  }
  return { spies, user, view }
}

afterEach(() => {
  vi.resetModules()
  vi.restoreAllMocks()
})

describe('LibraryPage', () => {
  it('shows a readable failure reason and offers retry', async () => {
    const { spies, user } = await renderLibrary()
    expect(screen.getByText('Failed')).toBeInTheDocument()
    expect(screen.getByText('Unsupported file type.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(spies.retryDocument).toHaveBeenCalledWith('doc-1'))
  })

  it('maps a server error to calm copy instead of raw JSON', async () => {
    const { user } = await renderLibrary({
      uploadDocument: vi.fn(async () => {
        throw new ApiError(500, '{"error":{"code":"INTERNAL_ERROR","message":"The activity event could not be recorded."}}')
      }),
    })

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, new File(['data'], 'broken.png', { type: 'image/png' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Something went wrong on our side. Please try again.')
    expect(alert).not.toHaveTextContent('{')
  })

  it('lets the user dismiss the error banner', async () => {
    const { user } = await renderLibrary({
      listDocuments: vi.fn(async () => {
        throw new ApiError(500, '{}')
      }),
    })

    const alert = await screen.findByRole('alert')
    await user.click(screen.getByLabelText('Dismiss'))
    await waitFor(() => expect(alert).not.toBeInTheDocument())
  })

  it('shows a friendly type instead of a raw MIME string', async () => {
    await renderLibrary()
    expect(screen.getByText(/Image · JPEG/)).toBeInTheDocument()
  })

  it('says "Already in your library" for identical bytes', async () => {
    const { user } = await renderLibrary({
      uploadDocument: vi.fn(async () => ({ document: queued, duplicate: true })),
    })
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, new File(['x'], 'plan.jpg', { type: 'image/jpeg' }))
    expect(await screen.findByText(/Already in your library/)).toBeInTheDocument()
  })

  it('renames an item', async () => {
    const { spies, user } = await renderLibrary()
    await user.click(screen.getByLabelText('Rename plan.jpg'))
    const input = screen.getByDisplayValue('plan.jpg')
    await user.clear(input)
    await user.type(input, 'Squat plan.jpg')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(spies.renameDocument).toHaveBeenCalledWith('doc-1', 'Squat plan.jpg'))
  })

  it('deletes an item', async () => {
    const { spies, user } = await renderLibrary()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    await user.click(screen.getByLabelText('Delete plan.jpg'))
    await waitFor(() => expect(spies.deleteDocument).toHaveBeenCalledWith('doc-1'))
  })
})
