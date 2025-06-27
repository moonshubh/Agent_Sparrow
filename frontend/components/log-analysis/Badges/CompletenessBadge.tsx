"use client"

import React from 'react'
import { cn } from '@/lib/utils'

interface CompletenessBadgeProps {
  value: number | string
  className?: string
}

export function CompletenessBadge({ value, className }: CompletenessBadgeProps) {
  // 1. Safely parse the input value to a number.
  let numericValue: number;
  if (typeof value === 'string') {
    // Add radix 10 for safety.
    numericValue = parseInt(value.replace('%', ''), 10);
  } else if (typeof value === 'number') {
    numericValue = value;
  } else {
    // Default for null, undefined, etc.
    numericValue = NaN;
  }

  // 2. Validate the parsed number. If it's NaN, default to 0.
  if (isNaN(numericValue)) {
    numericValue = 0;
  }
  
  // 3. Normalize to a percentage. If the number is between 0 and 1 (inclusive),
  // treat it as a fraction; otherwise, treat it as a whole number.
  // This handles formats like 0.85 and 85 correctly.
  const percentage = (numericValue >= 0 && numericValue <= 1)
    ? Math.round(numericValue * 100)
    : Math.round(numericValue);

  // 4. Clamp the final value between 0 and 100 to ensure it's a valid percentage.
  // This also handles negative inputs, clamping them to 0.
  const displayValue = Math.max(0, Math.min(100, percentage));

  return (
    <div className={cn(
      "rounded-full bg-muted/40 px-3 py-1 inline-flex items-center min-w-[6.5rem] text-sm",
      className
    )}>
      <span className="shrink-0 text-muted-foreground font-medium">
        Completeness
      </span>
      <span className="ml-2 rounded-full bg-accent/10 text-accent px-2.5 py-1 text-xs font-semibold min-w-[2.5rem] text-center">
        {displayValue}%
      </span>
    </div>
  )
}