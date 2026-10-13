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
})
