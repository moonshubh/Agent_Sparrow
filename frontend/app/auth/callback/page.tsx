'use client'

import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { User } from '@supabase/supabase-js'

// Helper function to validate OAuth state parameter
const validateOAuthState = (urlSearchParams: URLSearchParams): void => {
  const stateFromUrl = urlSearchParams.get('state')
  const storedState = sessionStorage.getItem('oauth_state')
  
  if (!stateFromUrl || !storedState) {
    throw new Error('Missing OAuth state parameter')
  }
  
  if (stateFromUrl !== storedState) {
    throw new Error('OAuth state parameter mismatch - potential CSRF attack')
  }
  
  // Clean up stored state
  sessionStorage.removeItem('oauth_state')
}

// Helper function to validate user data completeness
const validateUserData = (user: User): void => {
  if (!user.id) {
    throw new Error('User ID is missing from session')
  }
  
  if (!user.email) {
    throw new Error('User email is missing from session')
  }
  
  // Validate email format
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  if (!emailRegex.test(user.email)) {
    throw new Error('Invalid user email format')
  }
  
  // Check for required metadata
  if (!user.user_metadata && !user.app_metadata) {
    throw new Error('User metadata is missing from session')
  }
  
  // Ensure user has a valid created_at timestamp
  if (!user.created_at || isNaN(new Date(user.created_at).getTime())) {
    throw new Error('Invalid user creation timestamp')
  }
}

export default function AuthCallbackPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let redirectTimeoutId: NodeJS.Timeout | null = null

    const handleCallback = async () => {
      try {
        // Validate OAuth state parameter for CSRF protection
        validateOAuthState(searchParams)
        
        // Get the session from Supabase
        const { data: { session }, error } = await supabase.auth.getSession()

        if (error) {
          throw error
        }

        if (!session) {
          throw new Error('No session found after OAuth callback')
        }
        
        if (!session.user) {
          throw new Error('No user data found in session')
        }
        
        // Validate user data completeness
        validateUserData(session.user)

        // Get the return URL from session storage
        const returnUrl = sessionStorage.getItem('authReturnUrl')
        sessionStorage.removeItem('authReturnUrl')

        toast.success('Successfully logged in!')
        
        // Redirect to the original destination or home
        router.push(returnUrl ? decodeURIComponent(returnUrl) : '/')
      } catch (error: unknown) {
        // Enhanced error handling with specific error messages
        const errorMessage = error instanceof Error ? error.message : 'Authentication failed'
        console.error('Auth callback error:', errorMessage)
        
        // Set user-friendly error messages based on error type
        let displayMessage = 'Authentication failed. Please try again.'
        if (errorMessage.includes('CSRF')) {
          displayMessage = 'Security validation failed. Please start the login process again.'
        } else if (errorMessage.includes('missing') || errorMessage.includes('Invalid')) {
          displayMessage = 'Incomplete authentication data. Please try logging in again.'
        } else if (errorMessage.includes('state parameter')) {
          displayMessage = 'Authentication security check failed. Please try again.'
        }
        
        setError(errorMessage)
        toast.error(displayMessage)
        
        // Clean up any remaining session storage items
        sessionStorage.removeItem('oauth_state')
        sessionStorage.removeItem('authReturnUrl')
        
        // Configurable redirect delay with proper cleanup
        const REDIRECT_DELAY = 3000
        redirectTimeoutId = setTimeout(() => {
          router.push('/login')
        }, REDIRECT_DELAY)
      }
    }

    handleCallback()

    // Cleanup function to prevent memory leaks
    return () => {
      if (redirectTimeoutId) {
        clearTimeout(redirectTimeoutId)
      }
    }
  }, [router])

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-semibold text-destructive">Authentication Error</h1>
          <p className="mt-2 text-muted-foreground">{error}</p>
          <p className="mt-4 text-sm text-muted-foreground">Redirecting to login...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <Loader2 className="mx-auto h-8 w-8 animate-spin text-accent" />
        <h1 className="mt-4 text-2xl font-semibold">Completing sign in...</h1>
        <p className="mt-2 text-muted-foreground">Please wait while we log you in.</p>
      </div>
    </div>
  )
}