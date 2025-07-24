'use client'

import React, { useState } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Loader2 } from 'lucide-react'
import { isOAuthEnabled, oauthConfig } from '@/lib/oauth-config'
import { toast } from 'sonner'

export const LoginForm: React.FC = () => {
  const { loginWithOAuth, isLoading: authLoading } = useAuth()
  const [isLoading, setIsLoading] = useState(false)
  const [loadingProvider, setLoadingProvider] = useState<'google' | 'github' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleOAuthLogin = async (provider: 'google' | 'github') => {
    if (!isOAuthEnabled) {
      toast.error('OAuth is not enabled. Please configure OAuth providers.')
      return
    }

    const config = oauthConfig[provider]
    if (!config.enabled) {
      toast.error(`${provider.charAt(0).toUpperCase() + provider.slice(1)} login is not configured.`)
      return
    }

    try {
      setIsLoading(true)
      setLoadingProvider(provider)
      setError(null)
      await loginWithOAuth(provider)
    } catch (error: any) {
      console.error(`${provider} login error:`, error)
      setError(error.message || `Failed to sign in with ${provider}`)
    } finally {
      setIsLoading(false)
      setLoadingProvider(null)
    }
  }

  const isButtonDisabled = authLoading || isLoading

  return (
    <div className="space-y-4">
      {/* Error display */}
      {error && (
        <div className="rounded-md bg-red-50 p-3 text-sm text-red-800 dark:bg-red-900/20 dark:text-red-200 border border-red-200 dark:border-red-800">
          {error}
        </div>
      )}

      <div className="space-y-3">
        <Button
          variant="outline"
          className="w-full h-12 text-base font-medium transition-all duration-200 hover:scale-[1.02] hover:shadow-lg active:scale-[0.98]"
          onClick={() => handleOAuthLogin('google')}
          disabled={isButtonDisabled || !oauthConfig.google.enabled}
        >
          {loadingProvider === 'google' ? (
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          ) : (
            <svg className="mr-2 h-5 w-5" viewBox="0 0 24 24">
              <path
                fill="currentColor"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="currentColor"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="currentColor"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="currentColor"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
          )}
          {loadingProvider === 'google' ? 'Connecting to Google...' : 'Continue with Google'}
        </Button>

        <Button
          variant="outline"
          className="w-full h-12 text-base font-medium transition-all duration-200 hover:scale-[1.02] hover:shadow-lg active:scale-[0.98]"
          onClick={() => handleOAuthLogin('github')}
          disabled={isButtonDisabled || !oauthConfig.github.enabled}
        >
          {loadingProvider === 'github' ? (
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          ) : (
            <svg className="mr-2 h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
            </svg>
          )}
          {loadingProvider === 'github' ? 'Connecting to GitHub...' : 'Continue with GitHub'}
        </Button>
      </div>

      {/* Configuration warnings */}
      {!isOAuthEnabled && (
        <div className="rounded-md bg-yellow-50 p-4 text-sm text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-200 border border-yellow-200 dark:border-yellow-800">
          <div className="flex items-center space-x-2">
            <div className="h-4 w-4 rounded-full bg-yellow-500" />
            <span className="font-medium">OAuth Not Configured</span>
          </div>
          <p className="mt-1">OAuth authentication is not enabled. Please set up OAuth providers in your environment configuration.</p>
        </div>
      )}

      {isOAuthEnabled && !oauthConfig.google.enabled && !oauthConfig.github.enabled && (
        <div className="rounded-md bg-yellow-50 p-4 text-sm text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-200 border border-yellow-200 dark:border-yellow-800">
          <div className="flex items-center space-x-2">
            <div className="h-4 w-4 rounded-full bg-yellow-500" />
            <span className="font-medium">No Providers Available</span>
          </div>
          <p className="mt-1">No OAuth providers are configured. Please configure at least one OAuth provider.</p>
        </div>
      )}

      {/* Connection status indicator */}
      {isOAuthEnabled && (oauthConfig.google.enabled || oauthConfig.github.enabled) && (
        <div className="flex items-center justify-center text-xs text-muted-foreground space-x-2">
          <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
          <span>Secure OAuth connection ready</span>
        </div>
      )}
    </div>
  )
}