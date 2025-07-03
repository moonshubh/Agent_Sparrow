/**
 * Analytics Store - Performance Metrics and Usage Statistics
 * 
 * Handles analytics data collection, performance monitoring,
 * and usage statistics for FeedMe system insights.
 */

import { create } from 'zustand'
import { devtools, subscribeWithSelector } from 'zustand/middleware'
import { 
  getApprovalWorkflowStats,
  getAnalytics,
  type ApprovalWorkflowStats
} from '@/lib/feedme-api'

// Types
export interface PerformanceMetrics {
  upload_success_rate: number
  avg_processing_time: number
  search_response_time: number
  system_health: number
  active_users: number
  websocket_connection_rate: number
  error_rate: number
  cache_hit_rate: number
}

export interface UsageStats {
  total_conversations: number
  total_examples: number
  searches_today: number
  uploads_today: number
  approvals_today: number
  most_active_folders: Array<{ folder_id: number; folder_name: string; activity_count: number }>
  trending_tags: Array<{ tag: string; usage_count: number }>
  user_activity: Array<{ date: string; active_users: number; actions: number }>
}

export interface SystemMetrics {
  cpu_usage: number
  memory_usage: number
  disk_usage: number
  network_latency: number
  database_connections: number
  redis_connections: number
  celery_queue_size: number
}

export interface QualityMetrics {
  avg_confidence_score: number
  avg_quality_score: number
  extraction_accuracy: number
  false_positive_rate: number
  user_satisfaction_score: number
  review_completion_rate: number
}

interface AnalyticsState {
  // Data State
  workflowStats: ApprovalWorkflowStats | null
  performanceMetrics: PerformanceMetrics | null
  usageStats: UsageStats | null
  systemMetrics: SystemMetrics | null
  qualityMetrics: QualityMetrics | null
  
  // UI State
  isLoading: boolean
  lastUpdated: string | null
  autoRefresh: boolean
  refreshInterval: number
  
  // Time Range
  timeRange: '1h' | '24h' | '7d' | '30d' | '90d'
  customDateRange: {
    from?: Date
    to?: Date
  }
  
  // Filters
  filters: {
    folders: number[]
    users: string[]
    platforms: string[]
  }
  
  // Error State
  error: string | null
}

interface AnalyticsActions {
  // Data Loading
  loadWorkflowStats: (forceRefresh?: boolean) => Promise<void>
  loadPerformanceMetrics: (forceRefresh?: boolean) => Promise<void>
  loadUsageStats: (forceRefresh?: boolean) => Promise<void>
  loadSystemMetrics: (forceRefresh?: boolean) => Promise<void>
  loadQualityMetrics: (forceRefresh?: boolean) => Promise<void>
  loadAllMetrics: (forceRefresh?: boolean) => Promise<void>
  
  // Time Range Management
  setTimeRange: (range: AnalyticsState['timeRange']) => void
  setCustomDateRange: (from?: Date, to?: Date) => void
  
  // Filters
  updateFilters: (filters: Partial<AnalyticsState['filters']>) => void
  clearFilters: () => void
  
  // Auto Refresh
  enableAutoRefresh: (interval?: number) => void
  disableAutoRefresh: () => void
  
  // Export
  exportAnalytics: (format: 'json' | 'csv' | 'pdf') => Promise<void>
  
  // Real-time Updates
  recordUserAction: (action: string, metadata?: Record<string, any>) => void
  recordPerformanceMetric: (metric: string, value: number, timestamp?: Date) => void
  
  // Utilities
  getMetricTrend: (metric: string, timeRange?: string) => Array<{ timestamp: string; value: number }>
  calculateGrowthRate: (metric: string, timeRange?: string) => number
  getTopPerformingFolders: (limit?: number) => Array<{ folder_id: number; score: number }>
}

export interface AnalyticsStore extends AnalyticsState {
  actions: AnalyticsActions
}

// Store Implementation
export const useAnalyticsStore = create<AnalyticsStore>()(
  devtools(
    subscribeWithSelector((set, get) => ({
      // Initial State
      workflowStats: null,
      performanceMetrics: null,
      usageStats: null,
      systemMetrics: null,
      qualityMetrics: null,
      
      isLoading: false,
      lastUpdated: null,
      autoRefresh: false,
      refreshInterval: 30000, // 30 seconds
      
      timeRange: '24h',
      customDateRange: {},
      
      filters: {
        folders: [],
        users: [],
        platforms: []
      },
      
      error: null,
      
      actions: {
        // ===========================
        // Data Loading
        // ===========================
        
        loadWorkflowStats: async (forceRefresh = false) => {
          const state = get()
          
          if (!forceRefresh && state.workflowStats && state.lastUpdated) {
            const lastUpdate = new Date(state.lastUpdated)
            const now = new Date()
            const diff = now.getTime() - lastUpdate.getTime()
            
            // Use cache if less than 5 minutes old
            if (diff < 5 * 60 * 1000) {
              return
            }
          }
          
          try {
            const stats = await getApprovalWorkflowStats()
            
            set(state => ({
              workflowStats: stats,
              lastUpdated: new Date().toISOString(),
              error: null
            }))
            
          } catch (error) {
            console.error('Failed to load workflow stats:', error)
            
            set({
              error: error instanceof Error ? error.message : 'Failed to load workflow stats'
            })
          }
        },
        
        loadPerformanceMetrics: async (forceRefresh = false) => {
          try {
            // Mock performance metrics - in real implementation, this would come from monitoring APIs
            const metrics: PerformanceMetrics = {
              upload_success_rate: 0.98,
              avg_processing_time: 2300, // ms
              search_response_time: 150, // ms
              system_health: 0.95,
              active_users: 24,
              websocket_connection_rate: 0.92,
              error_rate: 0.02,
              cache_hit_rate: 0.85
            }
            
            set({
              performanceMetrics: metrics,
              lastUpdated: new Date().toISOString(),
              error: null
            })
            
          } catch (error) {
            console.error('Failed to load performance metrics:', error)
            
            set({
              error: error instanceof Error ? error.message : 'Failed to load performance metrics'
            })
          }
        },
        
        loadUsageStats: async (forceRefresh = false) => {
          try {
            // Mock usage stats - in real implementation, this would come from analytics APIs
            const stats: UsageStats = {
              total_conversations: 1247,
              total_examples: 8532,
              searches_today: 145,
              uploads_today: 23,
              approvals_today: 67,
              most_active_folders: [
                { folder_id: 1, folder_name: 'Technical Support', activity_count: 234 },
                { folder_id: 2, folder_name: 'Account Issues', activity_count: 189 },
                { folder_id: 3, folder_name: 'Feature Requests', activity_count: 156 }
              ],
              trending_tags: [
                { tag: 'email-sync', usage_count: 89 },
                { tag: 'performance', usage_count: 67 },
                { tag: 'account-setup', usage_count: 45 }
              ],
              user_activity: [
                { date: '2024-01-01', active_users: 18, actions: 456 },
                { date: '2024-01-02', active_users: 22, actions: 523 },
                { date: '2024-01-03', active_users: 24, actions: 601 }
              ]
            }
            
            set({
              usageStats: stats,
              lastUpdated: new Date().toISOString(),
              error: null
            })
            
          } catch (error) {
            console.error('Failed to load usage stats:', error)
            
            set({
              error: error instanceof Error ? error.message : 'Failed to load usage stats'
            })
          }
        },
        
        loadSystemMetrics: async (forceRefresh = false) => {
          try {
            // Mock system metrics - in real implementation, this would come from system monitoring
            const metrics: SystemMetrics = {
              cpu_usage: 0.34,
              memory_usage: 0.67,
              disk_usage: 0.23,
              network_latency: 45, // ms
              database_connections: 12,
              redis_connections: 8,
              celery_queue_size: 3
            }
            
            set({
              systemMetrics: metrics,
              lastUpdated: new Date().toISOString(),
              error: null
            })
            
          } catch (error) {
            console.error('Failed to load system metrics:', error)
            
            set({
              error: error instanceof Error ? error.message : 'Failed to load system metrics'
            })
          }
        },
        
        loadQualityMetrics: async (forceRefresh = false) => {
          try {
            // Mock quality metrics - in real implementation, this would come from ML/AI APIs
            const metrics: QualityMetrics = {
              avg_confidence_score: 0.87,
              avg_quality_score: 0.91,
              extraction_accuracy: 0.94,
              false_positive_rate: 0.03,
              user_satisfaction_score: 4.2,
              review_completion_rate: 0.89
            }
            
            set({
              qualityMetrics: metrics,
              lastUpdated: new Date().toISOString(),
              error: null
            })
            
          } catch (error) {
            console.error('Failed to load quality metrics:', error)
            
            set({
              error: error instanceof Error ? error.message : 'Failed to load quality metrics'
            })
          }
        },
        
        loadAllMetrics: async (forceRefresh = false) => {
          set({ isLoading: true, error: null })
          
          try {
            await Promise.all([
              get().actions.loadWorkflowStats(forceRefresh),
              get().actions.loadPerformanceMetrics(forceRefresh),
              get().actions.loadUsageStats(forceRefresh),
              get().actions.loadSystemMetrics(forceRefresh),
              get().actions.loadQualityMetrics(forceRefresh)
            ])
            
          } catch (error) {
            console.error('Failed to load all metrics:', error)
          } finally {
            set({ isLoading: false })
          }
        },
        
        // ===========================
        // Time Range Management
        // ===========================
        
        setTimeRange: (range) => {
          set({ timeRange: range, customDateRange: {} })
          
          // Reload metrics with new time range
          get().actions.loadAllMetrics(true)
        },
        
        setCustomDateRange: (from, to) => {
          set({
            timeRange: '30d', // Default fallback
            customDateRange: { from, to }
          })
          
          // Reload metrics with custom range
          get().actions.loadAllMetrics(true)
        },
        
        // ===========================
        // Filters
        // ===========================
        
        updateFilters: (newFilters) => {
          set(state => ({
            filters: {
              ...state.filters,
              ...newFilters
            }
          }))
          
          // Reload metrics with new filters
          get().actions.loadAllMetrics(true)
        },
        
        clearFilters: () => {
          set({
            filters: {
              folders: [],
              users: [],
              platforms: []
            }
          })
          
          // Reload metrics without filters
          get().actions.loadAllMetrics(true)
        },
        
        // ===========================
        // Auto Refresh
        // ===========================
        
        enableAutoRefresh: (interval = 30000) => {
          const state = get()
          
          // Clear existing interval
          if (state.autoRefresh) {
            state.actions.disableAutoRefresh()
          }
          
          set({
            autoRefresh: true,
            refreshInterval: interval
          })
          
          // Set up interval
          const intervalId = setInterval(() => {
            get().actions.loadAllMetrics(true)
          }, interval)
          
          // Store interval ID for cleanup
          ;(globalThis as any).analyticsRefreshInterval = intervalId
        },
        
        disableAutoRefresh: () => {
          set({ autoRefresh: false })
          
          // Clear interval
          if ((globalThis as any).analyticsRefreshInterval) {
            clearInterval((globalThis as any).analyticsRefreshInterval)
            ;(globalThis as any).analyticsRefreshInterval = null
          }
        },
        
        // ===========================
        // Export
        // ===========================
        
        exportAnalytics: async (format) => {
          const state = get()
          
          const data = {
            export_timestamp: new Date().toISOString(),
            time_range: state.timeRange,
            custom_date_range: state.customDateRange,
            filters: state.filters,
            workflow_stats: state.workflowStats,
            performance_metrics: state.performanceMetrics,
            usage_stats: state.usageStats,
            system_metrics: state.systemMetrics,
            quality_metrics: state.qualityMetrics
          }
          
          if (format === 'json') {
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
            const url = URL.createObjectURL(blob)
            const link = document.createElement('a')
            link.href = url
            link.download = `feedme-analytics-${Date.now()}.json`
            link.click()
            URL.revokeObjectURL(url)
            
          } else if (format === 'csv') {
            // Flatten data for CSV export
            const csvData = [
              ['Metric', 'Value', 'Category'],
              // Performance metrics
              ...(state.performanceMetrics ? Object.entries(state.performanceMetrics).map(([key, value]) => [key, value, 'Performance']) : []),
              // Usage stats
              ...(state.usageStats ? Object.entries(state.usageStats).filter(([key, value]) => typeof value === 'number').map(([key, value]) => [key, value, 'Usage']) : []),
              // System metrics
              ...(state.systemMetrics ? Object.entries(state.systemMetrics).map(([key, value]) => [key, value, 'System']) : []),
              // Quality metrics
              ...(state.qualityMetrics ? Object.entries(state.qualityMetrics).map(([key, value]) => [key, value, 'Quality']) : [])
            ]
            
            const csvContent = csvData.map(row => row.map(cell => `"${cell}"`).join(',')).join('\n')
            
            const blob = new Blob([csvContent], { type: 'text/csv' })
            const url = URL.createObjectURL(blob)
            const link = document.createElement('a')
            link.href = url
            link.download = `feedme-analytics-${Date.now()}.csv`
            link.click()
            URL.revokeObjectURL(url)
            
          } else if (format === 'pdf') {
            // PDF export would require a PDF generation library
            console.log('PDF export not yet implemented')
          }
        },
        
        // ===========================
        // Real-time Updates
        // ===========================
        
        recordUserAction: (action, metadata = {}) => {
          // In a real implementation, this would send to analytics service
          console.log('User action recorded:', { action, metadata, timestamp: new Date().toISOString() })
        },
        
        recordPerformanceMetric: (metric, value, timestamp = new Date()) => {
          // In a real implementation, this would send to monitoring service
          console.log('Performance metric recorded:', { metric, value, timestamp: timestamp.toISOString() })
        },
        
        // ===========================
        // Utilities
        // ===========================
        
        getMetricTrend: (metric, timeRange = '24h') => {
          // Mock trend data - in real implementation, this would query time-series data
          const points = []
          const now = new Date()
          const hours = timeRange === '1h' ? 1 : timeRange === '24h' ? 24 : 168 // 7d = 168h
          
          for (let i = hours; i >= 0; i--) {
            const timestamp = new Date(now.getTime() - i * 60 * 60 * 1000)
            const value = Math.random() * 100 // Mock value
            
            points.push({
              timestamp: timestamp.toISOString(),
              value
            })
          }
          
          return points
        },
        
        calculateGrowthRate: (metric, timeRange = '24h') => {
          const trend = get().actions.getMetricTrend(metric, timeRange)
          
          if (trend.length < 2) return 0
          
          const first = trend[0].value
          const last = trend[trend.length - 1].value
          
          return ((last - first) / first) * 100
        },
        
        getTopPerformingFolders: (limit = 5) => {
          const state = get()
          
          if (!state.usageStats?.most_active_folders) return []
          
          return state.usageStats.most_active_folders
            .map(folder => ({
              folder_id: folder.folder_id,
              score: folder.activity_count
            }))
            .slice(0, limit)
        }
      }
    })),
    {
      name: 'feedme-analytics-store'
    }
  )
)

// Convenience hooks
export const useAnalytics = () => useAnalyticsStore(state => ({
  workflowStats: state.workflowStats,
  performanceMetrics: state.performanceMetrics,
  usageStats: state.usageStats,
  systemMetrics: state.systemMetrics,
  qualityMetrics: state.qualityMetrics,
  isLoading: state.isLoading,
  lastUpdated: state.lastUpdated,
  error: state.error
}))

export const useAnalyticsConfig = () => useAnalyticsStore(state => ({
  timeRange: state.timeRange,
  customDateRange: state.customDateRange,
  filters: state.filters,
  autoRefresh: state.autoRefresh,
  refreshInterval: state.refreshInterval
}))

export const useAnalyticsActions = () => useAnalyticsStore(state => state.actions)

// Auto-cleanup on page unload
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    useAnalyticsStore.getState().actions.disableAutoRefresh()
  })
}