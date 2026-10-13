import { createClient, type User } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  console.warn('Supabase URL or anon key is missing. Auth will not work.')
}

export const supabase = createClient(supabaseUrl ?? '', supabaseAnonKey ?? '', {
  auth: {
    autoRefreshToken: true,
    persistSession: true,
  },
})

export function toAppUser(user: User | null) {
  if (!user) return null
  return {
    id: user.id,
    email: user.email,
    displayName:
      user.user_metadata?.display_name ??
      user.user_metadata?.full_name ??
      user.email?.split('@')[0],
  }
}
