'use client'

import { useEffect } from 'react'
import { useSearchParams } from 'next/navigation'
import { LoginForm } from '@/components/auth/LoginForm'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden">
      {/* Animated Background */}
      <div className="absolute inset-0 bg-gradient-to-br from-blue-50 via-white to-blue-100 dark:from-gray-900 dark:via-gray-800 dark:to-blue-950">
        {/* Floating orbs with performance optimization */}
        <div 
          className="absolute top-1/4 left-1/4 h-64 w-64 rounded-full bg-accent/20 blur-3xl animate-float motion-reduce:animate-none" 
          style={{ willChange: 'transform' }}
        />
        <div 
          className="absolute top-3/4 right-1/4 h-48 w-48 rounded-full bg-blue-400/20 blur-2xl animate-float-delayed motion-reduce:animate-none" 
          style={{ willChange: 'transform' }}
        />
        <div 
          className="absolute top-1/2 left-3/4 h-32 w-32 rounded-full bg-purple-400/20 blur-xl animate-float-slow motion-reduce:animate-none" 
          style={{ willChange: 'transform' }}
        />
        
        {/* Grid pattern */}
        <div className="absolute inset-0 bg-grid-pattern opacity-5 dark:opacity-10" />
        
        {/* Gradient overlay */}
        <div className="absolute inset-0 bg-gradient-to-t from-white/90 via-transparent to-white/90 dark:from-gray-900/90 dark:via-transparent dark:to-gray-900/90" />
      </div>

      {/* Content */}
      <div className="relative z-10 w-full max-w-md space-y-8 px-4">
        {/* Logo and branding */}
        <div className="text-center space-y-6">
          <div className="mx-auto w-24 h-24 relative">
            <div className="absolute inset-0 rounded-full bg-accent/20 animate-pulse" />
            <div className="absolute inset-2 rounded-full bg-white dark:bg-gray-800 shadow-lg">
              <Image
                src="/agent-sparrow.png"
                alt="Agent Sparrow - AI-powered Mailbird support assistant logo"
                width={80}
                height={80}
                className="w-full h-full object-cover rounded-full p-2"
                priority
              />
            </div>
          </div>
          
          <div>
            <h1 className="text-4xl font-bold tracking-tight bg-gradient-to-r from-accent to-blue-600 bg-clip-text text-transparent">
              Agent Sparrow
            </h1>
            <p className="mt-3 text-lg text-muted-foreground">
              Your AI-powered Mailbird support assistant
            </p>
            <div className="mt-2 flex items-center justify-center space-x-2 text-sm text-muted-foreground">
              <div className="h-1 w-1 rounded-full bg-green-500 animate-pulse" />
              <span>Powered by advanced AI</span>
            </div>
          </div>
        </div>

        {/* Login Card */}
        <Card className="border-border/50 bg-card/80 backdrop-blur-xl shadow-2xl">
          <CardHeader className="space-y-1 text-center">
            <CardTitle className="text-2xl font-semibold">Welcome Back</CardTitle>
            <CardDescription className="text-base">
              Sign in to continue your support journey
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <LoginForm />
            
            {/* Features showcase */}
            <div className="pt-4 border-t border-border/50">
              <p className="text-xs text-center text-muted-foreground mb-3">
                What you&apos;ll get access to:
              </p>
              <div className="grid grid-cols-1 gap-2 text-xs">
                <div className="flex items-center space-x-2 text-muted-foreground">
                  <div className="h-1.5 w-1.5 rounded-full bg-accent" />
                  <span>Intelligent email troubleshooting</span>
                </div>
                <div className="flex items-center space-x-2 text-muted-foreground">
                  <div className="h-1.5 w-1.5 rounded-full bg-accent" />
                  <span>Advanced log analysis</span>
                </div>
                <div className="flex items-center space-x-2 text-muted-foreground">
                  <div className="h-1.5 w-1.5 rounded-full bg-accent" />
                  <span>Real-time web research</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Footer */}
        <div className="text-center space-y-2">
          <p className="text-xs text-muted-foreground">
            By signing in, you agree to our{' '}
            <a href="#" className="underline hover:text-accent transition-colors">
              Terms of Service
            </a>{' '}
            and{' '}
            <a href="#" className="underline hover:text-accent transition-colors">
              Privacy Policy
            </a>
          </p>
          <p className="text-xs text-muted-foreground">
            © {new Date().getFullYear()} MB-Sparrow. Crafted with ❤️ for Mailbird users.
          </p>
        </div>
      </div>
    </div>
  )
}