import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { ApiError, api } from '../services/api'
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

function msg(id: string, conversation: string, role: 'user' | 'assistant', content: string, second = 0): Message {
  return {
    id,
    conversation_id: conversation,
    role,
    content,
    created_at: `2026-01-01T00:00:${String(second).padStart(2, '0')}Z`,
  }
}

const c1 = [msg('m1', 'c1', 'user', 'Hello from c1', 0), msg('m2', 'c1', 'assistant', 'Reply in c1', 1)]
const c2 = [msg('m3', 'c2', 'user', 'Question in c2', 0), msg('m4', 'c2', 'assistant', 'Answer in c2', 1)]
const byConversation: Record<string, Message[]> = { c1, c2 }

function page(items: Message[], total = items.length, offset = 0): Page<Message> {
  return { items, total, limit: 100, offset }
}

/** Resolves a promise from the outside, to control response ordering. */
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

/** Mirrors the real route table: "/" is the new-chat screen, "/chat/:id" a saved one. */
function Harness({ path }: { path: string }) {
  return (
    <MemoryRouter initialEntries={[path]}>
      <nav>
        <Link to="/chat/c1">go-c1</Link>
        <Link to="/chat/c2">go-c2</Link>
        <Link to="/">go-new</Link>
      </nav>
      <Routes>
        <Route index element={<ChatPage onConversationCreated={() => {}} />} />
        <Route path="chat/:conversationId" element={<ChatPage onConversationCreated={() => {}} />} />
      </Routes>
    </MemoryRouter>
  )
}

function serveHistory() {
  vi.mocked(api.listMessages).mockImplementation(async (id) => page(byConversation[id] ?? []))
}

describe('ChatPage history', () => {
  afterEach(() => vi.clearAllMocks())

  it('loads persisted history when opened directly (page refresh)', async () => {
    serveHistory()
    render(<Harness path="/chat/c1" />)

    expect(await screen.findByText('Hello from c1')).toBeInTheDocument()
    expect(screen.getByText('Reply in c1')).toBeInTheDocument()
  })

  it('still loads history under React StrictMode, which runs effects twice in development', async () => {
    // Regression for the refresh bug: the first run's request was cancelled by
    // StrictMode's simulated unmount and a "same id as last time" guard then
    // stopped the second run from requesting again, so nothing ever loaded.
    serveHistory()
    render(
      <StrictMode>
        <MemoryRouter initialEntries={['/chat/c1']}>
          <Routes>
            <Route path="chat/:conversationId" element={<ChatPage />} />
          </Routes>
        </MemoryRouter>
      </StrictMode>,
    )

    expect(await screen.findByText('Hello from c1')).toBeInTheDocument()
    expect(screen.getByText('Reply in c1')).toBeInTheDocument()
    expect(screen.queryByText('Loading conversation…')).not.toBeInTheDocument()
  })

  it('shows a loading indicator, not an empty or welcome screen, while history loads', async () => {
    const pending = deferred<Page<Message>>()
    vi.mocked(api.listMessages).mockReturnValue(pending.promise)
    render(<Harness path="/chat/c1" />)

    expect(screen.getByText('Loading conversation…')).toBeInTheDocument()
    expect(screen.queryByText(/what can i help/i)).not.toBeInTheDocument()

    pending.resolve(page(c1))
    expect(await screen.findByText('Hello from c1')).toBeInTheDocument()
  })

  it('restores the first conversation after visiting another and coming back', async () => {
    serveHistory()
    const user = userEvent.setup()
    render(<Harness path="/chat/c1" />)
    await screen.findByText('Hello from c1')

    await user.click(screen.getByText('go-c2'))
    expect(await screen.findByText('Question in c2')).toBeInTheDocument()
    expect(screen.queryByText('Hello from c1')).not.toBeInTheDocument()

    await user.click(screen.getByText('go-c1'))
    expect(await screen.findByText('Hello from c1')).toBeInTheDocument()
    expect(screen.getByText('Reply in c1')).toBeInTheDocument()
    expect(screen.queryByText('Question in c2')).not.toBeInTheDocument()
  })

  it('never shows the previous conversation while the next one is loading', async () => {
    const second = deferred<Page<Message>>()
    vi.mocked(api.listMessages).mockImplementation((id) =>
      id === 'c1' ? Promise.resolve(page(c1)) : second.promise,
    )
    const user = userEvent.setup()
    render(<Harness path="/chat/c1" />)
    await screen.findByText('Hello from c1')

    await user.click(screen.getByText('go-c2'))
    expect(screen.queryByText('Hello from c1')).not.toBeInTheDocument()
    expect(screen.getByText('Loading conversation…')).toBeInTheDocument()

    second.resolve(page(c2))
    expect(await screen.findByText('Question in c2')).toBeInTheDocument()
  })

  it('ignores a slow response for a conversation the user already left', async () => {
    const slowC1 = deferred<Page<Message>>()
    vi.mocked(api.listMessages).mockImplementation((id) =>
      id === 'c1' ? slowC1.promise : Promise.resolve(page(c2)),
    )
    const user = userEvent.setup()
    render(<Harness path="/chat/c1" />)

    await user.click(screen.getByText('go-c2'))
    expect(await screen.findByText('Question in c2')).toBeInTheDocument()

    // The old request finally answers: it must not replace conversation 2.
    slowC1.resolve(page(c1))
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(screen.getByText('Question in c2')).toBeInTheDocument()
    expect(screen.queryByText('Hello from c1')).not.toBeInTheDocument()
  })

  it('survives rapid switching between several conversations', async () => {
    serveHistory()
    const user = userEvent.setup()
    render(<Harness path="/chat/c1" />)
    for (const target of ['go-c2', 'go-c1', 'go-c2', 'go-c1', 'go-c2']) {
      await user.click(screen.getByText(target))
    }
    expect(await screen.findByText('Question in c2')).toBeInTheDocument()
    expect(screen.queryByText('Hello from c1')).not.toBeInTheDocument()
  })

  it('shows a recoverable error when history fails, and Retry loads it', async () => {
    vi.mocked(api.listMessages).mockRejectedValueOnce(new Error('Server unavailable'))
    vi.mocked(api.listMessages).mockResolvedValue(page(c1))
    const user = userEvent.setup()
    render(<Harness path="/chat/c1" />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Could not load this conversation')
    expect(alert).toHaveTextContent('Server unavailable')
    // A failed load is not presented as an empty conversation.
    expect(screen.queryByText(/what can i help/i)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('Hello from c1')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
  })

  it('explains a deleted or foreign conversation instead of offering a pointless retry', async () => {
    vi.mocked(api.listMessages).mockRejectedValue(new ApiError(404, '{"error":{"message":"Conversation not found."}}'))
    render(<Harness path="/chat/c1" />)

    expect(await screen.findByText(/no longer exists/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start a new chat' })).toBeInTheDocument()
  })

  it('shows the welcome screen, not an error, for a genuinely empty conversation', async () => {
    vi.mocked(api.listMessages).mockResolvedValue(page([]))
    render(<Harness path="/chat/c1" />)

    await waitFor(() => expect(screen.queryByText('Loading conversation…')).not.toBeInTheDocument())
    expect(screen.queryByText(/could not load/i)).not.toBeInTheDocument()
  })

  it('reads every page of a long conversation instead of truncating at 100', async () => {
    const all = Array.from({ length: 130 }, (_, i) =>
      msg(`x${i}`, 'c1', i % 2 ? 'assistant' : 'user', `message ${i}`, i % 60),
    )
    vi.mocked(api.listMessages).mockImplementation(async (_id, _limit, offset = 0) =>
      page(all.slice(offset, offset + 100), all.length, offset),
    )
    render(<Harness path="/chat/c1" />)

    expect(await screen.findByText('message 129')).toBeInTheDocument()
    expect(screen.getByText('message 0')).toBeInTheDocument()
    expect(api.listMessages).toHaveBeenCalledTimes(2)
    expect(api.listMessages).toHaveBeenLastCalledWith('c1', 100, 100)
  })
})

describe('ChatPage sending', () => {
  afterEach(() => vi.clearAllMocks())

  it('creates a conversation from the new-chat screen and keeps its messages on screen', async () => {
    vi.mocked(api.listMessages).mockImplementation(async (id) =>
      page(id === 'c9' ? [msg('s1', 'c9', 'user', 'hi coach', 0), msg('s2', 'c9', 'assistant', 'hello athlete', 1)] : []),
    )
    vi.mocked(api.sendMessage).mockResolvedValue({
      conversation_id: 'c9',
      title: 'hi coach',
      response: 'hello athlete',
      sources: [],
      actions: [],
      tool_events: [],
    })
    const user = userEvent.setup()
    render(<Harness path="/" />)

    await user.type(screen.getByRole('textbox', { name: 'Message' }), 'hi coach{Enter}')

    expect(await screen.findByText('hello athlete')).toBeInTheDocument()
    expect(screen.getByText('hi coach')).toBeInTheDocument()
    expect(api.sendMessage).toHaveBeenCalledWith({ message: 'hi coach', conversation_id: undefined })
  })

  it('does not draw a late reply into a different conversation', async () => {
    serveHistory()
    const reply = deferred<Awaited<ReturnType<typeof api.sendMessage>>>()
    vi.mocked(api.sendMessage).mockReturnValue(reply.promise)
    const user = userEvent.setup()
    render(<Harness path="/chat/c1" />)
    await screen.findByText('Hello from c1')

    await user.type(screen.getByRole('textbox', { name: 'Message' }), 'slow question{Enter}')
    await user.click(screen.getByText('go-c2'))
    await screen.findByText('Question in c2')

    reply.resolve({
      conversation_id: 'c1',
      title: null,
      response: 'late answer for c1',
      sources: [],
      actions: [],
      tool_events: [],
    })
    await new Promise((resolve) => setTimeout(resolve, 20))

    expect(screen.queryByText('late answer for c1')).not.toBeInTheDocument()
    expect(screen.queryByText('slow question')).not.toBeInTheDocument()
    expect(screen.getByText('Question in c2')).toBeInTheDocument()
  })

  it('removes the optimistic message and keeps history when sending fails', async () => {
    serveHistory()
    vi.mocked(api.sendMessage).mockRejectedValue(new Error('Model unavailable'))
    const user = userEvent.setup()
    render(<Harness path="/chat/c1" />)
    await screen.findByText('Hello from c1')

    await user.type(screen.getByRole('textbox', { name: 'Message' }), 'will fail{Enter}')

    expect(await screen.findByText('Model unavailable')).toBeInTheDocument()
    expect(screen.queryByText('will fail')).not.toBeInTheDocument()
    expect(screen.getByText('Hello from c1')).toBeInTheDocument()
    expect(screen.getByText('Reply in c1')).toBeInTheDocument()
  })

  it('renders tool events from a live reply the same way as a reloaded one', async () => {
    serveHistory()
    vi.mocked(api.sendMessage).mockResolvedValue({
      conversation_id: 'c1',
      title: null,
      response: 'Here is what I found',
      sources: [],
      actions: [],
      tool_events: [{ tool: 'web_search', status: 'ok', sources: 3 }],
    } as Awaited<ReturnType<typeof api.sendMessage>>)
    const user = userEvent.setup()
    render(<Harness path="/chat/c1" />)
    await screen.findByText('Hello from c1')

    await user.type(screen.getByRole('textbox', { name: 'Message' }), 'search it{Enter}')
    expect(await screen.findByText('Here is what I found')).toBeInTheDocument()
    expect(screen.getByText('Searched the web (3 sources)')).toBeInTheDocument()
  })
})
