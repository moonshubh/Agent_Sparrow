"use client"

import React, { useState } from 'react'
import { LightDarkToggle } from '@/components/ui/LightDarkToggle'
import { FeedMeButton } from '@/components/ui/FeedMeButton'
import { SettingsButtonV2 } from '@/components/ui/SettingsButtonV2'
import { DailyUsageTracker } from '@/components/rate-limiting/DailyUsageTracker'
import { useAuth } from '@/hooks/useAuth'
import { UserMenu } from '@/components/auth/UserMenu'
import { Button } from '@/components/ui/button'
import { LogIn, Loader2 } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import Image from 'next/image'

export function Header() {
  const { user, isAuthenticated, logout } = useAuth()
  const router = useRouter()
  const [isNavigating, setIsNavigating] = useState(false)

  const handleLogin = async () => {
    try {
      setIsNavigating(true)
      
      // Attempt navigation to login page
      await router.push('/login')
    } catch (error) {
      // Handle navigation errors gracefully
      console.error('Navigation to login page failed:', error)
      
      // Show user-friendly error message
      toast.error('Unable to navigate to login page. Please try again.')
      
      // Optionally, try alternative navigation method
      if (typeof window !== 'undefined') {
        try {
          window.location.href = '/login'
        } catch (fallbackError) {
          console.error('Fallback navigation also failed:', fallbackError)
          toast.error('Navigation failed. Please refresh the page and try again.')
        }
      }
    } finally {
      // Reset loading state after a short delay to prevent flicker
      setTimeout(() => setIsNavigating(false), 100)
    }
  }

  return (
    <header 
      className="sticky top-0 z-30 flex h-14 items-center justify-between px-4 bg-background/70 backdrop-blur border-b border-border/30"
      role="banner"
    >
      <div className="flex items-center gap-2">
        <Image
          src="/agent-sparrow-logo.png"
          alt="Agent Sparrow"
          width={32}
          height={32}
          className="object-contain"
        />
        <span className="text-base font-semibold text-accent">Agent Sparrow</span>
      </div>
      <div className="flex items-center gap-3">
        <DailyUsageTracker />
        <FeedMeButton />
        <SettingsButtonV2 />
        <LightDarkToggle />
        
        {isAuthenticated && user ? (
          <UserMenu user={user} onLogout={logout} />
        ) : (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleLogin}
            disabled={isNavigating}
            className="gap-2"
            aria-label="Navigate to sign in page"
          >
            {isNavigating ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <LogIn className="h-4 w-4" />
            )}
            {isNavigating ? 'Loading...' : 'Sign In'}
          </Button>
        )}
      </div>
    </header>
  )
}
