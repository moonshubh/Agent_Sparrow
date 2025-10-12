/**
 * useStatsData Hook
 *
 * Custom hook for fetching and managing FeedMe statistics data.
 * Provides auto-refresh, error handling, and data transformation.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import {
  getApprovalWorkflowStats,
  type ApprovalWorkflowStats,
  feedMeApi,
  type GeminiUsage,
  type EmbeddingUsage,
} from '@/features/feedme/services/feedme-api'
import { useAnalyticsStore } from '@/state/stores/analytics-store'

// Types for stats data
export interface ConversationStats {
  total: number
  byPlatform: {
    windows: number
    macos: number
    linux: number
    other: number
  }
  byStatus: {
    pending: number
    processing: number
    completed: number
    failed: number
    approved: number
    rejected: number
  }
}

export interface ProcessingMetrics {
  averageTime: number // in seconds
  successRate: number // percentage
  failureRate: number // percentage
  currentlyProcessing: number
  queueSize: number
}

export interface ApiUsage {
  gemini: {
    dailyUsed: number
    dailyLimit: number
    dailyUtilization: number // percentage
    rpmLimit: number
    callsInWindow: number
    windowSecondsRemaining: number
    status: 'healthy' | 'warning' | 'critical'
  }
  embedding: {
    dailyUsed: number
    dailyLimit: number
    dailyUtilization: number // percentage
    rpmLimit: number
    tpmLimit: number
    callsInWindow: number
    tokensInWindow: number
    windowSecondsRemaining: number
    tokenWindowSecondsRemaining: number
    status: 'healthy' | 'warning' | 'critical'
  }
}

export interface RecentActivity {
  todayUploads: number
  todaySearches: number
  todayApprovals: number
  lastUploadTime?: string
  lastSearchTime?: string
  lastApprovalTime?: string
}

export interface SystemHealth {
  score: number // 0-100
  status: 'excellent' | 'good' | 'fair' | 'poor'
  issues: string[]
  uptime: number // in hours
}

export interface StatsData {
  conversations: ConversationStats
  processing: ProcessingMetrics
  apiUsage: ApiUsage
  recentActivity: RecentActivity
  systemHealth: SystemHealth
  lastUpdated: string
}

interface UseStatsDataOptions {
  autoRefresh?: boolean
  refreshInterval?: number // in milliseconds
  onError?: (error: Error) => void
}

interface UseStatsDataReturn {
  data: StatsData | null
  isLoading: boolean
  error: Error | null
  refetch: () => Promise<void>
  lastFetchTime: Date | null
}

/**
 * Custom hook for fetching and managing stats data
 */
export function useStatsData(options: UseStatsDataOptions = {}): UseStatsDataReturn {
  const {
    autoRefresh = true,
    refreshInterval = 30000, // 30 seconds default
    onError
  } = options

  const [data, setData] = useState<StatsData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const [lastFetchTime, setLastFetchTime] = useState<Date | null>(null)

  const intervalRef = useRef<NodeJS.Timeout | null>(null)
  const isMountedRef = useRef(true)

  // Get analytics store actions for supplementary data
  const analyticsActions = useAnalyticsStore(state => state.actions)

  // Transform API data into structured stats
  const transformData = useCallback((
    workflowStats: ApprovalWorkflowStats,
    geminiUsage: GeminiUsage | null,
    embeddingUsage: EmbeddingUsage | null,
    analyticsData: ReturnType<typeof useAnalyticsStore.getState>
  ): StatsData => {
    // Calculate platform breakdown - use actual data when API provides it
    const totalConversations = workflowStats.total_conversations || 0
    // TODO: Replace with actual platform data from API when available
    // For now, show 0 distribution until backend provides platform breakdown
    const windowsRatio = 0
    const macosRatio = 0
    const linuxRatio = 0
    const otherRatio = 0

    // Processing metrics
    const avgProcessingTime = workflowStats.avg_processing_time_ms
      ? workflowStats.avg_processing_time_ms / 1000 // Convert to seconds
      : 0 // No default, show actual data only

    const totalProcessed = (workflowStats.approved || 0) + (workflowStats.rejected || 0) + (workflowStats.published || 0)
    const totalAttempted = totalProcessed + (workflowStats.processing_failed || 0)
    const successRate = totalAttempted > 0
      ? ((totalProcessed / totalAttempted) * 100)
      : 0 // Show 0% when there's no data, not 100%

    // System health calculation
    const calculateHealthScore = () => {
      let score = 100
      const issues: string[] = []

      const geminiDailyUtilization = geminiUsage?.utilization.daily ?? 0
      if (geminiDailyUtilization > 80) {
        score -= 10
        issues.push('High Gemini API usage')
      }
      const embeddingDailyUtilization = embeddingUsage?.utilization.daily ?? 0
      if (embeddingDailyUtilization > 80) {
        score -= 10
        issues.push('High embedding API usage')
      }

      // Check processing queue
      if ((workflowStats.currently_processing || 0) > 10) {
        score -= 5
        issues.push('Large processing queue')
      }

      // Check failure rate
      const failureRate = 100 - successRate
      if (failureRate > 10) {
        score -= 15
        issues.push('High failure rate')
      }

      // Determine status
      let status: SystemHealth['status'] = 'excellent'
      if (score < 70) status = 'poor'
      else if (score < 80) status = 'fair'
      else if (score < 90) status = 'good'

      return { score, status, issues }
    }

    const { score, status, issues } = calculateHealthScore()

    // Get recent activity from analytics store
    const todayUploads = analyticsData?.usageStats?.uploads_today || 0
    const todaySearches = analyticsData?.usageStats?.searches_today || 0
    const todayApprovals = analyticsData?.usageStats?.approvals_today || 0

    return {
      conversations: {
        total: totalConversations,
        byPlatform: {
          windows: Math.round(totalConversations * windowsRatio),
          macos: Math.round(totalConversations * macosRatio),
          linux: Math.round(totalConversations * linuxRatio),
          other: Math.round(totalConversations * otherRatio)
        },
        byStatus: {
          pending: workflowStats.pending_approval || 0,
          processing: workflowStats.currently_processing || 0,
          completed: workflowStats.approved || 0,
          failed: workflowStats.processing_failed || 0,
          approved: workflowStats.approved || 0,
          rejected: workflowStats.rejected || 0
        }
      },
      processing: {
        averageTime: avgProcessingTime,
        successRate,
        failureRate: 100 - successRate,
        currentlyProcessing: workflowStats.currently_processing || 0,
        queueSize: workflowStats.awaiting_review || 0
      },
      apiUsage: {
        gemini: {
          dailyUsed: geminiUsage?.daily_used || 0,
          dailyLimit: geminiUsage?.daily_limit || 1500,
          dailyUtilization: geminiUsage?.utilization?.daily || 0,
          rpmLimit: geminiUsage?.rpm_limit || 15,
          callsInWindow: geminiUsage?.calls_in_window || 0,
          windowSecondsRemaining: geminiUsage?.window_seconds_remaining || 60,
          status: geminiUsage?.status || 'healthy'
        },
        embedding: {
          dailyUsed: embeddingUsage?.daily_used || 0,
          dailyLimit: embeddingUsage?.daily_limit || 3000,
          dailyUtilization: embeddingUsage?.utilization?.daily || 0,
          rpmLimit: embeddingUsage?.rpm_limit || 3000,
          tpmLimit: embeddingUsage?.tpm_limit || 1000000,
          callsInWindow: embeddingUsage?.calls_in_window || 0,
          tokensInWindow: embeddingUsage?.tokens_in_window || 0,
          windowSecondsRemaining: embeddingUsage?.window_seconds_remaining || 60,
          tokenWindowSecondsRemaining: embeddingUsage?.token_window_seconds_remaining || 60,
          status: embeddingUsage?.status || 'healthy'
        }
      },
      recentActivity: {
        todayUploads,
        todaySearches,
        todayApprovals,
        // TODO: Get actual timestamps from API when available
        lastUploadTime: '', // Will be populated by backend
        lastSearchTime: '', // Will be populated by backend
        lastApprovalTime: '' // Will be populated by backend
      },
      systemHealth: {
        score,
        status,
        issues,
        uptime: 0 // Will be populated by backend with actual system uptime
      },
      lastUpdated: new Date().toISOString()
    }
  }, [])

  // Fetch all stats data
  const fetchData = useCallback(async () => {
    if (!isMountedRef.current) return

    try {
      setIsLoading(true)
      setError(null)

      // Fetch all data in parallel
      const [workflowStats, geminiUsage, embeddingUsage] = await Promise.allSettled([
        getApprovalWorkflowStats(),
        feedMeApi.getGeminiUsage(),
        feedMeApi.getEmbeddingUsage()
      ])

      // Load analytics data
      await analyticsActions.loadUsageStats()
      const analyticsData = useAnalyticsStore.getState()

      // Process results
      const workflow = workflowStats.status === 'fulfilled'
        ? workflowStats.value
        : {
            total_conversations: 0,
            pending_approval: 0,
            awaiting_review: 0,
            approved: 0,
            rejected: 0,
            published: 0,
            currently_processing: 0,
            processing_failed: 0
          }

      const gemini = geminiUsage.status === 'fulfilled'
        ? geminiUsage.value
        : null

      const embedding = embeddingUsage.status === 'fulfilled'
        ? embeddingUsage.value
        : null

      // Transform and set data
      const transformedData = transformData(workflow, gemini, embedding, analyticsData)

      if (isMountedRef.current) {
        setData(transformedData)
        setLastFetchTime(new Date())
      }

    } catch (err) {
      if (isMountedRef.current) {
        const error = err instanceof Error ? err : new Error('Failed to fetch stats data')
        setError(error)
        onError?.(error)
      }
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false)
      }
    }
  }, [transformData, analyticsActions, onError])

  // Set up auto-refresh
  useEffect(() => {
    if (!autoRefresh) return

    // Initial fetch
    fetchData()

    // Set up interval
    intervalRef.current = setInterval(() => {
      fetchData()
    }, refreshInterval)

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [autoRefresh, refreshInterval, fetchData])

  // Cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true

    return () => {
      isMountedRef.current = false
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [])

  return {
    data,
    isLoading,
    error,
    refetch: fetchData,
    lastFetchTime
  }
}

// Utility function to format time ago
export function formatTimeAgo(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000)

  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

// Utility function to get status color
export function getStatusColor(status: 'healthy' | 'warning' | 'critical' | 'excellent' | 'good' | 'fair' | 'poor'): string {
  switch (status) {
    case 'healthy':
    case 'excellent':
      return 'text-green-500'
    case 'good':
      return 'text-green-400'
    case 'warning':
    case 'fair':
      return 'text-yellow-500'
    case 'critical':
    case 'poor':
      return 'text-red-500'
    default:
      return 'text-gray-500'
  }
}
