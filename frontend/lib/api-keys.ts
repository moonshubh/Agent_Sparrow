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

import { getApiUrl, logEnvironment } from '@/lib/utils/environment'

// API client functions
// Get API base URL from environment variable with fallback to default
const getAPIBaseURL = (): string => {
  const apiUrl = getApiUrl()
  
  // Debug logging
  if (typeof window !== 'undefined') {
    console.log('🔍 API Keys Module - Environment Check:', {
      apiUrl,
      NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
      NODE_ENV: process.env.NODE_ENV,
      willUse: apiUrl ? `${apiUrl}/api/v1` : '/api/v1'
    })
  }
  
  return apiUrl ? `${apiUrl}/api/v1` : '/api/v1'
}

const API_BASE = getAPIBaseURL()

// Log environment on module load
if (typeof window !== 'undefined') {
  logEnvironment()
}

// Secure token management utilities
class SecureTokenManager {
  private static readonly TOKEN_KEY = 'mb_sparrow_token'
  private static readonly EXPIRY_KEY = 'mb_sparrow_token_expiry'
  
  static setToken(token: string, expiresIn: number = 3600): void {
    try {
      const expiryTime = Date.now() + (expiresIn * 1000)
      sessionStorage.setItem(this.TOKEN_KEY, token) // Use sessionStorage instead of localStorage
      sessionStorage.setItem(this.EXPIRY_KEY, expiryTime.toString())
    } catch (error) {
      console.warn('Failed to store authentication token:', error)
    }
  }
  
  static getToken(): string | null {
    try {
      const token = sessionStorage.getItem(this.TOKEN_KEY)
      const expiry = sessionStorage.getItem(this.EXPIRY_KEY)
      
      if (!token || !expiry) {
        return null
      }
      
      // Check if token is expired
      if (Date.now() > parseInt(expiry)) {
        this.clearToken()
        return null
      }
      
      return token
    } catch (error) {
      console.warn('Failed to retrieve authentication token:', error)
      return null
    }
  }
  
  static clearToken(): void {
    try {
      sessionStorage.removeItem(this.TOKEN_KEY)
      sessionStorage.removeItem(this.EXPIRY_KEY)
    } catch (error) {
      console.warn('Failed to clear authentication token:', error)
    }
  }
  
  static isTokenExpired(): boolean {
    try {
      const expiry = sessionStorage.getItem(this.EXPIRY_KEY)
      return !expiry || Date.now() > parseInt(expiry)
    } catch (error) {
      return true
    }
  }
}

async function apiRequest<T>(
  endpoint: string,
  options: RequestInit & { timeout?: number } = {}
): Promise<T> {
  const token = SecureTokenManager.getToken()
  
  // Extract timeout from options and remove it before passing to fetch
  const { timeout = 30000, ...fetchOptions } = options
  
  // Create AbortController for timeout handling
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeout)
  
  try {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...fetchOptions,
      signal: controller.signal,
      credentials: 'include', // Include cookies for httpOnly support
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` }),
        ...fetchOptions.headers,
      },
    })
    
    clearTimeout(timeoutId)

    if (!response.ok) {
      // Handle token expiration
      if (response.status === 401) {
        SecureTokenManager.clearToken()
        // Redirect to login or trigger re-authentication
        if (typeof window !== 'undefined') {
          window.location.href = '/login'
        }
      }
      
      let errorData: any
      try {
        errorData = await response.json()
      } catch {
        // If response is not JSON, create a basic error structure
        errorData = {
          detail: response.status >= 500 ? 'Server error' : 'Network error',
          message: `HTTP ${response.status}: ${response.statusText}`
        }
      }

      // Extract structured error information
      const detail = errorData.detail || errorData.message || `HTTP ${response.status}: ${response.statusText}`
      const code = errorData.code || errorData.error_code
      const validationErrors = errorData.validation_errors || errorData.errors
      
      throw new APIError(
        `API request failed with status ${response.status}`,
        response.status,
        detail,
        code,
        validationErrors
      )
    }

    return response.json()
    
  } catch (error) {
    clearTimeout(timeoutId)
    
    // Handle AbortError (timeout)
    if (error instanceof Error && error.name === 'AbortError') {
      throw new APIError(
        'Request timeout - server may be busy',
        408,
        'The request took too long to complete. Please try again.',
        'TIMEOUT'
      )
    }
    
    // Handle network errors
    if (error instanceof TypeError && 
        (error.message === 'Failed to fetch' || 
         error.message.includes('NetworkError') ||
         error.message.includes('fetch'))) {
      throw new APIError(
        'Network connection failed',
        0,
        'Unable to connect to the server. Please check your internet connection and try again.',
        'NETWORK_ERROR'
      )
    }
    
    // Re-throw APIError instances
    if (error instanceof APIError) {
      throw error
    }
    
    // Handle other errors
    throw new APIError(
      'Unexpected error occurred',
      500,
      error instanceof Error ? error.message : 'An unexpected error occurred',
      'UNKNOWN_ERROR'
    )
  }
}

export const apiKeyService = {
  // Create or update an API key
  async createOrUpdateAPIKey(request: APIKeyCreateRequest): Promise<APIKeyCreateResponse> {
    return apiRequest<APIKeyCreateResponse>('/api-keys/', {
      method: 'POST',
      body: JSON.stringify(request),
    })
  },

  // List all user's API keys
  async listAPIKeys(): Promise<APIKeyListResponse> {
    return apiRequest<APIKeyListResponse>('/api-keys/')
  },

  // Update an existing API key
  async updateAPIKey(
    apiKeyType: APIKeyType,
    request: APIKeyUpdateRequest
  ): Promise<APIKeyUpdateResponse> {
    return apiRequest<APIKeyUpdateResponse>(`/api-keys/${apiKeyType}`, {
      method: 'PUT',
      body: JSON.stringify(request),
    })
  },

  // Delete an API key
  async deleteAPIKey(apiKeyType: APIKeyType): Promise<APIKeyDeleteResponse> {
    return apiRequest<APIKeyDeleteResponse>(`/api-keys/${apiKeyType}`, {
      method: 'DELETE',
    })
  },

  // Validate API key format
  async validateAPIKey(request: APIKeyValidateRequest): Promise<APIKeyValidateResponse> {
    return apiRequest<APIKeyValidateResponse>('/api-keys/validate', {
      method: 'POST',
      body: JSON.stringify(request),
    })
  },

  // Get API key status
  async getAPIKeyStatus(): Promise<APIKeyStatus> {
    return apiRequest<APIKeyStatus>('/api-keys/status')
  },
}

// Utility functions
export function getAPIKeyDisplayName(type: APIKeyType): string {
  switch (type) {
    case APIKeyType.GEMINI:
      return 'Google Gemini'
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

// Export the secure token manager for use in other components
export { SecureTokenManager }