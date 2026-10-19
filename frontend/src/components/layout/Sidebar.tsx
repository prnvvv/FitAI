import {
  Brain,
  CalendarDays,
  MessageSquarePlus,
  PanelLeftClose,
  PanelRightOpen,
  Search,
  Settings,
  TrendingUp,
  X,
} from 'lucide-react'
import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import type { Conversation } from '../../types'
import { BrandMark } from '../BrandMark'
import { ConversationList } from './ConversationList'
import { SidebarNavItem } from './SidebarNavItem'

/** Footer navigation, in the order the workspace presents it. */
const NAV_ITEMS = [
  { label: 'Plan', icon: <CalendarDays size={20} />, paths: ['/plan'] },
  { label: 'Progress', icon: <TrendingUp size={20} />, paths: ['/progress'] },
  { label: 'Memory', icon: <Brain size={20} />, paths: ['/memory'] },
  // Settings and Profile render the same page; both highlight the entry.
  { label: 'Settings', icon: <Settings size={20} />, paths: ['/settings', '/profile'] },
]

interface SidebarProps {
  id?: string
  open: boolean
  onToggle: () => void
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
  id,
  open,
  onToggle,
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
  const navigate = useNavigate()
  const location = useLocation()
  const isChat = location.pathname === '/' || location.pathname.startsWith('/chat/')

  useEffect(() => {
    if (!open) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  const go = (path: string) => {
    onClose()
    navigate(path)
  }

  return (
    <nav
      id={id}
      className={`sidebar ${open ? 'sidebar--open' : 'sidebar--closed'}`}
      aria-label="Main navigation"
      aria-expanded={open}
    >
      <div className="sidebar__header">
        {open && (
          <span className="sidebar__brand">
            <BrandMark className="sidebar__brand-mark" />
            <span className="sidebar__brand-wordmark">FitAI</span>
          </span>
        )}
        <button
          type="button"
          className="sidebar__icon-btn"
          aria-label={open ? 'Collapse sidebar' : 'Open sidebar'}
          aria-controls={id}
          onClick={onToggle}
        >
          {open ? <PanelLeftClose size={18} /> : <PanelRightOpen size={18} />}
        </button>
      </div>

      {open ? (
        <>
          <button type="button" className="sidebar__new-chat" onClick={onNewChat}>
            <MessageSquarePlus size={18} aria-hidden="true" />
            <span>New chat</span>
          </button>

          <div className="sidebar__search">
            <Search size={16} className="sidebar__search-icon" aria-hidden="true" />
            <input
              type="text"
              placeholder="Search conversations..."
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

          <ConversationList
            conversations={conversations}
            selectedId={selectedId}
            loading={loading}
            error={error}
            onSelect={onSelectConversation}
            onRename={onRename}
            onDelete={onDelete}
          />

          <div className="sidebar__footer">
            <div className="sidebar__nav">
              {NAV_ITEMS.map((item) => (
                <SidebarNavItem
                  key={item.label}
                  icon={item.icon}
                  label={item.label}
                  active={item.paths.includes(location.pathname)}
                  onClick={() => go(item.paths[0])}
                />
              ))}
            </div>
          </div>
        </>
      ) : (
        /* Collapsed rail: icon-only, no text nodes (see Sidebar.test). */
        <div className="sidebar__rail">
          <SidebarNavItem
            compact
            icon={<MessageSquarePlus size={20} />}
            label="New chat"
            active={isChat && !selectedId}
            onClick={onNewChat}
          />
          {NAV_ITEMS.map((item) => (
            <SidebarNavItem
              key={item.label}
              compact
              icon={item.icon}
              label={item.label}
              active={item.paths.includes(location.pathname)}
              onClick={() => go(item.paths[0])}
            />
          ))}
        </div>
      )}
    </nav>
  )
}
