import { apiClient } from '@/services/api/api-client'

export type Provider = 'google' | 'openai'
export type AgentType = 'primary' | 'log_analysis'

export type ProviderModels = Record<Provider, string[]>

const FALLBACK_MODELS: ProviderModels = {
  google: ['gemini-2.5-flash-preview-09-2025', 'gemini-2.5-flash'],
  openai: ['gpt-5-mini', 'gpt5-mini'],
}

function normalizeResponse(data: unknown): ProviderModels | null {
  if (!data || typeof data !== 'object') return null
  const obj = data as Record<string, unknown>
  // Accept either { providers: { google: [], openai: [] } } or { google: [], openai: [] }
  const providers = (obj.providers && typeof obj.providers === 'object'
    ? (obj.providers as Record<string, unknown>)
    : obj) as Record<string, unknown>
  const google = Array.isArray(providers.google) ? (providers.google as string[]) : undefined
  const openai = Array.isArray(providers.openai) ? (providers.openai as string[]) : undefined
  if (!google && !openai) return null
  return {
    google: google && google.length ? google : FALLBACK_MODELS.google,
    openai: openai && openai.length ? openai : FALLBACK_MODELS.openai,
  }
}

export const modelsAPI = {
  async list(agent: AgentType): Promise<ProviderModels> {
    try {
      const qs = new URLSearchParams({ agent_type: agent })
      const res = await apiClient.get<unknown>(`/api/v1/models?${qs.toString()}`)
      const normalized = normalizeResponse(res)
      return normalized || FALLBACK_MODELS
    } catch (e: unknown) {
      // Graceful fallback if endpoint doesn't exist or errors
      if (process.env.NODE_ENV === 'development') {
        // eslint-disable-next-line no-console
        console.debug('modelsAPI.list fallback due to error:', e)
      }
      return FALLBACK_MODELS
    }
  },
}
