import type {
  BmiPoint,
  ChatRequest,
  ChatResponse,
  Conversation,
  DaySummary,
  DerivedMetrics,
  Document,
  MetricDefinition,
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
/**
 * Base URL for the document routes. Defaults to the main API so a single-process
 * deployment is unchanged; set `VITE_DOCUMENTS_URL` when documents are served by
 * the separate Documents service (e.g. https://fitai-documents.onrender.com/api/v1).
 */
const DOCUMENTS_BASE = import.meta.env.VITE_DOCUMENTS_URL || API_BASE

/** An upload either creates a new item or returns the identical existing one. */
export interface UploadResult {
  document: Document
  duplicate: boolean
}

import { getToken } from './supabase'

const MAX_RETRIES = 3
const RETRY_DELAY_MS = 300
const DEFAULT_TIMEOUT_MS = 30_000
const CHAT_TIMEOUT_MS = 120_000

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function fetchApi<T>(
  path: string,
  options: RequestInit & { timeoutMs?: number; baseUrl?: string } = {},
  retryCount = 0,
  capture?: (response: Response) => void,
): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, baseUrl = API_BASE, ...init } = options
  const token = await getToken()
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  if (init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const isGet = !init.method || init.method.toUpperCase() === 'GET'

  // A stalled backend must surface as an error instead of an endless spinner.
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers,
      signal: controller.signal,
    })

    if (!response.ok) {
      const text = await response.text().catch(() => 'Unknown error')
      if (response.status === 401 && api.onAuthError) {
        api.onAuthError()
      }
      throw new ApiError(response.status, text)
    }

    capture?.(response)

    if (response.status === 204) {
      return undefined as T
    }

    return response.json() as Promise<T>
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new TimeoutError(
        `The request took longer than ${Math.round(timeoutMs / 1000)} seconds and was cancelled.`,
      )
    }
    const isNetworkError = err instanceof TypeError
    if (isNetworkError && isGet && retryCount < MAX_RETRIES) {
      await sleep(RETRY_DELAY_MS * (retryCount + 1))
      return fetchApi<T>(path, options, retryCount + 1, capture)
    }
    if (isNetworkError) {
      throw new NetworkError('The backend is unreachable. Please check your connection and try again.')
    }
    throw err
  } finally {
    clearTimeout(timer)
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

export class TimeoutError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'TimeoutError'
  }
}

/** True for a request cancelled by an AbortController (not a real failure). */
export function isAbortError(err: unknown): boolean {
  return err instanceof DOMException ? err.name === 'AbortError' : (err as Error)?.name === 'AbortError'
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
  if (status === 503) {
    return serverMessage ?? 'A required service is unavailable right now. Try again shortly.'
  }
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

/* --------------------------------------------------------------------------
 * Response normalizers
 *
 * A render must never crash on an unexpected payload. These helpers turn null,
 * a missing envelope or a partially filled object into a safe, empty value.
 * ----------------------------------------------------------------------- */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/** Accept either a bare array or a Page envelope and return the array. */
export function normalizePlannedSessions(page: unknown): PlannedSession[] {
  const source = isRecord(page) && Array.isArray(page.items) ? page.items : page
  if (!Array.isArray(source)) return []
  return source.filter(
    (item): item is PlannedSession =>
      isRecord(item) && typeof item.id === 'string' && typeof item.planned_date === 'string',
  ).map((item) => ({ ...item, exercises: Array.isArray(item.exercises) ? item.exercises : [] }))
}

export function normalizeDaySummaries(payload: unknown): DaySummary[] {
  if (!Array.isArray(payload)) return []
  return payload.filter(
    (item): item is DaySummary => isRecord(item) && typeof item.date === 'string',
  ).map((item) => ({
    date: item.date,
    planned_count: Number(item.planned_count ?? 0),
    completed_count: Number(item.completed_count ?? 0),
    day_type: typeof item.day_type === 'string' ? item.day_type : 'none',
    has_meals: Boolean(item.has_meals),
  }))
}

export function normalizeWorkoutSessions(payload: unknown): WorkoutSession[] {
  if (!Array.isArray(payload)) return []
  return payload
    .filter(
      (item): item is WorkoutSession =>
        isRecord(item) && typeof item.id === 'string' && typeof item.performed_at === 'string',
    )
    .map((item) => ({ ...item, sets: Array.isArray(item.sets) ? item.sets : [] }))
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
      timeoutMs: CHAT_TIMEOUT_MS,
    }),

  // Documents
  listDocuments: (limit = 50, offset = 0) =>
    fetchApi<Page<Document>>(`/documents?limit=${limit}&offset=${offset}`, {
      baseUrl: DOCUMENTS_BASE,
    }),
  /** Returns the existing item when the same bytes are already in the library. */
  uploadDocument: async (file: File): Promise<UploadResult> => {
    const formData = new FormData()
    formData.append('file', file)
    let duplicate = false
    const document = await fetchApi<Document>(
      '/documents',
      { method: 'POST', body: formData, baseUrl: DOCUMENTS_BASE },
      0,
      (response) => {
        duplicate = response.headers.get('X-Duplicate') === 'true'
      },
    )
    return { document, duplicate } satisfies UploadResult
  },
  deleteDocument: (id: string) =>
    fetchApi<void>(`/documents/${id}`, { method: 'DELETE', baseUrl: DOCUMENTS_BASE }),
  retryDocument: (id: string) =>
    fetchApi<Document>(`/documents/${id}/retry`, { method: 'POST', baseUrl: DOCUMENTS_BASE }),
  renameDocument: (id: string, filename: string) =>
    fetchApi<Document>(`/documents/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ filename }),
      baseUrl: DOCUMENTS_BASE,
    }),
  metricDefinitions: () => fetchApi<MetricDefinition[]>('/progress/metrics'),
  metricSeries: (type: string, from?: string, to?: string) => {
    const params = new URLSearchParams({ type })
    if (from) params.set('from', from)
    if (to) params.set('to', to)
    return fetchApi<Measurement[]>(`/progress/series?${params.toString()}`)
  },
  updateMeasurement: (id: string, patch: { value: number; notes?: string | null }) =>
    fetchApi<Measurement>(`/progress/measurements/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),

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
  listWorkouts: (limit = 50, offset = 0, signal?: AbortSignal) =>
    fetchApi<Page<WorkoutSession>>(
      `/workouts?limit=${limit}&offset=${offset}`,
      signal ? { signal } : {},
    ),
  listAllWorkouts: async (signal?: AbortSignal) => {
    const items: WorkoutSession[] = []
    let offset = 0
    const pageSize = 100
    while (true) {
      const page = await api.listWorkouts(pageSize, offset, signal)
      const batch = normalizeWorkoutSessions(page?.items)
      items.push(...batch)
      if (batch.length === 0 || items.length >= (page?.total ?? 0)) break
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
  // `from`/`to` are optional: omitted, the endpoint uses its own default window.
  derivedMetrics: (window?: { from: string; to: string }) => {
    const params = new URLSearchParams()
    if (window) {
      params.set('from', window.from)
      params.set('to', window.to)
    }
    const query = params.toString()
    return fetchApi<DerivedMetrics>(`/progress/derived${query ? `?${query}` : ''}`)
  },

  // Exercise library
  // The backend caps page size at 100; page rather than requesting more.
  listExercises: (limit = 100, offset = 0, signal?: AbortSignal) =>
    fetchApi<Page<Exercise>>(`/exercises?limit=${limit}&offset=${offset}`, signal ? { signal } : {}),
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
  listAllExercises: async (signal?: AbortSignal) => {
    const items: Exercise[] = []
    let offset = 0
    const pageSize = 100
    while (true) {
      const page = await api.listExercises(pageSize, offset, signal)
      const batch = Array.isArray(page?.items) ? (page.items as Exercise[]) : []
      items.push(...batch)
      if (batch.length === 0 || items.length >= (page?.total ?? 0)) break
      offset += pageSize
    }
    return items
  },

  // Plans
  getPlanSummary: (from: string, to: string, signal?: AbortSignal) =>
    fetchApi<DaySummary[]>(
      `/plan/summary?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
      signal ? { signal } : {},
    ),
  /** Raw page from `/plan/sessions`. The backend answers with a Page envelope. */
  getPlanWeek: (start: string, end: string, signal?: AbortSignal) =>
    fetchApi<Page<PlannedSession>>(
      `/plan/sessions?from=${encodeURIComponent(start)}&to=${encodeURIComponent(end)}&limit=100`,
      signal ? { signal } : {},
    ),
  /** Every planned session in a range, paging through the Page envelope. */
  getAllPlannedSessions: async (
    start: string,
    end: string,
    signal?: AbortSignal,
  ): Promise<PlannedSession[]> => {
    const items: PlannedSession[] = []
    let offset = 0
    const pageSize = 100
    while (true) {
      const page = await api.getPlanWeek(start, end, signal)
      items.push(...normalizePlannedSessions(page))
      if (items.length >= page.total || page.items.length === 0) break
      offset += pageSize
    }
    return items
  },
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
