/**
 * Secure API Key Service - Frontend
 * This service NEVER exposes actual API keys to the frontend.
 * All API keys remain on the backend and are used server-side only.
 */

import { supabase } from '@/lib/supabase-browser'
import { getApiUrl } from '@/lib/utils/environment'
import { APIKeyType } from '@/lib/api-keys'

// Re-export APIKeyType for other components to use
export { APIKeyType }

interface UserAPIKeyStatus {
  api_key_type: APIKeyType
  is_configured: boolean
  is_active: boolean
  last_used?: string
  created_at?: string
}

interface APIKeyTestResult {
  success: boolean
  message: string
  provider?: string
}

interface UserAPIKeyMasked {
  api_key_type: APIKeyType
  masked_key: string
  is_active: boolean
}

/**
 * Check if user has API keys configured (WITHOUT exposing the actual keys)
 */
export async function checkUserAPIKeyStatus(
  authToken: string | null,
  keyType: APIKeyType
): Promise<UserAPIKeyStatus | null> {
  if (!authToken) return null

  try {
    const apiUrl = getApiUrl()
    const response = await fetch(`${apiUrl}/api/v1/api-keys/status/${keyType}`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      if (response.status === 404) {
        return {
          api_key_type: keyType,
          is_configured: false,
          is_active: false
        }
      }
      return null
    }

    const data = await response.json()
    return data.status
  } catch (error) {
    console.error('Failed to check API key status:', error)
    return null
  }
}

/**
 * List all API key statuses for the user (WITHOUT actual keys)
 */
export async function getUserAPIKeyStatuses(authToken: string): Promise<UserAPIKeyStatus[]> {
  try {
    const apiUrl = getApiUrl()
    const response = await fetch(`${apiUrl}/api/v1/api-keys/status`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      return []
    }

    const data = await response.json()
    return data.statuses || []
  } catch (error) {
    console.error('Error fetching API key statuses:', error)
    return []
  }
}

/**
 * Configure a new API key (sent directly to backend, never stored in frontend)
 */
export async function configureAPIKey(
  authToken: string,
  keyType: APIKeyType,
  apiKey: string,
  keyName?: string
): Promise<{ success: boolean; message: string }> {
  try {
    const apiUrl = getApiUrl()
    const response = await fetch(`${apiUrl}/api/v1/api-keys`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        api_key_type: keyType,
        api_key: apiKey,
        key_name: keyName
      })
    })

    const data = await response.json()

    if (!response.ok) {
      return { 
        success: false, 
        message: data.detail || 'Failed to configure API key' 
      }
    }

    return { 
      success: true, 
      message: 'API key configured successfully' 
    }
  } catch (error) {
    return { 
      success: false, 
      message: 'Network error while configuring API key' 
    }
  }
}

/**
 * Delete an API key configuration
 */
export async function deleteAPIKey(
  authToken: string,
  keyType: APIKeyType
): Promise<{ success: boolean; message: string }> {
  try {
    const apiUrl = getApiUrl()
    const response = await fetch(`${apiUrl}/api/v1/api-keys/${keyType}`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      const data = await response.json()
      return { 
        success: false, 
        message: data.detail || 'Failed to delete API key' 
      }
    }

    return { 
      success: true, 
      message: 'API key deleted successfully' 
    }
  } catch (error) {
    return { 
      success: false, 
      message: 'Network error while deleting API key' 
    }
  }
}

/**
 * Test API key connectivity (backend tests the key, frontend only gets result)
 */
export async function testAPIKeyConnectivity(
  authToken: string,
  keyType: APIKeyType
): Promise<APIKeyTestResult> {
  try {
    const apiUrl = getApiUrl()
    const response = await fetch(`${apiUrl}/api/v1/api-keys/test/${keyType}`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      const data = await response.json()
      return { 
        success: false, 
        message: data.detail || 'Test failed' 
      }
    }

    const data = await response.json()
    return { 
      success: data.success, 
      message: data.message,
      provider: data.provider 
    }
  } catch (error) {
    return { 
      success: false, 
      message: 'Network error during connectivity test' 
    }
  }
}

/**
 * Test API key connectivity with a provided key (without storing it).
 * The key is sent to the backend for a one-off validation.
 */
export async function testAPIKeyConnectivityWithKey(
  authToken: string,
  keyType: APIKeyType,
  apiKey: string
): Promise<{ success: boolean; message: string }> {
  try {
    const apiUrl = getApiUrl()
    const response = await fetch(`${apiUrl}/api/v1/api-keys/test`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        api_key_type: keyType,
        api_key: apiKey
      })
    })

    if (!response.ok) {
      return { success: false, message: 'Failed to test API key' }
    }

    const data = await response.json()
    return { success: data.success, message: data.message }
  } catch (error) {
    return { success: false, message: 'Network error while testing API key' }
  }
}

/**
 * Get masked user API keys (safe for frontend display)
 */
export async function getUserAPIKeys(authToken: string): Promise<UserAPIKeyMasked[]> {
  try {
    const apiUrl = getApiUrl()
    const response = await fetch(`${apiUrl}/api/v1/api-keys/`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      return []
    }

    const data = await response.json()
    return data.api_keys || []
  } catch (error) {
    console.error('Error fetching API keys:', error)
    return []
  }
}

/**
 * Client-side format validation for API keys (no secrets stored)
 */
export function validateAPIKeyFormat(keyType: APIKeyType, apiKey: string): boolean {
  if (!apiKey || apiKey.length < 10) return false

  switch (keyType) {
    case APIKeyType.GEMINI:
      return apiKey.length >= 30 && apiKey.length <= 50
    case APIKeyType.TAVILY:
      return /^[a-zA-Z0-9-_]{20,50}$/.test(apiKey)
    case APIKeyType.FIRECRAWL:
      return apiKey.length >= 20 && apiKey.length <= 100
    default:
      return apiKey.length >= 10
  }
}

/**
 * Check if the current request should use user's API key or server key
 * This is determined by the backend based on user's configuration
 */
export async function shouldUseUserAPIKey(
  authToken: string | null,
  keyType: APIKeyType
): Promise<boolean> {
  if (!authToken) return false

  const status = await checkUserAPIKeyStatus(authToken, keyType)
  return status?.is_configured && status?.is_active || false
}

/**
 * Clear any cached data (for logout)
 */
export function clearAPIKeyCache() {
  // No-op since we don't cache actual keys in frontend
  // This function exists for API compatibility
}
