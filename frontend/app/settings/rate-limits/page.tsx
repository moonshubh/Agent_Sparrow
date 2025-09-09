"use client"

import React, { useState, useEffect } from 'react'
import { RateLimitIndicator } from '@/components/rate-limiting/RateLimitIndicator'
import { RateLimitCountdown } from '@/components/rate-limiting/RateLimitCountdown'
import { RateLimitMetrics } from '@/components/rate-limiting/RateLimitMetrics'
import { RateLimitStatus } from '@/components/rate-limiting/RateLimitStatus'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Separator } from '@/components/ui/separator'
import {
  Gauge,
  AlertCircle,
  CheckCircle,
  Clock,
  TrendingUp,
  Activity,
  RefreshCw,
  Zap,
  Info,
  Settings,
  BarChart3,
  Timer,
  Shield
} from 'lucide-react'
import { rateLimitApi, getUtilizationLevel, formatTimeRemaining, type UsageStats } from '@/lib/api/rateLimitApi'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

export default function RateLimitsSettingsPage() {
  const [usageStats, setUsageStats] = useState<UsageStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [activeTab, setActiveTab] = useState('overview')

  useEffect(() => {
    fetchUsageStats()
    const interval = setInterval(fetchUsageStats, 10000) // Refresh every 10 seconds
    return () => clearInterval(interval)
  }, [])

  const fetchUsageStats = async () => {
    try {
      setLoading(true)
      const stats = await rateLimitApi.getUsageStats()
      setUsageStats(stats)
    } catch (error) {
      console.error('Failed to fetch usage stats:', error)
      toast.error('Failed to load rate limit data')
    } finally {
      setLoading(false)
    }
  }

  const handleManualRefresh = async () => {
    setRefreshing(true)
    await fetchUsageStats()
    setRefreshing(false)
    toast.success('Rate limits refreshed')
  }

  const handleResetLimits = async (model?: string) => {
    const confirmed = window.confirm(
      `Are you sure you want to reset ${model || 'all'} rate limits? This action cannot be undone.`
    )
    if (!confirmed) return

    try {
      await rateLimitApi.resetLimits(model)
      toast.success(`Rate limits reset successfully`)
      fetchUsageStats()
    } catch (error) {
      toast.error('Failed to reset rate limits')
    }
  }

  const getHealthStatus = () => {
    if (!usageStats) return { status: 'unknown', color: 'gray' }
    
    const flashUtilization = usageStats.flash_stats.rpm_used / usageStats.flash_stats.rpm_limit
    const proUtilization = usageStats.pro_stats.rpm_used / usageStats.pro_stats.rpm_limit
    const maxUtilization = Math.max(flashUtilization, proUtilization)
    
    if (maxUtilization >= 0.9) return { status: 'Critical', color: 'red' }
    if (maxUtilization >= 0.8) return { status: 'High', color: 'orange' }
    if (maxUtilization >= 0.6) return { status: 'Medium', color: 'yellow' }
    return { status: 'Healthy', color: 'green' }
  }

  const healthStatus = getHealthStatus()

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <Gauge className="h-5 w-5 text-accent" />
            Rate Limits Management
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            Monitor and manage API rate limits for Gemini models
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge 
            variant="outline" 
            className={cn(
              "glass-effect",
              healthStatus.color === 'red' && "border-red-500/50 text-red-500",
              healthStatus.color === 'orange' && "border-orange-500/50 text-orange-500",
              healthStatus.color === 'yellow' && "border-yellow-500/50 text-yellow-500",
              healthStatus.color === 'green' && "border-green-500/50 text-green-500"
            )}
          >
            <Activity className="h-3 w-3 mr-1" />
            {healthStatus.status}
          </Badge>
          <Button
            variant="outline"
            size="sm"
            onClick={handleManualRefresh}
            disabled={refreshing}
            className="glass-effect"
          >
            <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} />
          </Button>
        </div>
      </div>

      <Separator />

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-4 glass-effect">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="flash">Gemini Flash</TabsTrigger>
          <TabsTrigger value="pro">Gemini Pro</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-4">
          {/* Quick Stats */}
          {usageStats && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <Card className="glass-effect">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs text-muted-foreground">Total Requests Today</p>
                      <p className="text-2xl font-bold">{usageStats.total_requests_today}</p>
                    </div>
                    <TrendingUp className="h-8 w-8 text-accent opacity-20" />
                  </div>
                </CardContent>
              </Card>
              
              <Card className="glass-effect">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs text-muted-foreground">Requests This Minute</p>
                      <p className="text-2xl font-bold">{usageStats.total_requests_this_minute}</p>
                    </div>
                    <Clock className="h-8 w-8 text-accent opacity-20" />
                  </div>
                </CardContent>
              </Card>
              
              <Card className="glass-effect">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs text-muted-foreground">Uptime</p>
                      <p className="text-2xl font-bold">{usageStats.uptime_percentage.toFixed(1)}%</p>
                    </div>
                    <CheckCircle className="h-8 w-8 text-green-500 opacity-20" />
                  </div>
                </CardContent>
              </Card>
              
              <Card className="glass-effect">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs text-muted-foreground">Circuit Status</p>
                      <div className="flex gap-2 mt-1">
                        <Badge variant="outline" className="text-xs glass-effect">
                          Flash: {usageStats.flash_circuit.state}
                        </Badge>
                        <Badge variant="outline" className="text-xs glass-effect">
                          Pro: {usageStats.pro_circuit.state}
                        </Badge>
                      </div>
                    </div>
                    <Shield className="h-8 w-8 text-accent opacity-20" />
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Rate Limit Indicators */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <RateLimitIndicator model="gemini-2.5-flash" showLabels animated />
            <RateLimitIndicator model="gemini-2.5-pro" showLabels animated />
          </div>

          {/* Countdown Timers */}
          <Card className="glass-effect">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Timer className="h-4 w-4" />
                Reset Countdowns
              </CardTitle>
              <CardDescription>Time until rate limits reset</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <RateLimitCountdown model="gemini-2.5-flash" type="both" animated />
                <RateLimitCountdown model="gemini-2.5-pro" type="both" animated />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Gemini Flash Tab */}
        <TabsContent value="flash" className="space-y-4">
          {usageStats && (
            <>
              <RateLimitStatus />
              <RateLimitMetrics model="gemini-2.5-flash" />
              
              <Card className="glass-effect">
                <CardHeader>
                  <CardTitle className="text-base">Detailed Metrics</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span>Requests Per Minute</span>
                      <span className="font-mono">
                        {usageStats.flash_stats.rpm_used}/{usageStats.flash_stats.rpm_limit}
                      </span>
                    </div>
                    <Progress 
                      value={(usageStats.flash_stats.rpm_used / usageStats.flash_stats.rpm_limit) * 100}
                      className="h-2"
                    />
                  </div>
                  
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span>Requests Per Day</span>
                      <span className="font-mono">
                        {usageStats.flash_stats.rpd_used}/{usageStats.flash_stats.rpd_limit}
                      </span>
                    </div>
                    <Progress 
                      value={(usageStats.flash_stats.rpd_used / usageStats.flash_stats.rpd_limit) * 100}
                      className="h-2"
                    />
                  </div>
                  
                  <Alert>
                    <Info className="h-4 w-4" />
                    <AlertDescription>
                      Gemini Flash is optimized for fast, efficient responses with lower rate limits.
                    </AlertDescription>
                  </Alert>
                </CardContent>
              </Card>
            </>
          )}
        </TabsContent>

        {/* Gemini Pro Tab */}
        <TabsContent value="pro" className="space-y-4">
          {usageStats && (
            <>
              <RateLimitStatus />
              <RateLimitMetrics model="gemini-2.5-pro" />
              
              <Card className="glass-effect">
                <CardHeader>
                  <CardTitle className="text-base">Detailed Metrics</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span>Requests Per Minute</span>
                      <span className="font-mono">
                        {usageStats.pro_stats.rpm_used}/{usageStats.pro_stats.rpm_limit}
                      </span>
                    </div>
                    <Progress 
                      value={(usageStats.pro_stats.rpm_used / usageStats.pro_stats.rpm_limit) * 100}
                      className="h-2"
                    />
                  </div>
                  
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span>Requests Per Day</span>
                      <span className="font-mono">
                        {usageStats.pro_stats.rpd_used}/{usageStats.pro_stats.rpd_limit}
                      </span>
                    </div>
                    <Progress 
                      value={(usageStats.pro_stats.rpd_used / usageStats.pro_stats.rpd_limit) * 100}
                      className="h-2"
                    />
                  </div>
                  
                  <Alert>
                    <Info className="h-4 w-4" />
                    <AlertDescription>
                      Gemini Pro offers advanced capabilities with higher rate limits for complex tasks.
                    </AlertDescription>
                  </Alert>
                </CardContent>
              </Card>
            </>
          )}
        </TabsContent>

        {/* Settings Tab */}
        <TabsContent value="settings" className="space-y-4">
          <Card className="glass-effect">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Settings className="h-4 w-4" />
                Rate Limit Configuration
              </CardTitle>
              <CardDescription>Advanced rate limiting settings</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Alert>
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Warning</AlertTitle>
                <AlertDescription>
                  Modifying rate limit settings may affect application performance. Use with caution.
                </AlertDescription>
              </Alert>
              
              <div className="space-y-2">
                <h3 className="text-sm font-medium">Emergency Actions</h3>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleResetLimits('gemini-2.5-flash')}
                    className="glass-effect"
                  >
                    Reset Flash Limits
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleResetLimits('gemini-2.5-pro')}
                    className="glass-effect"
                  >
                    Reset Pro Limits
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleResetLimits()}
                    className="glass-effect text-destructive"
                  >
                    Reset All Limits
                  </Button>
                </div>
              </div>
              
              <Separator />
              
              <div className="space-y-2">
                <h3 className="text-sm font-medium">Current Limits</h3>
                {usageStats && (
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <p className="font-medium">Gemini Flash</p>
                      <p className="text-xs text-muted-foreground">RPM: {usageStats.flash_stats.rpm_limit}</p>
                      <p className="text-xs text-muted-foreground">RPD: {usageStats.flash_stats.rpd_limit}</p>
                    </div>
                    <div>
                      <p className="font-medium">Gemini Pro</p>
                      <p className="text-xs text-muted-foreground">RPM: {usageStats.pro_stats.rpm_limit}</p>
                      <p className="text-xs text-muted-foreground">RPD: {usageStats.pro_stats.rpd_limit}</p>
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}