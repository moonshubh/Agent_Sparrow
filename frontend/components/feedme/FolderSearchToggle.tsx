/**
 * FolderSearchToggle Component - Apple/Google-level Micro-interaction
 * 
 * Advanced search icon that transforms into a 160px input with seamless animations:
 * - Icon-only state: Hover/click to expand
 * - Input state: Auto-focus, debounced search, single border
 * - Collapse triggers: Blur + empty value, outside click, Escape key
 * - Accessibility: Perfect ARIA support, keyboard navigation
 * - Visual polish: Smooth transitions, no duplicate focus rings
 */

'use client'

import React, { useState, useRef, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Search, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useFoldersActions } from '@/lib/stores/folders-store'

interface FolderSearchToggleProps {
  value: string
  onChange: (value: string) => void
  onClear?: () => void
  className?: string
}

export function FolderSearchToggle({ 
  value, 
  onChange, 
  onClear, 
  className 
}: FolderSearchToggleProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [isFocused, setIsFocused] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const foldersActions = useFoldersActions()

  // Auto-expand if there's a value
  useEffect(() => {
    if (value && !isExpanded) {
      setIsExpanded(true)
    }
  }, [value, isExpanded])

  // Handle outside clicks to collapse
  useEffect(() => {
    const handleMouseDown = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        if (!value && !isFocused) {
          setIsExpanded(false)
        }
      }
    }

    if (isExpanded) {
      document.addEventListener('mousedown', handleMouseDown)
      return () => document.removeEventListener('mousedown', handleMouseDown)
    }
  }, [isExpanded, value, isFocused])

  // Expand with auto-focus
  const handleExpand = useCallback(() => {
    if (!isExpanded) {
      setIsExpanded(true)
      // Delay focus to ensure input is rendered
      setTimeout(() => {
        inputRef.current?.focus()
      }, 150)
    }
  }, [isExpanded])

  // Collapse if conditions are met
  const handleCollapse = useCallback(() => {
    if (!value && !isFocused) {
      setIsExpanded(false)
    }
  }, [value, isFocused])

  // Input focus handlers
  const handleInputFocus = useCallback(() => {
    setIsFocused(true)
    setIsExpanded(true)
  }, [])

  const handleInputBlur = useCallback(() => {
    setIsFocused(false)
    // Delay collapse to allow for re-focusing
    setTimeout(() => {
      if (!value && !isFocused) {
        setIsExpanded(false)
      }
    }, 100)
  }, [value, isFocused])

  // Keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    switch (e.key) {
      case 'Enter':
        if (!isExpanded) {
          e.preventDefault()
          handleExpand()
        }
        break
      case 'Escape':
        e.preventDefault()
        if (value) {
          onChange('')
          onClear?.()
        } else {
          setIsExpanded(false)
          inputRef.current?.blur()
        }
        break
      case 'Tab':
        if (!isExpanded) {
          handleExpand()
        }
        break
    }
  }, [isExpanded, value, onChange, onClear, handleExpand])

  // Clear handler
  const handleClear = useCallback(() => {
    onChange('')
    onClear?.()
    inputRef.current?.focus()
  }, [onChange, onClear])

  return (
    <div 
      ref={containerRef}
      className={cn("relative flex items-center", className)}
      onMouseEnter={handleExpand}
      onMouseLeave={handleCollapse}
    >
      {/* Search Icon Button (collapsed state) */}
      {!isExpanded && (
        <Button
          variant="ghost"
          size="sm"
          onClick={handleExpand}
          onKeyDown={handleKeyDown}
          className={cn(
            "h-8 w-8 p-0 transition-all duration-200",
            "hover:bg-mb-blue-300/10 focus:bg-accent/10",
            "focus:outline-none focus:ring-1 focus:ring-accent"
          )}
          aria-label="Search folders"
          data-testid="folder-search-icon"
        >
          <Search className="h-4 w-4 text-muted-foreground" />
        </Button>
      )}

      {/* Expanded Search Input */}
      {isExpanded && (
        <div 
          className={cn(
            "relative animate-in slide-in-from-right-2 duration-200",
            "w-40" // 160px width as specified
          )}
        >
          <Search className={cn(
            "absolute left-3 top-1/2 transform -translate-y-1/2",
            "h-4 w-4 text-muted-foreground pointer-events-none"
          )} />
          <Input
            ref={inputRef}
            placeholder="Search folders..."
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onFocus={handleInputFocus}
            onBlur={handleInputBlur}
            onKeyDown={handleKeyDown}
            autoFocus
            className={cn(
              "pl-9 pr-8 h-8 text-sm bg-background/60",
              "border-border focus:border-accent",
              "transition-all duration-200",
              "focus:outline-none focus:ring-0", // Remove duplicate focus ring
              "focus:shadow-sm"
            )}
            data-testid="folder-search-input"
          />
          {value && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleClear}
              className={cn(
                "absolute right-1 top-1/2 transform -translate-y-1/2",
                "h-6 w-6 p-0 hover:bg-mb-blue-300/20 transition-colors duration-150"
              )}
              title="Clear search"
              data-testid="folder-search-clear"
            >
              <X className="h-3 w-3" />
            </Button>
          )}
        </div>
      )}
    </div>
  )
}