"use client"

import React from 'react'
import { BrainCog } from 'lucide-react'
import { cn } from '@/lib/utils'

interface BrainSpinnerProps {
  className?: string
  size?: 'sm' | 'md' | 'lg'
  text?: string
}

/**
 * A lightweight thinking indicator component that displays a spinning brain icon with text.
 * Used to show when agents are processing user queries.
 */
export function BrainSpinner({ 
  className, 
  size = 'sm',
  text = "Thinking…" 
}: BrainSpinnerProps) {
  const sizeClasses = {
    sm: 'size-4',
    md: 'size-5', 
    lg: 'size-6'
  }

  const textSizeClasses = {
    sm: 'text-xs',
    md: 'text-sm',
    lg: 'text-base'
  }

  return (
    <div className={cn(
      "flex items-center space-x-1 text-muted-foreground",
      className
    )}>
      <BrainCog 
        className={cn(
          sizeClasses[size],
          "animate-spin"
        )} 
      />
      <span className={textSizeClasses[size]}>{text}</span>
    </div>
  )
}

BrainSpinner.displayName = 'BrainSpinner'