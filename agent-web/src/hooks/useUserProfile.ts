import { useCallback, useEffect, useState } from 'react'

import { clearUserProfile, fetchUserProfile, updateUserProfile } from '../api/userProfile'
import type { UserProfile, UserProfileData } from '../types/userProfile'
import { toUserFacingError } from '../utils/userError'

interface UseUserProfileResult {
  profile: UserProfile | null
  status: 'idle' | 'loading' | 'ready' | 'error'
  error: string | null
  isSaving: boolean
  saveMessage: string | null
  refresh: () => Promise<void>
  save: (data: UserProfileData) => Promise<void>
  clear: () => Promise<void>
}

export function useUserProfile(tenantId: string): UseUserProfileResult {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setStatus('loading')
    setError(null)
    try {
      const result = await fetchUserProfile(tenantId)
      setProfile(result)
      setStatus('ready')
    } catch (err: unknown) {
      setError(toUserFacingError(err instanceof Error ? err.message : undefined))
      setStatus('error')
    }
  }, [tenantId])

  const save = useCallback(
    async (data: UserProfileData) => {
      setIsSaving(true)
      setError(null)
      setSaveMessage(null)
      try {
        const result = await updateUserProfile(tenantId, { profile: data })
        setProfile(result)
        setSaveMessage('画像已保存')
        setStatus('ready')
      } catch (err: unknown) {
        setError(toUserFacingError(err instanceof Error ? err.message : undefined))
        throw err
      } finally {
        setIsSaving(false)
      }
    },
    [tenantId],
  )

  const clear = useCallback(async () => {
    setIsSaving(true)
    setError(null)
    setSaveMessage(null)
    try {
      const result = await clearUserProfile(tenantId)
      setProfile(result)
      setSaveMessage('画像已清空')
      setStatus('ready')
    } catch (err: unknown) {
      setError(toUserFacingError(err instanceof Error ? err.message : undefined))
      throw err
    } finally {
      setIsSaving(false)
    }
  }, [tenantId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return {
    profile,
    status,
    error,
    isSaving,
    saveMessage,
    refresh,
    save,
    clear,
  }
}
