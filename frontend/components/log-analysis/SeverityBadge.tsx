import React from 'react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface SeverityBadgeProps {
  level: 'critical' | 'high' | 'medium'
  className?: string
}

export function SeverityBadge({ level, className }: SeverityBadgeProps) {
  const severityConfig = {
    critical: {
      label: 'Critical',
      className: 'bg-severity-critical text-white border-severity-critical',
    },
    high: {
      label: 'High', 
      className: 'bg-severity-high text-black border-severity-high',
    },
    medium: {
      label: 'Medium',
      className: 'bg-severity-medium text-white border-severity-medium',
    },
  }

  const config = severityConfig[level]

  return (
    <Badge
      variant="outline"
      className={cn(
        'px-2 py-0.5 text-xs font-semibold rounded-full border-2',
        config.className,
        className
      )}
    >
      {config.label}
    </Badge>
  )
}

export default SeverityBadge