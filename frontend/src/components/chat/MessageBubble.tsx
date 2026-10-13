import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Check, Copy, Database, Sparkles, Wrench } from 'lucide-react'
import type { Message, ToolEvent } from '../../types'

interface MessageBubbleProps {
  message: Message
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false)
  const isUser = message.role === 'user'

  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const toolEvents = (message.metadata?.tool_events as ToolEvent[] | undefined) ?? []

  const eventLabel = (event: ToolEvent): string => {
    if (event.tool === 'memory_write') {
      if (event.status === 'applied') return `Saved ${event.summary ?? event.key}`
      if (event.status === 'pending_created') return `Proposed ${event.summary ?? event.key}`
      if (event.status === 'history_recorded') return `Recorded ${event.summary ?? event.key}`
      return `Memory ${event.status ?? 'update'}`
    }
    if (event.tool === 'retriever') return `Searched knowledge base`
    return `Used ${event.tool}`
  }

  const eventIcon = (event: ToolEvent) => {
    if (event.tool === 'memory_write') return <Database size={12} />
    if (event.tool === 'retriever') return <Sparkles size={12} />
    return <Wrench size={12} />
  }

  return (
    <div className={`message ${isUser ? 'message--user' : 'message--assistant'}`}>
      {!isUser && <div className="message__avatar">F</div>}
      <div className={`message__bubble ${isUser ? 'message__bubble--user' : ''}`}>
        {isUser ? (
          <div className="message__text">{message.content}</div>
        ) : (
          <div className="message__markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          </div>
        )}
      </div>
      {!isUser && (
        <div className="message__actions">
          <button
            type="button"
            className="message__action"
            onClick={handleCopy}
            aria-label="Copy response"
            title="Copy"
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </button>
        </div>
      )}
      {!isUser && toolEvents.length > 0 && (
        <div className="message__tool-events">
          {toolEvents.map((event, index) => (
            <span key={`${event.tool}-${index}`} className="message__tool-event" title={JSON.stringify(event)}>
              {eventIcon(event)}
              {eventLabel(event)}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
