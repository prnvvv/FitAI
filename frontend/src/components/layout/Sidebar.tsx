import {
  Dumbbell,
  FileText,
  Menu,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  TrendingUp,
} from 'lucide-react'
import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import type { Conversation } from '../../types'
import { AccountMenu } from './AccountMenu'
import { ConversationList } from './ConversationList'
import { SidebarNavItem } from './SidebarNavItem'

interface SidebarProps {
  open: boolean
  onToggle: () => void
  conversations: Conversation[]
  selectedId: string | null
  loading: boolean
  onSelectConversation: (id: string) => void
  onNewChat: () => void
  onRename: (id: string, title: string) => void
  onDelete: (id: string) => void
}

export function Sidebar({
  open,
  onToggle,
  conversations,
  selectedId,
  loading,
  onSelectConversation,
  onNewChat,
  onRename,
  onDelete,
}: SidebarProps) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [search, setSearch] = useState('')
  const [accountOpen, setAccountOpen] = useState(false)

  const filtered = search
    ? conversations.filter((c) => (c.title ?? '').toLowerCase().includes(search.toLowerCase()))
    : conversations

  const initials = (user?.displayName ?? user?.email ?? 'U').slice(0, 2).toUpperCase()
  const isChat = location.pathname === '/' || location.pathname.startsWith('/chat/')

  return (
    <>
      <nav
        className={`sidebar ${open ? 'sidebar--open' : 'sidebar--closed'}`}
        aria-label="Main navigation"
      >
        <div className="sidebar__header">
          <span className="sidebar__brand">FitAI</span>
          <div className="sidebar__header-actions">
            <button
              type="button"
              className="sidebar__icon-btn"
              aria-label={open ? 'Collapse sidebar' : 'Expand sidebar'}
              onClick={onToggle}
            >
              {open ? <PanelLeftClose size={20} /> : <PanelLeftOpen size={20} />}
            </button>
          </div>
        </div>

        <div className="sidebar__search">
          <Search size={18} className="sidebar__search-icon" />
          <input
            type="text"
            placeholder="Search chats"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="sidebar__search-input"
          />
        </div>

        <div className="sidebar__nav">
          <SidebarNavItem
            icon={<MessageSquarePlus size={20} />}
            label="New chat"
            active={isChat && !selectedId}
            onClick={onNewChat}
          />
          <SidebarNavItem
            icon={<Dumbbell size={20} />}
            label="Workouts"
            onClick={() => navigate('/workouts')}
          />
          <SidebarNavItem
            icon={<TrendingUp size={20} />}
            label="Progress"
            onClick={() => navigate('/progress')}
          />
          <SidebarNavItem
            icon={<FileText size={20} />}
            label="Documents"
            onClick={() => navigate('/documents')}
          />
        </div>

        <div className="sidebar__section-label">Recents</div>
        <ConversationList
          conversations={filtered}
          selectedId={selectedId}
          loading={loading}
          onSelect={onSelectConversation}
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
            <div className="sidebar__avatar">{initials}</div>
            <div className="sidebar__account-info">
              <div className="sidebar__account-name">{user?.displayName ?? 'User'}</div>
              <div className="sidebar__account-email">{user?.email ?? ''}</div>
            </div>
          </button>
          <AccountMenu open={accountOpen} onClose={() => setAccountOpen(false)} />
        </div>
      </nav>

      {!open && (
        <button
          type="button"
          className="sidebar__open-btn"
          onClick={onToggle}
          aria-label="Open sidebar"
        >
          <Menu size={20} />
          <span>FitAI</span>
        </button>
      )}
    </>
  )
}
