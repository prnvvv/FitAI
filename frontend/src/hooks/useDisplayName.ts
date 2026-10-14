import { useAuth } from '../context/AuthContext'

/** Strip control characters and enforce a 1–50 character display name. */
export function sanitizeDisplayName(value: string | null | undefined): string {
  const cleaned = (value ?? '').replace(/[\u0000-\u001F\u007F]/g, '').trim()
  if (cleaned.length < 1) return ''
  return cleaned.slice(0, 50)
}

export function getFirstName(value: string | null | undefined): string {
  const cleaned = sanitizeDisplayName(value)
  if (!cleaned) return 'there'
  return cleaned.split(/\s+/)[0]
}

export function getInitials(value: string | null | undefined, email?: string | null): string {
  const cleaned = sanitizeDisplayName(value)
  const base = cleaned || sanitizeDisplayName(email?.split('@')[0]) || 'U'
  return base.slice(0, 2).toUpperCase()
}

export function useDisplayName(profileName?: string | null) {
  const { user } = useAuth()
  const supabaseName =
    (user as unknown as { user_metadata?: { full_name?: string; name?: string } })?.user_metadata?.full_name ||
    (user as unknown as { user_metadata?: { full_name?: string; name?: string } })?.user_metadata?.name

  const resolved =
    sanitizeDisplayName(profileName) ||
    sanitizeDisplayName(user?.displayName) ||
    sanitizeDisplayName(supabaseName) ||
    sanitizeDisplayName(user?.email?.split('@')[0]) ||
    'there'

  return {
    fullName: resolved,
    firstName: getFirstName(resolved),
    initials: getInitials(resolved, user?.email),
  }
}