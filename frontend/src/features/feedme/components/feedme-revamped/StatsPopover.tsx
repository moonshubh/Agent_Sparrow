/**
 * StatsPopover Component
 *
 * Main popover component that displays comprehensive FeedMe statistics
 * when the Stats button is clicked in the Dock.
 */

import React, { useState, useCallback } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogClose } from '@/shared/ui/dialog'
import { ScrollArea } from '@/shared/ui/scroll-area'
import { Separator } from '@/shared/ui/separator'
import { Button } from '@/shared/ui/button'
import { Badge } from '@/shared/ui/badge'
import {
  BarChart3,
  RefreshCw,
  X,
  AlertCircle
} from 'lucide-react'
import { cn } from '@/shared/lib/utils'
import { useStatsData, formatTimeAgo } from '@/features/feedme/hooks/use-stats-data'
import {
  ConversationStatsCard,
  ProcessingMetricsCard,
  ApiUsageCard,
  RecentActivityCard,
  SystemHealthCard,
  StatsCardSkeleton
} from './stats/StatsCards'
import { Alert, AlertDescription } from '@/shared/ui/alert'

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
        hideClose
        className={cn(
          "max-w-[800px] p-0 h-[600px] overflow-hidden",
          className
        )}
      >
        <DialogHeader className="sr-only">
          <DialogTitle>FeedMe Statistics</DialogTitle>
        </DialogHeader>

        <div className="flex h-full min-h-0 flex-col">
          {/* Header (Zendesk-style) */}
          <div className="flex items-center justify-between px-4 py-3 border-b bg-muted/40">
            <div className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5 text-muted-foreground" />
              <h3 className="text-base font-semibold">FeedMe — Stats</h3>
              <Badge variant="outline" className="text-xs">Live</Badge>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Updated {lastUpdatedText}</span>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={handleRefresh}
                aria-label="Refresh stats"
                disabled={isRefreshing || isLoading}
              >
                <RefreshCw className={cn('h-4 w-4', isRefreshing && 'animate-spin')} />
              </Button>
              {/* Close button in header for consistency with settings UIs */}
              <DialogClose asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Close">
                  <X className="h-4 w-4" />
                </Button>
              </DialogClose>
            </div>
          </div>

          <Separator className="my-0" />

          <div className="flex-1 overflow-hidden min-h-0">
            <div className="flex h-full min-h-0 flex-col">
              <ScrollArea className="flex-1 h-full px-4 pb-4">
                {error && !data && (
                  <Alert variant="destructive" className="mb-4">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>
                      Failed to load statistics. Please try again later.
                    </AlertDescription>
                  </Alert>
                )}

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
                    <div>
                      <h4 className="mb-3 text-sm font-medium text-muted-foreground">Overview</h4>
                      <div className="grid grid-cols-2 gap-4">
                        <ConversationStatsCard data={data.conversations} />
                        <ProcessingMetricsCard data={data.processing} />
                      </div>
                    </div>

                    <div>
                      <h4 className="mb-3 text-sm font-medium text-muted-foreground">API Usage</h4>
                      <ApiUsageCard data={data.apiUsage} />
                    </div>

                    {/* Activity & Health and Quick Stats removed to avoid mock data; only live sections shown */}
                  </div>
                ) : null}
              </ScrollArea>

              {/* Bottom dashboard link removed */}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
