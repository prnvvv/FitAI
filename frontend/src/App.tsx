import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import './App.css'
import { AppShell } from './components/layout/AppShell'
import { PageErrorBoundary } from './components/layout/PageErrorBoundary'
import { useAuth } from './context/AuthContext'
import { ThemeProvider } from './context/ThemeContext'
import { useConversations } from './hooks/useConversations'
import { ChatPage } from './pages/ChatPage'
import { LandingPage } from './pages/LandingPage'
import { LibraryPage } from './pages/LibraryPage'
import { LoginPage } from './pages/LoginPage'
import { MemoryPage } from './pages/MemoryPage'
import { PlanPage } from './pages/PlanPage'
import { ProfilePage } from './pages/ProfilePage'
import { ProgressPage } from './pages/ProgressPage'

function AuthenticatedApp() {
  const { user, loading: authLoading } = useAuth()
  const navigate = useNavigate()
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    const stored = typeof window !== 'undefined' ? window.localStorage.getItem('fitai_sidebar_open') : null
    if (stored !== null) return stored === 'true'
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

  const handleNewChat = useCallback(async () => {
    setSidebarOpen(false)
    navigate('/chat')
  }, [navigate])

  const handleSelectConversation = useCallback(
    (id: string) => {
      if (id === activeId) return
      setSidebarOpen(false)
      navigate(`/chat/${id}`)
    },
    [navigate, activeId],
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
      if (activeId === id) {
        navigate('/chat')
      }
    },
    [deleteConversation, activeId, navigate],
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
        path="/chat"
        element={
          <AppShell
            sidebarOpen={sidebarOpen}
            onToggleSidebar={() => setSidebarOpen((v) => !v)}
            onCloseSidebar={() => setSidebarOpen(false)}
            conversations={conversations}
            selectedId={activeId}
            conversationsLoading={conversationsLoading}
            conversationsError={conversationsError}
            searchQuery={searchQuery}
            onSearchQueryChange={setSearchQuery}
            onSelectConversation={handleSelectConversation}
            onNewChat={handleNewChat}
            onRename={renameConversation}
            onDelete={handleDelete}
          />
        }
      >
        <Route index element={<ChatPage onConversationCreated={handleConversationCreated} />} />
        <Route path=":conversationId" element={<ChatPage onConversationCreated={handleConversationCreated} />} />
        <Route
          path="library"
          element={
            <PageErrorBoundary name="Library">
              <LibraryPage />
            </PageErrorBoundary>
          }
        />
        <Route path="memory" element={<MemoryPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route
          path="plan"
          element={
            <PageErrorBoundary name="Plan">
              <PlanPage />
            </PageErrorBoundary>
          }
        />
        <Route
          path="progress"
          element={
            <PageErrorBoundary name="Progress">
              <ProgressPage />
            </PageErrorBoundary>
          }
        />
        <Route path="settings" element={<ProfilePage />} />
        <Route path="workouts" element={<Navigate to="/chat/plan" replace />} />
        <Route path="documents" element={<Navigate to="/chat/library" replace />} />
      </Route>
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  )
}

function App() {
  return (
    <ThemeProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<LandingPage />} />
        <Route path="/*" element={<AuthenticatedApp />} />
      </Routes>
    </ThemeProvider>
  )
}

export default App