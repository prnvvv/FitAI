import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Share2, Check } from 'lucide-react'
import { Composer } from '../components/chat/Composer'
import { MessageList } from '../components/chat/MessageList'
import { WelcomeScreen } from '../components/chat/WelcomeScreen'
import { api } from '../services/api'
import type { Message } from '../types'

interface ChatPageProps {
  onConversationCreated?: (id: string, title: string | null) => void
}

export function ChatPage({ onConversationCreated }: ChatPageProps) {
  const { conversationId } = useParams<{ conversationId?: string }>()
  const navigate = useNavigate()
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [shareCopied, setShareCopied] = useState(false)
  const lastConversationId = useRef<string | undefined>(conversationId)
  const sendLock = useRef(false)

  useEffect(() => {
    if (conversationId === lastConversationId.current) return
    lastConversationId.current = conversationId
    setError(null)

    if (!conversationId) {
      setMessages([])
      setLoading(false)
      return
    }

    let cancelled = false
    setLoading(true)
    api
      .listMessages(conversationId)
      .then((page) => {
        if (!cancelled) setMessages(page.items)
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load messages')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [conversationId])

  const handleSend = useCallback(
    async (text: string, _files: File[]) => {
      if (sendLock.current || streaming) return
      sendLock.current = true
      setStreaming(true)
      setError(null)

      const optimisticUserMessage: Message = {
        id: `temp-${Date.now()}`,
        conversation_id: conversationId ?? '',
        role: 'user',
        content: text,
        created_at: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, optimisticUserMessage])

      try {
        const result = await api.sendMessage({
          message: text,
          conversation_id: conversationId,
        })

        onConversationCreated?.(result.conversation_id, result.title)

        if (result.conversation_id !== conversationId) {
          navigate(`/chat/${result.conversation_id}`, { replace: true })
        }

        const assistantMessage: Message = {
          id: `resp-${Date.now()}`,
          conversation_id: result.conversation_id,
          role: 'assistant',
          content: result.response,
          metadata: {
            sources: result.sources ?? [],
            actions: result.actions ?? [],
            activity: (result.tool_events ?? []).map((e) => ({
              tool: e.tool,
              status: e.status,
            })),
          },
          created_at: new Date().toISOString(),
        }
        setMessages((prev) =>
          prev
            .filter((m) => m.id !== optimisticUserMessage.id)
            .concat(
              {
                ...optimisticUserMessage,
                conversation_id: result.conversation_id,
              },
              assistantMessage,
            ),
        )
      } catch (err) {
        console.error(err)
        const message = err instanceof Error ? err.message : 'Failed to send message'
        setError(message)
        setMessages((prev) => prev.filter((m) => m.id !== optimisticUserMessage.id))
      } finally {
        setStreaming(false)
        sendLock.current = false
      }
    },
    [conversationId, navigate, onConversationCreated, streaming],
  )

  const handleShare = useCallback(async () => {
    if (!conversationId) return
    const url = `${window.location.origin}/chat/${conversationId}`
    try {
      await navigator.clipboard.writeText(url)
      setShareCopied(true)
      setTimeout(() => setShareCopied(false), 2000)
    } catch {
      // Fallback for older browsers
      const textarea = document.createElement('textarea')
      textarea.value = url
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
      setShareCopied(true)
      setTimeout(() => setShareCopied(false), 2000)
    }
  }, [conversationId])

  const hasMessages = messages.length > 0
  const showChatHeader = hasMessages && conversationId

  return (
    <div className="chat-page">
      {showChatHeader && (
        <header className="chat-page__header">
          <div className="chat-page__header-content">
            <h2 className="chat-page__conversation-title">
              {messages.find((m) => m.role === 'user')?.content?.slice(0, 50) ?? 'New conversation'}
            </h2>
          </div>
          <button
            type="button"
            className={`chat-page__share-btn ${shareCopied ? 'chat-page__share-btn--copied' : ''}`}
            onClick={handleShare}
            aria-label={shareCopied ? 'Copied!' : 'Share conversation'}
            title={shareCopied ? 'Copied to clipboard!' : 'Copy conversation link'}
          >
            {shareCopied ? <Check size={18} /> : <Share2 size={18} />}
            <span className="sr-only">{shareCopied ? 'Copied!' : 'Share conversation'}</span>
          </button>
        </header>
      )}
      {!hasMessages && !loading && !error ? (
        <WelcomeScreen onSuggestion={(text) => handleSend(text, [])} />
      ) : (
        <MessageList messages={messages} loading={streaming} />
      )}
      {error && (
        <div className="chat-page__error" role="alert">
          {error}
        </div>
      )}
      <div className="chat-page__composer">
        <Composer onSend={handleSend} disabled={streaming} streaming={streaming} />
        <div className="chat-page__disclaimer">
          FitAI can make mistakes. Always consult a professional for medical advice.
        </div>
      </div>
    </div>
  )
}