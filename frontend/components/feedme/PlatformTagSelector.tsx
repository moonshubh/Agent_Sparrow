'use client'

import React, { useCallback, useMemo, useRef, useState } from 'react'
import { Tags, X } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { WindowsIcon, MacOSIcon } from './PlatformIcons'
import { cn } from '@/lib/utils'
import type { PlatformTag } from '@/types/feedme'

interface PlatformTagSelectorProps {
  conversationId: number
  currentTags: string[]
  onTagUpdate: (tags: string[]) => Promise<void>
  disabled?: boolean
  className?: string
}

const PLATFORM_OPTIONS = {
  windows: {
    label: 'Windows',
    icon: WindowsIcon,
    color: 'text-[#0078D4]',
  },
  macos: {
    label: 'macOS',
    icon: MacOSIcon,
    color: 'text-[#555555]',
  },
} as const

function isPlatformTag(tag: string): tag is PlatformTag {
  return tag === 'windows' || tag === 'macos'
}

export default function PlatformTagSelector({
  conversationId,
  currentTags,
  onTagUpdate,
  disabled = false,
  className,
}: PlatformTagSelectorProps) {
  const [isUpdating, setIsUpdating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const updateTimeoutRef = useRef<NodeJS.Timeout>()
  const lastUpdateRef = useRef<string>('')

  // Derive current platform from tags - single source of truth
  const currentPlatform = useMemo(() => {
    return currentTags.find(isPlatformTag) || ''
  }, [currentTags])

  // Debounced update function
  const handlePlatformChange = useCallback(
    async (value: string) => {
      if (isUpdating || disabled) return

      // Clear any pending updates
      if (updateTimeoutRef.current) {
        clearTimeout(updateTimeoutRef.current)
      }

      // Prevent duplicate updates
      if (value === lastUpdateRef.current) return
      lastUpdateRef.current = value

      setError(null)
      setIsUpdating(true)

      // Store previous state for rollback
      const previousTags = [...currentTags]

      try {
        // Remove any existing platform tags and add the new one
        const nonPlatformTags = currentTags.filter(tag => !isPlatformTag(tag))
        const newTags = value && value !== 'none'
          ? [...nonPlatformTags, value]
          : nonPlatformTags

        await onTagUpdate(newTags)
      } catch (err) {
        // Rollback on failure
        setError(err instanceof Error ? err.message : 'Failed to update tag')
        console.error('Failed to update platform tag:', err)

        // Revert the update by calling with previous tags
        try {
          await onTagUpdate(previousTags)
        } catch (revertErr) {
          console.error('Failed to revert tags:', revertErr)
        }
      } finally {
        setIsUpdating(false)
      }
    },
    [currentTags, onTagUpdate, disabled, isUpdating]
  )

  // Cleanup timeout on unmount
  React.useEffect(() => {
    return () => {
      if (updateTimeoutRef.current) {
        clearTimeout(updateTimeoutRef.current)
      }
    }
  }, [])

  const selectedValue = currentPlatform || 'none'

  return (
    <div className={cn('relative', className)}>
      <Select
        value={selectedValue}
        onValueChange={handlePlatformChange}
        disabled={disabled || isUpdating}
      >
        <SelectTrigger
          className={cn(
            'w-[140px] h-9',
            error && 'border-destructive',
            isUpdating && 'opacity-70'
          )}
          aria-label="Select platform tag"
          aria-describedby={error ? 'platform-tag-error' : undefined}
        >
          <div className="flex items-center gap-2">
            <Tags className="h-4 w-4" aria-hidden="true" />
            <SelectValue placeholder="Tags">
              {selectedValue === 'none' ? (
                <span className="text-muted-foreground">No tag</span>
              ) : (
                <div className="flex items-center gap-2">
                  {currentPlatform && PLATFORM_OPTIONS[currentPlatform] && (
                    <>
                      {React.createElement(PLATFORM_OPTIONS[currentPlatform].icon, {
                        className: cn('h-4 w-4', PLATFORM_OPTIONS[currentPlatform].color)
                      })}
                      <span>{PLATFORM_OPTIONS[currentPlatform].label}</span>
                    </>
                  )}
                </div>
              )}
            </SelectValue>
          </div>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="none">
            <div className="flex items-center gap-2">
              <X className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
              <span>Clear tag</span>
            </div>
          </SelectItem>
          {Object.entries(PLATFORM_OPTIONS).map(([key, option]) => (
            <SelectItem key={key} value={key}>
              <div className="flex items-center gap-2">
                {React.createElement(option.icon, {
                  className: cn('h-4 w-4', option.color),
                  'aria-hidden': true
                })}
                <span>{option.label}</span>
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {error && (
        <p id="platform-tag-error" className="text-xs text-destructive mt-1">
          {error}
        </p>
      )}
    </div>
  )
}