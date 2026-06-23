export interface UserProfileData {
  focus_domains: string[]
  preferred_answer_style: string
  common_systems: string[]
  notes: string
}

export interface UserProfile {
  tenant_id: string
  profile: UserProfileData
  profile_summary: string | null
  source: 'auto' | 'manual'
  updated_at: string | null
}

export interface UserProfileUpdateRequest {
  profile: UserProfileData
  profile_summary?: string | null
}

export const EMPTY_PROFILE: UserProfileData = {
  focus_domains: [],
  preferred_answer_style: '',
  common_systems: [],
  notes: '',
}
