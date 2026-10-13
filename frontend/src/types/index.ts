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

export interface PendingMemoryUpdate {
  id: string
  key: string
  proposed_value: unknown
  previous_value: unknown
  confidence: number | null
  source: string | null
  reason: string | null
  status: string
  created_at: string
  resolved_at: string | null
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
  preferences?: ProfilePreferences
  created_at: string
  updated_at: string
}

export interface ProfilePreferences {
  display_name?: string | null
  about_you?: string | null
  assistant_should_know?: string | null
  preferred_tone?: string | null
  units?: 'metric' | 'imperial' | null
}

export interface NavItem {
  id: string
  label: string
  icon: string
  path: string
}

export interface WorkoutSet {
  id: string
  position: number
  exercise_name: string
  reps: number | null
  weight: number | null
  weight_unit: string | null
  duration_seconds: number | null
  distance_meters: number | null
  notes: string | null
}

export interface WorkoutSession {
  id: string
  name: string | null
  performed_at: string
  duration_minutes: number | null
  notes: string | null
  created_at: string
  sets: WorkoutSet[]
}

export interface WorkoutSetCreate {
  exercise_name: string
  reps?: number | null
  weight?: number | null
  weight_unit?: string | null
  duration_seconds?: number | null
  distance_meters?: number | null
  notes?: string | null
}

export interface WorkoutSessionCreate {
  name?: string | null
  performed_at: string
  duration_minutes?: number | null
  notes?: string | null
  sets: WorkoutSetCreate[]
}

export interface Measurement {
  id: string
  type: string
  value: number
  unit: string
  measured_at: string
  notes: string | null
  created_at: string
}
