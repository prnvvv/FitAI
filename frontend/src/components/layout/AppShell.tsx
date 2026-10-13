import { Outlet } from 'react-router-dom'
import type { Conversation } from '../../types'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

interface AppShellProps {
  sidebarOpen: boolean
  onToggleSidebar: () => void
  onCloseSidebar: () => void
  conversations: Conversation[]
  selectedId: string | null
  conversationsLoading: boolean
  conversationsError: string | null
  searchQuery: string
  onSearchQueryChange: (query: string) => void
  onSelectConversation: (id: string) => void
  onNewChat: () => void
  onRename: (id: string, title: string) => void
  onDelete: (id: string) => void
}

export function AppShell({
  sidebarOpen,
  onToggleSidebar,
  onCloseSidebar,
  conversations,
  selectedId,
  conversationsLoading,
  conversationsError,
  searchQuery,
  onSearchQueryChange,
  onSelectConversation,
  onNewChat,
  onRename,
  onDelete,
}: AppShellProps) {
  return (
    <div className="app-shell">
      <Sidebar
        open={sidebarOpen}
        onClose={onCloseSidebar}
        conversations={conversations}
        selectedId={selectedId}
        loading={conversationsLoading}
        error={conversationsError}
        searchQuery={searchQuery}
        onSearchQueryChange={onSearchQueryChange}
        onSelectConversation={onSelectConversation}
        onNewChat={onNewChat}
        onRename={onRename}
        onDelete={onDelete}
      />
      <div className={`app-shell__content ${sidebarOpen ? 'app-shell__content--shifted' : ''}`}>
        <TopBar onToggleSidebar={onToggleSidebar} />
        <main className="app-shell__main">
          <Outlet />
        </main>
      </div>
      {sidebarOpen && (
        <button
          type="button"
          className="sidebar-overlay"
          aria-label="Close sidebar"
          onClick={onCloseSidebar}
        />
      )}
    </div>
  )
}
