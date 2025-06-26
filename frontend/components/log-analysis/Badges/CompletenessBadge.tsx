"use client"

import React from 'react'
import { cn } from '@/lib/utils'

interface CompletenessBadgeProps {
  value: number | string
  className?: string
}

export function CompletenessBadge({ value, className }: CompletenessBadgeProps) {
  // Convert value to number and ensure it's between 0-100
  const percentage = typeof value === 'string' 
    ? parseInt(value.replace('%', '')) 
    : typeof value === 'number' 
    ? Math.round(value * (value <= 1 ? 100 : 1)) // Handle both 0.5 and 50 formats
    : 0

  const displayValue = Math.max(0, Math.min(100, percentage))

  return (
    <div className={cn(
      "rounded-full bg-muted/40 px-3 py-1 inline-flex items-center min-w-[6.5rem] text-sm",
      className
    )}>
      <span className="shrink-0 text-muted-foreground font-medium">
        Completeness
      </span>
      <span className="ml-2 rounded-full bg-sky-100 dark:bg-sky-900/40 text-sky-600 dark:text-sky-400 px-2.5 py-1 text-xs font-semibold min-w-[2.5rem] text-center">
        {displayValue}%
      </span>
    </div>
  )
}