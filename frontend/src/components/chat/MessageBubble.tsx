import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Check, Copy, Database, History, Sparkles, Wrench, X, AlertCircle, ExternalLink } from 'lucide-react'
import { BrandMark } from '../BrandMark'
import { api } from '../../services/api'
import { formatMessageTime } from '../../utils/dates'
import type { ActionItem, Message, Source, ToolEvent } from '../../types'

interface MessageBubbleProps {
  message: Message
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false)
  const [resolvedActions, setResolvedActions] = useState<Set<string>>(new Set())
  const [actionError, setActionError] = useState<string | null>(null)
  const isUser = message.role === 'user'
  const timestamp = formatMessageTime(message.created_at)

  const sources = (message.metadata?.sources as Source[] | undefined) ?? []
  const actions = (message.metadata?.actions as ActionItem[] | undefined) ?? []
  const toolEvents = (message.metadata?.tool_events as ToolEvent[] | undefined) ?? []

  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleConfirm = async (action: ActionItem) => {
    if (!action.proposal_id) return
    setActionError(null)
    try {
      await api.confirmMemoryUpdate(action.proposal_id)
      setResolvedActions((prev) => new Set(prev).add(action.proposal_id!))
    } catch (err) {
      setActionError('Could not confirm. Please try again.')
    }
  }

  const handleDismiss = async (action: ActionItem) => {
    if (!action.proposal_id) return
    setActionError(null)
    try {
      await api.rejectMemoryUpdate(action.proposal_id)
      setResolvedActions((prev) => new Set(prev).add(action.proposal_id!))
    } catch (err) {
      setActionError('Could not dismiss. Please try again.')
    }
  }

  // Transform inline [1], [2] markers into markdown links that our custom
  // renderer turns into compact citation chips.
  const contentWithCitations = sources.length
    ? message.content.replace(/\[(\d+)\]/g, '[$1](#source-$1)')
    : message.content

  const eventLabel = (event: ToolEvent): string => {
    const t = event.tool
    if (t === 'memory_write') {
      if (event.status === 'applied') return `Saved ${event.summary ?? event.key}`
      if (event.status === 'pending_created') return `Proposed ${event.summary ?? event.key}`
      if (event.status === 'history_recorded') return `Recorded ${event.summary ?? event.key}`
      return `Memory ${event.status ?? 'update'}`
    }
    if (t === 'retriever') return 'Searched knowledge base'
    if (t === 'web_search') {
      const count = event.sources ?? event.result?.results?.length ?? 0
      return count ? `Searched the web (${count} sources)` : 'Searched the web'
    }
    if (t === 'read_webpage') return `Read ${event.pages ?? 1} page${event.pages === 1 ? '' : 's'}`
    if (t === 'news_search') return 'Searched news'
    if (t === 'find_places') {
      if (!event.location) return 'Looked for places'
      const count = event.places ?? 0
      return count ? `Found ${count} place${count === 1 ? '' : 's'} near ${event.location}` : `Searched near ${event.location}`
    }
    if (t === 'get_weather') return `Checked weather for ${event.location ?? 'your area'}`
    if (t === 'geocode' || t === 'reverse_geocode') return 'Resolved location'
    if (t === 'get_datetime') return 'Checked date and time'
    if (t === 'multi_agent') return `Research mode: ${event.route ?? 'mixed'}`
    if (t === 'router') return `Route: ${event.route ?? 'mixed'}`
    if (t === 'continuity') {
      const memories = Number(event.memories ?? 0)
      const pastChats = Number(event.past_chats ?? 0)
      const parts: string[] = []
      if (memories) parts.push(`${memories} saved fact${memories === 1 ? '' : 's'}`)
      if (pastChats) parts.push(`${pastChats} earlier chat${pastChats === 1 ? '' : 's'}`)
      return parts.length ? `Recalled ${parts.join(' and ')}` : 'Recalled earlier context'
    }
    return `Used ${t}`
  }

  const eventIcon = (event: ToolEvent) => {
    if (event.tool === 'memory_write') return <Database size={12} />
    if (event.tool === 'retriever') return <Sparkles size={12} />
    if (event.tool === 'continuity') return <History size={12} />
    if (['web_search', 'read_webpage', 'news_search', 'multi_agent', 'router'].includes(event.tool)) {
      return <ExternalLink size={12} />
    }
    return <Wrench size={12} />
  }

  return (
    <div className={`message ${isUser ? 'message--user' : 'message--assistant'}`}>
      {!isUser && (
        <span className="message__avatar">
          <BrandMark className="message__avatar-mark" />
        </span>
      )}
      <div className={`message__bubble ${isUser ? 'message__bubble--user' : 'message__bubble--assistant'}`}>
        {isUser ? (
          <>
            <div className="message__text">{message.content}</div>
            {timestamp && (
              <time className="message__time" dateTime={message.created_at}>
                {timestamp}
              </time>
            )}
          </>
        ) : (
          <div className="message__markdown">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href, children, ...props }) => {
                  const sourceMatch = href?.match(/^#source-(\d+)$/)
                  if (sourceMatch) {
                    const index = Number(sourceMatch[1])
                    return (
                      <a
                        href={href}
                        className="message__citation"
                        onClick={(e) => {
                          e.preventDefault()
                          document
                            .getElementById(`source-${message.id}-${index}`)
                            ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
                        }}
                        {...props}
                      >
                        {children}
                      </a>
                    )
                  }
                  return (
                    <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
                      {children}
                    </a>
                  )
                },
              }}
            >
              {contentWithCitations}
            </ReactMarkdown>
            {sources.length > 0 && (
              <div className="message__sources">
                <div className="message__sources-header">Sources</div>
                <div className="message__sources-list">
                  {sources.map((source) => (
                    <a
                      key={`${message.id}-source-${source.index}`}
                      id={`source-${message.id}-${source.index}`}
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="message__source"
                      title={source.snippet}
                    >
                      <ExternalLink size={12} />
                      <span className="message__source-index">[{source.index}]</span>
                      <span className="message__source-title">{source.title}</span>
                    </a>
                  ))}
                </div>
              </div>
            )}
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
          {timestamp && (
            <time className="message__time" dateTime={message.created_at}>
              {timestamp}
            </time>
          )}
        </div>
      )}
      {!isUser && actions.length > 0 && (
        <div className="message__actions-row">
          {actions.map((action) => {
            if (action.type !== 'memory_confirm' || !action.proposal_id) return null
            if (resolvedActions.has(action.proposal_id)) return null
            return (
              <div key={action.proposal_id} className="message__action-card">
                <div className="message__action-card-icon">
                  <AlertCircle size={14} />
                </div>
                <div className="message__action-card-body">
                  <div className="message__action-card-title">{action.title}</div>
                  <div className="message__action-card-desc">{action.description}</div>
                </div>
                <div className="message__action-card-buttons">
                  <button
                    type="button"
                    className="message__action-card-btn message__action-card-btn--primary"
                    onClick={() => handleConfirm(action)}
                  >
                    Confirm
                  </button>
                  <button
                    type="button"
                    className="message__action-card-btn"
                    onClick={() => handleDismiss(action)}
                    aria-label="Dismiss"
                  >
                    <X size={14} />
                  </button>
                </div>
              </div>
            )
          })}
          {actionError && <div className="message__action-error">{actionError}</div>}
        </div>
      )}
      {!isUser && toolEvents.length > 0 && (
        <div className="message__tool-events">
          {toolEvents.map((event, index) => (
            <span key={`${event.tool}-${index}`} className="message__tool-event">
              {eventIcon(event)}
              {eventLabel(event)}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
