'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { 
  Activity, 
  AlertTriangle, 
  CheckCircle, 
  Clock, 
  RefreshCw, 
  TrendingUp, 
  Zap 
} from 'lucide-react';
import { 
  rateLimitApi, 
  type RateLimitMetrics as MetricsType, 
  type RateLimitStatus,
  getUtilizationLevel 
} from '@/lib/api/rateLimitApi';

interface RateLimitMetricsProps {
  className?: string;
  adminMode?: boolean;
  autoRefresh?: boolean;
  refreshInterval?: number;
}

export const RateLimitMetrics: React.FC<RateLimitMetricsProps> = ({
  className = '',
  adminMode = false,
  autoRefresh = true,
  refreshInterval = 30000, // 30 seconds
}) => {
  const [metrics, setMetrics] = useState<MetricsType | null>(null);
  const [status, setStatus] = useState<RateLimitStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [metricsData, statusData] = await Promise.all([
        rateLimitApi.getMetrics(),
        rateLimitApi.getStatus(),
      ]);
      setMetrics(metricsData);
      setStatus(statusData);
      setLastUpdated(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch metrics');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();

    if (autoRefresh) {
      const interval = setInterval(fetchData, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [fetchData, autoRefresh, refreshInterval]);

  const getUtilizationColor = (utilization: number) => {
    const level = getUtilizationLevel(utilization);
    switch (level) {
      case 'low': return '#10b981'; // green
      case 'medium': return '#f59e0b'; // yellow
      case 'high': return '#f97316'; // orange
      case 'critical': return '#ef4444'; // red
      default: return '#6b7280'; // gray
    }
  };

  if (loading) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>Rate Limit Metrics</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-32">
            <div className="flex items-center space-x-2">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600" />
              <span className="text-sm text-gray-600">Loading metrics...</span>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>Rate Limit Metrics</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <AlertTriangle className="h-4 w-4 text-red-500" />
              <span className="text-sm text-red-600">{error}</span>
            </div>
            <Button size="sm" variant="outline" onClick={fetchData}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Retry
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!metrics || !status) {
    return null;
  }

  // Prepare chart data with colors
  const utilizationData = [
    {
      name: 'Flash RPM',
      utilization: metrics.flash_rpm_utilization * 100,
      used: metrics.gemini_flash_rpm_used,
      limit: metrics.gemini_flash_rpm_limit,
      color: getUtilizationColor(metrics.flash_rpm_utilization),
    },
    {
      name: 'Flash RPD',
      utilization: metrics.flash_rpd_utilization * 100,
      used: metrics.gemini_flash_rpd_used,
      limit: metrics.gemini_flash_rpd_limit,
      color: getUtilizationColor(metrics.flash_rpd_utilization),
    },
    {
      name: 'Pro RPM',
      utilization: metrics.pro_rpm_utilization * 100,
      used: metrics.gemini_pro_rpm_used,
      limit: metrics.gemini_pro_rpm_limit,
      color: getUtilizationColor(metrics.pro_rpm_utilization),
    },
    {
      name: 'Pro RPD',
      utilization: metrics.pro_rpd_utilization * 100,
      used: metrics.gemini_pro_rpd_used,
      limit: metrics.gemini_pro_rpd_limit,
      color: getUtilizationColor(metrics.pro_rpd_utilization),
    },
  ];

  const pieData = [
    { name: 'Flash Requests', value: metrics.gemini_flash_rpm_used + metrics.gemini_flash_rpd_used, color: '#3b82f6' },
    { name: 'Pro Requests', value: metrics.gemini_pro_rpm_used + metrics.gemini_pro_rpd_used, color: '#8b5cf6' },
  ];

  const COLORS = ['#3b82f6', '#8b5cf6'];

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center space-x-2">
            <Activity className="h-5 w-5" />
            <span>Rate Limit Metrics</span>
          </CardTitle>
          <div className="flex items-center space-x-2">
            <Badge variant={status.status === 'healthy' ? 'default' : 'destructive'}>
              {status.status}
            </Badge>
            <Button size="sm" variant="outline" onClick={fetchData}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="overview" className="w-full">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="utilization">Utilization</TabsTrigger>
            <TabsTrigger value="circuit">Circuit Breakers</TabsTrigger>
            <TabsTrigger value="details">Details</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-4">
            {/* Key Metrics */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center space-x-2">
                    <TrendingUp className="h-4 w-4 text-blue-500" />
                    <div>
                      <div className="text-2xl font-bold">{metrics.total_requests_today}</div>
                      <div className="text-xs text-gray-500">Requests Today</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center space-x-2">
                    <Clock className="h-4 w-4 text-green-500" />
                    <div>
                      <div className="text-2xl font-bold">{metrics.total_requests_this_minute}</div>
                      <div className="text-xs text-gray-500">This Minute</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center space-x-2">
                    <CheckCircle className="h-4 w-4 text-green-500" />
                    <div>
                      <div className="text-2xl font-bold">{Math.round(metrics.uptime_percentage)}%</div>
                      <div className="text-xs text-gray-500">Uptime</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center space-x-2">
                    <AlertTriangle className="h-4 w-4 text-orange-500" />
                    <div>
                      <div className="text-2xl font-bold">
                        {metrics.circuit_breaker_flash_failures + metrics.circuit_breaker_pro_failures}
                      </div>
                      <div className="text-xs text-gray-500">Circuit Failures</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Usage Distribution */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Usage Distribution</CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={200}>
                    <PieChart>
                      <Pie
                        data={pieData}
                        cx="50%"
                        cy="50%"
                        labelLine={false}
                        label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                        outerRadius={60}
                        fill="#8884d8"
                        dataKey="value"
                      >
                        {pieData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Current Limits</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-sm">
                      <span className="flex items-center space-x-1">
                        <Zap className="h-3 w-3 text-blue-500" />
                        <span>Flash RPM</span>
                      </span>
                      <span className="font-mono">{metrics.gemini_flash_rpm_used}/{metrics.gemini_flash_rpm_limit}</span>
                    </div>
                    <Progress value={metrics.flash_rpm_utilization * 100} className="h-2" />
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-sm">
                      <span className="flex items-center space-x-1">
                        <Zap className="h-3 w-3 text-accent" />
                        <span>Pro RPM</span>
                      </span>
                      <span className="font-mono">{metrics.gemini_pro_rpm_used}/{metrics.gemini_pro_rpm_limit}</span>
                    </div>
                    <Progress value={metrics.pro_rpm_utilization * 100} className="h-2" />
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="utilization" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Rate Limit Utilization</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={utilizationData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip 
                      formatter={(value, name) => [
                        `${Number(value).toFixed(1)}%`, 
                        'Utilization'
                      ]}
                      labelFormatter={(label) => `Limit: ${label}`}
                    />
                    <Bar 
                      dataKey="utilization" 
                      radius={[4, 4, 0, 0]}
                    >
                      {utilizationData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="circuit" className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm flex items-center space-x-2">
                    <Zap className="h-4 w-4 text-blue-500" />
                    <span>Flash Circuit Breaker</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span>State</span>
                    <Badge variant={metrics.circuit_breaker_flash_state === 0 ? 'default' : 'destructive'}>
                      {metrics.circuit_breaker_flash_state === 0 ? 'Closed' : 'Open'}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Failures</span>
                    <span className="font-mono">{metrics.circuit_breaker_flash_failures}</span>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-sm flex items-center space-x-2">
                    <Zap className="h-4 w-4 text-accent" />
                    <span>Pro Circuit Breaker</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span>State</span>
                    <Badge variant={metrics.circuit_breaker_pro_state === 0 ? 'default' : 'destructive'}>
                      {metrics.circuit_breaker_pro_state === 0 ? 'Closed' : 'Open'}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Failures</span>
                    <span className="font-mono">{metrics.circuit_breaker_pro_failures}</span>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="details" className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Flash Model Details */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm flex items-center space-x-2">
                    <Zap className="h-4 w-4 text-blue-500" />
                    <span>Gemini 2.5 Flash</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <div className="text-gray-500">RPM Used</div>
                      <div className="font-mono text-lg">{metrics.gemini_flash_rpm_used}</div>
                    </div>
                    <div>
                      <div className="text-gray-500">RPM Limit</div>
                      <div className="font-mono text-lg">{metrics.gemini_flash_rpm_limit}</div>
                    </div>
                    <div>
                      <div className="text-gray-500">RPD Used</div>
                      <div className="font-mono text-lg">{metrics.gemini_flash_rpd_used}</div>
                    </div>
                    <div>
                      <div className="text-gray-500">RPD Limit</div>
                      <div className="font-mono text-lg">{metrics.gemini_flash_rpd_limit}</div>
                    </div>
                  </div>
                  <div className="pt-2 border-t">
                    <div className="text-xs text-gray-500">
                      RPM Utilization: {Math.round(metrics.flash_rpm_utilization * 100)}%
                    </div>
                    <div className="text-xs text-gray-500">
                      RPD Utilization: {Math.round(metrics.flash_rpd_utilization * 100)}%
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Pro Model Details */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm flex items-center space-x-2">
                    <Zap className="h-4 w-4 text-accent" />
                    <span>Gemini 2.5 Pro</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <div className="text-gray-500">RPM Used</div>
                      <div className="font-mono text-lg">{metrics.gemini_pro_rpm_used}</div>
                    </div>
                    <div>
                      <div className="text-gray-500">RPM Limit</div>
                      <div className="font-mono text-lg">{metrics.gemini_pro_rpm_limit}</div>
                    </div>
                    <div>
                      <div className="text-gray-500">RPD Used</div>
                      <div className="font-mono text-lg">{metrics.gemini_pro_rpd_used}</div>
                    </div>
                    <div>
                      <div className="text-gray-500">RPD Limit</div>
                      <div className="font-mono text-lg">{metrics.gemini_pro_rpd_limit}</div>
                    </div>
                  </div>
                  <div className="pt-2 border-t">
                    <div className="text-xs text-gray-500">
                      RPM Utilization: {Math.round(metrics.pro_rpm_utilization * 100)}%
                    </div>
                    <div className="text-xs text-gray-500">
                      RPD Utilization: {Math.round(metrics.pro_rpd_utilization * 100)}%
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>

        {lastUpdated && (
          <div className="text-xs text-gray-400 mt-4 text-center">
            Last updated: {lastUpdated.toLocaleString()}
          </div>
        )}
      </CardContent>
    </Card>
  );
};