import { BookOpen, CalendarDays, MessageSquarePlus, PanelLeftClose, Search, TrendingUp, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import type { Conversation } from '../../types'
import { AccountMenu } from './AccountMenu'
import { ConversationList } from './ConversationList'
import { SidebarNavItem } from './SidebarNavItem'

interface SidebarProps {
  open: boolean
  onClose: () => void
  conversations: Conversation[]
  selectedId: string | null
  loading: boolean
  error: string | null
  searchQuery: string
  onSearchQueryChange: (query: string) => void
  onSelectConversation: (id: string) => void
  onNewChat: () => void
  onRename: (id: string, title: string) => void
  onDelete: (id: string) => void
}

export function Sidebar({
  open,
  onClose,
  conversations,
  selectedId,
  loading,
  error,
  searchQuery,
  onSearchQueryChange,
  onSelectConversation,
  onNewChat,
  onRename,
  onDelete,
}: SidebarProps) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [accountOpen, setAccountOpen] = useState(false)
  const isChat = location.pathname === '/' || location.pathname.startsWith('/chat/')

  useEffect(() => {
    if (!open) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  const handleNewChat = () => {
    onNewChat()
  }

  return (
    <nav
      className={`sidebar ${open ? 'sidebar--open' : 'sidebar--closed'}`}
      aria-label="Main navigation"
      aria-hidden={!open}
    >
      <div className="sidebar__header">
        <span className="sidebar__brand">FitAI</span>
        <div className="sidebar__header-actions">
          <button
            type="button"
            className="sidebar__icon-btn"
            aria-label="Close sidebar"
            onClick={onClose}
          >
            <PanelLeftClose size={20} />
          </button>
        </div>
      </div>

      <div className="sidebar__search">
        <Search size={18} className="sidebar__search-icon" />
        <input
          type="text"
          placeholder="Search chats"
          value={searchQuery}
          onChange={(e) => onSearchQueryChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') onSearchQueryChange('')
          }}
          className="sidebar__search-input"
          aria-label="Search conversations"
        />
        {searchQuery && (
          <button
            type="button"
            className="sidebar__search-clear"
            onClick={() => onSearchQueryChange('')}
            aria-label="Clear search"
          >
            <X size={14} />
          </button>
        )}
      </div>

      <div className="sidebar__nav">
        <SidebarNavItem
          icon={<MessageSquarePlus size={20} />}
          label="New chat"
          active={isChat && !selectedId}
          onClick={handleNewChat}
        />
        <SidebarNavItem
          icon={<CalendarDays size={20} />}
          label="Plan"
          active={location.pathname === '/plan'}
          onClick={() => {
            onClose()
            navigate('/plan')
          }}
        />
        <SidebarNavItem
          icon={<TrendingUp size={20} />}
          label="Progress"
          active={location.pathname === '/progress'}
          onClick={() => {
            onClose()
            navigate('/progress')
          }}
        />
        <SidebarNavItem
          icon={<BookOpen size={20} />}
          label="Library"
          active={location.pathname === '/library'}
          onClick={() => {
            onClose()
            navigate('/library')
          }}
        />
      </div>

      <div className="sidebar__section-label">Chat history</div>
      <ConversationList
        conversations={conversations}
        selectedId={selectedId}
        loading={loading}
        error={error}
        onSelect={(id) => {
          onSelectConversation(id)
        }}
        onRename={onRename}
        onDelete={onDelete}
      />

      <div className="sidebar__footer">
        <button
          type="button"
          className="sidebar__account"
          onClick={() => setAccountOpen((v) => !v)}
          aria-expanded={accountOpen}
          aria-haspopup="menu"
        >
          <div className="sidebar__avatar">
            {(user?.displayName ?? user?.email ?? 'U').slice(0, 2).toUpperCase()}
          </div>
          <div className="sidebar__account-info">
            <div className="sidebar__account-name">{user?.displayName ?? 'User'}</div>
            <div className="sidebar__account-email">{user?.email}</div>
          </div>
        </button>
        <AccountMenu open={accountOpen} onClose={() => setAccountOpen(false)} />
      </div>
    </nav>
  )
}
