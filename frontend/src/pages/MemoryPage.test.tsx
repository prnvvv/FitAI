import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../services/api'
import { MemoryPage } from './MemoryPage'
import type { Memory, PendingMemoryUpdate } from '../types'

vi.mock('../services/api', async () => {
  const actual = await vi.importActual<typeof import('../services/api')>('../services/api')
  return {
    ...actual,
    api: {
      ...actual.api,
      listMemory: vi.fn(),
      listPendingMemory: vi.fn(),
      deleteMemory: vi.fn(),
      correctMemory: vi.fn(),
      confirmMemoryUpdate: vi.fn(),
      rejectMemoryUpdate: vi.fn(),
    },
  }
})

const memory: Memory = {
  id: 'mem-1',
  key: 'weight',
  value: 72,
  confidence: 0.9,
  source: 'agent',
  status: 'active',
  effective_at: null,
  updated_at: '2026-01-01T00:00:00Z',
  created_at: '2026-01-01T00:00:00Z',
}

function page<T>(items: T[]) {
  return { items, total: items.length, limit: 50, offset: 0 }
}

function applyDefaults() {
  const listMemory = vi.mocked(api.listMemory)
  const listPendingMemory = vi.mocked(api.listPendingMemory)
  vi.mocked(api.deleteMemory).mockResolvedValue(undefined)
  vi.mocked(api.correctMemory).mockImplementation(async (id: string, value: unknown) => ({
    ...memory,
    id,
    value: value as number,
  }))
  listPendingMemory.mockResolvedValue(page<PendingMemoryUpdate>([]))
  listMemory.mockResolvedValue(page([memory]))
  return { listMemory }
}

async function renderLoaded() {
  const spies = applyDefaults()
  render(<MemoryPage />)
  await waitFor(() => expect(screen.getByText('weight')).toBeInTheDocument())
  return spies
}

describe('MemoryPage', () => {
  beforeEach(() => {
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  it('reloads persisted memories after deleting a memory', async () => {
    const user = userEvent.setup()
    const { listMemory } = await renderLoaded()

    await user.click(screen.getByLabelText('Delete weight'))
    // Delete is guarded by an in-app confirmation dialog.
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Forget' }))

    await waitFor(() => expect(api.deleteMemory).toHaveBeenCalledWith('mem-1'))
    // Regression: previously the row was only removed from local state; the page
    // did not re-read the persisted records.
    await waitFor(() => expect(listMemory).toHaveBeenCalledTimes(2))
  })

  it('reloads persisted memories after correcting a memory', async () => {
    const user = userEvent.setup()
    const { listMemory } = await renderLoaded()

    await user.click(screen.getByLabelText('Edit weight'))
    const input = screen.getByRole('spinbutton')
    await user.clear(input)
    await user.type(input, '75')
    await user.click(screen.getByLabelText('Save'))

    await waitFor(() => expect(api.correctMemory).toHaveBeenCalledWith('mem-1', 75))
    await waitFor(() => expect(listMemory).toHaveBeenCalledTimes(2))
  })
})
