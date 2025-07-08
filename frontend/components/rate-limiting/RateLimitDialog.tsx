'use client';

import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { AlertTriangle, Clock, Zap, RefreshCw } from 'lucide-react';
import { formatTimeRemaining, getTimeToReset } from '@/lib/api/rateLimitApi';

interface RateLimitDialogProps {
  isOpen: boolean;
  onClose: () => void;
  blockedModel: 'gemini-2.5-flash' | 'gemini-2.5-pro';
  blockedBy: 'rpm' | 'rpd';
  metadata: {
    rpm_used: number;
    rpm_limit: number;
    rpm_remaining: number;
    rpd_used: number;
    rpd_limit: number;
    rpd_remaining: number;
    reset_time_rpm: string;
    reset_time_rpd: string;
    model: string;
    safety_margin: number;
  };
  retryAfter?: number;
  onRetry?: () => void;
  onCancel?: () => void;
}

export const RateLimitDialog: React.FC<RateLimitDialogProps> = ({
  isOpen,
  onClose,
  blockedModel,
  blockedBy,
  metadata,
  retryAfter,
  onRetry,
  onCancel,
}) => {
  const [timeRemaining, setTimeRemaining] = useState<number>(
    retryAfter || getTimeToReset(
      blockedBy === 'rpm' ? metadata.reset_time_rpm : metadata.reset_time_rpd
    )
  );

  useEffect(() => {
    if (!isOpen) return;

    const interval = setInterval(() => {
      const newTime = getTimeToReset(
        blockedBy === 'rpm' ? metadata.reset_time_rpm : metadata.reset_time_rpd
      );
      setTimeRemaining(newTime);

      // Auto-close if limit has reset
      if (newTime <= 0) {
        onClose();
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [isOpen, blockedBy, metadata.reset_time_rpm, metadata.reset_time_rpd, onClose]);

  const modelName = blockedModel === 'gemini-2.5-flash' ? 'Flash' : 'Pro';
  const limitType = blockedBy === 'rpm' ? 'per minute' : 'per day';
  const currentUsed = blockedBy === 'rpm' ? metadata.rpm_used : metadata.rpd_used;
  const currentLimit = blockedBy === 'rpm' ? metadata.rpm_limit : metadata.rpd_limit;
  const utilization = currentUsed / Math.max(currentLimit, 1);

  const getModelIcon = () => {
    return blockedModel === 'gemini-2.5-flash' ? 
      <Zap className="h-5 w-5 text-blue-500" /> : 
      <Zap className="h-5 w-5 text-accent" />;
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent 
        className="max-w-md" 
        aria-labelledby="rate-limit-dialog-title"
        aria-describedby="rate-limit-dialog-description"
      >
        <DialogHeader>
          <div className="flex items-center space-x-2">
            <AlertTriangle className="h-5 w-5 text-red-500" />
            <DialogTitle id="rate-limit-dialog-title">Rate Limit Reached</DialogTitle>
          </div>
          <DialogDescription id="rate-limit-dialog-description">
            You've reached the rate limit for Gemini {modelName} model
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Model and Limit Info */}
          <div className="p-4 bg-gray-50 rounded-lg space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                {getModelIcon()}
                <span className="font-medium">Gemini {modelName}</span>
              </div>
              <Badge variant="destructive" className="text-xs">
                {blockedBy.toUpperCase()} Limit
              </Badge>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Requests {limitType}</span>
                <span className="font-mono">{currentUsed}/{currentLimit}</span>
              </div>
              <Progress 
                value={utilization * 100} 
                className="h-2"
                aria-valuenow={Math.round(utilization * 100)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`Rate limit utilization: ${Math.round(utilization * 100)}% used`}
                role="progressbar"
              />
              <div className="text-xs text-gray-500">
                {Math.round(utilization * 100)}% of free tier limit used
              </div>
            </div>
          </div>

          {/* Reset Timer */}
          <div className="flex items-center justify-center p-4 bg-blue-50 rounded-lg">
            <div className="text-center space-y-2">
              <div className="flex items-center justify-center space-x-2">
                <Clock className="h-4 w-4 text-blue-500" />
                <span className="text-sm font-medium">Limit resets in</span>
              </div>
              <div className="text-2xl font-mono font-bold text-blue-600">
                {formatTimeRemaining(timeRemaining)}
              </div>
            </div>
          </div>

          {/* Additional Info */}
          <div className="text-sm text-gray-600 space-y-1">
            <p>
              <strong>What happened?</strong> You've reached the {blockedBy.toUpperCase()} limit for 
              the Gemini {modelName} model. This helps keep the service free by staying within 
              Google's free tier limits.
            </p>
            <p>
              <strong>What's next?</strong> You can wait for the limit to reset or try using a 
              different model if available.
            </p>
          </div>

          {/* Safety Margin Info */}
          {metadata.safety_margin > 0 && (
            <div className="text-xs text-gray-500 p-2 bg-yellow-50 rounded border-l-2 border-yellow-200">
              <strong>Safety margin:</strong> Limits are set to {Math.round(metadata.safety_margin * 100)}% 
              below Google's actual limits to prevent any overage charges.
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex space-x-2 pt-2">
            {onRetry && timeRemaining <= 0 && (
              <Button onClick={onRetry} className="flex-1">
                <RefreshCw className="h-4 w-4 mr-2" />
                Try Again
              </Button>
            )}
            <Button 
              variant={onCancel ? "outline" : "default"} 
              onClick={onCancel || onClose} 
              className={onCancel ? "flex-1" : "w-full"}
            >
              {onCancel ? 'Cancel Request' : 'Close'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};