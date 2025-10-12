"use client"

import { useEffect, useState, useRef } from 'react'
import { Progress } from '@/shared/ui/progress'
import { AlertCircle, Activity } from 'lucide-react'
import { Alert, AlertDescription } from '@/shared/ui/alert'
import { supabase } from '@/services/supabase/browser-client'
import { useAuth } from '@/features/auth/hooks/useAuth'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/shared/ui/tooltip"

// Centralized rate limit configuration
const RATE_LIMITS = {
  'gemini-2.5-flash': { daily: 250, rpm: 10 },
  'gemini-2.5-pro': { daily: 100, rpm: 5 }
} as const

interface UsageData {
  model: string
  request_count: number
}

export function DailyUsageTracker() {
  const { user } = useAuth()
  const [usage, setUsage] = useState<UsageData[]>([])
  const [loading, setLoading] = useState(true)
  const [showWarning, setShowWarning] = useState(false)
  const intervalRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    if (!user) {
      setLoading(false)
      return
    }

    const fetchUsage = async () => {
      try {
        // Get today's usage
        const today = new Date().toISOString().split('T')[0]
        const { data, error } = await supabase
          .from('user_api_usage')
          .select('model, request_count')
          .eq('user_id', user.id)
          .eq('date', today)

        if (!error && data) {
          setUsage(data)
          
          // Check if any model is at 90% usage using configuration
          const hasHighUsage = data.some(row => {
            const modelKey = row.model.includes('flash') ? 'gemini-2.5-flash' : 'gemini-2.5-pro'
            const limit = RATE_LIMITS[modelKey].daily
            return (row.request_count / limit) >= 0.9
          })
          setShowWarning(hasHighUsage)
        }
      } catch (error) {
        console.error('Failed to fetch usage:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchUsage()
    // Refresh every 30 seconds with proper cleanup
    intervalRef.current = setInterval(fetchUsage, 30000)
    
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [user])

  if (!user || loading) return null

  // Get usage for current models
  const flashUsage = usage.find(u => u.model.includes('flash'))
  const proUsage = usage.find(u => u.model.includes('pro'))
  
  // Get limits from configuration
  const flashLimit = RATE_LIMITS['gemini-2.5-flash'].daily
  const proLimit = RATE_LIMITS['gemini-2.5-pro'].daily
  const flashRpm = RATE_LIMITS['gemini-2.5-flash'].rpm
  const proRpm = RATE_LIMITS['gemini-2.5-pro'].rpm
  
  // Get current counts (default to 0 if not found)
  const flashCount = flashUsage?.request_count || 0
  const proCount = proUsage?.request_count || 0
  
  // Calculate primary model usage percentage
  const primaryModel = flashCount >= proCount ? 'flash' : 'pro'
  const primaryCount = primaryModel === 'flash' ? flashCount : proCount
  const primaryLimit = primaryModel === 'flash' ? flashLimit : proLimit
  const usagePercent = Math.round((primaryCount / primaryLimit) * 100)
  
  // Determine color based on usage
  const getUsageColor = () => {
    if (usagePercent >= 90) return 'text-red-500'
    if (usagePercent >= 75) return 'text-yellow-500'
    return 'text-green-500'
  }

  return (
    <>
      {/* Compact header display: show both Flash and Pro counts */}
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <button className="flex items-center gap-3 px-3 py-1.5 rounded-lg hover:bg-secondary/50 transition-colors">
              <Activity className={`h-4 w-4 ${getUsageColor()}`} />
              <span className="flex items-center gap-2 text-sm font-medium">
                <span className="flex items-center gap-1">
                  <span className="inline-block w-2 h-2 rounded-full bg-blue-500" aria-hidden />
                  Flash {flashCount}/{flashLimit}
                </span>
                <span className="text-muted-foreground">|</span>
                <span className="flex items-center gap-1">
                  <span className="inline-block w-2 h-2 rounded-full bg-accent" aria-hidden />
                  Pro {proCount}/{proLimit}
                </span>
              </span>
              {showWarning && (
                <AlertCircle className="h-4 w-4 text-yellow-500 animate-pulse" />
              )}
            </button>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="w-64">
            <div className="space-y-3 p-2">
              <p className="text-xs font-semibold text-foreground">Daily API Usage</p>
              
              <div>
                <div className="flex justify-between mb-1">
                  <span className="text-xs font-medium">Gemini 2.5 Flash</span>
                  <span className="text-xs text-muted-foreground">
                    {flashCount} / {flashLimit} ({flashRpm} RPM)
                  </span>
                </div>
                <Progress value={(flashCount / flashLimit) * 100} className="h-2" />
              </div>

              <div>
                <div className="flex justify-between mb-1">
                  <span className="text-xs font-medium">Gemini 2.5 Pro</span>
                  <span className="text-xs text-muted-foreground">
                    {proCount} / {proLimit} ({proRpm} RPM)
                  </span>
                </div>
                <Progress value={(proCount / proLimit) * 100} className="h-2" />
              </div>

              <div className="pt-2 border-t">
                <p className="text-xs text-muted-foreground">Daily limits reset at midnight Pacific Time</p>
                <p className="text-xs text-muted-foreground mt-1">Using your own API key for full quota</p>
              </div>
            </div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      {/* 90% usage warning - positioned fixed at bottom right */}
      {showWarning && (
        <Alert className="fixed bottom-4 right-4 w-96 z-50 border-yellow-500/50 bg-yellow-500/10">
          <AlertCircle className="h-4 w-4 text-yellow-500" />
          <AlertDescription>
            <strong>High usage alert!</strong> You have used over 90% of your daily quota for {primaryModel === 'flash' ? 'Gemini 2.5 Flash' : 'Gemini 2.5 Pro'}. Consider switching models or waiting for the daily reset at midnight PT.
          </AlertDescription>
        </Alert>
      )}
    </>
  )
}
