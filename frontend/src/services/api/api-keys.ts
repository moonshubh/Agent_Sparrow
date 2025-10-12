// API types and functions for API key management

// Custom API error class for structured error handling
export class APIError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail: string,
    public code?: string,
    public validationErrors?: Record<string, string[]>
  ) {
    super(message)
    this.name = 'APIError'
  }

  // Helper methods for error handling
  isValidationError(): boolean {
    return this.status === 422 && Boolean(this.validationErrors)
  }

  isAuthenticationError(): boolean {
    return this.status === 401
  }

  isAuthorizationError(): boolean {
    return this.status === 403
  }

  isNotFoundError(): boolean {
    return this.status === 404
  }

  isServerError(): boolean {
    return this.status >= 500
  }

  isClientError(): boolean {
    return this.status >= 400 && this.status < 500
  }

  // Format error for display
  getDisplayMessage(): string {
    if (this.isValidationError() && this.validationErrors) {
      const errors = Object.entries(this.validationErrors)
        .map(([field, messages]) => `${field}: ${messages.join(', ')}`)
        .join('; ')
      return `Validation failed: ${errors}`
    }
    
    return this.detail || this.message
  }

  // Get user-friendly error message
  getUserFriendlyMessage(): string {
    switch (this.status) {
      case 400:
        return this.detail || 'Invalid request. Please check your input and try again.'
      case 401:
        return 'Authentication required. Please log in and try again.'
      case 403:
        return 'You do not have permission to perform this action.'
      case 404:
        return 'The requested resource was not found.'
      case 422:
        return this.getDisplayMessage()
      case 429:
        return 'Too many requests. Please wait a moment and try again.'
      case 500:
        return 'Internal server error. Please try again later.'
      case 502:
      case 503:
      case 504:
        return 'Service temporarily unavailable. Please try again later.'
      default:
        return this.detail || 'An unexpected error occurred. Please try again.'
    }
  }
}

export enum APIKeyType {
  GEMINI = "gemini",
  OPENAI = "openai",
  TAVILY = "tavily", 
  FIRECRAWL = "firecrawl"
}

export interface APIKeyInfo {
  id: number
  api_key_type: APIKeyType
  key_name: string | null
  is_active: boolean
  created_at: string
  updated_at: string
  last_used_at: string | null
  masked_key: string
}

export interface APIKeyCreateRequest {
  api_key_type: APIKeyType
  api_key: string
  key_name?: string
}

export interface APIKeyUpdateRequest {
  api_key?: string
  key_name?: string
  is_active?: boolean
}

export interface APIKeyCreateResponse {
  success: boolean
  message: string
  api_key_info?: APIKeyInfo
}

export interface APIKeyUpdateResponse {
  success: boolean
  message: string
  api_key_info?: APIKeyInfo
}

export interface APIKeyDeleteResponse {
  success: boolean
  message: string
}

export interface APIKeyListResponse {
  api_keys: APIKeyInfo[]
  total_count: number
}

export interface APIKeyValidateRequest {
  api_key_type: APIKeyType
  api_key: string
}

export interface APIKeyValidateResponse {
  is_valid: boolean
  message: string
  format_requirements?: string
}

export interface APIKeyStatus {
  user_id: string
  gemini_configured: boolean
  tavily_configured: boolean
  firecrawl_configured: boolean
  all_required_configured: boolean
  last_validation_check?: string
}

import { apiClient, APIRequestError } from '@/services/api/api-client'

type ErrorRecord = Record<string, unknown>

const isRecord = (value: unknown): value is ErrorRecord => (
  typeof value === 'object' && value !== null && !Array.isArray(value)
)

const isStringArray = (value: unknown): value is string[] => (
  Array.isArray(value) && value.every(item => typeof item === 'string')
)

const extractValidationErrors = (body: ErrorRecord): Record<string, string[]> | undefined => {
  const raw = body.validation_errors ?? body.validationErrors
  if (!isRecord(raw)) {
    return undefined
  }

  const entries = Object.entries(raw).reduce<Record<string, string[]>>((acc, [key, value]) => {
    if (isStringArray(value)) {
      acc[key] = value
    }
    return acc
  }, {})

  return Object.keys(entries).length > 0 ? entries : undefined
}

const extractErrorPayload = (body: unknown): {
  detail: string
  code?: string
  validationErrors?: Record<string, string[]>
} => {
  if (typeof body === 'string' && body.trim()) {
    return { detail: body }
  }

  if (!isRecord(body)) {
    return { detail: 'Unknown error' }
  }

  const detailCandidate = body.detail ?? body.message
  let detail = typeof detailCandidate === 'string' && detailCandidate.trim()
    ? detailCandidate
    : undefined

  if (!detail && (isRecord(body.detail) || Array.isArray(body.detail))) {
    try {
      detail = JSON.stringify(body.detail)
    } catch {
      detail = undefined
    }
  }

  return {
    detail: detail ?? 'Unknown error',
    code: typeof body.code === 'string' ? body.code : undefined,
    validationErrors: extractValidationErrors(body)
  }
}

const createAPIError = (error: unknown): APIError => {
  if (error instanceof APIError) {
    return error
  }

  if (error instanceof APIRequestError) {
    const payload = extractErrorPayload(error.body)
    return new APIError(
      error.message,
      error.status,
      payload.detail,
      payload.code,
      payload.validationErrors
    )
  }

  if (error instanceof Error) {
    return new APIError(error.message, 500, error.message)
  }

  return new APIError('Unknown error', 500, 'Unknown error')
}

export const apiKeyService = {
  // Create or update an API key
  async createOrUpdateAPIKey(request: APIKeyCreateRequest): Promise<APIKeyCreateResponse> {
    try {
      return await apiClient.post<APIKeyCreateResponse>('/api/v1/api-keys/', request)
    } catch (error) {
      throw createAPIError(error)
    }
  },

  // List all user's API keys
  async listAPIKeys(): Promise<APIKeyListResponse> {
    try {
      return await apiClient.get<APIKeyListResponse>('/api/v1/api-keys/')
    } catch (error) {
      throw createAPIError(error)
    }
  },

  // Update an existing API key
  async updateAPIKey(
    apiKeyType: APIKeyType,
    request: APIKeyUpdateRequest
  ): Promise<APIKeyUpdateResponse> {
    try {
      return await apiClient.put<APIKeyUpdateResponse>(`/api/v1/api-keys/${apiKeyType}`, request)
    } catch (error) {
      throw createAPIError(error)
    }
  },

  // Delete an API key
  async deleteAPIKey(apiKeyType: APIKeyType): Promise<APIKeyDeleteResponse> {
    try {
      return await apiClient.delete<APIKeyDeleteResponse>(`/api/v1/api-keys/${apiKeyType}`)
    } catch (error) {
      throw createAPIError(error)
    }
  },

  // Validate API key format
  async validateAPIKey(request: APIKeyValidateRequest): Promise<APIKeyValidateResponse> {
    try {
      return await apiClient.post<APIKeyValidateResponse>('/api/v1/api-keys/validate', request)
    } catch (error) {
      throw createAPIError(error)
    }
  },

  // Get API key status
  async getAPIKeyStatus(): Promise<APIKeyStatus> {
    try {
      return await apiClient.get<APIKeyStatus>('/api/v1/api-keys/status')
    } catch (error) {
      throw createAPIError(error)
    }
  },
}

// Utility functions
export function getAPIKeyDisplayName(type: APIKeyType): string {
  switch (type) {
    case APIKeyType.GEMINI:
      return 'Google Gemini'
    case APIKeyType.OPENAI:
      return 'OpenAI'
    case APIKeyType.TAVILY:
      return 'Tavily Search'
    case APIKeyType.FIRECRAWL:
      return 'Firecrawl'
    default:
      return type
  }
}

export function getAPIKeyDescription(type: APIKeyType): string {
  switch (type) {
    case APIKeyType.GEMINI:
      return 'Required for AI model access (primary agent and log analysis)'
    case APIKeyType.OPENAI:
      return 'Optional for OpenAI provider support in chat'
    case APIKeyType.TAVILY:
      return 'Optional for web search functionality (research agent)'
    case APIKeyType.FIRECRAWL:
      return 'Optional for web scraping (FeedMe system)'
    default:
      return ''
  }
}

export function getAPIKeyFormatRequirements(type: APIKeyType): string {
  switch (type) {
    case APIKeyType.GEMINI:
      return 'Should start with "AIza" and be 39 characters long'
    case APIKeyType.OPENAI:
      return 'Should start with "sk-" and be at least 20 characters'
    case APIKeyType.TAVILY:
      return 'Should be 32-40 alphanumeric characters'
    case APIKeyType.FIRECRAWL:
      return 'Should start with "fc-" and be at least 20 characters'
    default:
      return ''
  }
}

export function isAPIKeyRequired(type: APIKeyType): boolean {
  return type === APIKeyType.GEMINI
}
