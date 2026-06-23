import type { UserProfile, UserProfileUpdateRequest } from '../types/userProfile'
import { EMPTY_PROFILE } from '../types/userProfile'
import { buildHeaders, formatErrorWithRequestId, readRequestId } from './client'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export async function fetchUserProfile(tenantId: string): Promise<UserProfile> {
  const response = await fetch(`${API_BASE}/api/profile`, {
    headers: buildHeaders({ 'X-Tenant-Id': tenantId }),
  })
  if (!response.ok) {
    throw new Error(formatErrorWithRequestId(`加载用户画像失败 (${response.status})`, readRequestId(response)))
  }
  return response.json()
}

export async function updateUserProfile(
  tenantId: string,
  body: UserProfileUpdateRequest,
): Promise<UserProfile> {
  const response = await fetch(`${API_BASE}/api/profile`, {
    method: 'PUT',
    headers: buildHeaders({
      'X-Tenant-Id': tenantId,
      'Content-Type': 'application/json',
    }),
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(formatErrorWithRequestId(`保存用户画像失败 (${response.status})`, readRequestId(response)))
  }
  return response.json()
}

export async function clearUserProfile(tenantId: string): Promise<UserProfile> {
  return updateUserProfile(tenantId, { profile: EMPTY_PROFILE, profile_summary: null })
}
