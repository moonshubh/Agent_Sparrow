'use client'

import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from 'sonner'
import { AlertCircle, LogIn } from 'lucide-react'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export const LocalDevLoginForm: React.FC = () => {
  const router = useRouter()
  const [email, setEmail] = useState('dev@localhost.com')
  const [password, setPassword] = useState('dev')
  const [isLoading, setIsLoading] = useState(false)

  const handleLocalLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    
    setIsLoading(true)
    
    try {
      // Call local auth endpoint
      const response = await fetch(`${API_BASE_URL}/api/v1/auth/local-signin`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Local authentication failed')
      }

      const data = await response.json()
      
      // Store tokens in localStorage (for development only)
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      localStorage.setItem('user', JSON.stringify(data.user))
      
      // Show success message
      toast.success('Successfully logged in with local auth!')
      
      // Redirect to main app
      const returnUrl = sessionStorage.getItem('authReturnUrl') || '/chat'
      sessionStorage.removeItem('authReturnUrl')
      router.push(returnUrl)
      
    } catch (error) {
      console.error('Local login error:', error)
      toast.error(error instanceof Error ? error.message : 'Failed to login')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* Warning banner */}
      <div className="rounded-lg border border-yellow-500 bg-yellow-50 dark:bg-yellow-950/20 p-4">
        <div className="flex items-start space-x-2">
          <AlertCircle className="h-5 w-5 text-yellow-600 dark:text-yellow-500 mt-0.5" />
          <div className="text-sm">
            <p className="font-semibold text-yellow-800 dark:text-yellow-400">
              Local Development Mode
            </p>
            <p className="text-yellow-700 dark:text-yellow-500 mt-1">
              OAuth is bypassed for local testing. This mode should never be used in production.
            </p>
          </div>
        </div>
      </div>

      {/* Login form */}
      <form onSubmit={handleLocalLogin} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="dev@localhost.com"
            disabled={isLoading}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="dev"
            disabled={isLoading}
          />
        </div>

        <Button
          type="submit"
          className="w-full"
          disabled={isLoading}
        >
          {isLoading ? (
            <>
              <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
              Signing in...
            </>
          ) : (
            <>
              <LogIn className="mr-2 h-4 w-4" />
              Sign in (Local Dev)
            </>
          )}
        </Button>
      </form>

      {/* Quick login hint */}
      <div className="text-center text-xs text-muted-foreground">
        Default credentials: dev@localhost.com / dev
      </div>
    </div>
  )
}