'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'

export default function AuthCallbackPage() {
  const router = useRouter()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const handleCallback = async () => {
      try {
        // Get the code from URL
        const { data: { session }, error } = await supabase.auth.getSession()

        if (error) {
          throw error
        }

        if (!session) {
          throw new Error('No session found after OAuth callback')
        }

        // Get the return URL from session storage
        const returnUrl = sessionStorage.getItem('authReturnUrl')
        sessionStorage.removeItem('authReturnUrl')

        toast.success('Successfully logged in!')
        
        // Redirect to the original destination or home
        router.push(returnUrl ? decodeURIComponent(returnUrl) : '/')
      } catch (error: any) {
        console.error('Auth callback error:', error)
        setError(error.message || 'Authentication failed')
        toast.error('Authentication failed. Please try again.')
        
        // Redirect to login after a delay
        setTimeout(() => {
          router.push('/login')
        }, 3000)
      }
    }

    handleCallback()
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