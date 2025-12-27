'use client'

import React, { useCallback, useMemo, useRef, useState } from 'react'
import { Tags, X } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/ui/select'
import { WindowsIcon, MacOSIcon } from './PlatformIcons'
import { cn } from '@/shared/lib/utils'
import type { PlatformTag } from '@/shared/types/feedme'

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
  both: {
    label: 'Both',
    icon: null, // Will render both icons
    color: 'text-purple-600',
  },
} as const

type PlatformKey = keyof typeof PLATFORM_OPTIONS

function isPlatformTag(tag: string): tag is PlatformTag {
  return tag === 'windows' || tag === 'macos' || tag === 'both'
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
  const updateTimeoutRef = useRef<NodeJS.Timeout | null>(null)
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
    const timeoutId = updateTimeoutRef.current
    return () => {
      if (timeoutId) {
        clearTimeout(timeoutId)
      }
    }
  }, [])

  const selectedValue = currentPlatform || 'none'
  const selectedOption = currentPlatform ? PLATFORM_OPTIONS[currentPlatform as PlatformKey] : undefined
  const SelectedIcon = selectedOption?.icon

  // Helper to render platform icon(s)
  const renderPlatformIcon = (key: string, option: typeof PLATFORM_OPTIONS[PlatformKey], size = 'h-4 w-4') => {
    // No icon for 'both' - just use text label
    if (key === 'both') {
      return null
    }
    const OptionIcon = option.icon
    return OptionIcon ? (
      <OptionIcon className={cn(size, option.color)} aria-hidden="true" />
    ) : null
  }

  return (
    <div className={cn('relative', className)}>
      <Select
        value={selectedValue}
        onValueChange={handlePlatformChange}
        disabled={disabled || isUpdating}
      >
        <SelectTrigger
          className={cn(
            'w-[160px] h-9',
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
              ) : selectedOption ? (
                <div className="flex items-center gap-2">
                  {renderPlatformIcon(selectedValue, selectedOption)}
                  <span>{selectedOption.label}</span>
                </div>
              ) : null}
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
          {(Object.entries(PLATFORM_OPTIONS) as [PlatformKey, typeof PLATFORM_OPTIONS[PlatformKey]][]).map(([key, option]) => (
            <SelectItem key={key} value={key}>
              <div className="flex items-center gap-2">
                {renderPlatformIcon(key, option)}
                <span>{key === 'both' ? 'Both Windows and macOS' : option.label}</span>
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
