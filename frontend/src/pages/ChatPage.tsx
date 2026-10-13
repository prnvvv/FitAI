import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Composer } from '../components/chat/Composer'
import { MessageList } from '../components/chat/MessageList'
import { WelcomeScreen } from '../components/chat/WelcomeScreen'
import { api } from '../services/api'
import type { Message } from '../types'

interface ChatPageProps {
  onConversationCreated?: (id: string) => void
}

export function ChatPage({ onConversationCreated }: ChatPageProps) {
  const { conversationId } = useParams<{ conversationId?: string }>()
  const navigate = useNavigate()
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)

  /* eslint-disable react/set-state-in-effect */
  useEffect(() => {
    if (!conversationId) return
    let cancelled = false
    setLoading(true)
    api
      .listMessages(conversationId)
      .then((page) => {
        if (!cancelled) setMessages(page.items)
      })
      .catch(console.error)
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [conversationId])
  /* eslint-enable react/set-state-in-effect */

  const handleSend = useCallback(
    async (text: string, _files: File[]) => {
      setStreaming(true)
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

        onConversationCreated?.(result.conversation_id)

        if (result.conversation_id !== conversationId) {
          navigate(`/chat/${result.conversation_id}`, { replace: true })
        }

        const assistantMessage: Message = {
          id: `resp-${Date.now()}`,
          conversation_id: result.conversation_id,
          role: 'assistant',
          content: result.response,
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
        setMessages((prev) =>
          prev.map((m) =>
            m.id === optimisticUserMessage.id
              ? { ...m, content: `${m.content}\n\n_Error sending message. Please try again._` }
              : m,
          ),
        )
      } finally {
        setStreaming(false)
      }
    },
    [conversationId, navigate, onConversationCreated],
  )

  const hasMessages = messages.length > 0

  return (
    <div className="chat-page">
      {!hasMessages && !loading ? (
        <WelcomeScreen onSuggestion={(text) => handleSend(text, [])} />
      ) : (
        <MessageList messages={messages} loading={streaming} />
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
