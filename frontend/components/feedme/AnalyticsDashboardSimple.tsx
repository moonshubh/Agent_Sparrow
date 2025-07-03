/**
 * AnalyticsDashboard - Simplified Version
 * Basic analytics and metrics display
 */

'use client'

import React, { useEffect } from 'react'
import { BarChart3, Users, FileText, Clock, TrendingUp } from 'lucide-react'
import { useAnalytics, useActions } from '@/lib/stores/feedme-store'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

interface MetricCardProps {
  title: string
  value: string | number
  description?: string
  icon: React.ReactNode
  trend?: 'up' | 'down' | 'neutral'
}

const MetricCard = ({ title, value, description, icon, trend }: MetricCardProps) => (
  <Card>
    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
      <CardTitle className="text-sm font-medium">{title}</CardTitle>
      {icon}
    </CardHeader>
    <CardContent>
      <div className="text-2xl font-bold">{value}</div>
      {description && (
        <p className="text-xs text-muted-foreground">{description}</p>
      )}
      {trend && (
        <div className="flex items-center mt-2">
          <TrendingUp className={`h-4 w-4 mr-1 ${
            trend === 'up' ? 'text-green-500' : 
            trend === 'down' ? 'text-red-500' : 
            'text-gray-500'
          }`} />
          <Badge variant={trend === 'up' ? 'default' : 'secondary'}>
            {trend === 'up' ? 'Increasing' : trend === 'down' ? 'Decreasing' : 'Stable'}
          </Badge>
        </div>
      )}
    </CardContent>
  </Card>
)

export function AnalyticsDashboard() {
  const { workflowStats, isLoading } = useAnalytics()
  const actions = useActions()

  useEffect(() => {
    actions.loadAnalytics()
  }, [actions])

  if (isLoading) {
    return (
      <div className="p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[...Array(4)].map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardHeader>
                <div className="h-4 bg-gray-200 rounded w-3/4"></div>
              </CardHeader>
              <CardContent>
                <div className="h-8 bg-gray-200 rounded w-1/2 mb-2"></div>
                <div className="h-3 bg-gray-200 rounded w-full"></div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Analytics Dashboard</h2>
        <Badge variant="outline">Real-time</Badge>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard
          title="Total Conversations"
          value={workflowStats?.total_conversations || 0}
          description="All uploaded transcripts"
          icon={<FileText className="h-4 w-4 text-blue-500" />}
          trend="up"
        />
        
        <MetricCard
          title="Pending Approval"
          value={workflowStats?.pending_approval || 0}
          description="Awaiting review"
          icon={<Clock className="h-4 w-4 text-yellow-500" />}
          trend="neutral"
        />
        
        <MetricCard
          title="Approved"
          value={workflowStats?.approved || 0}
          description="Ready for use"
          icon={<Users className="h-4 w-4 text-green-500" />}
          trend="up"
        />
        
        <MetricCard
          title="Processing"
          value={workflowStats?.currently_processing || 0}
          description="Currently being analyzed"
          icon={<BarChart3 className="h-4 w-4 text-purple-500" />}
          trend="neutral"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Processing Performance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex justify-between">
                <span className="text-sm">Average Processing Time</span>
                <span className="font-medium">
                  {workflowStats?.avg_processing_time_ms 
                    ? `${(workflowStats.avg_processing_time_ms / 1000).toFixed(1)}s`
                    : 'N/A'
                  }
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm">Average Quality Score</span>
                <span className="font-medium">
                  {workflowStats?.avg_quality_score?.toFixed(2) || 'N/A'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm">Failed Processing</span>
                <span className="font-medium">
                  {workflowStats?.processing_failed || 0}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Workflow Status</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex justify-between">
                <span className="text-sm">Awaiting Review</span>
                <Badge variant="secondary">
                  {workflowStats?.awaiting_review || 0}
                </Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-sm">Rejected</span>
                <Badge variant="destructive">
                  {workflowStats?.rejected || 0}
                </Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-sm">Published</span>
                <Badge variant="default">
                  {workflowStats?.published || 0}
                </Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}