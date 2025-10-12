// Helper function for case-insensitive boolean environment variable parsing
const parseEnvBoolean = (value: string | undefined): boolean => {
  return value?.toLowerCase().trim() === 'true'
}

// Validate and sanitize base URL to prevent invalid URLs
const getValidBaseUrl = (): string => {
  const baseUrl = process.env.NEXT_PUBLIC_BASE_URL
  
  // Return default for undefined or invalid URLs
  if (!baseUrl || baseUrl === 'undefined' || baseUrl.trim() === '') {
    // Use window.location.origin in browser, fallback for server-side rendering
    if (typeof window !== 'undefined') {
      return window.location.origin
    }
    return 'http://localhost:3000' // Fallback for development
  }
  
  // Ensure URL has protocol
  if (!baseUrl.startsWith('http://') && !baseUrl.startsWith('https://')) {
    return `https://${baseUrl}`
  }
  
  return baseUrl
}

// Generate default redirect URI with validated base URL
const getDefaultRedirectUri = (): string => {
  return `${getValidBaseUrl()}/auth/callback`
}

// OAuth provider configuration interface
interface OAuthProviderConfig {
  readonly clientId: string
  readonly redirectUri: string
  readonly scope: string
  readonly enabled: boolean
}

// OAuth configuration interface
interface OAuthConfig {
  readonly google: OAuthProviderConfig
  readonly github: OAuthProviderConfig
}

// Global OAuth enable flag
const isOAuthGloballyEnabled = parseEnvBoolean(process.env.NEXT_PUBLIC_ENABLE_OAUTH)

// Debug logging
if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
  console.log('OAuth Debug:', {
    NEXT_PUBLIC_ENABLE_OAUTH: process.env.NEXT_PUBLIC_ENABLE_OAUTH,
    isOAuthGloballyEnabled,
    GOOGLE_CLIENT_ID: process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID,
    GITHUB_CLIENT_ID: process.env.NEXT_PUBLIC_GITHUB_CLIENT_ID,
    hasGoogleId: !!process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID,
    hasGithubId: !!process.env.NEXT_PUBLIC_GITHUB_CLIENT_ID
  })
}

export const oauthConfig: OAuthConfig = Object.freeze({
  google: Object.freeze({
    clientId: process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || '',
    redirectUri: process.env.NEXT_PUBLIC_AUTH_REDIRECT_URL || getDefaultRedirectUri(),
    scope: 'openid email profile',
    enabled: isOAuthGloballyEnabled && !!process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID
  }),
  github: Object.freeze({
    clientId: process.env.NEXT_PUBLIC_GITHUB_CLIENT_ID || '',
    redirectUri: process.env.NEXT_PUBLIC_AUTH_REDIRECT_URL || getDefaultRedirectUri(),
    scope: 'user:email',
    enabled: isOAuthGloballyEnabled && !!process.env.NEXT_PUBLIC_GITHUB_CLIENT_ID
  })
})

export const isOAuthEnabled = isOAuthGloballyEnabled
export const isDebugAuthEnabled = parseEnvBoolean(process.env.NEXT_PUBLIC_ENABLE_DEBUG_AUTH)