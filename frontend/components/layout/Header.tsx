"use client"

import React from 'react'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { LightDarkToggle } from '@/components/ui/LightDarkToggle'
import { FeedMeButton } from '@/components/ui/FeedMeButton'
import { SettingsButton } from '@/components/ui/SettingsButton'
import { RateLimitDropdown } from '@/components/rate-limiting'

export function Header() {
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
        <SettingsButton />
        <LightDarkToggle />
      </div>
    </header>
  )
}