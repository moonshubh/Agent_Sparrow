'use client'

import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { supabase } from '@/services/supabase'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { User } from '@supabase/supabase-js'

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
        // Supabase client will automatically handle the OAuth callback
        // when detectSessionInUrl is true (which is the default)
        
        // Wait a moment for Supabase to process the callback
        await new Promise(resolve => setTimeout(resolve, 1500))
        
        // Get the session after Supabase has processed the callback
        const { data: { session }, error } = await supabase.auth.getSession()

        console.log('Auth callback - session check:', { session: !!session, error })

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

        console.log('Auth callback - user validated:', session.user.email)

        // Enforce allowed email domain client-side for better UX (server enforces too)
        const allowedDomain = (process.env.NEXT_PUBLIC_ALLOWED_EMAIL_DOMAIN || 'getmailbird.com').trim().toLowerCase()
        const userDomain = (session.user.email || '').split('@').pop()?.toLowerCase()
        if (!userDomain || userDomain !== allowedDomain) {
          await supabase.auth.signOut()
          throw new Error('Your account is not authorized for this application')
        }

        // Get the return URL from session storage
        const returnUrl = sessionStorage.getItem('authReturnUrl')
        sessionStorage.removeItem('authReturnUrl')

        console.log('Auth callback - redirecting to:', returnUrl || '/')

        toast.success('Successfully logged in!')
        
        // Force a hard navigation to ensure middleware runs
        window.location.href = returnUrl ? decodeURIComponent(returnUrl) : '/'
      } catch (error: unknown) {
        // Enhanced error handling with specific error messages
        const errorMessage = error instanceof Error ? error.message : 'Authentication failed'
        console.error('Auth callback error:', errorMessage)
        
        // Set user-friendly error messages based on error type
        let displayMessage = 'Authentication failed. Please try again.'
        if (errorMessage.includes('code verifier')) {
          displayMessage = 'Authentication session expired. Please try logging in again.'
        } else if (errorMessage.includes('missing') || errorMessage.includes('Invalid')) {
          displayMessage = 'Incomplete authentication data. Please try logging in again.'
        }
        
        setError(errorMessage)
        toast.error(displayMessage)
        
        // Clean up any remaining session storage items
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
