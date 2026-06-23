import { useEffect, useState } from 'react'

import type { UserProfile, UserProfileData } from '../types/userProfile'
import { EMPTY_PROFILE } from '../types/userProfile'

interface UserProfileDrawerProps {
  open: boolean
  profile: UserProfile | null
  status: 'idle' | 'loading' | 'ready' | 'error'
  error: string | null
  isSaving: boolean
  saveMessage: string | null
  onClose: () => void
  onRefresh: () => Promise<void>
  onSave: (data: UserProfileData) => Promise<void>
  onClear: () => Promise<void>
}

function parseListInput(value: string): string[] {
  return value
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function formatListInput(items: string[]): string {
  return items.join('，')
}

function isProfileEmpty(data: UserProfileData, summary: string | null | undefined): boolean {
  return (
    data.focus_domains.length === 0 &&
    data.common_systems.length === 0 &&
    !data.preferred_answer_style.trim() &&
    !data.notes.trim() &&
    !summary?.trim()
  )
}

function formatUpdatedAt(value: string | null): string {
  if (!value) {
    return '暂无'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function UserProfileDrawer({
  open,
  profile,
  status,
  error,
  isSaving,
  saveMessage,
  onClose,
  onRefresh,
  onSave,
  onClear,
}: UserProfileDrawerProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [draft, setDraft] = useState<UserProfileData>(EMPTY_PROFILE)
  const [focusDomainsInput, setFocusDomainsInput] = useState('')
  const [commonSystemsInput, setCommonSystemsInput] = useState('')

  useEffect(() => {
    if (!open) {
      setIsEditing(false)
      return
    }
    void onRefresh()
  }, [open, onRefresh])

  useEffect(() => {
    if (!profile) {
      return
    }
    setDraft(profile.profile)
    setFocusDomainsInput(formatListInput(profile.profile.focus_domains))
    setCommonSystemsInput(formatListInput(profile.profile.common_systems))
  }, [profile])

  if (!open) {
    return null
  }

  const profileData = profile?.profile ?? EMPTY_PROFILE
  const summary = profile?.profile_summary
  const empty = isProfileEmpty(profileData, summary)

  const handleCancel = () => {
    setDraft(profileData)
    setFocusDomainsInput(formatListInput(profileData.focus_domains))
    setCommonSystemsInput(formatListInput(profileData.common_systems))
    setIsEditing(false)
  }

  const handleSave = async () => {
    const nextProfile: UserProfileData = {
      focus_domains: parseListInput(focusDomainsInput),
      common_systems: parseListInput(commonSystemsInput),
      preferred_answer_style: draft.preferred_answer_style.trim(),
      notes: draft.notes.trim(),
    }
    await onSave(nextProfile)
    setIsEditing(false)
  }

  const handleClear = async () => {
    if (!window.confirm('确定清空画像吗？清空后助手将不再使用这些偏好信息。')) {
      return
    }
    await onClear()
    setIsEditing(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="关闭画像面板"
        className="absolute inset-0 bg-slate-900/30"
        onClick={onClose}
      />

      <aside className="relative flex h-full w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-xl">
        <header className="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">我的画像</h2>
            <p className="mt-1 text-sm text-slate-500">助手根据你的对话自动学习偏好</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-2 py-1 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
          >
            关闭
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {status === 'loading' ? (
            <p className="text-sm text-slate-500">加载画像中…</p>
          ) : null}

          {error ? <p className="mb-4 text-sm text-red-600">{error}</p> : null}

          {saveMessage ? <p className="mb-4 text-sm text-green-700">{saveMessage}</p> : null}

          {status === 'ready' && empty && !isEditing ? (
            <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center">
              <p className="text-sm text-slate-600">暂无画像，多聊几句后助手会自动学习你的偏好</p>
            </div>
          ) : null}

          {status === 'ready' && (!empty || isEditing) ? (
            <div className="space-y-5">
              {!isEditing && summary ? (
                <section>
                  <h3 className="text-sm font-medium text-slate-900">摘要</h3>
                  <p className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-700">
                    {summary}
                  </p>
                </section>
              ) : null}

              {isEditing ? (
                <>
                  <section>
                    <label htmlFor="focus-domains" className="text-sm font-medium text-slate-900">
                      关注领域
                    </label>
                    <textarea
                      id="focus-domains"
                      value={focusDomainsInput}
                      onChange={(event) => setFocusDomainsInput(event.target.value)}
                      placeholder="多个领域用逗号或换行分隔"
                      rows={2}
                      className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    />
                  </section>

                  <section>
                    <label htmlFor="common-systems" className="text-sm font-medium text-slate-900">
                      常用系统
                    </label>
                    <textarea
                      id="common-systems"
                      value={commonSystemsInput}
                      onChange={(event) => setCommonSystemsInput(event.target.value)}
                      placeholder="多个系统用逗号或换行分隔"
                      rows={2}
                      className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    />
                  </section>

                  <section>
                    <label htmlFor="answer-style" className="text-sm font-medium text-slate-900">
                      回答风格
                    </label>
                    <textarea
                      id="answer-style"
                      value={draft.preferred_answer_style}
                      onChange={(event) =>
                        setDraft((prev) => ({ ...prev, preferred_answer_style: event.target.value }))
                      }
                      placeholder="例如：简洁分点、附带示例"
                      rows={2}
                      className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    />
                  </section>

                  <section>
                    <label htmlFor="profile-notes" className="text-sm font-medium text-slate-900">
                      补充说明
                    </label>
                    <textarea
                      id="profile-notes"
                      value={draft.notes}
                      onChange={(event) => setDraft((prev) => ({ ...prev, notes: event.target.value }))}
                      placeholder="其他希望助手记住的背景信息"
                      rows={3}
                      className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    />
                  </section>
                </>
              ) : (
                <>
                  {profileData.focus_domains.length > 0 ? (
                    <section>
                      <h3 className="text-sm font-medium text-slate-900">关注领域</h3>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {profileData.focus_domains.map((item) => (
                          <span
                            key={item}
                            className="rounded-full bg-blue-50 px-3 py-1 text-xs text-blue-700"
                          >
                            {item}
                          </span>
                        ))}
                      </div>
                    </section>
                  ) : null}

                  {profileData.common_systems.length > 0 ? (
                    <section>
                      <h3 className="text-sm font-medium text-slate-900">常用系统</h3>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {profileData.common_systems.map((item) => (
                          <span
                            key={item}
                            className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700"
                          >
                            {item}
                          </span>
                        ))}
                      </div>
                    </section>
                  ) : null}

                  {profileData.preferred_answer_style ? (
                    <section>
                      <h3 className="text-sm font-medium text-slate-900">回答风格</h3>
                      <p className="mt-2 text-sm text-slate-700">{profileData.preferred_answer_style}</p>
                    </section>
                  ) : null}

                  {profileData.notes ? (
                    <section>
                      <h3 className="text-sm font-medium text-slate-900">补充说明</h3>
                      <p className="mt-2 text-sm text-slate-700">{profileData.notes}</p>
                    </section>
                  ) : null}
                </>
              )}

              {profile ? (
                <section className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-500">
                  <div className="flex flex-wrap items-center gap-2">
                    <span>
                      来源：
                      {profile.source === 'manual' ? '手动设置' : '自动学习'}
                    </span>
                    {profile.source === 'manual' ? (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-700">
                        手动设置后不再自动覆盖
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1">更新于：{formatUpdatedAt(profile.updated_at)}</p>
                </section>
              ) : null}
            </div>
          ) : null}
        </div>

        <footer className="border-t border-slate-200 px-5 py-4">
          {isEditing ? (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => {
                  void handleSave()
                }}
                disabled={isSaving}
                className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSaving ? '保存中…' : '保存'}
              </button>
              <button
                type="button"
                onClick={handleCancel}
                disabled={isSaving}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                取消
              </button>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setIsEditing(true)}
                disabled={status !== 'ready' || isSaving}
                className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                编辑画像
              </button>
              <button
                type="button"
                onClick={() => {
                  void handleClear()
                }}
                disabled={status !== 'ready' || isSaving || empty}
                className="rounded-lg border border-red-200 px-4 py-2 text-sm text-red-600 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                清空画像
              </button>
            </div>
          )}
        </footer>
      </aside>
    </div>
  )
}
