/**
 * StatsPopover Component
 *
 * Main popover component that displays comprehensive FeedMe statistics
 * when the Stats button is clicked in the Dock.
 */

import React, { useState, useCallback } from 'react'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  BarChart3,
  RefreshCw,
  X,
  AlertCircle
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useStatsData, formatTimeAgo } from '@/hooks/use-stats-data'
import {
  ConversationStatsCard,
  ProcessingMetricsCard,
  ApiUsageCard,
  RecentActivityCard,
  SystemHealthCard,
  StatsCardSkeleton
} from './stats/StatsCards'
import { Alert, AlertDescription } from '@/components/ui/alert'

interface StatsPopoverProps {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  className?: string
}

export function StatsPopover({
  open = false,
  onOpenChange,
  className
}: StatsPopoverProps) {
  const [isRefreshing, setIsRefreshing] = useState(false)

  // Fetch stats data with auto-refresh
  const { data, isLoading, error, refetch, lastFetchTime } = useStatsData({
    autoRefresh: open, // Only auto-refresh when dialog is open
    refreshInterval: 30000, // 30 seconds
    onError: (error) => {
      // Error is already being handled by the error state in the UI
      // No need to log to console in production
    }
  })

  // Manual refresh handler without memory leak
  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true)
    try {
      await refetch()
    } finally {
      // Use requestAnimationFrame instead of setTimeout to avoid memory leak
      // and ensure the animation is visible for at least one frame
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          setIsRefreshing(false)
        })
      })
    }
  }, [refetch])

  // Format last updated time
  const lastUpdatedText = lastFetchTime
    ? formatTimeAgo(lastFetchTime.toISOString())
    : 'Never'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={cn(
          "max-w-[800px] p-0 h-[600px] overflow-hidden",
          className
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 pb-0">
          <div className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-muted-foreground" />
            <h3 className="font-semibold text-lg">FeedMe Statistics</h3>
            <Badge variant="outline" className="text-xs">
              Live
            </Badge>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">
              Updated {lastUpdatedText}
            </span>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={handleRefresh}
              disabled={isRefreshing || isLoading}
            >
              <RefreshCw className={cn(
                "h-4 w-4",
                isRefreshing && "animate-spin"
              )} />
            </Button>
          </div>
        </div>

        <Separator className="my-4" />

        {/* Content */}
        <ScrollArea className="h-[500px] px-4 pb-4">
          {/* Error State */}
          {error && !data && (
            <Alert variant="destructive" className="mb-4">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                Failed to load statistics. Please try again later.
              </AlertDescription>
            </Alert>
          )}

          {/* Loading State */}
          {isLoading && !data ? (
            <div className="grid gap-4">
              <div className="grid grid-cols-2 gap-4">
                <StatsCardSkeleton />
                <StatsCardSkeleton />
              </div>
              <StatsCardSkeleton />
              <div className="grid grid-cols-2 gap-4">
                <StatsCardSkeleton />
                <StatsCardSkeleton />
              </div>
            </div>
          ) : data ? (
            <div className="space-y-4">
              {/* Overview Section */}
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-3">Overview</h4>
                <div className="grid grid-cols-2 gap-4">
                  <ConversationStatsCard data={data.conversations} />
                  <ProcessingMetricsCard data={data.processing} />
                </div>
              </div>

              {/* API Usage Section */}
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-3">API Usage</h4>
                <ApiUsageCard data={data.apiUsage} />
              </div>

              {/* Activity & Health Section */}
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-3">Activity & Health</h4>
                <div className="grid grid-cols-2 gap-4">
                  <RecentActivityCard data={data.recentActivity} />
                  <SystemHealthCard data={data.systemHealth} />
                </div>
              </div>

              {/* Quick Stats */}
              <div className="pt-2">
                <h4 className="text-sm font-medium text-muted-foreground mb-3">Quick Stats</h4>
                <div className="grid grid-cols-3 gap-3">
                  <div className="text-center p-3 rounded-lg bg-muted/30">
                    <div className="text-2xl font-bold text-primary">
                      {data.conversations.total}
                    </div>
                    <div className="text-xs text-muted-foreground">Total Conversations</div>
                  </div>
                  <div className="text-center p-3 rounded-lg bg-muted/30">
                    <div className="text-2xl font-bold text-green-500">
                      {data.processing.successRate.toFixed(0)}%
                    </div>
                    <div className="text-xs text-muted-foreground">Success Rate</div>
                  </div>
                  <div className="text-center p-3 rounded-lg bg-muted/30">
                    <div className="text-2xl font-bold text-blue-500">
                      {data.recentActivity.todayUploads + data.recentActivity.todaySearches + data.recentActivity.todayApprovals}
                    </div>
                    <div className="text-xs text-muted-foreground">Actions Today</div>
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </ScrollArea>

        {/* Footer */}
        {data && (
          <>
            <Separator />
            <div className="p-3 bg-muted/30">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4 text-xs text-muted-foreground">
                  <span>Auto-refresh: 30s</span>
                  <span>•</span>
                  <span>System Status: {data.systemHealth.status}</span>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs"
                  onClick={() => {
                    // Full dashboard navigation will be implemented when dashboard route is ready
                    // For now, this serves as a placeholder for future functionality
                  }}
                >
                  View Full Dashboard →
                </Button>
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

