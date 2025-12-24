'use client'

import React, { useState } from 'react'
import { useAuth } from '@/features/auth/hooks/useAuth'
import { isOAuthEnabled, oauthConfig } from '@/services/auth/oauth-config'
import { toast } from 'sonner'
import { Button } from '@/shared/ui/button'
import { Loader2 } from 'lucide-react'
import { cn } from '@/shared/lib/utils'

// Google icon component
const GoogleIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg 
    className={className} 
    viewBox="0 0 24 24"
    role="img"
    aria-label="Google logo"
  >
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
)

// Helper function to create user-friendly error messages
const getErrorMessage = (error: unknown): string => {
  if (error instanceof Error) {
    // Handle specific OAuth error patterns
    if (error.message.includes('popup_closed_by_user')) {
      return 'Google login was cancelled. Please try again.'
    }
    if (error.message.includes('unauthorized_client')) {
      return 'Google login is not properly configured. Please contact support.'
    }
    if (error.message.includes('access_denied')) {
      return 'Access denied by Google. Please check your permissions and try again.'
    }
    if (error.message.includes('network')) {
      return 'Network error occurred. Please check your connection and try again.'
    }
    // Return the original message for other errors
    return error.message
  }
  
  // Fallback for unknown error types
  return 'Failed to sign in with Google. Please try again.'
}

interface GoogleLoginFormProps {
  className?: string
}

export const GoogleLoginForm: React.FC<GoogleLoginFormProps> = ({ className }) => {
  const { loginWithOAuth, isLoading: authLoading } = useAuth()
  const [isLoading, setIsLoading] = useState(false)

  const handleGoogleLogin = async () => {
    // Pre-flight checks with user-friendly messages
    if (!isOAuthEnabled) {
      const message = 'OAuth authentication is not enabled. Please configure OAuth providers.'
      toast.error(message)
      return
    }

    const config = oauthConfig.google
    if (!config.enabled) {
      const message = 'Google login is not configured. Please contact your administrator.'
      toast.error(message)
      return
    }

    try {
      setIsLoading(true)
      await loginWithOAuth('google')
      
      // Success feedback (loginWithOAuth handles redirect, so this may not be reached)
      toast.success('Successfully connected to Google')
    } catch (error: unknown) {
      const errorMessage = getErrorMessage(error)
      
      // Log error with conditional detail level
      if (process.env.NODE_ENV === 'development') {
        console.error('Google login error:', error)
      } else {
        console.error(errorMessage)
      }
      
      // Show toast notification
      toast.error(errorMessage)
    } finally {
      setIsLoading(false)
    }
  }

  const isButtonDisabled = authLoading || isLoading

  return (
    <div className={cn("flex flex-col gap-6", className)}>
      <div className="flex flex-col items-center gap-2 text-center">
        <h1 className="text-2xl font-bold">Login to your account</h1>
        <p className="text-balance text-sm text-muted-foreground">
          Sign in with your Google account to continue
        </p>
      </div>
      <div className="grid gap-6">
        <Button
          type="button"
          variant="outline"
          className={cn(
            'w-full h-12 text-base font-medium transition-all duration-200',
            'hover:scale-[1.02] hover:shadow-lg active:scale-[0.98]'
          )}
          onClick={handleGoogleLogin}
          disabled={isButtonDisabled || !oauthConfig.google.enabled}
          aria-label="Login with Google"
        >
          {isLoading || authLoading ? (
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          ) : (
            <GoogleIcon className="mr-2 h-5 w-5" />
          )}
          {isLoading || authLoading ? 'Connecting to Google...' : 'Login with Google'}
        </Button>
      </div>
      {!isOAuthEnabled && (
        <div className="text-center text-sm text-destructive">
          OAuth authentication is not enabled. Please set up OAuth providers in your environment configuration.
        </div>
      )}
      {isOAuthEnabled && !oauthConfig.google.enabled && (
        <div className="text-center text-sm text-destructive">
          Google login is not configured. Please contact your administrator.
        </div>
      )}
    </div>
  )
}
