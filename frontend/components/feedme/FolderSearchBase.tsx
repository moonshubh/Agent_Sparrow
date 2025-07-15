/**
 * FolderSearchBase Component
 * 
 * Shared base component for folder search functionality.
 * Provides reusable search icon-to-input transition with configurable:
 * - Animation direction (left/right slide-in)
 * - Container styling
 * - Input width and styling
 * - Keyboard accessibility (Enter/Tab expand, Escape collapse)
 * - Auto-collapse on blur when empty
 */

'use client'

import React, { useState, useRef, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Search, X } from 'lucide-react'
import { cn } from '@/lib/utils'

interface FolderSearchBaseProps {
  value: string
  onChange: (value: string) => void
  onClear: () => void
  className?: string
  animationDirection?: 'left' | 'right'
  containerClassName?: string
  inputClassName?: string
  inputWidth?: string
  placeholder?: string
}

export function FolderSearchBase({ 
  value, 
  onChange, 
  onClear, 
  className,
  animationDirection = 'left',
  containerClassName,
  inputClassName,
  inputWidth = 'w-40',
  placeholder = 'Search folders...'
}: FolderSearchBaseProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [isFocused, setIsFocused] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Expand on hover or focus
  const handleExpand = () => {
    setIsExpanded(true)
    setTimeout(() => {
      inputRef.current?.focus()
    }, 150) // Wait for transition
  }

  // Collapse if empty and not focused
  const handleCollapse = () => {
    if (!value && !isFocused) {
      setIsExpanded(false)
    }
  }

  // Handle input focus/blur
  const handleInputFocus = () => {
    setIsFocused(true)
    setIsExpanded(true)
  }

  const handleInputBlur = () => {
    setIsFocused(false)
    // Collapse after a brief delay to allow for re-focusing
    setTimeout(() => {
      if (!value && !isFocused) {
        setIsExpanded(false)
      }
    }, 100)
  }

  // Handle keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isExpanded) {
      e.preventDefault()
      handleExpand()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      if (value) {
        onClear()
      } else {
        setIsExpanded(false)
        inputRef.current?.blur()
      }
    } else if (e.key === 'Tab' && !isExpanded) {
      // Allow tab to expand on focus
      handleExpand()
    }
  }

  // Auto-expand if there's a value
  useEffect(() => {
    if (value && !isExpanded) {
      setIsExpanded(true)
    }
  }, [value, isExpanded])

  const slideDirection = animationDirection === 'left' ? 'slide-in-from-left-2' : 'slide-in-from-right-2'

  return (
    <div 
      ref={containerRef}
      className={cn("relative", containerClassName, className)}
      onMouseEnter={handleExpand}
      onMouseLeave={handleCollapse}
    >
      {/* Search Icon Button (visible when collapsed) */}
      {!isExpanded && (
        <Button
          variant="ghost"
          size="sm"
          onClick={handleExpand}
          onKeyDown={handleKeyDown}
          className="h-8 w-8 p-0 hover:bg-mb-blue-300/10 transition-all duration-200"
          aria-label="Search folders"
          data-testid="folder-search-icon"
        >
          <Search className="h-4 w-4 text-muted-foreground" />
        </Button>
      )}

      {/* Expanded Search Input */}
      {isExpanded && (
        <div className={cn(
          "relative animate-in duration-200",
          `animate-in ${slideDirection}`,
          inputWidth
        )}>
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          <Input
            ref={inputRef}
            placeholder={placeholder}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onFocus={handleInputFocus}
            onBlur={handleInputBlur}
            onKeyDown={handleKeyDown}
            className={cn(
              "pl-9 pr-8 h-8 text-sm bg-background/60",
              "border-border focus:border-accent",
              "transition-all duration-200",
              inputClassName
            )}
            data-testid="folder-search-input"
          />
          {value && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                onClear()
                inputRef.current?.focus()
              }}
              className="absolute right-1 top-1/2 transform -translate-y-1/2 h-6 w-6 p-0 hover:bg-mb-blue-300/20"
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