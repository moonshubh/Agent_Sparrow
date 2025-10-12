'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent } from '@/shared/ui/card';
import { Badge } from '@/shared/ui/badge';
import { Button } from '@/shared/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/shared/ui/tooltip';
import { 
  Timer,
  RefreshCw,
  Calendar,
  Hourglass,
  Play,
  Pause,
  RotateCcw
} from 'lucide-react';
import { rateLimitApi, formatTimeRemaining, getTimeToReset } from '@/services/api/endpoints/rateLimitApi';
import { cn } from '@/shared/lib/utils';

interface RateLimitCountdownProps {
  model?: 'gemini-2.5-flash' | 'gemini-2.5-pro';
  type?: 'rpm' | 'rpd' | 'both';
  className?: string;
  showIcon?: boolean;
  animated?: boolean;
  autoRefresh?: boolean;
  onReset?: () => void;
}

interface CountdownState {
  rpmSeconds: number;
  rpdSeconds: number;
  isPaused: boolean;
}

export const RateLimitCountdown: React.FC<RateLimitCountdownProps> = ({
  model,
  type = 'both',
  className,
  showIcon = true,
  animated = true,
  autoRefresh = true,
  onReset
}) => {
  const [countdowns, setCountdowns] = useState<Record<string, CountdownState>>({
    'gemini-2.5-flash': { rpmSeconds: 0, rpdSeconds: 0, isPaused: false },
    'gemini-2.5-pro': { rpmSeconds: 0, rpdSeconds: 0, isPaused: false }
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isPaused, setIsPaused] = useState(false);

  const fetchResetTimes = useCallback(async () => {
    try {
      setError(null);
      const status = await rateLimitApi.getStatus();
      const { flash_stats, pro_stats } = status.details.usage_stats;
      
      setCountdowns({
        'gemini-2.5-flash': {
          rpmSeconds: getTimeToReset(flash_stats.reset_time_rpm),
          rpdSeconds: getTimeToReset(flash_stats.reset_time_rpd),
          isPaused: false
        },
        'gemini-2.5-pro': {
          rpmSeconds: getTimeToReset(pro_stats.reset_time_rpm),
          rpdSeconds: getTimeToReset(pro_stats.reset_time_rpd),
          isPaused: false
        }
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch reset times');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchResetTimes();

    if (autoRefresh) {
      const fetchInterval = setInterval(fetchResetTimes, 30000); // Refresh every 30 seconds
      return () => clearInterval(fetchInterval);
    }
  }, [fetchResetTimes, autoRefresh]);

  useEffect(() => {
    if (isPaused) return;

    const countdownInterval = setInterval(() => {
      setCountdowns(prev => {
        const updated = { ...prev };
        let hasReset = false;

        Object.keys(updated).forEach(modelKey => {
          if (updated[modelKey].rpmSeconds > 0) {
            updated[modelKey].rpmSeconds--;
            if (updated[modelKey].rpmSeconds === 0) {
              hasReset = true;
            }
          }
          if (updated[modelKey].rpdSeconds > 0) {
            updated[modelKey].rpdSeconds--;
            if (updated[modelKey].rpdSeconds === 0) {
              hasReset = true;
            }
          }
        });

        if (hasReset && onReset) {
          onReset();
        }

        return updated;
      });
    }, 1000);

    return () => clearInterval(countdownInterval);
  }, [isPaused, onReset]);

  const togglePause = () => {
    setIsPaused(!isPaused);
  };

  const handleManualRefresh = () => {
    setLoading(true);
    fetchResetTimes();
  };

  const renderCountdown = (modelKey: string, state: CountdownState) => {
    const getCountdownColor = (seconds: number) => {
      if (seconds <= 10) return 'text-red-500';
      if (seconds <= 30) return 'text-orange-500';
      if (seconds <= 60) return 'text-yellow-500';
      return 'text-green-500';
    };

    const renderTimer = (seconds: number, label: string, icon: React.ReactNode) => {
      const isExpired = seconds === 0;
      const formattedTime = formatTimeRemaining(seconds);

      return (
        <div className={cn(
          "flex items-center gap-2 p-2 rounded-lg",
          "glass-effect transition-all duration-200",
          isExpired && "opacity-50",
          !isExpired && animated && "hover:scale-105"
        )}>
          {showIcon && (
            <div className={cn(
              "p-1.5 rounded-full glass-effect",
              getCountdownColor(seconds)
            )}>
              {icon}
            </div>
          )}
          <div className="flex-1">
            <div className="text-xs text-muted-foreground">{label}</div>
            <div className={cn(
              "text-sm font-mono font-medium",
              getCountdownColor(seconds),
              animated && !isExpired && "animate-pulse"
            )}>
              {formattedTime}
            </div>
          </div>
          {isExpired && (
            <Badge variant="outline" className="text-xs glass-effect">
              Ready
            </Badge>
          )}
        </div>
      );
    };

    return (
      <Card className="glass-effect">
        <CardContent className="p-3 space-y-2">
          <div className="flex items-center justify-between">
            <Badge variant="outline" className="text-xs glass-effect">
              {modelKey.includes('flash') ? 'Flash' : 'Pro'}
            </Badge>
            {autoRefresh && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={togglePause}
                      className="h-6 w-6 p-0"
                    >
                      {isPaused ? (
                        <Play className="h-3 w-3" />
                      ) : (
                        <Pause className="h-3 w-3" />
                      )}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    {isPaused ? 'Resume countdown' : 'Pause countdown'}
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
          </div>

          {(type === 'rpm' || type === 'both') && (
            renderTimer(
              state.rpmSeconds,
              'Minute Reset',
              <Timer className="h-3 w-3" />
            )
          )}
          
          {(type === 'rpd' || type === 'both') && (
            renderTimer(
              state.rpdSeconds,
              'Daily Reset',
              <Calendar className="h-3 w-3" />
            )
          )}

          {/* Visual countdown ring for RPM */}
          {type === 'both' && (
            <div className="flex justify-center pt-2">
              <div className="relative w-16 h-16">
                <svg className="w-full h-full transform -rotate-90">
                  <circle
                    cx="32"
                    cy="32"
                    r="28"
                    stroke="currentColor"
                    strokeWidth="4"
                    fill="none"
                    className="text-secondary"
                  />
                  <circle
                    cx="32"
                    cy="32"
                    r="28"
                    stroke="currentColor"
                    strokeWidth="4"
                    fill="none"
                    strokeDasharray={`${2 * Math.PI * 28}`}
                    strokeDashoffset={`${2 * Math.PI * 28 * (1 - (60 - Math.min(state.rpmSeconds, 60)) / 60)}`}
                    className={cn(
                      "transition-all duration-1000 ease-linear",
                      getCountdownColor(state.rpmSeconds)
                    )}
                  />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <Hourglass className={cn(
                    "h-4 w-4",
                    getCountdownColor(state.rpmSeconds),
                    animated && state.rpmSeconds > 0 && "animate-pulse"
                  )} />
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    );
  };

  if (loading) {
    return (
      <Card className={cn("glass-effect animate-pulse", className)}>
        <CardContent className="p-4">
          <div className="h-24 bg-secondary/20 rounded" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className={cn("glass-effect", className)}>
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-destructive">{error}</span>
            <Button
              size="sm"
              variant="ghost"
              onClick={handleManualRefresh}
            >
              <RotateCcw className="h-3 w-3" />
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  const modelsToRender = model 
    ? [model]
    : ['gemini-2.5-flash', 'gemini-2.5-pro'] as const;

  return (
    <div className={cn("space-y-2", className)}>
      {modelsToRender.map(m => (
        <div key={m}>
          {renderCountdown(m, countdowns[m])}
        </div>
      ))}
      
      {!autoRefresh && (
        <Button
          size="sm"
          variant="outline"
          onClick={handleManualRefresh}
          disabled={loading}
          className="w-full glass-effect"
        >
          <RefreshCw className={cn(
            "h-3 w-3 mr-1",
            loading && "animate-spin"
          )} />
          Refresh Timers
        </Button>
      )}
    </div>
  );
};
