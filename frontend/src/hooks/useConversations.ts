import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import { api } from '../services/api'
import type { Conversation } from '../types'

interface UseConversationsOptions {
  enabled: boolean
}

interface UseConversationsResult {
  conversations: Conversation[]
  loading: boolean
  error: string | null
  searchQuery: string
  setSearchQuery: (query: string) => void
  activeId: string | null
  refresh: () => Promise<void>
  createConversation: (title?: string) => Promise<Conversation>
  renameConversation: (id: string, title: string) => Promise<void>
  deleteConversation: (id: string) => Promise<void>
  updateConversationTitle: (id: string, title: string | null) => void
}

function normalizeTitle(title: string | null | undefined): string {
  return (title ?? '').trim()
}

function extractConversationIdFromPath(pathname: string): string | null {
  const match = pathname.match(/^\/chat\/([^/]+)$/)
  return match ? match[1] : null
}

export function useConversations({ enabled }: UseConversationsOptions): UseConversationsResult {
  const { conversationId: paramConversationId } = useParams<{ conversationId?: string }>()
  const location = useLocation()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  // Get conversationId from URL path (works for both parent and child routes)
  const urlConversationId = paramConversationId ?? extractConversationIdFromPath(location.pathname)
  const activeId = urlConversationId ?? null

  // Overlapping refreshes (e.g. one per sent message) can resolve out of order;
  // only the most recently started request may update the list.
  const latestLoad = useRef(0)

  const load = useCallback(async () => {
    if (!enabled) return
    const requestId = (latestLoad.current += 1)
    setError(null)
    try {
      const page = await api.listConversations(100, 0)
      if (requestId === latestLoad.current) setConversations(page.items)
    } catch (err) {
      if (requestId !== latestLoad.current) return
      const message = err instanceof Error ? err.message : 'Failed to load conversations'
      setError(message)
    } finally {
      if (requestId === latestLoad.current) setLoading(false)
    }
  }, [enabled])

  useEffect(() => {
    let cancelled = false
    load().then(() => {
      if (cancelled) return
    })
    return () => {
      cancelled = true
    }
  }, [load])

  // Background refreshes (one per sent message) must not blank a list that is
  // already on screen; only an empty list shows the loading state.
  const hasConversations = useRef(false)
  useEffect(() => {
    hasConversations.current = conversations.length > 0
  }, [conversations])

  const refresh = useCallback(async () => {
    if (!hasConversations.current) setLoading(true)
    await load()
  }, [load])

  const createConversation = useCallback(
    async (title?: string): Promise<Conversation> => {
      const conversation = await api.createConversation(title)
      setConversations((prev) => [conversation, ...prev])
      return conversation
    },
    [],
  )

  const renameConversation = useCallback(async (id: string, title: string) => {
    const trimmed = normalizeTitle(title)
    if (!trimmed) return
    const previous = conversations.find((c) => c.id === id)
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, title: trimmed } : c)),
    )
    try {
      await api.renameConversation(id, trimmed)
    } catch (err) {
      if (previous) {
        setConversations((prev) =>
          prev.map((c) => (c.id === id ? { ...c, title: previous.title } : c)),
        )
      }
      throw err
    }
  }, [conversations])

  const deleteConversation = useCallback(async (id: string) => {
    const previous = conversations.find((c) => c.id === id)
    setConversations((prev) => prev.filter((c) => c.id !== id))
    try {
      await api.deleteConversation(id)
    } catch (err) {
      if (previous) {
        setConversations((prev) => [previous, ...prev].sort((a, b) =>
          new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
        ))
      }
      throw err
    }
  }, [conversations])

  const updateConversationTitle = useCallback((id: string, title: string | null) => {
    const trimmed = normalizeTitle(title)
    if (!trimmed) return
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, title: trimmed } : c)),
    )
  }, [])

  const filteredConversations = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    if (!query) return conversations
    return conversations.filter((c) =>
      (c.title ?? '').toLowerCase().includes(query),
    )
  }, [conversations, searchQuery])

  return {
    conversations: filteredConversations,
    loading,
    error,
    searchQuery,
    setSearchQuery,
    activeId,
    refresh,
    createConversation,
    renameConversation,
    deleteConversation,
    updateConversationTitle,
  }
}
