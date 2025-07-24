"use client"

import React from 'react'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { LightDarkToggle } from '@/components/ui/LightDarkToggle'
import { FeedMeButton } from '@/components/ui/FeedMeButton'
// import { SettingsButton } from '@/components/ui/SettingsButton' // Removed - API Keys moved to user menu
import { RateLimitDropdown } from '@/components/rate-limiting'
import { useAuth } from '@/hooks/useAuth'
import { UserMenu } from '@/components/auth/UserMenu'
import { Button } from '@/components/ui/button'
import { LogIn } from 'lucide-react'
import { useRouter } from 'next/navigation'

export function Header() {
  const { user, isAuthenticated, logout } = useAuth()
  const router = useRouter()

  const handleLogin = () => {
    router.push('/login')
  }

  return (
    <header 
      className="sticky top-0 z-30 flex h-14 items-center justify-between px-4 bg-background/70 backdrop-blur border-b border-border/30"
      role="banner"
    >
      <div className="flex items-center gap-2 text-base font-semibold text-accent">
        <span>MB-Sparrow</span>
      </div>
      <div className="flex items-center gap-3">
        <RateLimitDropdown 
          autoUpdate={true}
          updateInterval={15000}
        />
        <FeedMeButton />
        <LightDarkToggle />
        
        {isAuthenticated && user ? (
          <UserMenu user={user} onLogout={logout} />
        ) : (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleLogin}
            className="gap-2"
          >
            <LogIn className="h-4 w-4" />
            Sign In
          </Button>
        )}
      </div>
    </header>
  )
}