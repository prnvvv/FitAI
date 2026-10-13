import type {
  ChatRequest,
  ChatResponse,
  Conversation,
  Document,
  Measurement,
  Memory,
  Message,
  Page,
  Profile,
  WorkoutSession,
  WorkoutSessionCreate,
} from '../types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

import { supabase } from './supabase'

async function getToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token ?? null
}

async function fetchApi<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = await getToken()
  const headers = new Headers(options.headers)
  headers.set('Accept', 'application/json')
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  })

  if (!response.ok) {
    const text = await response.text().catch(() => 'Unknown error')
    throw new ApiError(response.status, text)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

export class ApiError extends Error {
  status: number
  body: string

  constructor(status: number, body: string) {
    super(`API error ${status}: ${body}`)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

export const api = {
  // Auth
  me: () => fetchApi<{ id: string; email: string | null }>('/auth/me'),

  // Conversations
  listConversations: (limit = 50, offset = 0) =>
    fetchApi<Page<Conversation>>(`/conversations?limit=${limit}&offset=${offset}`),
  createConversation: (title?: string) =>
    fetchApi<Conversation>('/conversations', {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),
  getConversation: (id: string) => fetchApi<Conversation>(`/conversations/${id}`),
  renameConversation: (id: string, title: string) =>
    fetchApi<Conversation>(`/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),
  deleteConversation: (id: string) =>
    fetchApi<void>(`/conversations/${id}`, { method: 'DELETE' }),
  listMessages: (id: string, limit = 100, offset = 0) =>
    fetchApi<Page<Message>>(`/conversations/${id}/messages?limit=${limit}&offset=${offset}`),

  // Chat
  sendMessage: (payload: ChatRequest) =>
    fetchApi<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // Documents
  listDocuments: (limit = 50, offset = 0) =>
    fetchApi<Page<Document>>(`/documents?limit=${limit}&offset=${offset}`),
  uploadDocument: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return fetchApi<Document>('/documents', {
      method: 'POST',
      body: formData,
    })
  },
  deleteDocument: (id: string) =>
    fetchApi<void>(`/documents/${id}`, { method: 'DELETE' }),

  // Memory
  listMemory: (limit = 50, offset = 0) =>
    fetchApi<Page<Memory>>(`/memory?limit=${limit}&offset=${offset}`),
  deleteMemory: (id: string) =>
    fetchApi<void>(`/memory/${id}`, { method: 'DELETE' }),
  correctMemory: (id: string, value: unknown) =>
    fetchApi<Memory>(`/memory/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ value }),
    }),

  // Profile
  getProfile: () => fetchApi<Profile>('/profile'),
  updateProfile: (patch: Partial<Profile>) =>
    fetchApi<Profile>('/profile', {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),
  replaceProfile: (profile: Partial<Profile>) =>
    fetchApi<Profile>('/profile', {
      method: 'PUT',
      body: JSON.stringify(profile),
    }),

  // Workouts
  listWorkouts: (limit = 50, offset = 0) =>
    fetchApi<Page<WorkoutSession>>(`/workouts?limit=${limit}&offset=${offset}`),
  createWorkout: (payload: WorkoutSessionCreate) =>
    fetchApi<WorkoutSession>('/workouts', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteWorkout: (id: string) =>
    fetchApi<void>(`/workouts/${id}`, { method: 'DELETE' }),

  // Progress
  weightSeries: () => fetchApi<Measurement[]>('/progress/weight'),
}
