import { MessageSquare, MoreHorizontal, Pencil, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { Conversation } from '../../types'
import { useConfirmAction } from '../ui/ConfirmDialog'
import { CONVERSATION_GROUPS, conversationDateGroup } from '../../utils/dates'

interface ConversationListProps {
  conversations: Conversation[]
  selectedId: string | null
  loading: boolean
  error: string | null
  onSelect: (id: string) => void
  onRename: (id: string, title: string) => void
  onDelete: (id: string) => void | Promise<void>
}

interface ConversationBucket {
  label: string
  items: Conversation[]
}

/**
 * Buckets the (already newest-first) conversation list by last activity, so the
 * sidebar can label each section. Empty buckets are dropped and the surviving
 * buckets keep CONTRIBUTION_GROUPS order even if the server order changes.
 */
function groupConversations(conversations: Conversation[]): ConversationBucket[] {
  const buckets = new Map<string, Conversation[]>()
  for (const conversation of conversations) {
    const label = conversationDateGroup(conversation.updated_at || conversation.created_at)
    const bucket = buckets.get(label)
    if (bucket) bucket.push(conversation)
    else buckets.set(label, [conversation])
  }

  return CONVERSATION_GROUPS.filter((label) => buckets.has(label)).map((label) => ({
    label,
    items: buckets.get(label) as Conversation[],
  }))
}

function ConversationItem({
  conversation,
  selected,
  onSelect,
  onRename,
  onRequestDelete,
}: {
  conversation: Conversation
  selected: boolean
  onSelect: (id: string) => void
  onRename: (id: string, title: string) => void
  onRequestDelete: (conversation: Conversation) => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editTitle, setEditTitle] = useState(conversation.title ?? '')
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!menuOpen) return
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [menuOpen])

  const handleRename = () => {
    const trimmed = editTitle.trim()
    if (trimmed && trimmed !== (conversation.title ?? '')) {
      onRename(conversation.id, trimmed)
    }
    setEditing(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleRename()
    }
    if (e.key === 'Escape') {
      setEditTitle(conversation.title ?? '')
      setEditing(false)
    }
  }

  return (
    <div
      className={`conversation-item ${selected ? 'conversation-item--selected' : ''}`}
      data-testid={`conversation-item-${conversation.id}`}
    >
      {editing ? (
        <input
          type="text"
          className="conversation-item__input"
          value={editTitle}
          onChange={(e) => setEditTitle(e.target.value)}
          onBlur={handleRename}
          onKeyDown={handleKeyDown}
          autoFocus
          aria-label="Rename conversation"
        />
      ) : (
        <button
          type="button"
          className="conversation-item__button"
          onClick={() => onSelect(conversation.id)}
          title={conversation.title ?? 'Untitled'}
        >
          <MessageSquare size={15} className="conversation-item__icon" aria-hidden="true" />
          <span className="conversation-item__title">
            {conversation.title || 'New chat'}
          </span>
        </button>
      )}
      <div className="conversation-item__actions" ref={menuRef}>
        <button
          type="button"
          className="conversation-item__menu-btn"
          aria-label="Conversation options"
          aria-expanded={menuOpen}
          onClick={(e) => {
            e.stopPropagation()
            setMenuOpen((v) => !v)
          }}
        >
          <MoreHorizontal size={16} />
        </button>
        {menuOpen && (
          <div className="conversation-item__menu" role="menu">
            <button
              type="button"
              role="menuitem"
              className="conversation-item__menu-item"
              onClick={(e) => {
                e.stopPropagation()
                setMenuOpen(false)
                setEditing(true)
              }}
            >
              <Pencil size={16} />
              Rename
            </button>
            <button
              type="button"
              role="menuitem"
              className="conversation-item__menu-item conversation-item__menu-item--danger"
              onClick={(e) => {
                e.stopPropagation()
                setMenuOpen(false)
                onRequestDelete(conversation)
              }}
            >
              <Trash2 size={16} />
              Delete
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function ConversationListBody({
  conversations,
  selectedId,
  loading,
  error,
  onSelect,
  onRename,
  onRequestDelete,
}: Omit<ConversationListProps, 'onDelete'> & {
  onRequestDelete: (conversation: Conversation) => void
}) {
  if (loading) {
    return (
      <div className="conversation-list conversation-list--loading">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="conversation-item__skeleton" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="conversation-list conversation-list--empty">
        <span>Error loading chats</span>
      </div>
    )
  }

  if (conversations.length === 0) {
    return (
      <div className="conversation-list conversation-list--empty">
        <span>No chats found</span>
      </div>
    )
  }

  const groups = groupConversations(conversations)

  return (
    <div className="conversation-list">
      {groups.map((group) => {
        const labelId = `conversation-group-${group.label.replace(/\s+/g, '-').toLowerCase()}`
        return (
          <section className="conversation-group" key={group.label} aria-labelledby={labelId}>
            <h2 className="conversation-group__label" id={labelId}>
              {group.label}
            </h2>
            <ul className="conversation-group__items">
              {group.items.map((conversation) => (
                <li key={conversation.id}>
                  <ConversationItem
                    conversation={conversation}
                    selected={selectedId === conversation.id}
                    onSelect={onSelect}
                    onRename={onRename}
                    onRequestDelete={onRequestDelete}
                  />
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}

export function ConversationList({ onDelete, ...props }: ConversationListProps) {
  // The dialog lives here (not in each row) so it survives the optimistic removal
  // and rollback of the row while the delete request is in flight.
  const { request, dialog } = useConfirmAction()

  return (
    <>
      <ConversationListBody
        {...props}
        onRequestDelete={(conversation) =>
          request({
            title: 'Delete conversation?',
            description: (
              <>
                <strong>{conversation.title || 'New chat'}</strong> and its messages will be permanently
                deleted. This cannot be undone.
              </>
            ),
            confirmLabel: 'Delete',
            onConfirm: () => onDelete(conversation.id),
          })
        }
      />
      {dialog}
    </>
  )
}
