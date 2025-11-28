import { apiClient } from '@/services/api/api-client'

export type Provider = 'google' | 'xai'
export type AgentType = 'primary' | 'log_analysis'

export type ProviderModels = Partial<Record<Provider, string[]>>
export type ProviderAvailability = Record<Provider, boolean>

// Fallback models when API is unavailable
const FALLBACK_MODELS: Record<Provider, string[]> = {
  google: ['gemini-2.5-flash', 'gemini-2.5-pro'],
  xai: ['grok-4-1-fast-reasoning'],
}

// Human-readable provider labels
export const PROVIDER_LABELS: Record<Provider, string> = {
  google: 'Gemini',
  xai: 'Grok',
}

function normalizeModelsResponse(data: unknown): ProviderModels | null {
  if (!data || typeof data !== 'object') return null
  const obj = data as Record<string, unknown>

  // Accept either { providers: { google: [], xai: [] } } or { google: [], xai: [] }
  const providers = (obj.providers && typeof obj.providers === 'object'
    ? (obj.providers as Record<string, unknown>)
    : obj) as Record<string, unknown>

  const google = Array.isArray(providers.google) ? (providers.google as string[]) : undefined
  const xai = Array.isArray(providers.xai) ? (providers.xai as string[]) : undefined

  if (!google && !xai) return null

  const result: ProviderModels = {}
  if (google && google.length) result.google = google
  if (xai && xai.length) result.xai = xai

  return result
}

function normalizeProvidersResponse(data: unknown): ProviderAvailability | null {
  if (!data || typeof data !== 'object') return null
  const obj = data as Record<string, unknown>

  const providers = (obj.providers && typeof obj.providers === 'object'
    ? (obj.providers as Record<string, unknown>)
    : obj) as Record<string, unknown>

  return {
    google: Boolean(providers.google),
    xai: Boolean(providers.xai),
  }
}

export const modelsAPI = {
  /**
   * Fetch available models grouped by provider.
   * Only returns providers that have API keys configured on the backend.
   */
  async list(agent: AgentType): Promise<ProviderModels> {
    try {
      const qs = new URLSearchParams({ agent_type: agent })
      const res = await apiClient.get<unknown>(`/api/v1/models?${qs.toString()}`)
      const normalized = normalizeModelsResponse(res)
      // Return only configured providers, or fallback to Google
      return normalized || { google: FALLBACK_MODELS.google }
    } catch (e: unknown) {
      if (process.env.NODE_ENV === 'development') {
        // eslint-disable-next-line no-console
        console.debug('modelsAPI.list fallback due to error:', e)
      }
      // Graceful fallback to Google only
      return { google: FALLBACK_MODELS.google }
    }
  },

  /**
   * Fetch which providers are available (have API keys configured).
   */
  async getAvailableProviders(): Promise<ProviderAvailability> {
    try {
      const res = await apiClient.get<unknown>('/api/v1/providers')
      const normalized = normalizeProvidersResponse(res)
      return normalized || { google: true, xai: false }
    } catch (e: unknown) {
      if (process.env.NODE_ENV === 'development') {
        // eslint-disable-next-line no-console
        console.debug('modelsAPI.getAvailableProviders fallback due to error:', e)
      }
      // Assume Google is always available as fallback
      return { google: true, xai: false }
    }
  },

  /**
   * Get the default model for a provider.
   */
  getDefaultModel(provider: Provider): string {
    return FALLBACK_MODELS[provider]?.[0] || 'gemini-2.5-flash'
  },
}
