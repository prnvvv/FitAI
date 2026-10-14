import type {
  BmiPoint,
  ChatRequest,
  ChatResponse,
  Conversation,
  DaySummary,
  DerivedMetrics,
  Document,
  Exercise,
  Measurement,
  Memory,
  Message,
  Page,
  PendingMemoryUpdate,
  PlannedSession,
  Profile,
  Template,
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
    super(errorMessage(status, body))
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

export interface ValidationIssue {
  field: string
  message: string
}

function parseBody(body: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(body)
    return typeof parsed === 'object' && parsed !== null ? (parsed as Record<string, unknown>) : null
  } catch {
    return null
  }
}

/** Extract FastAPI's 422 field errors so forms can show them inline. */
export function validationIssues(err: unknown): ValidationIssue[] {
  if (!(err instanceof ApiError) || err.status !== 422) return []
  const parsed = parseBody(err.body)
  const details = parsed?.detail
  if (!Array.isArray(details)) return []
  const issues: ValidationIssue[] = []
  for (const item of details) {
    if (typeof item !== 'object' || item === null) continue
    const entry = item as { loc?: unknown[]; msg?: unknown }
    const loc = Array.isArray(entry.loc) ? entry.loc.map(String) : []
    issues.push({
      field: loc.filter((part) => part !== 'body').join('.'),
      message: typeof entry.msg === 'string' ? entry.msg : 'This value is not valid.',
    })
  }
  return issues
}

/**
 * Map an HTTP failure to calm, human copy. Never surfaces raw JSON.
 */
export function errorMessage(status: number, body: string): string {
  const parsed = parseBody(body)
  const error = parsed?.error as { message?: unknown; code?: unknown } | undefined
  const serverMessage = typeof error?.message === 'string' ? error.message : null
  const code = typeof error?.code === 'string' ? error.code : null

  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 403) return "You don't have access to that."
  if (status === 404) return serverMessage ?? "We couldn't find that."
  if (status === 413) return 'That file is too large to upload.'
  if (status === 415) return serverMessage ?? 'That file type is not supported.'
  if (status === 422) {
    const detail = parsed?.detail
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: unknown }
      const message = typeof first?.msg === 'string' ? first.msg : null
      if (message) return message.replace(/^Value error, /, '')
    }
    return serverMessage ?? 'Please check the values you entered.'
  }
  if (status === 429) return 'Too many requests. Please wait a moment and try again.'
  if (status >= 500) {
    if (code === 'SERVICE_UNAVAILABLE') {
      return serverMessage ?? 'A required service is unavailable right now.'
    }
    if (code === 'MIGRATION_REQUIRED') {
      return 'The database needs updating. Run migrations, then try again.'
    }
    return 'Something went wrong on our side. Please try again.'
  }
  return serverMessage ?? 'That request could not be completed.'
}

/** Convenience wrapper used by pages so they never render an ApiError body. */
export function toMessage(err: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (err instanceof ApiError || err instanceof NetworkError) return err.message
  if (err instanceof Error && err.message) return err.message
  return fallback
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
  retryDocument: (id: string) =>
    fetchApi<Document>(`/documents/${id}/retry`, { method: 'POST' }),

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
  heightSeries: () => fetchApi<Measurement[]>('/progress/height'),
  bmiSeries: () => fetchApi<BmiPoint[]>('/progress/bmi'),
  createMeasurement: (payload: { type: string; value: number; unit: string; measured_at: string; notes?: string }) =>
    fetchApi<Measurement>('/progress/measurements', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteMeasurement: (id: string) =>
    fetchApi<void>(`/progress/measurements/${id}`, { method: 'DELETE' }),
  derivedMetrics: () => fetchApi<DerivedMetrics>('/progress/derived'),

  // Exercise library
  listExercises: (limit = 200, offset = 0) =>
    fetchApi<Page<Exercise>>(`/exercises?limit=${limit}&offset=${offset}`),
  searchExercises: (search: string, limit = 20, offset = 0) =>
    fetchApi<Page<Exercise>>(
      `/exercises?search=${encodeURIComponent(search)}&limit=${limit}&offset=${offset}`,
    ),
  createExercise: (payload: {
    name: string
    primary_muscle_group?: string | null
    equipment?: string | null
    movement_type?: string | null
    unit_mode?: string
  }) =>
    fetchApi<Exercise>('/exercises', { method: 'POST', body: JSON.stringify(payload) }),
  listAllExercises: async () => {
    const items: Exercise[] = []
    let offset = 0
    const pageSize = 200
    while (true) {
      const page = await api.listExercises(pageSize, offset)
      items.push(...page.items)
      if (items.length >= page.total || page.items.length === 0) break
      offset += pageSize
    }
    return items
  },

  // Plans
  getPlanSummary: (from: string, to: string) =>
    fetchApi<DaySummary[]>(
      `/plan/summary?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
    ),
  getPlanWeek: (start: string, end: string) =>
    fetchApi<PlannedSession[]>(
      `/plan/sessions?from=${encodeURIComponent(start)}&to=${encodeURIComponent(end)}&limit=100`,
    ),
  createPlannedSession: (payload: {
    planned_date: string
    title?: string | null
    day_type: string
    notes?: string | null
    exercises: Array<{
      exercise_name: string
      position: number
      target_sets?: number | null
      target_reps?: number | null
      target_weight?: number | null
      target_weight_unit?: string | null
      duration_seconds?: number | null
      distance_meters?: number | null
      notes?: string | null
    }>
  }) =>
    fetchApi<PlannedSession>('/plan/sessions', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updatePlannedSession: (
    id: string,
    payload: {
      planned_date?: string
      title?: string | null
      day_type?: string
      notes?: string | null
      exercises?: Array<{
        exercise_name: string
        position: number
        target_sets?: number | null
        target_reps?: number | null
        target_weight?: number | null
        target_weight_unit?: string | null
        duration_seconds?: number | null
        distance_meters?: number | null
        notes?: string | null
      }>
    },
  ) =>
    fetchApi<PlannedSession>(`/plan/sessions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  completePlannedSession: (id: string) =>
    fetchApi<PlannedSession>(`/plan/sessions/${id}/complete`, { method: 'POST' }),
  deletePlannedSession: (id: string) =>
    fetchApi<void>(`/plan/sessions/${id}`, { method: 'DELETE' }),
  getPlanTemplates: () => fetchApi<Template[]>('/plan/templates'),
  applyPlanTemplate: (templateKey: string, startDate: string) =>
    fetchApi<PlannedSession[]>('/plan/templates/apply', {
      method: 'POST',
      body: JSON.stringify({ template_key: templateKey, start_date: startDate }),
    }),
}
