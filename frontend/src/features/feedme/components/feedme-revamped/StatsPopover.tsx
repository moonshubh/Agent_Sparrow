/**
 * StatsPopover Component
 *
 * Main popover component that displays comprehensive FeedMe statistics
 * when the Stats button is clicked in the Dock.
 */

import React, { useState, useCallback } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/shared/ui/dialog'
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/ui/tabs'
import ObservabilityTab from '@/features/feedme/components/feedme-revamped/global-knowledge/ObservabilityTab'

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
  const [activeTab, setActiveTab] = useState<'analytics' | 'observability'>('analytics')

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
        <DialogHeader className="sr-only">
          <DialogTitle>FeedMe Statistics</DialogTitle>
        </DialogHeader>

        <Tabs
          value={activeTab}
          onValueChange={value => setActiveTab(value as 'analytics' | 'observability')}
          className="flex h-full flex-col"
        >
          <div className="flex flex-col gap-4 px-4 pb-0">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div className="flex items-center gap-2">
                <BarChart3 className="h-5 w-5 text-muted-foreground" />
                <h3 className="text-lg font-semibold">
                  {activeTab === 'analytics' ? 'FeedMe Statistics' : 'Global Knowledge Observability'}
                </h3>
                <Badge variant="outline" className="text-xs">
                  Live
                </Badge>
              </div>
              <TabsList className="w-full md:w-auto">
                <TabsTrigger value="analytics">Analytics</TabsTrigger>
                <TabsTrigger value="observability">Observability</TabsTrigger>
              </TabsList>
            </div>

            {activeTab === 'analytics' ? (
              <div className="flex flex-wrap items-center justify-between gap-3">
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
            ) : (
              <div className="text-xs text-muted-foreground">
                Live observability stream with manual controls available inside the tab.
              </div>
            )}
          </div>

          <Separator className="my-4" />

          <TabsContent value="analytics" className="flex-1 overflow-hidden">
            <div className="flex h-full flex-col">
              <ScrollArea className="flex-1 px-4 pb-4">
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

                    <div>
                      <h4 className="mb-3 text-sm font-medium text-muted-foreground">Activity &amp; Health</h4>
                      <div className="grid grid-cols-2 gap-4">
                        <RecentActivityCard data={data.recentActivity} />
                        <SystemHealthCard data={data.systemHealth} />
                      </div>
                    </div>

                    <div className="pt-2">
                      <h4 className="mb-3 text-sm font-medium text-muted-foreground">Quick Stats</h4>
                      <div className="grid grid-cols-3 gap-3">
                        <div className="rounded-lg bg-muted/30 p-3 text-center">
                          <div className="text-2xl font-bold text-primary">
                            {data.conversations.total}
                          </div>
                          <div className="text-xs text-muted-foreground">Total Conversations</div>
                        </div>
                        <div className="rounded-lg bg-muted/30 p-3 text-center">
                          <div className="text-2xl font-bold text-green-500">
                            {data.processing.successRate.toFixed(0)}%
                          </div>
                          <div className="text-xs text-muted-foreground">Success Rate</div>
                        </div>
                        <div className="rounded-lg bg-muted/30 p-3 text-center">
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

              {data && (
                <>
                  <Separator />
                  <div className="bg-muted/30 p-3">
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
                          // Placeholder for future dashboard route navigation
                        }}
                      >
                        View Full Dashboard →
                      </Button>
                    </div>
                  </div>
                </>
              )}
            </div>
          </TabsContent>

          <TabsContent value="observability" className="flex-1 overflow-hidden">
            <ScrollArea className="h-[500px] px-4 pb-4">
              <ObservabilityTab />
            </ScrollArea>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}

