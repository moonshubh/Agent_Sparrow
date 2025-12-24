'use client'

import { useEffect, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { GoogleLoginForm } from '@/features/auth/components/GoogleLoginForm'
import { Loader2 } from 'lucide-react'
import Image from 'next/image'

function LoginInner() {
  const searchParams = useSearchParams()
  const returnUrl = searchParams.get('returnUrl')

  useEffect(() => {
    // Store return URL in session storage for use after OAuth callback
    if (returnUrl) {
      sessionStorage.setItem('authReturnUrl', returnUrl)
    }
  }, [returnUrl])

  return (
    <div className="grid min-h-screen w-full lg:grid-cols-2">
      {/* Left Column - Login Form */}
      <div className="flex flex-col items-center justify-center p-6 lg:p-8">
        <div className="w-full max-w-md space-y-6">
          <div className="flex flex-col items-center gap-2 text-center">
            <h2 className="text-3xl font-bold tracking-tight">Agent Sparrow</h2>
            <p className="text-balance text-muted-foreground">
              Welcome back! Please sign in to continue.
            </p>
          </div>
          <GoogleLoginForm />
        </div>
      </div>

      {/* Right Column - Logo Image */}
      <div className="hidden bg-muted lg:flex lg:items-center lg:justify-center lg:p-8">
        <div className="flex flex-col items-center justify-center space-y-4">
          <div className="relative w-full max-w-md aspect-square">
            <Image
              src="/Sparrow_login_logo.png"
              alt="Agent Sparrow"
              fill
              className="object-contain"
              priority
            />
          </div>
        </div>
      </div>
    </div>
  )
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-accent" />
      </div>
    }>
      <LoginInner />
    </Suspense>
  )
}