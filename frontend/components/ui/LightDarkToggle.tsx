"use client"

import React from 'react'
import { useTheme } from 'next-themes'
import { Switch } from '@/components/ui/switch'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { SunIcon, MoonIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

export function LightDarkToggle() {
  const { theme, setTheme } = useTheme()
  const isDark = theme === 'dark'
  
  const handleToggle = (checked: boolean) => {
    setTheme(checked ? 'dark' : 'light')
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div 
            className="relative w-10 h-[22px]"
            aria-label="Toggle theme"
            role="button"
            tabIndex={0}
          >
            <Switch 
              checked={isDark}
              onCheckedChange={handleToggle}
              className="w-10 h-[22px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
              aria-label="Toggle between light and dark theme"
            />
            {/* Icon overlay */}
            <div className={cn(
              "absolute inset-0 flex items-center justify-center pointer-events-none",
              "transition-all duration-200"
            )}>
              {isDark ? (
                <SunIcon className="w-3 h-3 text-accent-foreground ml-2" />
              ) : (
                <MoonIcon className="w-3 h-3 text-accent-foreground mr-2" />
              )}
            </div>
          </div>
        </TooltipTrigger>
        <TooltipContent>
          <p>Toggle theme</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}