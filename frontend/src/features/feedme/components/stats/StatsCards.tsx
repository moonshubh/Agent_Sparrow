/**
 * StatsCards Components - Clean Redesign
 *
 * Modern, minimalist stat cards with appropriate visualizations
 * for each type of statistic.
 */

'use client'

import React from 'react'
import { motion } from 'motion/react'
import { cn } from '@/shared/lib/utils'
import { Skeleton } from '@/shared/ui/skeleton'
import {
  MessageSquare,
  Activity,
  Zap,
  Database,
  Heart,
  TrendingUp,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2
} from 'lucide-react'
import type {
  ConversationStats,
  ProcessingMetrics,
  ApiUsage,
  SystemHealth
} from '@/features/feedme/hooks/use-stats-data'

// Shared card wrapper component
interface StatCardProps {
  label: string
  value: string | number
  subtitle?: string
  icon: React.ReactNode
  children?: React.ReactNode
  className?: string
  animationDelay?: number
  accentColor?: string
}

function StatCard({
  label,
  value,
  subtitle,
  icon,
  children,
  className,
  animationDelay = 0,
  accentColor = 'hsl(200.4 98% 38%)'
}: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: animationDelay, ease: [0.4, 0, 0.2, 1] }}
      className={cn(
        'relative rounded-xl p-5',
        'bg-card border border-border',
        'shadow-sm hover:shadow-md transition-shadow duration-200',
        className
      )}
    >
      {/* Header with icon */}
      <div className="flex items-center justify-between mb-3">
        <span
          className="text-xs font-medium uppercase tracking-wide"
          style={{ color: accentColor }}
        >
          {label}
        </span>
        <div
          className="p-1.5 rounded-lg flex items-center justify-center"
          style={{ backgroundColor: `${accentColor}15`, color: accentColor }}
        >
          {icon}
        </div>
      </div>

      {/* Main value */}
      <div className="text-3xl font-bold text-foreground tabular-nums">
        {value}
      </div>

      {/* Subtitle */}
      {subtitle && (
        <p className="text-xs text-muted-foreground mt-1">
          {subtitle}
        </p>
      )}

      {/* Custom content (charts, etc.) */}
      {children && (
        <div className="mt-4">
          {children}
        </div>
      )}
    </motion.div>
  )
}

// Simple progress bar component
interface ProgressBarProps {
  value: number
  max?: number
  color?: string
  showLabel?: boolean
  size?: 'sm' | 'md'
}

function ProgressBar({
  value,
  max = 100,
  color = 'hsl(200.4 98% 38%)',
  showLabel = true,
  size = 'sm'
}: ProgressBarProps) {
  // Protect against division by zero
  const percentage = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0
  const height = size === 'sm' ? 'h-1.5' : 'h-2.5'

  return (
    <div className="space-y-1">
      <div className={cn('w-full bg-muted rounded-full overflow-hidden', height)}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${percentage}%` }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
          className={cn('h-full rounded-full', height)}
          style={{ backgroundColor: color }}
        />
      </div>
      {showLabel && (
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>{value.toLocaleString()}</span>
          <span>{max.toLocaleString()}</span>
        </div>
      )}
    </div>
  )
}

// Mini bar chart for status breakdown
interface MiniBarChartProps {
  data: { label: string; value: number; color: string }[]
}

function MiniBarChart({ data }: MiniBarChartProps) {
  const maxValue = Math.max(...data.map(d => d.value), 1)

  return (
    <div className="flex items-end gap-1.5 h-10">
      {data.map((item, index) => (
        <motion.div
          key={item.label}
          initial={{ height: 0 }}
          animate={{ height: `${Math.max(4, (item.value / maxValue) * 100)}%` }}
          transition={{ duration: 0.5, delay: index * 0.1 }}
          className="flex-1 rounded-t"
          style={{ backgroundColor: item.color }}
          title={`${item.label}: ${item.value}`}
        />
      ))}
    </div>
  )
}

// Loading skeleton
export function StatsCardSkeleton() {
  return (
    <div className="rounded-xl p-5 bg-card border border-border">
      <div className="flex items-center justify-between mb-3">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-7 w-7 rounded-lg" />
      </div>
      <Skeleton className="h-9 w-24 mb-2" />
      <Skeleton className="h-3 w-32 mb-4" />
      <Skeleton className="h-2 w-full rounded-full" />
    </div>
  )
}

// ==========================================
// Conversation Stats Card
// ==========================================
interface ConversationStatsCardProps {
  data: ConversationStats
  className?: string
  animationDelay?: number
}

export function ConversationStatsCard({
  data,
  className,
  animationDelay = 0
}: ConversationStatsCardProps) {
  // Show all relevant statuses, with awaiting review being the most common state
  const statusData = [
    { label: 'Awaiting Review', value: data.byStatus.awaitingReview, color: 'hsl(280 60% 55%)' },
    { label: 'Pending', value: data.byStatus.pending, color: 'hsl(40 90% 50%)' },
    { label: 'Processing', value: data.byStatus.processing, color: 'hsl(200.4 98% 50%)' },
    { label: 'Approved', value: data.byStatus.approved, color: 'hsl(135 45% 45%)' },
    { label: 'Rejected', value: data.byStatus.rejected, color: 'hsl(0 70% 50%)' },
  ]

  // Filter to only show statuses with values > 0 for cleaner display
  const activeStatusData = statusData.filter(item => item.value > 0)
  // If all are zero, show all statuses
  const displayData = activeStatusData.length > 0 ? activeStatusData : statusData

  return (
    <StatCard
      label="Conversations"
      value={data.total.toLocaleString()}
      subtitle="Total in system"
      icon={<MessageSquare />}
      animationDelay={animationDelay}
      accentColor="hsl(200.4 98% 38%)"
      className={className}
    >
      <div className="space-y-3">
        {/* Status breakdown mini chart */}
        <MiniBarChart data={displayData} />

        {/* Status legend */}
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          {displayData.map(item => (
            <div key={item.label} className="flex items-center gap-1.5">
              <div
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: item.color }}
              />
              <span className="text-muted-foreground">{item.label}:</span>
              <span className="font-medium text-foreground">{item.value}</span>
            </div>
          ))}
        </div>
      </div>
    </StatCard>
  )
}

// ==========================================
// Processing Metrics Card
// ==========================================
interface ProcessingMetricsCardProps {
  data: ProcessingMetrics
  className?: string
  animationDelay?: number
}

export function ProcessingMetricsCard({
  data,
  className,
  animationDelay = 0
}: ProcessingMetricsCardProps) {
  const successColor = data.successRate >= 80
    ? 'hsl(135 45% 45%)'
    : data.successRate >= 50
      ? 'hsl(40 90% 50%)'
      : 'hsl(0 70% 50%)'

  return (
    <StatCard
      label="Processing"
      value={`${data.successRate.toFixed(1)}%`}
      subtitle="Success rate"
      icon={<Activity />}
      animationDelay={animationDelay}
      accentColor={successColor}
      className={className}
    >
      <div className="space-y-3">
        {/* Success rate bar */}
        <ProgressBar
          value={data.successRate}
          max={100}
          color={successColor}
          showLabel={false}
          size="md"
        />

        {/* Metrics grid */}
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div className="flex items-center gap-1.5">
            <Clock className="w-3 h-3 text-muted-foreground" />
            <span className="text-muted-foreground">Avg:</span>
            <span className="font-medium">
              {data.averageTime > 0 ? `${data.averageTime.toFixed(1)}s` : 'N/A'}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <Loader2 className="w-3 h-3 text-muted-foreground" />
            <span className="text-muted-foreground">Queue:</span>
            <span className="font-medium">{data.queueSize}</span>
          </div>
        </div>
      </div>
    </StatCard>
  )
}

// ==========================================
// API Usage Cards (Gemini)
// ==========================================
interface ApiUsageCardProps {
  data: ApiUsage
  className?: string
  animationDelay?: number
}

export function GeminiUsageCard({
  data,
  className,
  animationDelay = 0
}: ApiUsageCardProps) {
  const usage = data.gemini
  const percentage = usage.dailyLimit > 0
    ? (usage.dailyUsed / usage.dailyLimit) * 100
    : 0

  const statusColor = usage.status === 'healthy'
    ? 'hsl(135 45% 45%)'
    : usage.status === 'warning'
      ? 'hsl(40 90% 50%)'
      : 'hsl(0 70% 50%)'

  return (
    <StatCard
      label="Gemini API"
      value={usage.dailyUsed.toLocaleString()}
      subtitle={`of ${usage.dailyLimit.toLocaleString()} daily limit`}
      icon={<Zap />}
      animationDelay={animationDelay}
      accentColor={statusColor}
      className={className}
    >
      <div className="space-y-3">
        {/* Usage bar */}
        <ProgressBar
          value={usage.dailyUsed}
          max={usage.dailyLimit}
          color={statusColor}
          showLabel={false}
          size="md"
        />

        {/* Status indicator */}
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5">
            {usage.status === 'healthy' ? (
              <CheckCircle2 className="w-3 h-3" style={{ color: statusColor }} />
            ) : (
              <XCircle className="w-3 h-3" style={{ color: statusColor }} />
            )}
            <span className="font-medium capitalize">{usage.status}</span>
          </div>
          <span className="text-muted-foreground">
            {percentage.toFixed(1)}% used
          </span>
        </div>
      </div>
    </StatCard>
  )
}

export function EmbeddingUsageCard({
  data,
  className,
  animationDelay = 0
}: ApiUsageCardProps) {
  const usage = data.embedding
  const percentage = usage.dailyLimit > 0
    ? (usage.dailyUsed / usage.dailyLimit) * 100
    : 0

  const statusColor = usage.status === 'healthy'
    ? 'hsl(135 45% 45%)'
    : usage.status === 'warning'
      ? 'hsl(40 90% 50%)'
      : 'hsl(0 70% 50%)'

  return (
    <StatCard
      label="Embeddings"
      value={usage.dailyUsed.toLocaleString()}
      subtitle={`of ${usage.dailyLimit.toLocaleString()} daily limit`}
      icon={<Database />}
      animationDelay={animationDelay}
      accentColor={statusColor}
      className={className}
    >
      <div className="space-y-3">
        {/* Usage bar */}
        <ProgressBar
          value={usage.dailyUsed}
          max={usage.dailyLimit}
          color={statusColor}
          showLabel={false}
          size="md"
        />

        {/* Status indicator */}
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5">
            {usage.status === 'healthy' ? (
              <CheckCircle2 className="w-3 h-3" style={{ color: statusColor }} />
            ) : (
              <XCircle className="w-3 h-3" style={{ color: statusColor }} />
            )}
            <span className="font-medium capitalize">{usage.status}</span>
          </div>
          <span className="text-muted-foreground">
            {percentage.toFixed(1)}% used
          </span>
        </div>
      </div>
    </StatCard>
  )
}

// ==========================================
// System Health Card
// ==========================================
interface SystemHealthCardProps {
  data: SystemHealth
  className?: string
  animationDelay?: number
}

export function SystemHealthCard({
  data,
  className,
  animationDelay = 0
}: SystemHealthCardProps) {
  const statusConfig = {
    excellent: { color: 'hsl(135 45% 45%)', icon: Heart },
    good: { color: 'hsl(135 35% 50%)', icon: Heart },
    fair: { color: 'hsl(40 90% 50%)', icon: Heart },
    poor: { color: 'hsl(0 70% 50%)', icon: Heart },
  }

  const config = statusConfig[data.status]

  return (
    <StatCard
      label="System Health"
      value={`${data.score}/100`}
      subtitle={`Status: ${data.status}`}
      icon={<config.icon />}
      animationDelay={animationDelay}
      accentColor={config.color}
      className={className}
    >
      <div className="space-y-3">
        {/* Health score bar */}
        <ProgressBar
          value={data.score}
          max={100}
          color={config.color}
          showLabel={false}
          size="md"
        />

        {/* Issues or uptime */}
        <div className="text-xs">
          {data.issues.length > 0 ? (
            <div className="space-y-1">
              {data.issues.slice(0, 2).map((issue, i) => (
                <div key={i} className="flex items-center gap-1.5 text-muted-foreground">
                  <XCircle className="w-3 h-3 text-amber-500" />
                  <span>{issue}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <CheckCircle2 className="w-3 h-3" style={{ color: config.color }} />
              <span>All systems operational</span>
            </div>
          )}
        </div>
      </div>
    </StatCard>
  )
}