import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { useConversations } from './useConversations'
import { api } from '../services/api'
import type { Conversation } from '../types'

vi.mock('../services/api', () => ({
  api: {
    listConversations: vi.fn(),
    renameConversation: vi.fn(),
    deleteConversation: vi.fn(),
  },
}))

function wrapper(path = '/') {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/chat/:conversationId" element={children} />
          <Route path="*" element={children} />
        </Routes>
      </MemoryRouter>
    )
  }
}

describe('useConversations', () => {
  it('loads and filters conversations', async () => {
    const conversations: Conversation[] = [
      { id: '1', title: 'Workout plan', created_at: '', updated_at: '' },
      { id: '2', title: 'Nutrition goals', created_at: '', updated_at: '' },
    ]
    vi.mocked(api.listConversations).mockResolvedValueOnce({
      items: conversations,
      total: 2,
      limit: 100,
      offset: 0,
    })

    const { result } = renderHook(() => useConversations({ enabled: true }), {
      wrapper: wrapper(),
    })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.conversations).toHaveLength(2)

    act(() => {
      result.current.setSearchQuery('nutrition')
    })
    await waitFor(() => expect(result.current.conversations).toHaveLength(1))
    expect(result.current.conversations[0].title).toBe('Nutrition goals')
  })

  it('exposes active conversation from URL', async () => {
    vi.mocked(api.listConversations).mockResolvedValueOnce({
      items: [{ id: '1', title: 'Chat', created_at: '', updated_at: '' }],
      total: 1,
      limit: 100,
      offset: 0,
    })

    const { result } = renderHook(() => useConversations({ enabled: true }), {
      wrapper: wrapper('/chat/1'),
    })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.activeId).toBe('1')
  })

  it('renames conversation optimistically', async () => {
    const conversations: Conversation[] = [
      { id: '1', title: 'Old title', created_at: '', updated_at: '' },
    ]
    vi.mocked(api.listConversations).mockResolvedValueOnce({
      items: conversations,
      total: 1,
      limit: 100,
      offset: 0,
    })
    vi.mocked(api.renameConversation).mockResolvedValueOnce({
      id: '1',
      title: 'New title',
      created_at: '',
      updated_at: '',
    })

    const { result } = renderHook(() => useConversations({ enabled: true }), {
      wrapper: wrapper(),
    })

    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.renameConversation('1', 'New title')
    })
    await waitFor(() => expect(result.current.conversations[0].title).toBe('New title'))
    expect(api.renameConversation).toHaveBeenCalledWith('1', 'New title')
  })

  it('deletes conversation optimistically', async () => {
    const conversations: Conversation[] = [
      { id: '1', title: 'Chat', created_at: '', updated_at: '' },
    ]
    vi.mocked(api.listConversations).mockResolvedValueOnce({
      items: conversations,
      total: 1,
      limit: 100,
      offset: 0,
    })
    vi.mocked(api.deleteConversation).mockResolvedValueOnce(undefined)

    const { result } = renderHook(() => useConversations({ enabled: true }), {
      wrapper: wrapper(),
    })

    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.deleteConversation('1')
    })
    await waitFor(() => expect(result.current.conversations).toHaveLength(0))
    expect(api.deleteConversation).toHaveBeenCalledWith('1')
  })
  it('keeps the newest list when an older refresh resolves last', async () => {
    const stale: Conversation = { id: 'old', title: 'Stale', created_at: '', updated_at: '' }
    const fresh: Conversation = { id: 'new', title: 'Fresh', created_at: '', updated_at: '' }
    let resolveSlow!: (value: unknown) => void
    const page = (items: Conversation[]) => ({ items, total: items.length, limit: 100, offset: 0 })
    vi.mocked(api.listConversations)
      .mockImplementationOnce(() => new Promise((resolve) => (resolveSlow = resolve)) as never)
      .mockResolvedValueOnce(page([fresh]))

    const { result } = renderHook(() => useConversations({ enabled: true }), { wrapper: wrapper() })
    await act(async () => {
      await result.current.refresh()
    })
    await waitFor(() => expect(result.current.conversations[0]?.id).toBe('new'))

    // The first (older) request finally answers; it must not replace the newer list.
    await act(async () => {
      resolveSlow(page([stale]))
    })
    expect(result.current.conversations.map((c) => c.id)).toEqual(['new'])
  })

  it('does not blank a populated list while refreshing in the background', async () => {
    const one: Conversation = { id: '1', title: 'One', created_at: '', updated_at: '' }
    const page = { items: [one], total: 1, limit: 100, offset: 0 }
    vi.mocked(api.listConversations).mockResolvedValue(page)
    const { result } = renderHook(() => useConversations({ enabled: true }), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.loading).toBe(false))

    let sawLoading = false
    const refreshing = act(async () => {
      const p = result.current.refresh()
      sawLoading = result.current.loading
      await p
    })
    await refreshing
    expect(sawLoading).toBe(false)
    expect(result.current.conversations).toHaveLength(1)
  })
})
