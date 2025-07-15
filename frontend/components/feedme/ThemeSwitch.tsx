/**
 * ThemeSwitch Component
 * 
 * Light/Dark mode toggle with:
 * - Smooth transition animations
 * - Persistent theme preference
 * - Integration with existing UIStore.theme
 * - System theme detection
 */

'use client'

import React, { useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu'
import { Sun, Moon, Monitor } from 'lucide-react'
import { useUITheme, useUIActions } from '@/lib/stores/ui-store'
import { cn } from '@/lib/utils'

interface ThemeSwitchProps {
  className?: string
  variant?: 'button' | 'dropdown'
  size?: 'sm' | 'default' | 'lg'
}

export function ThemeSwitch({ 
  className,
  variant = 'dropdown',
  size = 'sm'
}: ThemeSwitchProps) {
  const { theme } = useUITheme()
  const { setTheme } = useUIActions()

  // Get computed theme based on system preference
  const getComputedTheme = React.useCallback(() => {
    if (theme === 'system') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    }
    return theme
  }, [theme])

  const [computedTheme, setComputedTheme] = React.useState<'light' | 'dark'>(() => {
    if (typeof window === 'undefined') return 'light'
    return getComputedTheme()
  })

  // Update computed theme when theme changes or system preference changes
  useEffect(() => {
    const updateComputedTheme = () => {
      const newComputedTheme = getComputedTheme()
      setComputedTheme(newComputedTheme)
      
      // Apply theme class only as a side effect, not as primary state management
      const root = window.document.documentElement
      root.classList.remove('light', 'dark')
      root.classList.add(newComputedTheme)
    }

    updateComputedTheme()

    // Listen for system theme changes only when theme is 'system'
    if (theme === 'system') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
      mediaQuery.addEventListener('change', updateComputedTheme)
      return () => mediaQuery.removeEventListener('change', updateComputedTheme)
    }
  }, [theme, getComputedTheme])

  const themes = [
    { value: 'light', label: 'Light', icon: Sun },
    { value: 'dark', label: 'Dark', icon: Moon },
    { value: 'system', label: 'System', icon: Monitor }
  ] as const

  const currentThemeInfo = themes.find(t => t.value === theme) || themes[0]
  const CurrentIcon = currentThemeInfo.icon

  if (variant === 'button') {
    // Simple toggle between light/dark (no system option)
    const toggleTheme = () => {
      setTheme(theme === 'dark' ? 'light' : 'dark')
    }

    return (
      <Button
        variant="ghost"
        size={size}
        onClick={toggleTheme}
        className={cn("h-9 w-9 px-0", className)}
        title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
        data-testid="theme-toggle"
      >
        <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
        <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
        <span className="sr-only">Toggle theme</span>
      </Button>
    )
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button 
          variant="ghost" 
          size={size}
          className={cn("h-9 w-9 px-0", className)}
          title={`Current theme: ${currentThemeInfo.label}`}
          data-testid="theme-dropdown"
        >
          <CurrentIcon className="h-4 w-4" />
          <span className="sr-only">Toggle theme</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-32">
        {themes.map((themeOption) => {
          const Icon = themeOption.icon
          return (
            <DropdownMenuItem
              key={themeOption.value}
              onClick={() => setTheme(themeOption.value)}
              className={cn(
                "flex items-center gap-2 cursor-pointer",
                theme === themeOption.value && "bg-accent text-accent-foreground"
              )}
              data-testid={`theme-option-${themeOption.value}`}
            >
              <Icon className="h-4 w-4" />
              {themeOption.label}
            </DropdownMenuItem>
          )
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}