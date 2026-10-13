export interface User {
  id: string
  email?: string
  displayName?: string
}

export interface Conversation {
  id: string
  title: string | null
  created_at: string
  updated_at: string
}

export interface Message {
  id: string
  conversation_id: string
  role: 'user' | 'assistant'
  content: string
  metadata?: Record<string, unknown> | null
  created_at: string
}

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface ChatRequest {
  message: string
  conversation_id?: string
}

export interface ChatResponse {
  conversation_id: string
  response: string
  title: string | null
}

export interface Document {
  id: string
  filename: string
  content_type: string
  status: string
  created_at: string
}

export interface Memory {
  id: string
  key: string
  value: unknown
  status: string
  confidence: number | null
  source: string | null
  effective_at: string | null
  created_at: string
  updated_at: string
}

export interface Profile {
  id: string
  user_id: string
  date_of_birth?: string | null
  age?: number | null
  height_cm?: number | null
  weight_kg?: number | null
  goal?: string | null
  activity_level?: string | null
  dietary_preferences?: string[]
  dietary_restrictions?: string[]
  created_at: string
  updated_at: string
}

export interface NavItem {
  id: string
  label: string
  icon: string
  path: string
}
