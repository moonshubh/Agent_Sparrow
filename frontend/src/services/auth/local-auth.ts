/**
 * Local Development Authentication Helper
 * Automatically generates and stores a local JWT token for development
 */

const defaultApiBaseUrl = 'http://localhost:8000'

const resolveApiBaseUrl = () => {
  const envUrl = process.env.NEXT_PUBLIC_API_URL
  if (envUrl && envUrl.trim().length > 0) {
    return envUrl
  }

  if (typeof window !== 'undefined') {
    try {
      const { protocol, hostname, port, origin } = window.location
      const normalizedPort = port || (protocol === 'https:' ? '443' : '80')
      const isLocalhost = hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '0.0.0.0'

      if (!isLocalhost) {
        // Deployed environment → assume same-origin API
        return origin
      }

      if (normalizedPort === '8000') {
        return origin
      }

      // Local dev frontend (usually 3000/3001) → use backend default
      return defaultApiBaseUrl
    } catch {
      return defaultApiBaseUrl
    }
  }

  return defaultApiBaseUrl
}

interface LocalAuthResponse {
  access_token: string
  refresh_token: string
  expires_in: number
  user: {
    id: string
    email: string
    full_name: string
    created_at: string
    last_sign_in_at: string
    metadata: any
  }
}

/**
 * Initialize local authentication for development
 * This will automatically create a local JWT token if in local auth bypass mode
 */
export async function initializeLocalAuth(): Promise<boolean> {
  const API_BASE_URL = resolveApiBaseUrl()
  // Only run in local auth bypass mode
  if (process.env.NEXT_PUBLIC_LOCAL_AUTH_BYPASS !== 'true') {
    return false
  }

  try {
    // Check if we already have a valid token
    const existingToken = localStorage.getItem('access_token')
    if (existingToken) {
      try {
        // Validate the existing token (server accepts JSON or query param)
        const validateResponse = await fetch(`${API_BASE_URL}/api/v1/auth/local-validate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: existingToken }),
        })

        if (validateResponse.ok) {
          const validation = await validateResponse.json()
          if (validation.valid) {
            console.log('✅ Existing local auth token is valid')
            return true
          }
        }
      } catch (e) {
        // swallow and fall through to re-signin
      }
      // Token invalid or validation failed → clear and reissue
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('user')
    }

    // Generate a new local auth token
    console.log('🔐 Initializing local authentication...')
    
    const response = await fetch(`${API_BASE_URL}/api/v1/auth/local-signin`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      mode: 'cors',
      credentials: 'include',
      body: JSON.stringify({
        email: 'dev@localhost.com',
        password: 'dev',
      }),
    })

    if (!response.ok) {
      console.error('Failed to initialize local auth:', response.statusText)
      return false
    }

    const data: LocalAuthResponse = await response.json()
    
    // Store tokens in localStorage
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    localStorage.setItem('user', JSON.stringify(data.user))
    
    console.log('✅ Local authentication initialized successfully')
    console.log('👤 Logged in as:', data.user.email)
    
    return true
  } catch (error) {
    console.error('❌ Failed to initialize local auth:', error)
    return false
  }
}

/**
 * Get the current authentication token
 * In local mode, this will return the local dev token
 */
export function getAuthToken(): string | null {
  if (process.env.NEXT_PUBLIC_LOCAL_AUTH_BYPASS === 'true') {
    return localStorage.getItem('access_token')
  }
  
  // In production mode, get token from Supabase or other auth provider
  return null
}

/**
 * Add authorization header to fetch requests
 */
export function getAuthHeaders(): HeadersInit {
  const token = getAuthToken()
  
  if (token) {
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    }
  }
  
  return {
    'Content-Type': 'application/json',
  }
}

/**
 * Check if user is authenticated (for local dev mode)
 */
export function isAuthenticated(): boolean {
  if (process.env.NEXT_PUBLIC_LOCAL_AUTH_BYPASS === 'true') {
    return !!localStorage.getItem('access_token')
  }
  
  // In production, check Supabase auth
  return false
}
