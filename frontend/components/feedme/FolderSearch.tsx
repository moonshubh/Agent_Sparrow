/**
 * FolderSearch Component
 * 
 * Search icon that expands to input on hover/focus with:
 * - Icon-to-input transition with CSS animation
 * - Keyboard accessibility (Enter/Tab expand, Escape collapse)
 * - Auto-collapse on blur when empty
 * - Integration with existing folder search logic
 */

'use client'

import React, { useState, useRef, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Search, X } from 'lucide-react'
import { cn } from '@/lib/utils'

interface FolderSearchProps {
  value: string
  onChange: (value: string) => void
  onClear: () => void
  className?: string
}

export function FolderSearch({ value, onChange, onClear, className }: FolderSearchProps) {
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
      handleExpand()
    } else if (e.key === 'Escape') {
      if (value) {
        onClear()
      } else {
        setIsExpanded(false)
        inputRef.current?.blur()
      }
    }
  }

  // Auto-expand if there's a value
  useEffect(() => {
    if (value && !isExpanded) {
      setIsExpanded(true)
    }
  }, [value, isExpanded])

  return (
    <div 
      ref={containerRef}
      className={cn("relative", className)}
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
        <div className="relative animate-in slide-in-from-left-2 duration-200">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            ref={inputRef}
            placeholder="Search folders..."
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onFocus={handleInputFocus}
            onBlur={handleInputBlur}
            onKeyDown={handleKeyDown}
            className="pl-9 pr-8 h-8 text-sm bg-background/60 w-40 transition-all duration-200"
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