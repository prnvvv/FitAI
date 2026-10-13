import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import './App.css'
import { AppShell } from './components/layout/AppShell'
import { useAuth } from './context/AuthContext'
import { api } from './services/api'
import { ChatPage } from './pages/ChatPage'
import { DocumentsPage } from './pages/DocumentsPage'
import { LoginPage } from './pages/LoginPage'
import { MemoryPage } from './pages/MemoryPage'
import { ProfilePage } from './pages/ProfilePage'
import { ProgressPage } from './pages/ProgressPage'
import { WorkoutsPage } from './pages/WorkoutsPage'
import type { Conversation } from './types'

function AuthenticatedApp() {
  const { user, loading } = useAuth()
  const navigate = useNavigate()
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [conversationsLoading, setConversationsLoading] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    if (!user) return
    let cancelled = false
    api
      .listConversations()
      .then((page) => {
        if (!cancelled) setConversations(page.items)
      })
      .catch(console.error)
      .finally(() => {
        if (!cancelled) setConversationsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [user])

  const handleNewChat = useCallback(() => {
    setSelectedId(null)
    navigate('/')
  }, [navigate])

  const handleSelectConversation = useCallback(
    (id: string) => {
      setSelectedId(id)
      navigate(`/chat/${id}`)
    },
    [navigate],
  )

  const handleConversationCreated = useCallback((id: string) => {
    setSelectedId(id)
    setConversations((prev) => {
      if (prev.some((c) => c.id === id)) return prev
      return [
        { id, title: 'New chat', created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
        ...prev,
      ]
    })
  }, [])

  const handleRename = useCallback(async (id: string, title: string) => {
    try {
      await api.renameConversation(id, title)
      setConversations((prev) =>
        prev.map((c) => (c.id === id ? { ...c, title } : c)),
      )
    } catch (err) {
      console.error(err)
    }
  }, [])

  const handleDelete = useCallback(
    async (id: string) => {
      try {
        await api.deleteConversation(id)
        setConversations((prev) => prev.filter((c) => c.id !== id))
        if (selectedId === id) {
          setSelectedId(null)
          navigate('/')
        }
      } catch (err) {
        console.error(err)
      }
    },
    [navigate, selectedId],
  )

  if (loading) {
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
            conversations={conversations}
            selectedId={selectedId}
            conversationsLoading={conversationsLoading}
            onSelectConversation={handleSelectConversation}
            onNewChat={handleNewChat}
            onRename={handleRename}
            onDelete={handleDelete}
          />
        }
      >
        <Route index element={<ChatPage onConversationCreated={handleConversationCreated} />} />
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
