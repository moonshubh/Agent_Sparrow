/**
 * AnalyticsDashboard Component
 * 
 * Real-time search performance metrics with visual charts,
 * usage analytics from Phase 2 backend, and performance optimization suggestions.
 * 
 * Part of FeedMe v2.0 Phase 3D: Advanced Search Interface
 */

'use client'

import React, { useState, useCallback, useMemo, useEffect } from 'react'
import { 
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, 
  AreaChart, Area, ResponsiveContainer, XAxis, YAxis, 
  CartesianGrid, Tooltip, Legend, RadialBarChart, RadialBar
} from 'recharts'
import { 
  TrendingUp, TrendingDown, Activity, Users, Search, 
  Clock, Target, Zap, Eye, Download, RefreshCw, Filter,
  Calendar, BarChart3, PieChart as PieChartIcon, LineChart as LineChartIcon,
  Settings, AlertCircle, CheckCircle2, ArrowUpRight, ArrowDownRight,
  Star, Tag, FileText, MessageCircle, Brain, Shield
} from 'lucide-react'
import { useAnalytics, useActions } from '@/lib/stores/feedme-store'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Tooltip as UITooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

// Types
interface AnalyticsDashboardProps {
  timeRange?: 'hour' | 'day' | 'week' | 'month' | 'year'
  refreshInterval?: number
  enableRealTime?: boolean
  className?: string
}

interface SearchMetrics {
  totalSearches: number
  uniqueUsers: number
  avgResponseTime: number
  successRate: number
  totalResults: number
  clickThroughRate: number
  conversionRate: number
  popularQueries: PopularQuery[]
  trendingTags: TrendingTag[]
  userEngagement: UserEngagement
  performanceMetrics: PerformanceMetrics
  qualityMetrics: QualityMetrics
  systemHealth: SystemHealth
}

interface PopularQuery {
  query: string
  count: number
  avgResults: number
  successRate: number
  trend: 'up' | 'down' | 'stable'
}

interface TrendingTag {
  tag: string
  count: number
  growth: number
  category: string
}

interface UserEngagement {
  sessionsWithSearch: number
  avgSessionDuration: number
  bounceRate: number
  returnUsers: number
  searchDepth: number
  refinementRate: number
}

interface PerformanceMetrics {
  searchLatency: number[]
  indexingTime: number
  cacheHitRate: number
  errorRate: number
  throughput: number
  resourceUsage: ResourceUsage
}

interface ResourceUsage {
  cpu: number
  memory: number
  storage: number
  network: number
}

interface QualityMetrics {
  resultRelevance: number
  userSatisfaction: number
  precisionAtK: number
  recallAtK: number
  diversityScore: number
}

interface SystemHealth {
  uptime: number
  availability: number
  errorCount: number
  warningCount: number
  lastIncident: string | null
  status: 'healthy' | 'warning' | 'error'
}

interface TimeSeriesData {
  timestamp: string
  searches: number
  users: number
  responseTime: number
  successRate: number
}

// Metric Card Component
const MetricCard: React.FC<{
  title: string
  value: string | number
  change?: number
  trend?: 'up' | 'down' | 'stable'
  icon: React.ComponentType<{ className?: string }>
  description?: string
  format?: 'number' | 'percentage' | 'duration' | 'bytes'
}> = ({ title, value, change, trend, icon: Icon, description, format = 'number' }) => {
  const formatValue = (val: string | number) => {
    if (typeof val === 'string') return val
    
    switch (format) {
      case 'percentage':
        return `${Math.round(val * 100)}%`
      case 'duration':
        return `${val}ms`
      case 'bytes':
        return `${(val / 1024 / 1024).toFixed(1)}MB`
      default:
        return val.toLocaleString()
    }
  }

  const getTrendIcon = () => {
    if (!change || !trend) return null
    
    switch (trend) {
      case 'up':
        return <ArrowUpRight className="h-3 w-3 text-green-600" />
      case 'down':
        return <ArrowDownRight className="h-3 w-3 text-red-600" />
      default:
        return null
    }
  }

  const getTrendColor = () => {
    if (!change || !trend) return 'text-muted-foreground'
    return trend === 'up' ? 'text-green-600' : 'text-red-600'
  }

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">{title}</span>
          </div>
          {getTrendIcon()}
        </div>
        
        <div className="mt-2">
          <div className="text-2xl font-bold">{formatValue(value)}</div>
          {change !== undefined && (
            <div className={cn('text-xs flex items-center gap-1', getTrendColor())}>
              {change > 0 ? '+' : ''}{change}% from last period
            </div>
          )}
          {description && (
            <div className="text-xs text-muted-foreground mt-1">{description}</div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// Chart Card Component
const ChartCard: React.FC<{
  title: string
  children: React.ReactNode
  action?: React.ReactNode
  description?: string
}> = ({ title, children, action, description }) => {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <div>
          <CardTitle className="text-base font-medium">{title}</CardTitle>
          {description && (
            <p className="text-xs text-muted-foreground mt-1">{description}</p>
          )}
        </div>
        {action}
      </CardHeader>
      <CardContent>
        {children}
      </CardContent>
    </Card>
  )
}

// Performance Status Component
const PerformanceStatus: React.FC<{
  metrics: PerformanceMetrics
  health: SystemHealth
}> = ({ metrics, health }) => {
  const getStatusColor = (status: SystemHealth['status']) => {
    switch (status) {
      case 'healthy': return 'text-green-600 bg-green-100'
      case 'warning': return 'text-yellow-600 bg-yellow-100'
      case 'error': return 'text-red-600 bg-red-100'
    }
  }

  const getStatusIcon = (status: SystemHealth['status']) => {
    switch (status) {
      case 'healthy': return <CheckCircle2 className="h-4 w-4" />
      case 'warning': return <AlertCircle className="h-4 w-4" />
      case 'error': return <AlertCircle className="h-4 w-4" />
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-medium flex items-center gap-2">
          <Shield className="h-4 w-4" />
          System Performance
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Overall Status */}
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">Status</span>
          <div className={cn('flex items-center gap-2 px-3 py-1 rounded-full text-sm', getStatusColor(health.status))}>
            {getStatusIcon(health.status)}
            {health.status.toUpperCase()}
          </div>
        </div>

        {/* Key Metrics */}
        <div className="space-y-3">
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span>Uptime</span>
              <span className="font-medium">{Math.round(health.uptime * 100)}%</span>
            </div>
            <Progress value={health.uptime * 100} className="h-2" />
          </div>

          <div>
            <div className="flex justify-between text-sm mb-1">
              <span>Cache Hit Rate</span>
              <span className="font-medium">{Math.round(metrics.cacheHitRate * 100)}%</span>
            </div>
            <Progress value={metrics.cacheHitRate * 100} className="h-2" />
          </div>

          <div>
            <div className="flex justify-between text-sm mb-1">
              <span>Error Rate</span>
              <span className="font-medium">{(metrics.errorRate * 100).toFixed(2)}%</span>
            </div>
            <Progress 
              value={metrics.errorRate * 100} 
              className={cn('h-2', metrics.errorRate > 0.05 && 'bg-red-100')} 
            />
          </div>
        </div>

        {/* Resource Usage */}
        <div>
          <h4 className="text-sm font-medium mb-2">Resource Usage</h4>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="flex justify-between">
              <span>CPU:</span>
              <span className="font-medium">{Math.round(metrics.resourceUsage.cpu)}%</span>
            </div>
            <div className="flex justify-between">
              <span>Memory:</span>
              <span className="font-medium">{Math.round(metrics.resourceUsage.memory)}%</span>
            </div>
            <div className="flex justify-between">
              <span>Storage:</span>
              <span className="font-medium">{Math.round(metrics.resourceUsage.storage)}%</span>
            </div>
            <div className="flex justify-between">
              <span>Network:</span>
              <span className="font-medium">{Math.round(metrics.resourceUsage.network)}%</span>
            </div>
          </div>
        </div>

        {/* Recent Issues */}
        {(health.errorCount > 0 || health.warningCount > 0) && (
          <Alert>
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="text-xs">
              {health.errorCount > 0 && `${health.errorCount} errors, `}
              {health.warningCount > 0 && `${health.warningCount} warnings`}
              {health.lastIncident && ` • Last: ${new Date(health.lastIncident).toLocaleString()}`}
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}

// Popular Queries Table
const PopularQueriesTable: React.FC<{
  queries: PopularQuery[]
  onQueryClick?: (query: string) => void
}> = ({ queries, onQueryClick }) => {
  return (
    <div className="space-y-2">
      {queries.map((query, index) => (
        <div 
          key={index} 
          className="flex items-center justify-between p-2 hover:bg-muted rounded cursor-pointer"
          onClick={() => onQueryClick?.(query.query)}
        >
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <span className="text-xs text-muted-foreground w-4">{index + 1}</span>
            <span className="text-sm truncate">{query.query}</span>
            {query.trend === 'up' && <TrendingUp className="h-3 w-3 text-green-600" />}
            {query.trend === 'down' && <TrendingDown className="h-3 w-3 text-red-600" />}
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span>{query.count} searches</span>
            <span>{Math.round(query.successRate * 100)}% success</span>
          </div>
        </div>
      ))}
    </div>
  )
}

// Trending Tags Cloud
const TrendingTagsCloud: React.FC<{
  tags: TrendingTag[]
  onTagClick?: (tag: string) => void
}> = ({ tags, onTagClick }) => {
  const maxCount = Math.max(...tags.map(t => t.count))
  
  return (
    <div className="flex gap-2 flex-wrap">
      {tags.map((tag, index) => {
        const size = Math.max(0.7, (tag.count / maxCount) * 1.5)
        const growthColor = tag.growth > 0 ? 'text-green-600' : tag.growth < 0 ? 'text-red-600' : 'text-muted-foreground'
        
        return (
          <TooltipProvider key={index}>
            <UITooltip>
              <TooltipTrigger>
                <Badge 
                  variant="outline" 
                  className="cursor-pointer hover:bg-accent transition-colors"
                  style={{ fontSize: `${size * 0.75}rem` }}
                  onClick={() => onTagClick?.(tag.tag)}
                >
                  {tag.tag}
                </Badge>
              </TooltipTrigger>
              <TooltipContent>
                <div className="text-xs">
                  <div>{tag.count} uses</div>
                  <div className={growthColor}>
                    {tag.growth > 0 ? '+' : ''}{tag.growth}% growth
                  </div>
                  <div className="text-muted-foreground">{tag.category}</div>
                </div>
              </TooltipContent>
            </UITooltip>
          </TooltipProvider>
        )
      })}
    </div>
  )
}

// Main Component
export const AnalyticsDashboard: React.FC<AnalyticsDashboardProps> = ({
  timeRange = 'day',
  refreshInterval = 30000,
  enableRealTime = true,
  className
}) => {
  const { workflowStats, performanceMetrics, usageStats, isLoading } = useAnalytics()
  const { loadAnalytics, refreshAnalytics } = useActions()

  const [selectedTimeRange, setSelectedTimeRange] = useState(timeRange)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [activeTab, setActiveTab] = useState('overview')

  // Mock analytics data (in real app, this would come from the store)
  const mockMetrics: SearchMetrics = {
    totalSearches: 12847,
    uniqueUsers: 3241,
    avgResponseTime: 245,
    successRate: 0.92,
    totalResults: 156789,
    clickThroughRate: 0.68,
    conversionRate: 0.34,
    popularQueries: [
      { query: 'email sync issues', count: 1247, avgResults: 23, successRate: 0.89, trend: 'up' },
      { query: 'mailbird settings', count: 982, avgResults: 18, successRate: 0.94, trend: 'stable' },
      { query: 'account setup help', count: 756, avgResults: 31, successRate: 0.87, trend: 'up' },
      { query: 'troubleshooting guide', count: 643, avgResults: 42, successRate: 0.91, trend: 'down' },
      { query: 'performance issues', count: 521, avgResults: 27, successRate: 0.85, trend: 'up' }
    ],
    trendingTags: [
      { tag: 'sync', count: 3421, growth: 15.2, category: 'Issues' },
      { tag: 'settings', count: 2876, growth: 8.7, category: 'Configuration' },
      { tag: 'troubleshooting', count: 2543, growth: -3.1, category: 'Support' },
      { tag: 'performance', count: 1987, growth: 22.4, category: 'Issues' },
      { tag: 'email', count: 1654, growth: 5.8, category: 'Core' }
    ],
    userEngagement: {
      sessionsWithSearch: 8432,
      avgSessionDuration: 247,
      bounceRate: 0.23,
      returnUsers: 2154,
      searchDepth: 2.4,
      refinementRate: 0.41
    },
    performanceMetrics: {
      searchLatency: [120, 145, 167, 134, 198, 156, 143],
      indexingTime: 3.2,
      cacheHitRate: 0.85,
      errorRate: 0.02,
      throughput: 456,
      resourceUsage: {
        cpu: 42,
        memory: 67,
        storage: 34,
        network: 23
      }
    },
    qualityMetrics: {
      resultRelevance: 0.87,
      userSatisfaction: 0.84,
      precisionAtK: 0.91,
      recallAtK: 0.78,
      diversityScore: 0.73
    },
    systemHealth: {
      uptime: 0.999,
      availability: 0.998,
      errorCount: 3,
      warningCount: 7,
      lastIncident: '2025-07-01T14:30:00Z',
      status: 'healthy'
    }
  }

  // Mock time series data
  const timeSeriesData: TimeSeriesData[] = [
    { timestamp: '00:00', searches: 245, users: 67, responseTime: 156, successRate: 0.91 },
    { timestamp: '04:00', searches: 123, users: 34, responseTime: 134, successRate: 0.94 },
    { timestamp: '08:00', searches: 567, users: 145, responseTime: 167, successRate: 0.89 },
    { timestamp: '12:00', searches: 892, users: 234, responseTime: 198, successRate: 0.92 },
    { timestamp: '16:00', searches: 1234, users: 298, responseTime: 143, successRate: 0.95 },
    { timestamp: '20:00', searches: 756, users: 187, responseTime: 134, successRate: 0.93 }
  ]

  // Auto-refresh effect
  useEffect(() => {
    if (!enableRealTime) return

    const interval = setInterval(() => {
      handleRefresh()
    }, refreshInterval)

    return () => clearInterval(interval)
  }, [enableRealTime, refreshInterval])

  // Handle refresh
  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true)
    try {
      await refreshAnalytics()
    } catch (error) {
      console.error('Failed to refresh analytics:', error)
    } finally {
      setIsRefreshing(false)
    }
  }, [refreshAnalytics])

  // Handle export
  const handleExport = useCallback(() => {
    const exportData = {
      metrics: mockMetrics,
      timeRange: selectedTimeRange,
      generatedAt: new Date().toISOString()
    }
    
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `feedme-analytics-${selectedTimeRange}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, [mockMetrics, selectedTimeRange])

  return (
    <div className={cn('h-full flex flex-col', className)}>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-medium flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            Search Analytics
          </h2>
          {enableRealTime && (
            <Badge variant="outline" className="text-xs">
              <div className="w-2 h-2 bg-green-500 rounded-full mr-1 animate-pulse" />
              Live
            </Badge>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Select value={selectedTimeRange} onValueChange={(value) => setSelectedTimeRange(value as 'hour' | 'day' | 'week' | 'month' | 'year')}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="hour">Last Hour</SelectItem>
              <SelectItem value="day">Last Day</SelectItem>
              <SelectItem value="week">Last Week</SelectItem>
              <SelectItem value="month">Last Month</SelectItem>
              <SelectItem value="year">Last Year</SelectItem>
            </SelectContent>
          </Select>

          <Button variant="outline" size="sm" onClick={handleExport}>
            <Download className="h-3 w-3 mr-1" />
            Export
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={isRefreshing}
          >
            <RefreshCw className={cn('h-3 w-3 mr-1', isRefreshing && 'animate-spin')} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full">
          <div className="px-4 pt-4">
            <TabsList className="grid w-full grid-cols-4">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="performance">Performance</TabsTrigger>
              <TabsTrigger value="engagement">Engagement</TabsTrigger>
              <TabsTrigger value="insights">Insights</TabsTrigger>
            </TabsList>
          </div>

          <ScrollArea className="flex-1 p-4">
            <TabsContent value="overview" className="space-y-6 mt-0">
              {/* Key Metrics */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <MetricCard
                  title="Total Searches"
                  value={mockMetrics.totalSearches}
                  change={12.5}
                  trend="up"
                  icon={Search}
                  description="Searches performed"
                />
                <MetricCard
                  title="Unique Users"
                  value={mockMetrics.uniqueUsers}
                  change={8.2}
                  trend="up"
                  icon={Users}
                  description="Active searchers"
                />
                <MetricCard
                  title="Avg Response"
                  value={mockMetrics.avgResponseTime}
                  change={-5.1}
                  trend="down"
                  icon={Clock}
                  format="duration"
                  description="Search latency"
                />
                <MetricCard
                  title="Success Rate"
                  value={mockMetrics.successRate}
                  change={2.3}
                  trend="up"
                  icon={Target}
                  format="percentage"
                  description="Successful searches"
                />
              </div>

              {/* Charts */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <ChartCard 
                  title="Search Volume" 
                  description="Search activity over time"
                  action={
                    <Button variant="ghost" size="sm">
                      <LineChartIcon className="h-3 w-3" />
                    </Button>
                  }
                >
                  <ResponsiveContainer width="100%" height={200}>
                    <AreaChart data={timeSeriesData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="timestamp" />
                      <YAxis />
                      <Tooltip />
                      <Area type="monotone" dataKey="searches" stroke="#0095ff" fill="#0095ff" fillOpacity={0.3} />
                    </AreaChart>
                  </ResponsiveContainer>
                </ChartCard>

                <ChartCard 
                  title="Response Time" 
                  description="Search performance metrics"
                  action={
                    <Button variant="ghost" size="sm">
                      <BarChart3 className="h-3 w-3" />
                    </Button>
                  }
                >
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={timeSeriesData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="timestamp" />
                      <YAxis />
                      <Tooltip />
                      <Line type="monotone" dataKey="responseTime" stroke="#22c55e" strokeWidth={2} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
              </div>

              {/* Popular Queries and Trending Tags */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <ChartCard title="Popular Queries" description="Most searched terms">
                  <PopularQueriesTable 
                    queries={mockMetrics.popularQueries} 
                    onQueryClick={(query) => console.log('Search:', query)}
                  />
                </ChartCard>

                <ChartCard title="Trending Tags" description="Popular tags and growth">
                  <TrendingTagsCloud 
                    tags={mockMetrics.trendingTags}
                    onTagClick={(tag) => console.log('Filter by tag:', tag)}
                  />
                </ChartCard>
              </div>
            </TabsContent>

            <TabsContent value="performance" className="space-y-6 mt-0">
              {/* Performance Overview */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <MetricCard
                  title="Cache Hit Rate"
                  value={mockMetrics.performanceMetrics.cacheHitRate}
                  change={3.2}
                  trend="up"
                  icon={Zap}
                  format="percentage"
                />
                <MetricCard
                  title="Error Rate"
                  value={mockMetrics.performanceMetrics.errorRate}
                  change={-15.7}
                  trend="down"
                  icon={AlertCircle}
                  format="percentage"
                />
                <MetricCard
                  title="Throughput"
                  value={mockMetrics.performanceMetrics.throughput}
                  change={8.9}
                  trend="up"
                  icon={Activity}
                  description="req/sec"
                />
                <MetricCard
                  title="Indexing Time"
                  value={mockMetrics.performanceMetrics.indexingTime}
                  change={-12.3}
                  trend="down"
                  icon={Clock}
                  description="seconds"
                />
              </div>

              {/* Performance Charts and System Status */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <PerformanceStatus 
                  metrics={mockMetrics.performanceMetrics}
                  health={mockMetrics.systemHealth}
                />

                <ChartCard title="Response Time Distribution">
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={mockMetrics.performanceMetrics.searchLatency.map((time, index) => ({ 
                      range: `${index * 50}-${(index + 1) * 50}ms`, 
                      count: time 
                    }))}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="range" />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="count" fill="#0095ff" />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>
              </div>
            </TabsContent>

            <TabsContent value="engagement" className="space-y-6 mt-0">
              {/* Engagement Metrics */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <MetricCard
                  title="CTR"
                  value={mockMetrics.clickThroughRate}
                  change={4.7}
                  trend="up"
                  icon={Eye}
                  format="percentage"
                  description="Click-through rate"
                />
                <MetricCard
                  title="Conversion"
                  value={mockMetrics.conversionRate}
                  change={6.2}
                  trend="up"
                  icon={Target}
                  format="percentage"
                  description="Goal completion"
                />
                <MetricCard
                  title="Bounce Rate"
                  value={mockMetrics.userEngagement.bounceRate}
                  change={-3.1}
                  trend="down"
                  icon={TrendingDown}
                  format="percentage"
                />
                <MetricCard
                  title="Return Users"
                  value={mockMetrics.userEngagement.returnUsers}
                  change={15.8}
                  trend="up"
                  icon={Users}
                  description="Returning searchers"
                />
              </div>

              {/* Engagement Charts */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <ChartCard title="User Activity" description="Searches by time of day">
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={timeSeriesData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="timestamp" />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="users" fill="#8b5cf6" />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>

                <ChartCard title="Success Rate Trend" description="Search success over time">
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={timeSeriesData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="timestamp" />
                      <YAxis domain={[0.8, 1]} />
                      <Tooltip />
                      <Line type="monotone" dataKey="successRate" stroke="#10b981" strokeWidth={2} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>
              </div>
            </TabsContent>

            <TabsContent value="insights" className="space-y-6 mt-0">
              {/* Quality Metrics */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <MetricCard
                  title="Relevance"
                  value={mockMetrics.qualityMetrics.resultRelevance}
                  change={2.1}
                  trend="up"
                  icon={Star}
                  format="percentage"
                />
                <MetricCard
                  title="Satisfaction"
                  value={mockMetrics.qualityMetrics.userSatisfaction}
                  change={5.3}
                  trend="up"
                  icon={CheckCircle2}
                  format="percentage"
                />
                <MetricCard
                  title="Precision@10"
                  value={mockMetrics.qualityMetrics.precisionAtK}
                  change={1.8}
                  trend="up"
                  icon={Target}
                  format="percentage"
                />
                <MetricCard
                  title="Diversity"
                  value={mockMetrics.qualityMetrics.diversityScore}
                  change={-1.2}
                  trend="down"
                  icon={Brain}
                  format="percentage"
                />
              </div>

              {/* Insights and Recommendations */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base font-medium">Key Insights</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <Alert>
                      <TrendingUp className="h-4 w-4" />
                      <AlertDescription>
                        Search volume increased 12.5% with mobile users driving 65% of the growth.
                      </AlertDescription>
                    </Alert>
                    <Alert>
                      <Brain className="h-4 w-4" />
                      <AlertDescription>
                        AI-powered suggestions improved success rate by 8.2% for complex queries.
                      </AlertDescription>
                    </Alert>
                    <Alert>
                      <Target className="h-4 w-4" />
                      <AlertDescription>
                        Users with filtered searches show 34% higher engagement rates.
                      </AlertDescription>
                    </Alert>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base font-medium">Optimization Recommendations</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3 text-sm">
                    <div className="flex items-start gap-2">
                      <Badge variant="outline" className="text-xs">High</Badge>
                      <span>Implement query suggestions for incomplete searches to reduce refinement rate.</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <Badge variant="outline" className="text-xs">Med</Badge>
                      <span>Add more tag-based filters to improve result precision for power users.</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <Badge variant="outline" className="text-xs">Low</Badge>
                      <span>Consider A/B testing different result layouts to improve click-through rates.</span>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </TabsContent>
          </ScrollArea>
        </Tabs>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between p-2 border-t text-xs text-muted-foreground">
        <div className="flex items-center gap-4">
          <span>Last updated: {new Date().toLocaleTimeString()}</span>
          <span>Data range: {selectedTimeRange}</span>
        </div>
        <div className="flex items-center gap-4">
          <span>{mockMetrics.totalResults.toLocaleString()} total results indexed</span>
          <span>System health: {mockMetrics.systemHealth.status}</span>
        </div>
      </div>
    </div>
  )
}

export default AnalyticsDashboard