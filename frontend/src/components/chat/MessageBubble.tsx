import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Check,
  Copy,
  Database,
  Sparkles,
  Wrench,
  X,
  AlertCircle,
  Calendar,
  ExternalLink,
  Ruler,
} from 'lucide-react'
import { api } from '../../services/api'
import type { ActionItem, Message, Source, ToolEvent } from '../../types'

const CONFIRMABLE_ACTION_TYPES = new Set([
  'memory_confirm',
  'log_workout',
  'use_measurements',
])

const CHAT_ACTION_TYPES = new Set(['log_workout', 'use_measurements'])

interface MessageBubbleProps {
  message: Message
  onReply?: (message: Message) => void
}

export function MessageBubble({ message, onReply }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false)
  const [resolvedActions, setResolvedActions] = useState<Set<string>>(new Set())
  const [actionError, setActionError] = useState<string | null>(null)
  const isUser = message.role === 'user'

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
      if (CHAT_ACTION_TYPES.has(action.type)) {
        const result = await api.confirmChatAction(action.proposal_id)
        onReply?.(result.message)
      } else {
        await api.confirmMemoryUpdate(action.proposal_id)
      }
      setResolvedActions((prev) => new Set(prev).add(action.proposal_id!))
    } catch {
      setActionError('Could not confirm. Please try again.')
    }
  }

  const handleDismiss = async (action: ActionItem) => {
    if (!action.proposal_id) return
    setActionError(null)
    try {
      if (CHAT_ACTION_TYPES.has(action.type)) {
        const result = await api.rejectChatAction(action.proposal_id)
        onReply?.(result.message)
      } else {
        await api.rejectMemoryUpdate(action.proposal_id)
      }
      setResolvedActions((prev) => new Set(prev).add(action.proposal_id!))
    } catch {
      setActionError('Could not dismiss. Please try again.')
    }
  }

  const actionIcon = (action: ActionItem) => {
    if (action.type === 'log_workout') return <Calendar size={14} />
    if (action.type === 'use_measurements') return <Ruler size={14} />
    return <AlertCircle size={14} />
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
    return `Used ${t}`
  }

  const eventIcon = (event: ToolEvent) => {
    if (event.tool === 'memory_write') return <Database size={12} />
    if (event.tool === 'retriever') return <Sparkles size={12} />
    if (['web_search', 'read_webpage', 'news_search', 'multi_agent', 'router'].includes(event.tool)) {
      return <ExternalLink size={12} />
    }
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
        </div>
      )}
      {!isUser && actions.length > 0 && (
        <div className="message__actions-row">
          {actions.map((action) => {
            if (!action.proposal_id || !CONFIRMABLE_ACTION_TYPES.has(action.type)) return null
            if (resolvedActions.has(action.proposal_id)) return null
            return (
              <div key={action.proposal_id} className="message__action-card">
                <div className="message__action-card-icon">{actionIcon(action)}</div>
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
