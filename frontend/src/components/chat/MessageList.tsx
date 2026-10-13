import { useEffect, useRef, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import type { Message } from '../../types'
import { MessageBubble } from './MessageBubble'

interface ActivityEvent {
  tool: string
  status?: string
}

interface MessageListProps {
  messages: Message[]
  loading?: boolean
  activity?: ActivityEvent[]
}

function activityLabel(activity: ActivityEvent[]): string {
  if (activity.some((a) => a.tool === 'web_search')) return 'Searching the web…'
  if (activity.some((a) => a.tool === 'nearby_gyms')) return 'Finding nearby places…'
  if (activity.some((a) => a.tool === 'retriever')) return 'Reviewing sources…'
  if (activity.some((a) => a.tool === 'memory_write')) return 'Updating memory…'
  return 'Thinking…'
}

export function MessageList({ messages, loading, activity = [] }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)

  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, autoScroll])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const handleScroll = () => {
      const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
      setAutoScroll(nearBottom)
    }

    el.addEventListener('scroll', handleScroll)
    return () => el.removeEventListener('scroll', handleScroll)
  }, [])

  return (
    <div ref={containerRef} className="message-list" aria-live="polite" aria-atomic="false">
      <div className="message-list__inner">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {loading && (
          <div className="message message--assistant">
            <div className="message__avatar">F</div>
            <div className="message__bubble message__bubble--assistant">
              <div className="message__thinking" aria-label={activityLabel(activity)}>
                <span className="message__thinking-label">{activityLabel(activity)}</span>
                <span className="message__thinking-dot" />
                <span className="message__thinking-dot" />
                <span className="message__thinking-dot" />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      {!autoScroll && (
        <button
          type="button"
          className="message-list__scroll-btn"
          onClick={() => {
            setAutoScroll(true)
            bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
          }}
          aria-label="Scroll to bottom"
        >
          <ChevronDown size={18} />
        </button>
      )}
    </div>
  )
}
