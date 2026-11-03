import { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useToast } from './components/ui/Toast'
import './App.css'
import { AppShell } from './components/layout/AppShell'
import { PageErrorBoundary } from './components/layout/PageErrorBoundary'
import { SiteBackdrop } from './components/SiteBackdrop'
import { PersistentHeader } from './components/PersistentHeader'
import { useAuth } from './context/AuthContext'
import { useConversations } from './hooks/useConversations'
import { ChatPage } from './pages/ChatPage'
import { LandingPage } from './pages/LandingPage'
import { LoginPage } from './pages/LoginPage'
import './backdrop.css'

// Secondary pages load on demand so the first paint ships only chat, landing and login.
const LibraryPage = lazy(() => import('./pages/LibraryPage').then((m) => ({ default: m.LibraryPage })))
const MemoryPage = lazy(() => import('./pages/MemoryPage').then((m) => ({ default: m.MemoryPage })))
const PlanPage = lazy(() => import('./pages/PlanPage').then((m) => ({ default: m.PlanPage })))
const ProfilePage = lazy(() => import('./pages/ProfilePage').then((m) => ({ default: m.ProfilePage })))
const ProgressPage = lazy(() => import('./pages/ProgressPage').then((m) => ({ default: m.ProgressPage })))

function PageFallback() {
  return (
    <div className="auth-loading">
      <div className="auth-loading__spinner" />
    </div>
  )
}

function RootLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <SiteBackdrop />
      <PersistentHeader />
      {children}
    </>
  )
}

/* Keep in sync with .page-transition.is-exit in backdrop.css */
const PAGE_EXIT_MS = 100

/**
 * Renders the public routes with a coordinated exit/enter sequence.
 *
 * The backdrop, header and amber atmosphere are rendered once by RootLayout and
 * never remount, so only the page foreground animates: the outgoing page fades
 * out with a slight rise, then the incoming page mounts and plays its own
 * entrance animation. The exiting page is rendered from the last location so it
 * cannot disappear mid-animation, and it never covers the new page (no overlap).
 */
function PublicRoutes() {
  const location = useLocation()
  const [renderedLocation, setRenderedLocation] = useState(location)

  const pathChanged = location.pathname !== renderedLocation.pathname
  // Derived during render so the outgoing page gets its exit class in the same
  // commit that renders the new location.
  const isExiting = pathChanged && location.key !== renderedLocation.key

  useEffect(() => {
    if (location.key === renderedLocation.key) return

    const prefersReducedMotion =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches

    // Query-only changes (e.g. /login -> /login?mode=signup) render the same
    // page, so swap immediately instead of flashing an exit/enter animation.
    const timer = window.setTimeout(
      () => setRenderedLocation(location),
      pathChanged && !prefersReducedMotion ? PAGE_EXIT_MS : 0,
    )

    return () => window.clearTimeout(timer)
  }, [location, renderedLocation, pathChanged])

  return (
    <div
      key={renderedLocation.key}
      className={`page-transition${isExiting ? ' is-exit' : ''}`}
    >
      <Routes location={renderedLocation}>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  )
}

function AuthenticatedApp() {
  const { user, loading: authLoading } = useAuth()
  const navigate = useNavigate()
  const toast = useToast()
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    const stored = typeof window !== 'undefined' ? window.localStorage.getItem('fitai_sidebar_open') : null
    if (stored !== null) return stored !== 'false'
    const isMobile = typeof window !== 'undefined' && window.innerWidth < 768
    return !isMobile
  })

  const {
    conversations,
    loading: conversationsLoading,
    error: conversationsError,
    searchQuery,
    setSearchQuery,
    activeId,
    refresh,
    renameConversation,
    deleteConversation,
    updateConversationTitle,
  } = useConversations({ enabled: !!user })

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('fitai_sidebar_open', String(sidebarOpen))
    }
  }, [sidebarOpen])

  /**
   * Dismisses the sidebar only when it is an overlay drawer (below the desktop
   * breakpoint). On desktop the sidebar is a permanent column that the user
   * controls with the toggle, so opening a conversation or another destination
   * must never collapse it.
   */
  const closeSidebarDrawer = useCallback(() => {
    if (typeof window !== 'undefined' && window.innerWidth < 768) {
      setSidebarOpen(false)
    }
  }, [])

  const handleNewChat = useCallback(() => {
    closeSidebarDrawer()
    navigate('/')
  }, [closeSidebarDrawer, navigate])

  const handleSelectConversation = useCallback(
    (id: string) => {
      if (id === activeId) return
      closeSidebarDrawer()
      navigate(`/chat/${id}`)
    },
    [closeSidebarDrawer, navigate, activeId],
  )

  const handleConversationCreated = useCallback(
    (id: string, title: string | null) => {
      updateConversationTitle(id, title)
      refresh().catch(console.error)
    },
    [updateConversationTitle, refresh],
  )

  const handleDelete = useCallback(
    async (id: string) => {
      await deleteConversation(id)
      toast.show('Conversation deleted', 'success')
      if (activeId === id) {
        navigate('/')
      }
    },
    [deleteConversation, activeId, navigate, toast],
  )

  const handleRename = useCallback(
    (id: string, title: string) => {
      renameConversation(id, title).catch(() => toast.show('Could not rename the conversation', 'error'))
    },
    [renameConversation, toast],
  )

  if (authLoading) {
    return (
      <div className="auth-loading">
        <div className="auth-loading__spinner" />
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  return (
    <Routes>
      <Route
        path="/"
        element={
          <AppShell
            sidebarOpen={sidebarOpen}
            onToggleSidebar={() => setSidebarOpen((v) => !v)}
            onCloseSidebar={closeSidebarDrawer}
            conversations={conversations}
            selectedId={activeId}
            conversationsLoading={conversationsLoading}
            conversationsError={conversationsError}
            searchQuery={searchQuery}
            onSearchQueryChange={setSearchQuery}
            onSelectConversation={handleSelectConversation}
            onNewChat={handleNewChat}
            onRename={handleRename}
            onDelete={handleDelete}
          />
        }
      >
        <Route
          index
          element={<ChatPage onConversationCreated={handleConversationCreated} />}
        />
        <Route
          path="chat/:conversationId"
          element={<ChatPage onConversationCreated={handleConversationCreated} />}
        />
        <Route
          path="library"
          element={
            <PageErrorBoundary name="Library">
              <Suspense fallback={<PageFallback />}>
                <LibraryPage />
              </Suspense>
            </PageErrorBoundary>
          }
        />
        <Route path="memory" element={<Suspense fallback={<PageFallback />}><MemoryPage /></Suspense>} />
        <Route path="profile" element={<Suspense fallback={<PageFallback />}><ProfilePage /></Suspense>} />
        <Route
          path="plan"
          element={
            <PageErrorBoundary name="Plan">
              <Suspense fallback={<PageFallback />}>
                <PlanPage />
              </Suspense>
            </PageErrorBoundary>
          }
        />
        <Route
          path="progress"
          element={
            <PageErrorBoundary name="Progress">
              <Suspense fallback={<PageFallback />}>
                <ProgressPage />
              </Suspense>
            </PageErrorBoundary>
          }
        />
        <Route path="settings" element={<Suspense fallback={<PageFallback />}><ProfilePage /></Suspense>} />
        <Route path="workouts" element={<Navigate to="/plan" replace />} />
        <Route path="documents" element={<Navigate to="/library" replace />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

function PublicApp() {
  const { user, loading: authLoading } = useAuth()

  if (authLoading) {
    return (
      <div className="auth-loading">
        <div className="auth-loading__spinner" />
      </div>
    )
  }

  if (user) {
    return <AuthenticatedApp />
  }

  return (
    <RootLayout>
      <PublicRoutes />
    </RootLayout>
  )
}

function App() {
  return (
    <Routes>
      <Route path="/*" element={<PublicApp />} />
    </Routes>
  )
}

export default App