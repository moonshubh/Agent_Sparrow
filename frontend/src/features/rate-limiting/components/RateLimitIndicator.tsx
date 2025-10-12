"use client"

import React, { useCallback, useEffect, useState } from 'react'
import { AlertCircle, Zap } from 'lucide-react'
import { rateLimitApi } from '@/services/api/endpoints/rateLimitApi'
import { cn } from '@/shared/lib/utils'

interface RateLimitIndicatorProps {
  model?: 'gemini-2.5-flash' | 'gemini-2.5-pro'
  className?: string
}

export function RateLimitIndicator({ model = 'gemini-2.5-flash', className }: RateLimitIndicatorProps) {
  const [usage, setUsage] = useState<{
    rpm_used: number
    rpm_limit: number
    rpd_used: number
    rpd_limit: number
  } | null>(null)
  const [loading, setLoading] = useState(true)

  const checkRateLimit = useCallback(async () => {
    try {
      setLoading(true)
      const status = await rateLimitApi.getStatus()
      if (status && status.details?.usage_stats) {
        const stats = model === 'gemini-2.5-pro' 
          ? status.details.usage_stats.pro_stats 
          : status.details.usage_stats.flash_stats
        
        setUsage({
          rpm_used: stats.rpm_used || 0,
          // Free tier defaults: Pro 5 RPM, Flash 10 RPM
          rpm_limit: stats.rpm_limit || (model === 'gemini-2.5-pro' ? 5 : 10),
          rpd_used: stats.rpd_used || 0,
          // Free tier defaults: Pro 100 RPD, Flash 250 RPD
          rpd_limit: stats.rpd_limit || (model === 'gemini-2.5-pro' ? 100 : 250)
        })
      }
    } catch (error) {
      console.error('Failed to check rate limit:', error)
    } finally {
      setLoading(false)
    }
  }, [model])

  useEffect(() => {
    void checkRateLimit()
    const interval = setInterval(checkRateLimit, 30000) // Check every 30 seconds
    return () => clearInterval(interval)
  }, [checkRateLimit])

  if (loading || !usage) {
    return null
  }

  const rpmPercentage = (usage.rpm_used / usage.rpm_limit) * 100
  const rpdPercentage = (usage.rpd_used / usage.rpd_limit) * 100
  const maxPercentage = Math.max(rpmPercentage, rpdPercentage)

  const getStatusColor = () => {
    if (maxPercentage >= 90) return 'text-red-500 border-red-500/30 bg-red-500/10'
    if (maxPercentage >= 70) return 'text-yellow-500 border-yellow-500/30 bg-yellow-500/10'
    return 'text-green-500 border-green-500/30 bg-green-500/10'
  }

  const getProgressColor = () => {
    if (maxPercentage >= 90) return 'bg-red-500'
    if (maxPercentage >= 70) return 'bg-yellow-500'
    return 'bg-green-500'
  }

  return (
    <div className={cn(
      'group relative flex items-center gap-2 px-3 py-1.5 rounded-full border backdrop-blur-sm transition-all duration-200',
      'hover:scale-105 cursor-pointer',
      getStatusColor(),
      className
    )}>
      <Zap className="w-3.5 h-3.5" />
      <span className="text-xs font-medium">
        {Math.round(maxPercentage)}%
      </span>
      
      {/* Hover tooltip */}
      <div className="absolute top-full mt-2 right-0 w-64 p-3 bg-background/95 backdrop-blur-lg border border-border/50 rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-50">
        <div className="space-y-2">
          <div className="text-xs font-semibold">{model} Rate Limits</div>
          
          <div className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">Per Minute:</span>
              <span>{usage.rpm_used}/{usage.rpm_limit}</span>
            </div>
            <div className="w-full h-1.5 bg-secondary rounded-full overflow-hidden">
              <div 
                className={cn('h-full transition-all duration-300', getProgressColor())}
                style={{ width: `${Math.min(rpmPercentage, 100)}%` }}
              />
            </div>
          </div>

          <div className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">Per Day:</span>
              <span>{usage.rpd_used}/{usage.rpd_limit}</span>
            </div>
            <div className="w-full h-1.5 bg-secondary rounded-full overflow-hidden">
              <div 
                className={cn('h-full transition-all duration-300', getProgressColor())}
                style={{ width: `${Math.min(rpdPercentage, 100)}%` }}
              />
            </div>
          </div>

          {maxPercentage >= 90 && (
            <div className="flex items-center gap-1 text-xs text-red-500 pt-1">
              <AlertCircle className="w-3 h-3" />
              <span>Approaching rate limit!</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
