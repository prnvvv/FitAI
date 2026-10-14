import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { api } from '../services/api'
import { ChatPage } from './ChatPage'
import type { Message, Page } from '../types'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1', email: 'a@b.c', displayName: 'A' }, loading: false }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}))

// jsdom does not implement scrollIntoView, used by the message list autoscroll.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

vi.mock('../services/api', async () => {
  const actual = await vi.importActual<typeof import('../services/api')>('../services/api')
  return {
    ...actual,
    api: {
      ...actual.api,
      listMessages: vi.fn(),
      sendMessage: vi.fn(),
      confirmMemoryUpdate: vi.fn(),
      rejectMemoryUpdate: vi.fn(),
    },
  }
})

const history: Message[] = [
  {
    id: 'm1',
    conversation_id: 'c1',
    role: 'user',
    content: 'Hello there',
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'm2',
    conversation_id: 'c1',
    role: 'assistant',
    content: 'Hi! How can I help?',
    created_at: '2026-01-01T00:00:01Z',
  },
]

function messagePage(items: Message[]): Page<Message> {
  return { items, total: items.length, limit: 100, offset: 0 }
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/chat/:conversationId" element={<ChatPage onConversationCreated={() => {}} />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ChatPage', () => {
  afterEach(() => vi.clearAllMocks())

  it('loads persisted history when opened directly (survives a page refresh)', async () => {
    vi.mocked(api.listMessages).mockResolvedValue(messagePage(history))

    renderAt('/chat/c1')

    // Regression: previously the mount effect early-returned because the ref was
    // seeded with the current URL id, so no history request was ever made.
    await waitFor(() => expect(api.listMessages).toHaveBeenCalledWith('c1'))
    expect(await screen.findByText('Hello there')).toBeInTheDocument()
    expect(screen.getByText('Hi! How can I help?')).toBeInTheDocument()
  })
})
