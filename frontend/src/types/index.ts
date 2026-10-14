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

export interface Source {
  index: number
  title: string
  url: string
  snippet?: string
}

export interface ActionItem {
  type: string
  proposal_id?: string
  key?: string
  summary?: string
  title: string
  description: string
}

export interface ChatResponse {
  conversation_id: string
  response: string
  title: string | null
  sources?: Source[]
  actions?: ActionItem[]
  tool_events?: ToolEvent[]
}

export interface ToolEvent {
  tool: string
  status?: string
  summary?: string
  key?: string
  history_recorded?: boolean
  docs?: string[]
  result?: { results?: unknown[] }
  sources?: number
  pages?: number
  places?: number
  location?: string
  route?: string
  [key: string]: unknown
}

export interface Document {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  status: string
  /** Short human-readable failure reason from the backend (never a traceback). */
  failure_reason?: string | null
  created_at: string
  completed_at?: string | null
  failed_at?: string | null
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
  supplements?: unknown[]
  preferences?: ProfilePreferences
  location_label?: string | null
  location_lat?: number | null
  location_lon?: number | null
  location_timezone?: string | null
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

export interface Exercise {
  id: string
  slug: string
  name: string
  primary_muscle_group: string | null
  equipment: string | null
  movement_type: string | null
  unit_mode: string
  is_custom: boolean
}

export interface PlannedExercise {
  id: string
  position: number
  exercise_name: string
  target_sets: number | null
  target_reps: number | null
  target_weight: number | null
  target_weight_unit: string | null
  duration_seconds: number | null
  distance_meters: number | null
  notes: string | null
}

export interface PlannedSession {
  id: string
  planned_date: string
  title: string | null
  day_type: string
  status: string
  completed_session_id: string | null
  notes: string | null
  created_at: string
  updated_at: string
  exercises: PlannedExercise[]
}

export interface DaySummary {
  date: string
  planned_count: number
  completed_count: number
  day_type: string
  has_meals: boolean
}

export interface Template {
  key: string
  name: string
  days: Record<string, unknown>[]
}

export interface BmiPoint {
  measured_at: string
  value: number
  unit: string
  source: string
  weight_kg: number
  height_cm: number
}

export interface PersonalRecord {
  exercise_name: string
  weight: number
  weight_unit: string | null
  achieved_on: string
}

export interface WeeklySessions {
  week_of: string
  sessions: number
}

export interface DerivedMetrics {
  window: Record<string, string>
  sessions_completed: number
  active_days: number
  sessions_per_week: number
  weekly_sessions: WeeklySessions[]
  total_volume_kg: number
  personal_records: PersonalRecord[]
  current_streak_days: number
  longest_streak_days: number
  planned_sessions: number
  planned_completed: number
  planned_completion_rate: number | null
  source: string
}

export interface MetricDefinition {
  type: string
  label: string
  canonical_unit: string
  units: string[]
  min: number
  max: number
  derived: boolean
}
