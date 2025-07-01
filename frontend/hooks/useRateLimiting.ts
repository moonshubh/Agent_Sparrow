/**
 * React hook for rate limiting functionality
 */

import { useState, useEffect, useCallback } from 'react';
import { rateLimitApi, type RateLimitStatus, type RateLimitCheckResult } from '@/lib/api/rateLimitApi';

interface UseRateLimitingOptions {
  autoCheck?: boolean;
  checkInterval?: number;
  warningThreshold?: number;
  criticalThreshold?: number;
}

interface RateLimitState {
  status: RateLimitStatus | null;
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  isNearLimit: boolean;
  isCritical: boolean;
  blockedModels: string[];
}

export const useRateLimiting = (options: UseRateLimitingOptions = {}) => {
  const {
    autoCheck = true,
    checkInterval = 30000, // 30 seconds
    warningThreshold = 0.7,
    criticalThreshold = 0.85,
  } = options;

  const [state, setState] = useState<RateLimitState>({
    status: null,
    loading: true,
    error: null,
    lastUpdated: null,
    isNearLimit: false,
    isCritical: false,
    blockedModels: [],
  });

  const checkRateLimits = useCallback(async () => {
    try {
      setState(prev => ({ ...prev, error: null }));
      
      const status = await rateLimitApi.getStatus();
      const { utilization } = status.details;
      
      // Determine warning states
      const maxUtilization = Math.max(
        utilization.flash_rpm,
        utilization.flash_rpd,
        utilization.pro_rpm,
        utilization.pro_rpd
      );
      
      const isNearLimit = maxUtilization >= warningThreshold;
      const isCritical = maxUtilization >= criticalThreshold;
      
      // Check which models are blocked
      const blockedModels: string[] = [];
      
      if (utilization.flash_rpm >= 1.0 || utilization.flash_rpd >= 1.0) {
        blockedModels.push('gemini-2.5-flash');
      }
      
      if (utilization.pro_rpm >= 1.0 || utilization.pro_rpd >= 1.0) {
        blockedModels.push('gemini-2.5-pro');
      }
      
      setState(prev => ({
        ...prev,
        status,
        loading: false,
        lastUpdated: new Date(),
        isNearLimit,
        isCritical,
        blockedModels,
      }));
      
    } catch (error) {
      setState(prev => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Failed to check rate limits',
        loading: false,
      }));
    }
  }, [warningThreshold, criticalThreshold]);

  const checkModelAvailability = useCallback(async (model: 'gemini-2.5-flash' | 'gemini-2.5-pro'): Promise<RateLimitCheckResult> => {
    return rateLimitApi.checkRateLimit(model);
  }, []);

  const refreshStatus = useCallback(() => {
    setState(prev => ({ ...prev, loading: true }));
    checkRateLimits();
  }, [checkRateLimits]);

  const resetLimits = useCallback(async (model?: string) => {
    try {
      await rateLimitApi.resetLimits(model);
      // Refresh status after reset
      await checkRateLimits();
      return true;
    } catch (error) {
      setState(prev => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Failed to reset rate limits',
      }));
      return false;
    }
  }, [checkRateLimits]);

  // Auto-check rate limits
  useEffect(() => {
    if (autoCheck) {
      checkRateLimits();
      const interval = setInterval(checkRateLimits, checkInterval);
      return () => clearInterval(interval);
    }
  }, [autoCheck, checkInterval, checkRateLimits]);

  return {
    // State
    status: state.status,
    loading: state.loading,
    error: state.error,
    lastUpdated: state.lastUpdated,
    isNearLimit: state.isNearLimit,
    isCritical: state.isCritical,
    blockedModels: state.blockedModels,
    
    // Actions
    refreshStatus,
    checkModelAvailability,
    resetLimits,
    
    // Utilities
    isModelBlocked: (model: string) => state.blockedModels.includes(model),
    getUtilization: (model: 'flash' | 'pro', type: 'rpm' | 'rpd') => {
      if (!state.status) return 0;
      return state.status.details.utilization[`${model}_${type}` as keyof typeof state.status.details.utilization];
    },
    getWarningLevel: () => {
      if (state.isCritical) return 'critical';
      if (state.isNearLimit) return 'warning';
      return 'normal';
    },
  };
};