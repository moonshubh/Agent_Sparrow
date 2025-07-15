/**
 * FolderSearchInput Component
 * 
 * Search icon that expands to input on hover/focus for secondary folder panel.
 * Features:
 * - Icon-to-input transition with CSS animation (right slide-in, 160px width)
 * - Hover/focus expand, auto-collapse on blur when empty
 * - Keyboard accessibility (Enter/Tab expand, Escape collapse)
 * - Debounced search input
 * - Integration with folders store search filter
 */

'use client'

import React from 'react'
import { FolderSearchBase } from './FolderSearchBase'
import { cn } from '@/lib/utils'

interface FolderSearchInputProps {
  value: string
  onChange: (value: string) => void
  onClear: () => void
  className?: string
}

export function FolderSearchInput({ 
  value, 
  onChange, 
  onClear, 
  className 
}: FolderSearchInputProps) {
  return (
    <FolderSearchBase
      value={value}
      onChange={onChange}
      onClear={onClear}
      className={className}
      animationDirection="right"
      containerClassName="flex items-center"
      inputWidth="w-40" // 160px width as specified
      placeholder="Search folders..."
    />
  )
}