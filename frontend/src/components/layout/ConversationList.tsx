import { MoreHorizontal, Pencil, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { Conversation } from '../../types'

interface ConversationListProps {
  conversations: Conversation[]
  selectedId: string | null
  loading: boolean
  error: string | null
  onSelect: (id: string) => void
  onRename: (id: string, title: string) => void
  onDelete: (id: string) => void
}

function ConversationItem({
  conversation,
  selected,
  onSelect,
  onRename,
  onDelete,
}: {
  conversation: Conversation
  selected: boolean
  onSelect: (id: string) => void
  onRename: (id: string, title: string) => void
  onDelete: (id: string) => void
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
                if (confirm('Delete this conversation?')) onDelete(conversation.id)
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

export function ConversationList({
  conversations,
  selectedId,
  loading,
  error,
  onSelect,
  onRename,
  onDelete,
}: ConversationListProps) {
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

  return (
    <div className="conversation-list" role="list">
      {conversations.map((conversation) => (
        <ConversationItem
          key={conversation.id}
          conversation={conversation}
          selected={selectedId === conversation.id}
          onSelect={onSelect}
          onRename={onRename}
          onDelete={onDelete}
        />
      ))}
    </div>
  )
}
