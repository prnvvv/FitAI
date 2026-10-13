import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import './App.css'
import { AppShell } from './components/layout/AppShell'
import { useAuth } from './context/AuthContext'
import { useConversations } from './hooks/useConversations'
import { ChatPage } from './pages/ChatPage'
import { DocumentsPage } from './pages/DocumentsPage'
import { LoginPage } from './pages/LoginPage'
import { MemoryPage } from './pages/MemoryPage'
import { ProfilePage } from './pages/ProfilePage'
import { ProgressPage } from './pages/ProgressPage'
import { WorkoutsPage } from './pages/WorkoutsPage'

function AuthenticatedApp() {
  const { user, loading: authLoading } = useAuth()
  const navigate = useNavigate()
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    const stored = typeof window !== 'undefined' ? window.localStorage.getItem('fitai_sidebar_open') : null
    return stored !== 'false'
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
    navigate('/')
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
        navigate('/')
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
        path="/"
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
        <Route
          index
          element={<ChatPage onConversationCreated={handleConversationCreated} />}
        />
        <Route
          path="chat/:conversationId"
          element={<ChatPage onConversationCreated={handleConversationCreated} />}
        />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="memory" element={<MemoryPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="workouts" element={<WorkoutsPage />} />
        <Route path="progress" element={<ProgressPage />} />
        <Route path="settings" element={<ProfilePage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/*" element={<AuthenticatedApp />} />
    </Routes>
  )
}

export default App
