import { Loader2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Composer } from '../components/chat/Composer'
import { MessageList } from '../components/chat/MessageList'
import { WelcomeScreen } from '../components/chat/WelcomeScreen'
import { api } from '../services/api'
import type { Message } from '../types'

interface ChatPageProps {
  onConversationCreated?: (id: string, title: string | null) => void
}

/** Messages always travel with the conversation they belong to. */
interface Thread {
  conversationId: string | null
  items: Message[]
}

interface HistoryError {
  conversationId: string
  message: string
}

const HISTORY_PAGE_SIZE = 100
/** Upper bound so a pathological conversation cannot load unbounded data. */
const MAX_HISTORY_PAGES = 50
/** Key used for the "new chat" screen while a first message is in flight. */
const NEW_CHAT_KEY = '__new__'

/**
 * Loads a conversation's full persisted history. The API caps a page at 100
 * messages, so longer conversations are read page by page rather than silently
 * truncated.
 */
async function loadHistory(conversationId: string): Promise<Message[]> {
  const items: Message[] = []
  for (let page = 0; page < MAX_HISTORY_PAGES; page += 1) {
    const result = await api.listMessages(conversationId, HISTORY_PAGE_SIZE, items.length)
    items.push(...result.items)
    if (result.items.length === 0 || items.length >= result.total) break
  }
  return items
}

export function ChatPage({ onConversationCreated }: ChatPageProps) {
  const { conversationId } = useParams<{ conversationId?: string }>()
  const navigate = useNavigate()
  const viewingKey = conversationId ?? null

  const [thread, setThread] = useState<Thread>({ conversationId: null, items: [] })
  const [historyError, setHistoryError] = useState<HistoryError | null>(null)
  const [reloadToken, setReloadToken] = useState(0)
  const [pendingKey, setPendingKey] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Refs mirror state the async handlers need to read at the moment they resume.
  const threadRef = useRef<Thread>(thread)
  const viewingRef = useRef<string | null>(viewingKey)
  const sendLock = useRef(false)
  const reconcileToken = useRef(0)

  const applyThread = useCallback((next: Thread) => {
    threadRef.current = next
    setThread(next)
  }, [])

  // The database is the source of truth: every time the user opens a
  // conversation that is not already on screen, its history is read from the API.
  // Keyed on the id only, and every run owns its own `cancelled` flag, so a slow
  // response for a previous conversation can never overwrite the current one
  // (and React StrictMode's mount/unmount/mount cycle simply fetches again).
  useEffect(() => {
    viewingRef.current = viewingKey
    setError(null)

    if (viewingKey === null) {
      setHistoryError(null)
      if (threadRef.current.conversationId !== null) applyThread({ conversationId: null, items: [] })
      return
    }
    // Already showing this conversation (e.g. it was just created here).
    if (threadRef.current.conversationId === viewingKey) {
      setHistoryError(null)
      return
    }

    let cancelled = false
    setHistoryError(null)
    loadHistory(viewingKey)
      .then((items) => {
        if (!cancelled) applyThread({ conversationId: viewingKey, items })
      })
      .catch((err) => {
        if (cancelled) return
        setHistoryError({
          conversationId: viewingKey,
          message: err instanceof Error ? err.message : 'Failed to load messages',
        })
      })
    return () => {
      cancelled = true
    }
  }, [viewingKey, reloadToken, applyThread])

  const retryHistory = useCallback(() => {
    setHistoryError(null)
    setReloadToken((n) => n + 1)
  }, [])

  /** Appends to the on-screen thread only if the user is still looking at `key`. */
  const updateIfViewing = useCallback(
    (key: string | null, update: (items: Message[]) => Message[], nextId = key) => {
      if (viewingRef.current !== key) return false
      applyThread({ conversationId: nextId, items: update(threadRef.current.items) })
      return true
    },
    [applyThread],
  )

  const handleSend = useCallback(
    async (text: string) => {
      if (sendLock.current) return
      sendLock.current = true
      reconcileToken.current += 1
      const targetKey = viewingRef.current
      setPendingKey(targetKey ?? NEW_CHAT_KEY)
      setError(null)

      const optimisticUserMessage: Message = {
        id: `temp-${Date.now()}`,
        conversation_id: targetKey ?? '',
        role: 'user',
        content: text,
        created_at: new Date().toISOString(),
      }
      updateIfViewing(targetKey, (items) => [...items, optimisticUserMessage])

      try {
        const result = await api.sendMessage({
          message: text,
          conversation_id: targetKey ?? undefined,
        })

        onConversationCreated?.(result.conversation_id, result.title)

        const assistantMessage: Message = {
          id: `resp-${Date.now()}`,
          conversation_id: result.conversation_id,
          role: 'assistant',
          content: result.response,
          metadata: {
            sources: result.sources ?? [],
            actions: result.actions ?? [],
            tool_events: result.tool_events ?? [],
          },
          created_at: new Date().toISOString(),
        }

        // If the user moved to another conversation while waiting, the reply is
        // already saved server-side; it must not be drawn into the wrong thread.
        const stillViewing = updateIfViewing(
          targetKey,
          (items) =>
            items
              .filter((m) => m.id !== optimisticUserMessage.id)
              .concat(
                { ...optimisticUserMessage, conversation_id: result.conversation_id },
                assistantMessage,
              ),
          result.conversation_id,
        )

        if (stillViewing) {
          if (result.conversation_id !== targetKey) {
            viewingRef.current = result.conversation_id
            navigate(`/chat/${result.conversation_id}`, { replace: true })
          }
          // Swap the temporary ids for the stored messages (quietly, no spinner).
          const token = reconcileToken.current
          const reconciledId = result.conversation_id
          loadHistory(reconciledId)
            .then((items) => {
              const unchanged =
                token === reconcileToken.current &&
                !sendLock.current &&
                viewingRef.current === reconciledId
              if (unchanged && items.length >= threadRef.current.items.length) {
                applyThread({ conversationId: reconciledId, items })
              }
            })
            .catch(() => {
              // Keep the optimistic copy; it matches what was just saved.
            })
        }
      } catch (err) {
        console.error(err)
        const message = err instanceof Error ? err.message : 'Failed to send message'
        if (viewingRef.current === targetKey) setError(message)
        updateIfViewing(targetKey, (items) => items.filter((m) => m.id !== optimisticUserMessage.id))
      } finally {
        setPendingKey(null)
        sendLock.current = false
      }
    },
    [applyThread, navigate, onConversationCreated, updateIfViewing],
  )

  const threadMatches = thread.conversationId === viewingKey
  const messages = threadMatches ? thread.items : []
  const failedHistory = historyError?.conversationId === viewingKey ? historyError : null
  const loadingHistory = viewingKey !== null && !threadMatches && failedHistory === null
  const sending = pendingKey !== null
  const streaming = pendingKey === (viewingKey ?? NEW_CHAT_KEY)
  const hasMessages = messages.length > 0

  let body
  if (loadingHistory) {
    body = (
      <div className="chat-page__history" role="status" aria-busy="true">
        <Loader2 className="page__spinner" size={20} aria-hidden="true" />
        <span>Loading conversation…</span>
      </div>
    )
  } else if (failedHistory) {
    body = (
      <div className="chat-page__history chat-page__history--error" role="alert">
        <span>Could not load this conversation. {failedHistory.message}</span>
        <button type="button" className="chat-page__retry" onClick={retryHistory}>
          Retry
        </button>
      </div>
    )
  } else if (!hasMessages && !streaming && !error) {
    body = <WelcomeScreen onSuggestion={(text) => handleSend(text)} />
  } else {
    body = <MessageList messages={messages} loading={streaming} />
  }

  return (
    <div className="chat-page">
      {body}
      {error && (
        <div className="chat-page__error" role="alert">
          {error}
        </div>
      )}
      <div className="chat-page__composer">
        <Composer
          // Keyed by conversation: switching conversations remounts the
          // composer, which cancels any recording or transcription in flight so
          // a transcript cannot land in another conversation.
          key={conversationId ?? 'new'}
          onSend={handleSend}
          disabled={sending || loadingHistory}
          streaming={streaming}
          onSpeechError={setError}
          onOpenDocuments={() => navigate('/library')}
        />
        <div className="chat-page__disclaimer">
          FitAI can make mistakes. Always consult a professional for medical advice.
        </div>
      </div>
    </div>
  )
}
