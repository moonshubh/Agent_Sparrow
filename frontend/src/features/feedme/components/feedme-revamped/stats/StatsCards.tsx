/**
 * StatsCards Components
 *
 * Reusable card components for displaying various statistics
 * in the FeedMe stats popover.
 */

import React, { useMemo } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'
import { Progress } from '@/shared/ui/progress'
import { Badge } from '@/shared/ui/badge'
import { Skeleton } from '@/shared/ui/skeleton'
import {
  Activity,
  BarChart3,
  CheckCircle2,
  Clock,
  Database,
  FileText,
  Gauge,
  Globe,
  Hash,
  Heart,
  Laptop,
  MonitorSmartphone,
  TrendingUp,
  Upload,
  XCircle,
  Zap,
  Search,
  ThumbsUp,
  AlertCircle,
  Server
} from 'lucide-react'
import { cn } from '@/shared/lib/utils'
import { formatTimeAgo, getStatusColor } from '@/features/feedme/hooks/use-stats-data'
import type {
  ConversationStats,
  ProcessingMetrics,
  ApiUsage,
  RecentActivity,
  SystemHealth
} from '@/features/feedme/hooks/use-stats-data'

// Loading skeleton for cards
export function StatsCardSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-6 w-32 mt-1" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4 mt-2" />
      </CardContent>
    </Card>
  )
}

// Conversation Stats Card
interface ConversationStatsCardProps {
  data: ConversationStats
  className?: string
}

export function ConversationStatsCard({ data, className }: ConversationStatsCardProps) {
  // Memoize platform data array to prevent recreation on every render
  const platforms = useMemo(() => [
    { name: 'Windows', value: data.byPlatform.windows, icon: <Laptop className="h-3 w-3" /> },
    { name: 'macOS', value: data.byPlatform.macos, icon: <MonitorSmartphone className="h-3 w-3" /> },
    { name: 'Linux', value: data.byPlatform.linux, icon: <Server className="h-3 w-3" /> },
    { name: 'Other', value: data.byPlatform.other, icon: <Globe className="h-3 w-3" /> }
  ], [data.byPlatform])

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">Conversations</CardTitle>
          <FileText className="h-4 w-4 text-muted-foreground" />
        </div>
        <div className="text-2xl font-bold">{data.total.toLocaleString()}</div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-2">
          <div className="text-xs font-medium text-muted-foreground">Platform Distribution</div>
          <div className="grid grid-cols-2 gap-2">
            {platforms.map((platform) => (
              <div key={platform.name} className="flex items-center gap-1.5">
                {platform.icon}
                <span className="text-xs text-muted-foreground">{platform.name}:</span>
                <span className="text-xs font-medium">{platform.value}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          {data.byStatus.pending > 0 && (
            <Badge variant="outline" className="text-xs">
              {data.byStatus.pending} pending
            </Badge>
          )}
          {data.byStatus.processing > 0 && (
            <Badge variant="secondary" className="text-xs">
              {data.byStatus.processing} processing
            </Badge>
          )}
          {data.byStatus.approved > 0 && (
            <Badge variant="default" className="text-xs">
              {data.byStatus.approved} approved
            </Badge>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// Processing Metrics Card
interface ProcessingMetricsCardProps {
  data: ProcessingMetrics
  className?: string
}

export function ProcessingMetricsCard({ data, className }: ProcessingMetricsCardProps) {
  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">Processing</CardTitle>
          <Activity className="h-4 w-4 text-muted-foreground" />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="flex items-center gap-1">
              <Clock className="h-3 w-3 text-muted-foreground" />
              <span className="text-xs text-muted-foreground">Avg Time</span>
            </div>
            <div className="text-lg font-semibold">{data.averageTime.toFixed(1)}s</div>
          </div>
          <div>
            <div className="flex items-center gap-1">
              <CheckCircle2 className="h-3 w-3 text-muted-foreground" />
              <span className="text-xs text-muted-foreground">Success Rate</span>
            </div>
            <div className="text-lg font-semibold">{data.successRate.toFixed(1)}%</div>
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex justify-between text-xs">
            <span className="text-muted-foreground">Processing Queue</span>
            <span className="font-medium">{data.currentlyProcessing + data.queueSize}</span>
          </div>
          <Progress
            value={
              // Proper division by zero handling
              data.currentlyProcessing + data.queueSize > 0
                ? (data.currentlyProcessing / (data.currentlyProcessing + data.queueSize)) * 100
                : 0
            }
            className="h-1.5"
          />
        </div>

        {data.currentlyProcessing > 0 && (
          <div className="flex items-center gap-1.5">
            <div className="h-2 w-2 bg-yellow-500 rounded-full animate-pulse" />
            <span className="text-xs text-muted-foreground">
              {data.currentlyProcessing} currently processing
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// API Usage Card
interface ApiUsageCardProps {
  data: ApiUsage
  className?: string
}

export function ApiUsageCard({ data, className }: ApiUsageCardProps) {
  // Memoize percentage calculations with proper division by zero handling
  const geminiPercent = useMemo(() => {
    return data.gemini.dailyLimit > 0
      ? (data.gemini.dailyUsed / data.gemini.dailyLimit) * 100
      : 0
  }, [data.gemini.dailyUsed, data.gemini.dailyLimit])

  const embeddingPercent = useMemo(() => {
    return data.embedding.dailyLimit > 0
      ? (data.embedding.dailyUsed / data.embedding.dailyLimit) * 100
      : 0
  }, [data.embedding.dailyUsed, data.embedding.dailyLimit])

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">API Usage</CardTitle>
          <Zap className="h-4 w-4 text-muted-foreground" />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Gemini API */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Gauge className="h-3 w-3 text-muted-foreground" />
              <span className="text-xs font-medium">Gemini Vision</span>
            </div>
            <Badge variant={data.gemini.status === 'healthy' ? 'default' : data.gemini.status === 'warning' ? 'secondary' : 'destructive'} className="text-xs">
              {data.gemini.status}
            </Badge>
          </div>
          <div className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">Daily Limit</span>
              <span className="font-medium">{data.gemini.dailyUsed}/{data.gemini.dailyLimit}</span>
            </div>
            <Progress value={geminiPercent} className={cn("h-1.5", geminiPercent > 80 && "bg-yellow-100")} />
          </div>
        </div>

        {/* Embedding API */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Database className="h-3 w-3 text-muted-foreground" />
              <span className="text-xs font-medium">Embeddings</span>
            </div>
            <Badge variant={data.embedding.status === 'healthy' ? 'default' : data.embedding.status === 'warning' ? 'secondary' : 'destructive'} className="text-xs">
              {data.embedding.status}
            </Badge>
          </div>
          <div className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">Daily Limit</span>
              <span className="font-medium">{data.embedding.dailyUsed}/{data.embedding.dailyLimit}</span>
            </div>
            <Progress value={embeddingPercent} className={cn("h-1.5", embeddingPercent > 80 && "bg-yellow-100")} />
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="flex items-center gap-1">
              <Hash className="h-3 w-3 text-muted-foreground" />
              <span className="text-muted-foreground">RPM:</span>
              <span className="font-medium">{data.embedding.callsInWindow}/{data.embedding.rpmLimit}</span>
            </div>
            <div className="flex items-center gap-1">
              <BarChart3 className="h-3 w-3 text-muted-foreground" />
              <span className="text-muted-foreground">TPM:</span>
              <span className="font-medium">{(data.embedding.tokensInWindow / 1000).toFixed(0)}k</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// Recent Activity Card
interface RecentActivityCardProps {
  data: RecentActivity
  className?: string
}

export function RecentActivityCard({ data, className }: RecentActivityCardProps) {
  // Memoize activities array to prevent recreation on every render
  const activities = useMemo(() => [
    {
      icon: <Upload className="h-3 w-3" />,
      label: 'Uploads',
      value: data.todayUploads,
      time: data.lastUploadTime,
      color: 'text-blue-500'
    },
    {
      icon: <Search className="h-3 w-3" />,
      label: 'Searches',
      value: data.todaySearches,
      time: data.lastSearchTime,
      color: 'text-purple-500'
    },
    {
      icon: <ThumbsUp className="h-3 w-3" />,
      label: 'Approvals',
      value: data.todayApprovals,
      time: data.lastApprovalTime,
      color: 'text-green-500'
    }
  ], [data.todayUploads, data.todaySearches, data.todayApprovals, data.lastUploadTime, data.lastSearchTime, data.lastApprovalTime])

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">Today's Activity</CardTitle>
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {activities.map((activity) => (
          <div key={activity.label} className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className={cn("p-1.5 rounded-md bg-muted/50", activity.color)}>
                {activity.icon}
              </div>
              <div>
                <div className="text-sm font-medium">{activity.value}</div>
                <div className="text-xs text-muted-foreground">{activity.label}</div>
              </div>
            </div>
            {activity.time && (
              <span className="text-xs text-muted-foreground">
                {formatTimeAgo(activity.time)}
              </span>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

// System Health Card
interface SystemHealthCardProps {
  data: SystemHealth
  className?: string
}

export function SystemHealthCard({ data, className }: SystemHealthCardProps) {
  // Memoize status icon mapping
  const statusIcon = useMemo(() => ({
    excellent: <Heart className="h-4 w-4 text-green-500" />,
    good: <CheckCircle2 className="h-4 w-4 text-green-400" />,
    fair: <AlertCircle className="h-4 w-4 text-yellow-500" />,
    poor: <XCircle className="h-4 w-4 text-red-500" />
  }), [])

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">System Health</CardTitle>
          {statusIcon[data.status]}
        </div>
        <div className="flex items-center gap-2">
          <div className="text-2xl font-bold">{data.score}</div>
          <Badge variant={data.status === 'excellent' ? 'default' : data.status === 'good' ? 'secondary' : data.status === 'fair' ? 'outline' : 'destructive'}>
            {data.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1">
          <Progress value={data.score} className={cn("h-2", data.score < 70 && "bg-red-100")} />
        </div>

        {data.issues.length > 0 && (
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">Issues</div>
            <div className="space-y-1">
              {data.issues.map((issue, i) => (
                <div key={i} className="flex items-center gap-1.5 text-xs">
                  <div className="h-1 w-1 bg-yellow-500 rounded-full" />
                  <span className="text-muted-foreground">{issue}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex items-center gap-1.5 text-xs">
          <Clock className="h-3 w-3 text-muted-foreground" />
          <span className="text-muted-foreground">Uptime:</span>
          <span className="font-medium">{data.uptime}h</span>
        </div>
      </CardContent>
    </Card>
  )
}