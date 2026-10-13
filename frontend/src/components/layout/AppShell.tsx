import { Outlet } from 'react-router-dom'
import type { Conversation } from '../../types'
import { Sidebar } from './Sidebar'

interface AppShellProps {
  sidebarOpen: boolean
  onToggleSidebar: () => void
  conversations: Conversation[]
  selectedId: string | null
  conversationsLoading: boolean
  onSelectConversation: (id: string) => void
  onNewChat: () => void
  onRename: (id: string, title: string) => void
  onDelete: (id: string) => void
}

export function AppShell({
  sidebarOpen,
  onToggleSidebar,
  conversations,
  selectedId,
  conversationsLoading,
  onSelectConversation,
  onNewChat,
  onRename,
  onDelete,
}: AppShellProps) {
  return (
    <div className="app-shell">
      <Sidebar
        open={sidebarOpen}
        onToggle={onToggleSidebar}
        conversations={conversations}
        selectedId={selectedId}
        loading={conversationsLoading}
        onSelectConversation={onSelectConversation}
        onNewChat={onNewChat}
        onRename={onRename}
        onDelete={onDelete}
      />
      <main className="app-shell__main">
        <Outlet />
      </main>
    </div>
  )
}
