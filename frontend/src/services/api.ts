import type {
  ChatRequest,
  ChatResponse,
  Conversation,
  Document,
  Measurement,
  Memory,
  Message,
  Page,
  PendingMemoryUpdate,
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

const MAX_RETRIES = 3
const RETRY_DELAY_MS = 300

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function fetchApi<T>(
  path: string,
  options: RequestInit = {},
  retryCount = 0,
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

  const isGet = !options.method || options.method.toUpperCase() === 'GET'

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    })

    if (!response.ok) {
      const text = await response.text().catch(() => 'Unknown error')
      if (response.status === 401 && api.onAuthError) {
        api.onAuthError()
      }
      throw new ApiError(response.status, text)
    }

    if (response.status === 204) {
      return undefined as T
    }

    return response.json() as Promise<T>
  } catch (err) {
    const isNetworkError = err instanceof TypeError
    if (isNetworkError && isGet && retryCount < MAX_RETRIES) {
      await sleep(RETRY_DELAY_MS * (retryCount + 1))
      return fetchApi<T>(path, options, retryCount + 1)
    }
    if (isNetworkError) {
      throw new NetworkError('The backend is unreachable. Please check your connection and try again.')
    }
    throw err
  }
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

export class NetworkError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'NetworkError'
  }
}

export const api = {
  onAuthError: null as (() => void) | null,

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

  // Pending memory proposals
  listPendingMemory: (limit = 50, offset = 0) =>
    fetchApi<Page<PendingMemoryUpdate>>(`/memory/pending?limit=${limit}&offset=${offset}`),
  confirmMemoryUpdate: (id: string) =>
    fetchApi<Memory>(`/memory/pending/${id}/confirm`, { method: 'POST' }),
  rejectMemoryUpdate: (id: string) =>
    fetchApi<PendingMemoryUpdate>(`/memory/pending/${id}/reject`, { method: 'POST' }),

  // Location helpers
  geocode: (place: string) =>
    fetchApi<{ label: string; lat: number; lon: number; timezone?: string | null }>(
      `/location/geocode?place=${encodeURIComponent(place)}`,
    ),
  reverseGeocode: (lat: number, lon: number) =>
    fetchApi<{ label: string; lat: number; lon: number; timezone?: string | null }>(
      `/location/reverse?lat=${lat}&lon=${lon}`,
    ),

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
  listAllWorkouts: async () => {
    const items: WorkoutSession[] = []
    let offset = 0
    const pageSize = 100
    while (true) {
      const page = await api.listWorkouts(pageSize, offset)
      items.push(...page.items)
      if (items.length >= page.total || page.items.length === 0) break
      offset += pageSize
    }
    return items
  },
  createWorkout: (payload: WorkoutSessionCreate) =>
    fetchApi<WorkoutSession>('/workouts', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteWorkout: (id: string) =>
    fetchApi<void>(`/workouts/${id}`, { method: 'DELETE' }),

  // Progress
  weightSeries: () => fetchApi<Measurement[]>('/progress/weight'),
  createMeasurement: (payload: { type: string; value: number; unit: string; measured_at: string; notes?: string }) =>
    fetchApi<Measurement>('/progress/measurements', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteMeasurement: (id: string) =>
    fetchApi<void>(`/progress/measurements/${id}`, { method: 'DELETE' }),
}
