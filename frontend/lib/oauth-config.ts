export const oauthConfig = {
  google: {
    clientId: process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || '',
    redirectUri: process.env.NEXT_PUBLIC_AUTH_REDIRECT_URL || `${process.env.NEXT_PUBLIC_BASE_URL}/auth/callback`,
    scope: 'openid email profile',
    enabled: !!process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID
  },
  github: {
    clientId: process.env.NEXT_PUBLIC_GITHUB_CLIENT_ID || '',
    redirectUri: process.env.NEXT_PUBLIC_AUTH_REDIRECT_URL || `${process.env.NEXT_PUBLIC_BASE_URL}/auth/callback`,
    scope: 'user:email',
    enabled: !!process.env.NEXT_PUBLIC_GITHUB_CLIENT_ID
  }
}

export const isOAuthEnabled = process.env.NEXT_PUBLIC_ENABLE_OAUTH === 'true'
export const isDebugAuthEnabled = process.env.NEXT_PUBLIC_ENABLE_DEBUG_AUTH === 'true'