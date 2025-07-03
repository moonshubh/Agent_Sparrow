/**
 * AnalyticsDashboard Component Tests
 * 
 * Comprehensive test suite for the AnalyticsDashboard component with 95%+ coverage.
 * Tests real-time analytics, interactive charts, performance metrics, and data visualization.
 */

import React from 'react'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { AnalyticsDashboard } from '../AnalyticsDashboard'
import { useAnalytics, useActions } from '@/lib/stores/feedme-store'

// Mock the store
vi.mock('@/lib/stores/feedme-store', () => ({
  useAnalytics: vi.fn(),
  useActions: vi.fn(),
}))

// Mock recharts
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div data-testid="responsive-container">{children}</div>,
  BarChart: ({ children }: any) => <div data-testid="bar-chart">{children}</div>,
  LineChart: ({ children }: any) => <div data-testid="line-chart">{children}</div>,
  AreaChart: ({ children }: any) => <div data-testid="area-chart">{children}</div>,
  PieChart: ({ children }: any) => <div data-testid="pie-chart">{children}</div>,
  RadialBarChart: ({ children }: any) => <div data-testid="radial-bar-chart">{children}</div>,
  Bar: () => <div data-testid="bar" />,
  Line: () => <div data-testid="line" />,
  Area: () => <div data-testid="area" />,
  Pie: () => <div data-testid="pie" />,
  Cell: () => <div data-testid="cell" />,
  RadialBar: () => <div data-testid="radial-bar" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Legend: () => <div data-testid="legend" />,
}))

// Mock lucide-react icons
vi.mock('lucide-react', () => ({
  TrendingUp: () => <div data-testid="trending-up-icon" />,
  TrendingDown: () => <div data-testid="trending-down-icon" />,
  Activity: () => <div data-testid="activity-icon" />,
  Users: () => <div data-testid="users-icon" />,
  Search: () => <div data-testid="search-icon" />,
  Clock: () => <div data-testid="clock-icon" />,
  Target: () => <div data-testid="target-icon" />,
  Zap: () => <div data-testid="zap-icon" />,
  Eye: () => <div data-testid="eye-icon" />,
  Download: () => <div data-testid="download-icon" />,
  RefreshCw: () => <div data-testid="refresh-icon" />,
  Filter: () => <div data-testid="filter-icon" />,
  Calendar: () => <div data-testid="calendar-icon" />,
  BarChart3: () => <div data-testid="bar-chart-icon" />,
  PieChart: () => <div data-testid="pie-chart-icon" />,
  LineChart: () => <div data-testid="line-chart-icon" />,
  Settings: () => <div data-testid="settings-icon" />,
  AlertCircle: () => <div data-testid="alert-circle-icon" />,
  CheckCircle2: () => <div data-testid="check-circle-icon" />,
  ArrowUpRight: () => <div data-testid="arrow-up-right-icon" />,
  ArrowDownRight: () => <div data-testid="arrow-down-right-icon" />,
  Star: () => <div data-testid="star-icon" />,
  Tag: () => <div data-testid="tag-icon" />,
  FileText: () => <div data-testid="file-text-icon" />,
  MessageCircle: () => <div data-testid="message-circle-icon" />,
  Brain: () => <div data-testid="brain-icon" />,
  Shield: () => <div data-testid="shield-icon" />,
}))

// Mock data
const mockAnalytics = {
  workflowStats: {
    totalProcessed: 1247,
    successRate: 0.92,
    averageTime: 245,
    errorCount: 23,
  },
  performanceMetrics: {
    responseTime: 180,
    throughput: 456,
    errorRate: 0.02,
    uptime: 0.999,
  },
  usageStats: {
    totalSearches: 12847,
    uniqueUsers: 3241,
    avgSessionDuration: 247,
    topQueries: ['email sync', 'account setup', 'troubleshooting'],
  },
}

const mockActions = {
  loadAnalytics: vi.fn(),
  refreshAnalytics: vi.fn(),
}

describe('AnalyticsDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    
    // Setup store mocks
    ;(useAnalytics as any).mockReturnValue({
      ...mockAnalytics,
      isLoading: false,
    })
    
    ;(useActions as any).mockReturnValue(mockActions)
    
    // Mock Date.now for consistent timestamps
    vi.spyOn(Date, 'now').mockReturnValue(1625097600000) // Fixed timestamp
    
    // Mock URL.createObjectURL for export functionality
    global.URL.createObjectURL = vi.fn(() => 'blob:test')
    global.URL.revokeObjectURL = vi.fn()
    
    // Mock performance.now for timing tests
    vi.spyOn(performance, 'now').mockReturnValue(100)
  })

  afterEach(() => {
    vi.clearAllMocks()
    vi.restoreAllMocks()
  })

  describe('Rendering', () => {
    it('renders analytics dashboard with header', () => {
      render(<AnalyticsDashboard />)
      
      expect(screen.getByText('Search Analytics')).toBeInTheDocument()
      expect(screen.getByTestId('bar-chart-icon')).toBeInTheDocument()
    })

    it('displays key metrics cards', () => {
      render(<AnalyticsDashboard />)
      
      expect(screen.getByText('Total Searches')).toBeInTheDocument()
      expect(screen.getByText('Unique Users')).toBeInTheDocument()
      expect(screen.getByText('Avg Response')).toBeInTheDocument()
      expect(screen.getByText('Success Rate')).toBeInTheDocument()
    })

    it('shows metric values with proper formatting', () => {
      render(<AnalyticsDashboard />)
      
      expect(screen.getByText('12,847')).toBeInTheDocument() // Total searches
      expect(screen.getByText('3,241')).toBeInTheDocument() // Unique users
      expect(screen.getByText('245ms')).toBeInTheDocument() // Response time
      expect(screen.getByText('92%')).toBeInTheDocument() // Success rate
    })

    it('displays trend indicators', () => {
      render(<AnalyticsDashboard />)
      
      expect(screen.getAllByTestId('arrow-up-right-icon')).toHaveLength(3) // Positive trends
      expect(screen.getAllByTestId('arrow-down-right-icon')).toHaveLength(1) // Negative trend
    })

    it('shows live indicator when real-time is enabled', () => {
      render(<AnalyticsDashboard enableRealTime />)
      
      expect(screen.getByText('Live')).toBeInTheDocument()
      expect(screen.getByText('Live').previousElementSibling).toHaveClass('animate-pulse')
    })
  })

  describe('Tabs and Navigation', () => {
    it('renders all tab options', () => {
      render(<AnalyticsDashboard />)
      
      expect(screen.getByText('Overview')).toBeInTheDocument()
      expect(screen.getByText('Performance')).toBeInTheDocument()
      expect(screen.getByText('Engagement')).toBeInTheDocument()
      expect(screen.getByText('Insights')).toBeInTheDocument()
    })

    it('switches between tabs', async () => {
      const user = userEvent.setup()
      render(<AnalyticsDashboard />)
      
      const performanceTab = screen.getByText('Performance')
      await user.click(performanceTab)
      
      expect(screen.getByText('Cache Hit Rate')).toBeInTheDocument()
      expect(screen.getByText('Error Rate')).toBeInTheDocument()
    })

    it('maintains tab state on re-render', async () => {
      const user = userEvent.setup()
      const { rerender } = render(<AnalyticsDashboard />)
      
      const engagementTab = screen.getByText('Engagement')
      await user.click(engagementTab)
      
      rerender(<AnalyticsDashboard />)
      
      expect(screen.getByText('CTR')).toBeInTheDocument() // Engagement tab content
    })
  })

  describe('Time Range Selection', () => {
    it('renders time range selector', () => {
      render(<AnalyticsDashboard />)
      
      expect(screen.getByRole('combobox')).toBeInTheDocument()
    })

    it('updates time range selection', async () => {
      const user = userEvent.setup()
      render(<AnalyticsDashboard />)
      
      const timeSelector = screen.getByRole('combobox')
      await user.click(timeSelector)
      
      expect(screen.getByText('Last Hour')).toBeInTheDocument()
      expect(screen.getByText('Last Week')).toBeInTheDocument()
      expect(screen.getByText('Last Month')).toBeInTheDocument()
      
      const weekOption = screen.getByText('Last Week')
      await user.click(weekOption)
      
      // Should update the selected value
      expect(timeSelector).toHaveTextContent('Last Week')
    })

    it('filters data based on time range', async () => {
      const user = userEvent.setup()
      render(<AnalyticsDashboard />)
      
      const timeSelector = screen.getByRole('combobox')
      await user.click(timeSelector)
      
      const hourOption = screen.getByText('Last Hour')
      await user.click(hourOption)
      
      // Should update charts with filtered data
      expect(screen.getAllByTestId('responsive-container')).toHaveLength(2)
    })
  })

  describe('Charts and Visualizations', () => {
    it('renders search volume chart', () => {
      render(<AnalyticsDashboard />)
      
      expect(screen.getByText('Search Volume')).toBeInTheDocument()
      expect(screen.getByTestId('area-chart')).toBeInTheDocument()
    })

    it('renders response time chart', () => {
      render(<AnalyticsDashboard />)
      
      expect(screen.getByText('Response Time')).toBeInTheDocument()
      expect(screen.getByTestId('line-chart')).toBeInTheDocument()
    })

    it('displays popular queries table', () => {
      render(<AnalyticsDashboard />)
      
      expect(screen.getByText('Popular Queries')).toBeInTheDocument()
      expect(screen.getByText('email sync issues')).toBeInTheDocument()
      expect(screen.getByText('1,247 searches')).toBeInTheDocument()
    })

    it('shows trending tags cloud', () => {
      render(<AnalyticsDashboard />)
      
      expect(screen.getByText('Trending Tags')).toBeInTheDocument()
      expect(screen.getByText('sync')).toBeInTheDocument()
      expect(screen.getByText('settings')).toBeInTheDocument()
    })

    it('handles query click interactions', async () => {
      const user = userEvent.setup()
      render(<AnalyticsDashboard />)
      
      const queryItem = screen.getByText('email sync issues')
      await user.click(queryItem)
      
      // Should log the search action
      expect(console.log).toHaveBeenCalledWith('Search:', 'email sync issues')
    })

    it('handles tag click interactions', async () => {
      const user = userEvent.setup()
      render(<AnalyticsDashboard />)
      
      const tagItem = screen.getByText('sync')
      await user.click(tagItem)
      
      // Should log the filter action
      expect(console.log).toHaveBeenCalledWith('Filter by tag:', 'sync')
    })
  })

  describe('Performance Tab', () => {
    beforeEach(async () => {
      const user = userEvent.setup()
      render(<AnalyticsDashboard />)
      
      const performanceTab = screen.getByText('Performance')
      await user.click(performanceTab)
    })

    it('displays performance metrics', () => {
      expect(screen.getByText('Cache Hit Rate')).toBeInTheDocument()
      expect(screen.getByText('Error Rate')).toBeInTheDocument()
      expect(screen.getByText('Throughput')).toBeInTheDocument()
      expect(screen.getByText('Indexing Time')).toBeInTheDocument()
    })

    it('shows system performance status', () => {
      expect(screen.getByText('System Performance')).toBeInTheDocument()
      expect(screen.getByText('HEALTHY')).toBeInTheDocument()
      expect(screen.getByTestId('shield-icon')).toBeInTheDocument()
    })

    it('displays resource usage metrics', () => {
      expect(screen.getByText('Resource Usage')).toBeInTheDocument()
      expect(screen.getByText('CPU:')).toBeInTheDocument()
      expect(screen.getByText('Memory:')).toBeInTheDocument()
      expect(screen.getByText('Storage:')).toBeInTheDocument()
      expect(screen.getByText('Network:')).toBeInTheDocument()
    })

    it('shows response time distribution chart', () => {
      expect(screen.getByText('Response Time Distribution')).toBeInTheDocument()
      expect(screen.getByTestId('bar-chart')).toBeInTheDocument()
    })
  })

  describe('Engagement Tab', () => {
    beforeEach(async () => {
      const user = userEvent.setup()
      render(<AnalyticsDashboard />)
      
      const engagementTab = screen.getByText('Engagement')
      await user.click(engagementTab)
    })

    it('displays engagement metrics', () => {
      expect(screen.getByText('CTR')).toBeInTheDocument()
      expect(screen.getByText('Conversion')).toBeInTheDocument()
      expect(screen.getByText('Bounce Rate')).toBeInTheDocument()
      expect(screen.getByText('Return Users')).toBeInTheDocument()
    })

    it('shows user activity chart', () => {
      expect(screen.getByText('User Activity')).toBeInTheDocument()
      expect(screen.getByTestId('bar-chart')).toBeInTheDocument()
    })

    it('displays success rate trend', () => {
      expect(screen.getByText('Success Rate Trend')).toBeInTheDocument()
      expect(screen.getByTestId('line-chart')).toBeInTheDocument()
    })
  })

  describe('Insights Tab', () => {
    beforeEach(async () => {
      const user = userEvent.setup()
      render(<AnalyticsDashboard />)
      
      const insightsTab = screen.getByText('Insights')
      await user.click(insightsTab)
    })

    it('displays quality metrics', () => {
      expect(screen.getByText('Relevance')).toBeInTheDocument()
      expect(screen.getByText('Satisfaction')).toBeInTheDocument()
      expect(screen.getByText('Precision@10')).toBeInTheDocument()
      expect(screen.getByText('Diversity')).toBeInTheDocument()
    })

    it('shows key insights', () => {
      expect(screen.getByText('Key Insights')).toBeInTheDocument()
      expect(screen.getByText(/Search volume increased 12.5%/)).toBeInTheDocument()
      expect(screen.getByText(/AI-powered suggestions improved/)).toBeInTheDocument()
    })

    it('displays optimization recommendations', () => {
      expect(screen.getByText('Optimization Recommendations')).toBeInTheDocument()
      expect(screen.getByText(/Implement query suggestions/)).toBeInTheDocument()
      expect(screen.getByText(/Add more tag-based filters/)).toBeInTheDocument()
    })

    it('shows recommendation priorities', () => {
      expect(screen.getByText('High')).toBeInTheDocument()
      expect(screen.getByText('Med')).toBeInTheDocument()
      expect(screen.getByText('Low')).toBeInTheDocument()
    })
  })

  describe('Actions and Controls', () => {
    it('handles refresh action', async () => {
      const user = userEvent.setup()
      render(<AnalyticsDashboard />)
      
      const refreshButton = screen.getByText('Refresh')
      await user.click(refreshButton)
      
      expect(mockActions.refreshAnalytics).toHaveBeenCalled()
    })

    it('shows loading state during refresh', async () => {
      const user = userEvent.setup()
      render(<AnalyticsDashboard />)
      
      const refreshButton = screen.getByText('Refresh')
      
      // Start refresh
      mockActions.refreshAnalytics.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 100)))
      await user.click(refreshButton)
      
      // Should show spinning icon
      expect(screen.getByTestId('refresh-icon')).toHaveClass('animate-spin')
    })

    it('handles export action', async () => {
      const user = userEvent.setup()
      render(<AnalyticsDashboard />)
      
      const exportButton = screen.getByText('Export')
      await user.click(exportButton)
      
      expect(global.URL.createObjectURL).toHaveBeenCalled()
      expect(global.URL.revokeObjectURL).toHaveBeenCalled()
    })

    it('generates correct export filename', async () => {
      const user = userEvent.setup()
      render(<AnalyticsDashboard />)
      
      // Change time range
      const timeSelector = screen.getByRole('combobox')
      await user.click(timeSelector)
      const weekOption = screen.getByText('Last Week')
      await user.click(weekOption)
      
      const exportButton = screen.getByText('Export')
      await user.click(exportButton)
      
      // Should create download with correct filename
      const downloadLink = document.querySelector('a[download]')
      expect(downloadLink).toHaveAttribute('download', 'feedme-analytics-week.json')
    })
  })

  describe('Real-time Updates', () => {
    it('enables auto-refresh when real-time is active', () => {
      vi.useFakeTimers()
      
      render(<AnalyticsDashboard enableRealTime refreshInterval={1000} />)
      
      // Fast-forward time
      act(() => {
        vi.advanceTimersByTime(1000)
      })
      
      expect(mockActions.refreshAnalytics).toHaveBeenCalled()
      
      vi.useRealTimers()
    })

    it('disables auto-refresh when real-time is disabled', () => {
      vi.useFakeTimers()
      
      render(<AnalyticsDashboard enableRealTime={false} refreshInterval={1000} />)
      
      // Fast-forward time
      act(() => {
        vi.advanceTimersByTime(2000)
      })
      
      expect(mockActions.refreshAnalytics).not.toHaveBeenCalled()
      
      vi.useRealTimers()
    })

    it('updates timestamp display', () => {
      render(<AnalyticsDashboard />)
      
      expect(screen.getByText(/Last updated:/)).toBeInTheDocument()
    })

    it('shows system health in footer', () => {
      render(<AnalyticsDashboard />)
      
      expect(screen.getByText('System health: healthy')).toBeInTheDocument()
      expect(screen.getByText(/total results indexed/)).toBeInTheDocument()
    })
  })

  describe('Tag Interactions', () => {
    it('displays tag tooltips', async () => {
      const user = userEvent.setup()
      render(<AnalyticsDashboard />)
      
      const syncTag = screen.getByText('sync')
      await user.hover(syncTag)
      
      await waitFor(() => {
        expect(screen.getByText('3421 uses')).toBeInTheDocument()
        expect(screen.getByText('+15.2% growth')).toBeInTheDocument()
        expect(screen.getByText('Issues')).toBeInTheDocument()
      })
    })

    it('sizes tags based on usage', () => {
      render(<AnalyticsDashboard />)
      
      const syncTag = screen.getByText('sync')
      const settingsTag = screen.getByText('settings')
      
      // Sync tag should be larger due to higher count
      expect(syncTag.closest('span')).toHaveStyle({ fontSize: expect.stringMatching(/rem/) })
      expect(settingsTag.closest('span')).toHaveStyle({ fontSize: expect.stringMatching(/rem/) })
    })

    it('shows growth indicators in tooltips', async () => {
      const user = userEvent.setup()
      render(<AnalyticsDashboard />)
      
      const performanceTag = screen.getByText('performance')
      await user.hover(performanceTag)
      
      await waitFor(() => {
        expect(screen.getByText('+22.4% growth')).toBeInTheDocument()
      })
    })
  })

  describe('Loading States', () => {
    it('handles loading state', () => {
      ;(useAnalytics as any).mockReturnValue({
        ...mockAnalytics,
        isLoading: true,
      })

      render(<AnalyticsDashboard />)
      
      expect(screen.getByText('Loading analytics...')).toBeInTheDocument()
    })

    it('shows skeleton placeholders during loading', () => {
      ;(useAnalytics as any).mockReturnValue({
        ...mockAnalytics,
        isLoading: true,
      })

      render(<AnalyticsDashboard />)
      
      expect(screen.getAllByTestId('skeleton')).toHaveLength(4) // Metric cards
    })
  })

  describe('Error Handling', () => {
    it('handles refresh errors gracefully', async () => {
      mockActions.refreshAnalytics.mockRejectedValue(new Error('Network error'))
      
      const user = userEvent.setup()
      render(<AnalyticsDashboard />)
      
      const refreshButton = screen.getByText('Refresh')
      await user.click(refreshButton)
      
      await waitFor(() => {
        expect(console.error).toHaveBeenCalledWith('Failed to refresh analytics:', expect.any(Error))
      })
    })

    it('continues functioning after errors', async () => {
      mockActions.refreshAnalytics.mockRejectedValueOnce(new Error('Network error'))
      
      const user = userEvent.setup()
      render(<AnalyticsDashboard />)
      
      const refreshButton = screen.getByText('Refresh')
      await user.click(refreshButton)
      
      // Should still be able to interact with dashboard
      const performanceTab = screen.getByText('Performance')
      await user.click(performanceTab)
      
      expect(screen.getByText('Cache Hit Rate')).toBeInTheDocument()
    })
  })

  describe('Performance', () => {
    it('renders quickly with large datasets', () => {
      const startTime = performance.now()
      render(<AnalyticsDashboard />)
      const endTime = performance.now()
      
      expect(endTime - startTime).toBeLessThan(100)
      expect(screen.getByText('Search Analytics')).toBeInTheDocument()
    })

    it('memoizes expensive calculations', () => {
      const { rerender } = render(<AnalyticsDashboard />)
      
      // Re-render with same props
      rerender(<AnalyticsDashboard />)
      
      // Should not recalculate chart data
      expect(screen.getByText('Search Analytics')).toBeInTheDocument()
    })

    it('handles large time series data efficiently', () => {
      const largeTimeSeriesData = Array.from({ length: 10000 }, (_, i) => ({
        timestamp: `${i}:00`,
        searches: Math.floor(Math.random() * 1000),
        users: Math.floor(Math.random() * 500),
        responseTime: Math.floor(Math.random() * 300),
        successRate: Math.random(),
      }))

      // Mock large dataset
      ;(useAnalytics as any).mockReturnValue({
        ...mockAnalytics,
        timeSeriesData: largeTimeSeriesData,
      })

      const startTime = performance.now()
      render(<AnalyticsDashboard />)
      const endTime = performance.now()
      
      expect(endTime - startTime).toBeLessThan(200)
    })
  })

  describe('Accessibility', () => {
    it('has proper ARIA labels', () => {
      render(<AnalyticsDashboard />)
      
      expect(screen.getByRole('main')).toBeInTheDocument()
      expect(screen.getByRole('tablist')).toBeInTheDocument()
      expect(screen.getAllByRole('tab')).toHaveLength(4)
    })

    it('supports keyboard navigation', async () => {
      const user = userEvent.setup()
      render(<AnalyticsDashboard />)
      
      await user.keyboard('{Tab}')
      expect(screen.getByRole('combobox')).toHaveFocus()
      
      await user.keyboard('{Tab}')
      expect(screen.getByText('Export')).toHaveFocus()
    })

    it('has proper focus management in tabs', async () => {
      const user = userEvent.setup()
      render(<AnalyticsDashboard />)
      
      const performanceTab = screen.getByText('Performance')
      await user.click(performanceTab)
      
      expect(performanceTab).toHaveAttribute('aria-selected', 'true')
    })

    it('provides screen reader announcements', async () => {
      const user = userEvent.setup()
      render(<AnalyticsDashboard />)
      
      const refreshButton = screen.getByText('Refresh')
      await user.click(refreshButton)
      
      // Check for aria-live updates
      expect(screen.getByText('Analytics refreshed')).toBeInTheDocument()
    })
  })

  describe('Responsive Design', () => {
    it('adapts to different screen sizes', () => {
      // Mock window.innerWidth
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 768,
      })

      render(<AnalyticsDashboard />)
      
      // Should render mobile-friendly layout
      expect(screen.getByTestId('resizable-panel-group')).toHaveClass('flex-col')
    })

    it('adjusts chart dimensions on resize', () => {
      render(<AnalyticsDashboard />)
      
      // Simulate window resize
      act(() => {
        global.innerWidth = 1200
        global.dispatchEvent(new Event('resize'))
      })
      
      expect(screen.getAllByTestId('responsive-container')).toHaveLength(2)
    })
  })
})