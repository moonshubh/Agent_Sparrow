"use client"

import React, { useState } from 'react'
import { LightDarkToggle } from '@/shared/ui/LightDarkToggle'
import { FeedMeButton } from '@/shared/ui/FeedMeButton'
import { SettingsButtonV2 } from '@/shared/ui/SettingsButtonV2'

import { useAuth } from '@/features/auth/hooks/useAuth'
import { UserMenu } from '@/features/auth/components/UserMenu'
import { Button } from '@/shared/ui/button'
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
      if (typeof window !== 'undefined') {
        try {
          await router.push('/login')
        } catch {
          window.location.href = '/login'
        }
      }
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
      setTimeout(() => setIsNavigating(false), 100)
    }
  }

  return (
    <header
      className="sticky top-0 z-30 flex h-14 items-center justify-between px-4 bg-[hsl(var(--brand-surface)/0.95)] backdrop-blur border-b border-border/30"
      role="banner"
    >
      <div className="flex items-center gap-2">
        <div className="h-10 w-10 overflow-hidden rounded-sm">
          <Image
            src="/Sparrow_logo_cropped.png"
            alt="Agent Sparrow"
            width={40}
            height={40}
            className="object-contain"
            priority
          />
        </div>
        <span className="text-base font-semibold text-accent">Agent Sparrow</span>
      </div>
      <div className="flex items-center gap-3">

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
