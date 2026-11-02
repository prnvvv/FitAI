import { Outlet, useLocation } from 'react-router-dom'
import type { Conversation } from '../../types'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

/** Labels for the non-chat destinations, shown in the shared top bar. */
const PAGE_TITLES: Record<string, string> = {
  plan: 'Plan',
  progress: 'Progress',
  memory: 'Memory',
  settings: 'Settings',
  profile: 'Profile',
  library: 'Library',
}

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
  onDelete: (id: string) => void | Promise<void>
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
  const handleClose = () => {
    onCloseSidebar()
  }

  const { pathname } = useLocation()
  const isChatRoute = pathname === '/' || pathname.startsWith('/chat/')
  const activeTitle =
    conversations.find((c) => c.id === selectedId)?.title?.trim() || null

  // One title slot for every route: the conversation on chat routes, the
  // destination name everywhere else, so the header never collapses to blank.
  const title = isChatRoute
    ? (activeTitle ?? 'New chat')
    : (PAGE_TITLES[pathname.split('/')[1] ?? ''] ?? 'FitAI')

  // Every non-chat page renders its own <h1>, so the header label is only the
  // page heading on chat routes, where the page itself has no heading.
  const titleIsHeading = isChatRoute && (activeTitle !== null || pathname !== '/')

  return (
    <div className="app-shell">
      <Sidebar
        id="app-sidebar"
        open={sidebarOpen}
        onToggle={onToggleSidebar}
        onClose={handleClose}
        conversations={conversations}
        selectedId={selectedId}
        loading={conversationsLoading}
        error={conversationsError}
        searchQuery={searchQuery}
        onSearchQueryChange={onSearchQueryChange}
        onSelectConversation={(id) => {
          onSelectConversation(id)
          handleClose()
        }}
        onNewChat={() => {
          onNewChat()
          handleClose()
        }}
        onRename={onRename}
        onDelete={onDelete}
      />
      <div className="app-shell__content">
        <TopBar title={title} asHeading={titleIsHeading} />
        <main className="app-shell__main">
          <Outlet />
        </main>
      </div>
      {sidebarOpen && (
        <button
          type="button"
          className="sidebar-overlay"
          aria-label="Close sidebar"
          onClick={handleClose}
        />
      )}
    </div>
  )
}
