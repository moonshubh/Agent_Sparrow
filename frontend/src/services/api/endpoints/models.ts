import { apiClient } from '@/services/api/api-client'

export type Provider = 'google' | 'xai' | 'openrouter'
export type AgentType = 'primary' | 'log_analysis'
export type ModelTier = 'pro' | 'standard' | 'lite'

export type ProviderModels = Partial<Record<Provider, string[]>>
export type ProviderAvailability = Record<Provider, boolean>

// Model info from registry
export interface ModelInfo {
  display_name: string
  provider: Provider
  tier: ModelTier
  supports_reasoning: boolean
  supports_vision: boolean
}

// Full model config from registry
export interface ModelConfig {
  models: Record<string, ModelInfo>
  defaults: Record<Provider, string>
  fallback_chains: Record<Provider, Record<string, string | null>>
  available_providers: ProviderAvailability
}

// Fallback models when API is unavailable - main coordinator models only
const FALLBACK_MODELS: Record<Provider, string[]> = {
  google: ['gemini-3-flash-preview', 'gemini-2.5-pro', 'gemini-3-pro-preview'],
  xai: ['grok-4-1-fast-reasoning'],
  openrouter: ['x-ai/grok-4.1-fast:free', 'minimax/minimax-m2'],
}

// Official model display names (from ai.google.dev & docs.x.ai)
const FALLBACK_DISPLAY_NAMES: Record<string, string> = {
  // Google Gemini (official names)
  'gemini-3-pro-preview': 'Gemini 3.0 Pro',
  'gemini-3-flash-preview': 'Gemini 3.0 Flash',
  'gemini-2.5-pro': 'Gemini 2.5 Pro',
  'gemini-2.5-flash': 'Gemini 2.5 Flash',
  // xAI Grok
  'grok-4-1-fast-reasoning': 'Grok 4.1 Fast',
  // OpenRouter
  'x-ai/grok-4.1-fast:free': 'Grok 4.1 Fast (Free)',
  'minimax/minimax-m2': 'MiniMax M2',
}

// Human-readable provider labels
export const PROVIDER_LABELS: Record<Provider, string> = {
  google: 'Gemini',
  xai: 'Grok',
  openrouter: 'OpenRouter',
}

// Cache TTL in milliseconds (5 minutes)
const CACHE_TTL_MS = 5 * 60 * 1000

// Cached model config with timestamp
interface CachedModelConfig {
  config: ModelConfig
  timestamp: number
}

let cachedConfig: CachedModelConfig | null = null

/**
 * Check if cached config is still valid based on TTL.
 */
function isCacheValid(): boolean {
  if (!cachedConfig) return false
  return Date.now() - cachedConfig.timestamp < CACHE_TTL_MS
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
  const openrouter = Array.isArray(providers.openrouter) ? (providers.openrouter as string[]) : undefined

  if (!google && !xai && !openrouter) return null

  const result: ProviderModels = {}
  if (google && google.length) result.google = google
  if (xai && xai.length) result.xai = xai
  if (openrouter && openrouter.length) result.openrouter = openrouter

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
    openrouter: Boolean(providers.openrouter),
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
      return normalized || { google: FALLBACK_MODELS.google, xai: FALLBACK_MODELS.xai, openrouter: FALLBACK_MODELS.openrouter }
    } catch (e: unknown) {
      if (process.env.NODE_ENV === 'development') {
        console.debug('modelsAPI.list fallback due to error:', e)
      }
      // Graceful fallback to Google only
      return { google: FALLBACK_MODELS.google, xai: FALLBACK_MODELS.xai, openrouter: FALLBACK_MODELS.openrouter }
    }
  },

  /**
   * Fetch which providers are available (have API keys configured).
   */
  async getAvailableProviders(): Promise<ProviderAvailability> {
    try {
      const res = await apiClient.get<unknown>('/api/v1/providers')
      const normalized = normalizeProvidersResponse(res)
      return normalized || { google: true, xai: false, openrouter: false }
    } catch (e: unknown) {
      if (process.env.NODE_ENV === 'development') {
        console.debug('modelsAPI.getAvailableProviders fallback due to error:', e)
      }
      // Assume Google is always available as fallback
      return { google: true, xai: false, openrouter: false }
    }
  },

  /**
   * Get the default model for a provider.
   */
  getDefaultModel(provider: Provider): string {
    if (isCacheValid() && cachedConfig) {
      return cachedConfig.config.defaults[provider] || FALLBACK_MODELS[provider]?.[0] || 'gemini-3-flash-preview'
    }
    return FALLBACK_MODELS[provider]?.[0] || 'gemini-3-flash-preview'
  },

  /**
   * Fetch comprehensive model configuration from the registry.
   * This includes all models, display names, fallback chains, and provider availability.
   * Results are cached with a 5-minute TTL.
   */
  async getConfig(): Promise<ModelConfig> {
    // Return cached config if still valid
    if (isCacheValid() && cachedConfig) {
      return cachedConfig.config
    }

    try {
      const res = await apiClient.get<ModelConfig>('/api/v1/models/config')
      if (res && typeof res === 'object' && 'models' in res) {
        // Cache with timestamp for TTL
        cachedConfig = {
          config: res,
          timestamp: Date.now(),
        }
        return res
      }
    } catch (e: unknown) {
      if (process.env.NODE_ENV === 'development') {
        console.debug('modelsAPI.getConfig fallback due to error:', e)
      }
    }

    // Return fallback config (not cached to encourage retry)
    return {
      models: Object.fromEntries(
        Object.entries(FALLBACK_DISPLAY_NAMES).map(([id, name]) => {
          // Determine provider from model ID
          let provider: Provider = 'google'
          if (id.startsWith('grok-')) provider = 'xai'
          else if (id.includes('/')) provider = 'openrouter'

          return [
            id,
            {
              display_name: name,
              provider,
              tier: id.includes('pro') || id === 'gemini-3-pro-preview' ? 'pro' : 'standard',
              supports_reasoning: true,
              supports_vision: provider === 'google',
            } as ModelInfo,
          ]
        })
      ),
      defaults: {
        google: 'gemini-3-flash-preview',
        xai: 'grok-4-1-fast-reasoning',
        openrouter: 'x-ai/grok-4.1-fast:free',
      },
      fallback_chains: {
        google: {
          'gemini-3-pro-preview': 'gemini-2.5-pro',
          'gemini-2.5-pro': 'gemini-3-flash-preview',
          'gemini-3-flash-preview': null,
        },
        xai: {
          'grok-4-1-fast-reasoning': null,
        },
        openrouter: {
          'x-ai/grok-4.1-fast:free': 'minimax/minimax-m2',
          'minimax/minimax-m2': null,
        },
      },
      available_providers: { google: true, xai: false, openrouter: false },
    }
  },

  /**
   * Get display name for a model ID.
   */
  getDisplayName(modelId: string): string {
    if (isCacheValid() && cachedConfig?.config.models[modelId]) {
      return cachedConfig.config.models[modelId].display_name
    }
    return FALLBACK_DISPLAY_NAMES[modelId] || modelId
  },

  /**
   * Clear the cached config (useful for testing or forcing refresh).
   */
  clearCache(): void {
    cachedConfig = null
  },

  /**
   * Force refresh the cached config from the server.
   */
  async refreshConfig(): Promise<ModelConfig> {
    cachedConfig = null
    return this.getConfig()
  },
}
