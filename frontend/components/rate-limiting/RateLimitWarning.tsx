'use client';

import React, { useState, useEffect } from 'react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { AlertTriangle, Clock, X } from 'lucide-react';
import { rateLimitApi, getUtilizationLevel, formatTimeRemaining, getTimeToReset } from '@/lib/api/rateLimitApi';

interface RateLimitWarningProps {
  className?: string;
  warningThreshold?: number; // Show warning when utilization exceeds this (0-1)
  criticalThreshold?: number; // Show critical warning when utilization exceeds this (0-1)
  autoCheck?: boolean;
  checkInterval?: number;
  onDismiss?: () => void;
  dismissible?: boolean;
}

export const RateLimitWarning: React.FC<RateLimitWarningProps> = ({
  className = '',
  warningThreshold = 0.7,
  criticalThreshold = 0.85,
  autoCheck = true,
  checkInterval = 15000, // 15 seconds
  onDismiss,
  dismissible = true,
}) => {
  const [warning, setWarning] = useState<{
    level: 'warning' | 'critical';
    message: string;
    details: {
      model: string;
      type: 'rpm' | 'rpd';
      utilization: number;
      remaining: number;
      resetTime: string;
    }[];
  } | null>(null);
  const [dismissed, setDismissed] = useState(false);

  const checkLimits = async () => {
    try {
      const status = await rateLimitApi.getStatus();
      const { utilization, usage_stats } = status.details;

      const issues: Array<{
        model: string;
        type: 'rpm' | 'rpd';
        utilization: number;
        remaining: number;
        resetTime: string;
      }> = [];

      // Check Flash RPM
      if (utilization.flash_rpm >= warningThreshold) {
        issues.push({
          model: 'Flash',
          type: 'rpm',
          utilization: utilization.flash_rpm,
          remaining: usage_stats.flash_stats.rpm_remaining,
          resetTime: usage_stats.flash_stats.reset_time_rpm,
        });
      }

      // Check Flash RPD
      if (utilization.flash_rpd >= warningThreshold) {
        issues.push({
          model: 'Flash',
          type: 'rpd',
          utilization: utilization.flash_rpd,
          remaining: usage_stats.flash_stats.rpd_remaining,
          resetTime: usage_stats.flash_stats.reset_time_rpd,
        });
      }

      // Check Pro RPM
      if (utilization.pro_rpm >= warningThreshold) {
        issues.push({
          model: 'Pro',
          type: 'rpm',
          utilization: utilization.pro_rpm,
          remaining: usage_stats.pro_stats.rpm_remaining,
          resetTime: usage_stats.pro_stats.reset_time_rpm,
        });
      }

      // Check Pro RPD
      if (utilization.pro_rpd >= warningThreshold) {
        issues.push({
          model: 'Pro',
          type: 'rpd',
          utilization: utilization.pro_rpd,
          remaining: usage_stats.pro_stats.rpd_remaining,
          resetTime: usage_stats.pro_stats.reset_time_rpd,
        });
      }

      if (issues.length > 0) {
        const maxUtilization = Math.max(...issues.map(i => i.utilization));
        const level = maxUtilization >= criticalThreshold ? 'critical' : 'warning';
        
        let message = '';
        if (level === 'critical') {
          message = 'Critical: Rate limits nearly exhausted!';
        } else {
          message = 'Warning: Approaching rate limits';
        }

        setWarning({
          level,
          message,
          details: issues,
        });
        setDismissed(false);
      } else {
        setWarning(null);
      }
    } catch (error) {
      // Silently handle errors to avoid spamming the UI
      console.warn('Failed to check rate limits:', error);
    }
  };

  useEffect(() => {
    if (autoCheck) {
      checkLimits();
      const interval = setInterval(checkLimits, checkInterval);
      return () => clearInterval(interval);
    }
  }, [autoCheck, checkInterval, warningThreshold, criticalThreshold]);

  const handleDismiss = () => {
    setDismissed(true);
    onDismiss?.();
  };

  if (!warning || dismissed) {
    return null;
  }

  const alertVariant = warning.level === 'critical' ? 'destructive' : 'default';
  const alertIcon = warning.level === 'critical' ? 
    <AlertTriangle className="h-4 w-4 text-red-500" /> : 
    <AlertTriangle className="h-4 w-4 text-yellow-500" />;

  return (
    <Alert className={`${className} ${warning.level === 'critical' ? 'border-red-200 bg-red-50' : 'border-yellow-200 bg-yellow-50'}`} variant={alertVariant}>
      <div className="flex items-start justify-between">
        <div className="flex items-start space-x-3 flex-1">
          {alertIcon}
          <div className="flex-1 space-y-2">
            <AlertDescription className="font-medium">
              {warning.message}
            </AlertDescription>
            <div className="space-y-2">
              {warning.details.map((detail, index) => (
                <div key={index} className="flex items-center justify-between p-2 bg-white rounded border">
                  <div className="flex items-center space-x-2">
                    <Badge variant="outline" className="text-xs">
                      {detail.model} {detail.type.toUpperCase()}
                    </Badge>
                    <span className="text-sm">
                      {Math.round(detail.utilization * 100)}% used
                    </span>
                  </div>
                  <div className="flex items-center space-x-2 text-xs text-gray-500">
                    <Clock className="h-3 w-3" />
                    <span>
                      {detail.type === 'rpd' ? `${detail.remaining} requests left today` : `${detail.remaining} remaining`} • Resets in {formatTimeRemaining(getTimeToReset(detail.resetTime))}
                    </span>
                  </div>
                </div>
              ))}
            </div>
            <div className="text-sm text-gray-600">
              {warning.level === 'critical' ? 
                'Consider reducing usage or wait for limits to reset. New requests may be blocked.' :
                'Monitor usage closely to avoid hitting limits.'
              }
            </div>
          </div>
        </div>
        {dismissible && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleDismiss}
            className="h-6 w-6 p-0 hover:bg-transparent"
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>
    </Alert>
  );
};