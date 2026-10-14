import { useCallback, useEffect, useState } from 'react'
import { api } from '../services/api'
import type { Profile } from '../types'

interface UseProfileResult {
  profile: Profile | null
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}

export function useProfile(): UseProfileResult {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getProfile()
      setProfile(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load profile')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return { profile, loading, error, refresh: load }
}