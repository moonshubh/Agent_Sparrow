'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { 
  BarChart3, 
  ChevronDown, 
  ChevronUp, 
  CheckCircle, 
  AlertTriangle, 
  Clock, 
  Zap,
  Activity
} from 'lucide-react';
import { 
  rateLimitApi, 
  type RateLimitStatus as RateLimitStatusType, 
  getUtilizationLevel, 
  formatTimeRemaining, 
  getTimeToReset 
} from '@/lib/api/rateLimitApi';

interface RateLimitDropdownProps {
  className?: string;
  autoUpdate?: boolean;
  updateInterval?: number;
}

export const RateLimitDropdown: React.FC<RateLimitDropdownProps> = ({
  className = '',
  autoUpdate = true,
  updateInterval = 30000, // 30 seconds
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [status, setStatus] = useState<RateLimitStatusType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const fetchStatus = async () => {
    try {
      setError(null);
      const data = await rateLimitApi.getStatus();
      setStatus(data);
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

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  // Auto-close after 10 seconds when opened
  useEffect(() => {
    let timeout: NodeJS.Timeout;
    if (isOpen) {
      timeout = setTimeout(() => {
        setIsOpen(false);
      }, 10000); // Auto-close after 10 seconds
    }
    return () => {
      if (timeout) {
        clearTimeout(timeout);
      }
    };
  }, [isOpen]);

  const getStatusIcon = () => {
    if (loading) return <Activity className="h-4 w-4 animate-spin" />;
    if (error) return <AlertTriangle className="h-4 w-4 text-red-500" />;
    if (!status) return <BarChart3 className="h-4 w-4" />;

    const overallStatus = status.status;
    switch (overallStatus) {
      case 'healthy':
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'warning':
        return <AlertTriangle className="h-4 w-4 text-yellow-500" />;
      case 'degraded':
      case 'unhealthy':
        return <AlertTriangle className="h-4 w-4 text-red-500" />;
      default:
        return <BarChart3 className="h-4 w-4" />;
    }
  };

  const getButtonVariant = () => {
    if (loading || error || !status) return 'ghost';
    
    const overallStatus = status.status;
    switch (overallStatus) {
      case 'healthy':
        return 'ghost';
      case 'warning':
        return 'secondary';
      case 'degraded':
      case 'unhealthy':
        return 'destructive';
      default:
        return 'ghost';
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
        return 'bg-gray-400';
    }
  };

  const renderDropdownContent = () => {
    if (loading) {
      return (
        <Card className="w-80">
          <CardContent className="p-4">
            <div className="flex items-center space-x-2">
              <Activity className="h-4 w-4 animate-spin" />
              <span>Loading rate limit status...</span>
            </div>
          </CardContent>
        </Card>
      );
    }

    if (error) {
      return (
        <Card className="w-80">
          <CardContent className="p-4">
            <div className="flex items-center space-x-2 text-red-500">
              <AlertTriangle className="h-4 w-4" />
              <span>Error: {error}</span>
            </div>
          </CardContent>
        </Card>
      );
    }

    if (!status) {
      return (
        <Card className="w-80">
          <CardContent className="p-4">
            <span>No rate limit data available</span>
          </CardContent>
        </Card>
      );
    }

    const { usage_stats, utilization } = status.details;
    const { flash_stats, pro_stats } = usage_stats;

    return (
      <Card className="w-80 shadow-lg">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium flex items-center justify-between">
            <span>Gemini API Limits</span>
            <Badge 
              variant={status.status === 'healthy' ? 'default' : 'destructive'}
              className="text-xs"
            >
              {status.status}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Flash Model Status */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Zap className="h-3 w-3 text-blue-500" />
                <span className="text-xs font-medium">Flash (2.5)</span>
              </div>
              <TooltipProvider>
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
              </TooltipProvider>
            </div>
            <div className="space-y-1">
              <Progress 
                value={utilization.flash_rpm * 100} 
                className="h-2"
                indicatorClassName={getUtilizationColor(getUtilizationLevel(utilization.flash_rpm))}
              />
              <div className="flex justify-between text-xs text-gray-500">
                <span>RPM: {Math.round(utilization.flash_rpm * 100)}%</span>
                <span>Daily: {Math.round(utilization.flash_rpd * 100)}%</span>
              </div>
            </div>
          </div>

          {/* Pro Model Status */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Zap className="h-3 w-3 text-accent" />
                <span className="text-xs font-medium">Pro (2.5)</span>
              </div>
              <TooltipProvider>
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
              </TooltipProvider>
            </div>
            <div className="space-y-1">
              <Progress 
                value={utilization.pro_rpm * 100} 
                className="h-2"
                indicatorClassName={getUtilizationColor(getUtilizationLevel(utilization.pro_rpm))}
              />
              <div className="flex justify-between text-xs text-gray-500">
                <span>RPM: {Math.round(utilization.pro_rpm * 100)}%</span>
                <span>Daily: {Math.round(utilization.pro_rpd * 100)}%</span>
              </div>
            </div>
          </div>

          {/* Summary Info */}
          <div className="border-t pt-3">
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center space-x-1">
                <Clock className="h-3 w-3" />
                <span>Free Tier Protected</span>
              </div>
              <span className="text-gray-500">
                Last updated: {new Date(status.timestamp).toLocaleTimeString()}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  };

  return (
    <div className={`relative ${className}`} ref={dropdownRef}>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant={getButtonVariant()}
              size="sm"
              onClick={() => setIsOpen(!isOpen)}
              className="flex items-center space-x-1 px-2 py-1"
            >
              {getStatusIcon()}
              {isOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p>View Gemini API rate limits</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      {isOpen && (
        <div className="absolute right-0 top-full mt-1 z-50">
          {renderDropdownContent()}
        </div>
      )}
    </div>
  );
};