'use client';

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { AlertTriangle, CheckCircle, Clock, Zap } from 'lucide-react';
import { rateLimitApi, type RateLimitStatus as RateLimitStatusType, getUtilizationLevel, formatTimeRemaining, getTimeToReset } from '@/lib/api/rateLimitApi';

interface RateLimitStatusProps {
  className?: string;
  showDetails?: boolean;
  autoUpdate?: boolean;
  updateInterval?: number;
}

export const RateLimitStatus: React.FC<RateLimitStatusProps> = ({
  className = '',
  showDetails = true,
  autoUpdate = true,
  updateInterval = 30000, // 30 seconds
}) => {
  const [status, setStatus] = useState<RateLimitStatusType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchStatus = async () => {
    try {
      setError(null);
      const data = await rateLimitApi.getStatus();
      setStatus(data);
      setLastUpdated(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch rate limit status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();

    if (autoUpdate) {
      const interval = setInterval(fetchStatus, updateInterval);
      return () => clearInterval(interval);
    }
  }, [autoUpdate, updateInterval]);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'warning':
        return <AlertTriangle className="h-4 w-4 text-yellow-500" />;
      case 'degraded':
      case 'unhealthy':
        return <AlertTriangle className="h-4 w-4 text-red-500" />;
      default:
        return <Clock className="h-4 w-4 text-gray-500" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'bg-green-100 text-green-800 border-green-200';
      case 'warning':
        return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'degraded':
        return 'bg-orange-100 text-orange-800 border-orange-200';
      case 'unhealthy':
        return 'bg-red-100 text-red-800 border-red-200';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  const getUtilizationColor = (level: string) => {
    switch (level) {
      case 'low':
        return 'bg-green-500';
      case 'medium':
        return 'bg-yellow-500';
      case 'high':
        return 'bg-orange-500';
      case 'critical':
        return 'bg-red-500';
      default:
        return 'bg-gray-500';
    }
  };

  if (loading) {
    return (
      <Card className={className}>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Rate Limits</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center space-x-2">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600" />
            <span className="text-sm text-gray-600">Loading...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className={className}>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Rate Limits</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center space-x-2">
            <AlertTriangle className="h-4 w-4 text-red-500" />
            <span className="text-sm text-red-600">{error}</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!status) {
    return null;
  }

  const { flash_stats, pro_stats } = status.details.usage_stats;
  const { utilization } = status.details;

  return (
    <TooltipProvider>
      <Card className={className}>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium">Rate Limits</CardTitle>
            <Badge className={`text-xs ${getStatusColor(status.status)}`}>
              <div className="flex items-center space-x-1">
                {getStatusIcon(status.status)}
                <span>{status.status}</span>
              </div>
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Flash Model Status */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Zap className="h-3 w-3 text-blue-500" />
                <span className="text-xs font-medium">Flash (2.5)</span>
              </div>
              <Tooltip>
                <TooltipTrigger>
                  <Badge variant="outline" className="text-xs">
                    {flash_stats.rpm_used}/{flash_stats.rpm_limit} RPM
                  </Badge>
                </TooltipTrigger>
                <TooltipContent>
                  <div className="text-xs">
                    <div>Requests per minute: {flash_stats.rpm_used}/{flash_stats.rpm_limit}</div>
                    <div>Daily usage: {flash_stats.rpd_used}/{flash_stats.rpd_limit}</div>
                    <div>RPM resets in: {formatTimeRemaining(getTimeToReset(flash_stats.reset_time_rpm))}</div>
                  </div>
                </TooltipContent>
              </Tooltip>
            </div>
            <div className="space-y-1">
              <Progress 
                value={utilization.flash_rpm * 100} 
                className="h-2"
                indicatorClassName={getUtilizationColor(getUtilizationLevel(utilization.flash_rpm))}
              />
              {showDetails && (
                <div className="flex justify-between text-xs text-gray-500">
                  <span>RPM: {Math.round(utilization.flash_rpm * 100)}%</span>
                  <span>Daily: {Math.round(utilization.flash_rpd * 100)}%</span>
                </div>
              )}
            </div>
          </div>

          {/* Pro Model Status */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Zap className="h-3 w-3 text-accent" />
                <span className="text-xs font-medium">Pro (2.5)</span>
              </div>
              <Tooltip>
                <TooltipTrigger>
                  <Badge variant="outline" className="text-xs">
                    {pro_stats.rpm_used}/{pro_stats.rpm_limit} RPM
                  </Badge>
                </TooltipTrigger>
                <TooltipContent>
                  <div className="text-xs">
                    <div>Requests per minute: {pro_stats.rpm_used}/{pro_stats.rpm_limit}</div>
                    <div>Daily usage: {pro_stats.rpd_used}/{pro_stats.rpd_limit}</div>
                    <div>RPM resets in: {formatTimeRemaining(getTimeToReset(pro_stats.reset_time_rpm))}</div>
                  </div>
                </TooltipContent>
              </Tooltip>
            </div>
            <div className="space-y-1">
              <Progress 
                value={utilization.pro_rpm * 100} 
                className="h-2"
                indicatorClassName={getUtilizationColor(getUtilizationLevel(utilization.pro_rpm))}
              />
              {showDetails && (
                <div className="flex justify-between text-xs text-gray-500">
                  <span>RPM: {Math.round(utilization.pro_rpm * 100)}%</span>
                  <span>Daily: {Math.round(utilization.pro_rpd * 100)}%</span>
                </div>
              )}
            </div>
          </div>

          {/* Overall Status */}
          {showDetails && (
            <div className="pt-2 border-t">
              <div className="flex justify-between text-xs text-gray-500">
                <span>Total Today: {status.details.usage_stats.total_requests_today}</span>
                <span>Uptime: {Math.round(status.details.usage_stats.uptime_percentage)}%</span>
              </div>
              {lastUpdated && (
                <div className="text-xs text-gray-400 mt-1">
                  Updated: {lastUpdated.toLocaleTimeString()}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </TooltipProvider>
  );
};