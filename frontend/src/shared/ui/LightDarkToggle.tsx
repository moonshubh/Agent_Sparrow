"use client"

import React, { useState, useEffect } from 'react'
import { useTheme } from 'next-themes'
import { Switch } from '@/shared/ui/switch'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/shared/ui/tooltip'
import { SunIcon, MoonIcon } from 'lucide-react'
import { cn } from '@/shared/lib/utils'

export function LightDarkToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  
  // Ensure component is only rendered on client after hydration
  useEffect(() => {
    setMounted(true)
  }, [])

  // Use resolvedTheme for consistency, fallback to light for SSR
  const isDark = mounted ? resolvedTheme === 'dark' : false
  
  const handleToggle = (checked: boolean) => {
    setTheme(checked ? 'dark' : 'light')
  }

  // Don't render until mounted to prevent hydration mismatch
  if (!mounted) {
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
                checked={false}
                onCheckedChange={() => {}}
                className="w-10 h-[22px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
                aria-label="Toggle between light and dark theme"
                disabled
              />
              {/* Icon overlay - show moon (light mode) during loading */}
              <div className={cn(
                "absolute inset-0 flex items-center justify-center pointer-events-none",
                "transition-all duration-200"
              )}>
                <MoonIcon className="w-3 h-3 text-accent-foreground mr-2 opacity-50" />
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
            {/* Icon overlay - using CSS visibility to avoid DOM changes */}
            <div className={cn(
              "absolute inset-0 flex items-center justify-center pointer-events-none",
              "transition-all duration-200"
            )}>
              <SunIcon 
                className={cn(
                  "w-3 h-3 text-accent-foreground ml-2 absolute",
                  isDark ? "opacity-100" : "opacity-0"
                )} 
              />
              <MoonIcon 
                className={cn(
                  "w-3 h-3 text-accent-foreground mr-2 absolute",
                  isDark ? "opacity-0" : "opacity-100"
                )} 
              />
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