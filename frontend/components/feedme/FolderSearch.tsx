/**
 * FolderSearch Component
 * 
 * Search icon that expands to input on hover/focus with:
 * - Icon-to-input transition with CSS animation (left slide-in)
 * - Keyboard accessibility (Enter/Tab expand, Escape collapse)
 * - Auto-collapse on blur when empty
 * - Integration with existing folder search logic
 */

'use client'

import React from 'react'
import { FolderSearchBase } from './FolderSearchBase'

interface FolderSearchProps {
  value: string
  onChange: (value: string) => void
  onClear: () => void
  className?: string
}

export function FolderSearch({ value, onChange, onClear, className }: FolderSearchProps) {
  return (
    <FolderSearchBase
      value={value}
      onChange={onChange}
      onClear={onClear}
      className={className}
      animationDirection="left"
      placeholder="Search folders..."
    />
  )
}