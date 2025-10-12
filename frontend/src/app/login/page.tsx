'use client'

import { useEffect } from 'react'
import { useSearchParams } from 'next/navigation'
import { LoginForm } from '@/features/auth/components/LoginForm'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/ui/card'
import Image from 'next/image'

export default function LoginPage() {
  const searchParams = useSearchParams()
  const returnUrl = searchParams.get('returnUrl')

  useEffect(() => {
    // Store return URL in session storage for use after OAuth callback
    if (returnUrl) {
      sessionStorage.setItem('authReturnUrl', returnUrl)
    }
  }, [returnUrl])

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-background">
      {/* Simple gradient background */}
      <div className="absolute inset-0 bg-gradient-to-br from-blue-50/20 to-blue-100/20 dark:from-blue-950/20 dark:to-gray-900" />
      
      {/* Content */}
      <div className="relative z-10 w-full max-w-md px-4">
        {/* Logo */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 w-20 h-20">
            <Image
              src="/agent-sparrow-logo.png"
              alt="Agent Sparrow"
              width={80}
              height={80}
              className="w-full h-full object-contain"
              priority
            />
          </div>
          <h1 className="text-2xl font-semibold">Agent Sparrow</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Sign in to continue
          </p>
        </div>

        {/* Login Card */}
        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="text-center text-lg font-medium">Welcome</CardTitle>
          </CardHeader>
          <CardContent>
            <LoginForm />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}