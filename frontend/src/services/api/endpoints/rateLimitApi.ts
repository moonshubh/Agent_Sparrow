/**
 * API client for rate limiting endpoints
 */

import { getApiBasePath } from '@/shared/lib/utils/environment';

// Use environment-aware API base URL
const API_BASE_URL = getApiBasePath();

// Type definitions matching backend schemas
export interface RateLimitMetadata {
  bucket: string;
  provider: string;
  rpm_limit: number;
  rpm_used: number;
  rpm_remaining: number;
  rpd_limit: number;
  rpd_used: number;
  rpd_remaining: number;
  tpm_limit: number | null;
  tpm_used: number;
  tpm_remaining: number | null;
  reset_time_rpm: string;
  reset_time_rpd: string;
  reset_time_tpm: string | null;
  model: string;
  safety_margin: number;
}

export interface CircuitBreakerStatus {
  state: 'closed' | 'open' | 'half_open';
  failure_count: number;
  success_count: number;
  last_failure_time: string | null;
  next_attempt_time: string | null;
}

export interface UsageStats {
  buckets: Record<string, RateLimitMetadata>;
  circuits: Record<string, CircuitBreakerStatus>;
  total_requests_today: number;
  total_requests_this_minute: number;
  uptime_percentage: number;
  last_updated: string;
}

export interface RateLimitHealth {
  overall: 'healthy' | 'warning' | 'degraded' | 'unhealthy';
  [key: string]: unknown;
}

export interface RateLimitStatus {
  timestamp: string;
  status: 'healthy' | 'warning' | 'degraded' | 'unhealthy';
  message: string;
  details: {
    usage_stats: UsageStats;
    health: RateLimitHealth;
    utilization: Record<string, { rpm: number; rpd: number; tpm: number | null }>;
  };
}

export interface RateLimitCheckResult {
  bucket: string;
  allowed: boolean;
  metadata: RateLimitMetadata;
  retry_after: number | null;
  blocked_by: string | null;
}

export interface RateLimitConfig {
  rate_limiting: {
    safety_margin: number;
  };
  buckets: Record<
    string,
    {
      model_id: string;
      provider: string;
      rate_limits: { rpm: number; rpd: number; tpm?: number | null };
    }
  >;
  circuit_breaker: {
    enabled: boolean;
    failure_threshold: number;
    timeout_seconds: number;
    success_threshold: number;
  };
  redis: {
    key_prefix: string;
    db: number;
  };
  monitoring_enabled: boolean;
}

export type RateLimitMetrics = Record<string, number>;

class RateLimitApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}/rate-limits${endpoint}`;
    
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      throw new Error(`Rate limit API error: ${response.status} ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Get current rate limiting status and usage statistics
   */
  async getStatus(): Promise<RateLimitStatus> {
    return this.request<RateLimitStatus>('/status');
  }

  /**
   * Get detailed usage statistics for all models
   */
  async getUsageStats(): Promise<UsageStats> {
    return this.request<UsageStats>('/usage');
  }

  /**
   * Check system health
   */
  async getHealth(): Promise<RateLimitHealth> {
    return this.request<RateLimitHealth>('/health');
  }

  /**
   * Check if a request would be allowed for the specified bucket (dry-run).
   */
  async checkRateLimit(bucket: string): Promise<RateLimitCheckResult> {
    return this.request<RateLimitCheckResult>(`/check/${encodeURIComponent(bucket)}`, {
      method: 'POST',
    });
  }

  /**
   * Get current rate limiting configuration
   */
  async getConfig(): Promise<RateLimitConfig> {
    return this.request<RateLimitConfig>('/config');
  }

  /**
   * Get Prometheus-style metrics for rate limiting
   */
  async getMetrics(): Promise<RateLimitMetrics> {
    return this.request<RateLimitMetrics>('/metrics');
  }

  /**
   * Reset rate limits (development/emergency use only)
   */
  async resetLimits(bucket?: string): Promise<{ success: boolean; message: string; timestamp: string }> {
    return this.request<{ success: boolean; message: string; timestamp: string }>('/reset', {
      method: 'POST',
      body: JSON.stringify({
        bucket,
        confirm: true,
      }),
    });
  }
}

// Export singleton instance
export const rateLimitApi = new RateLimitApiClient();

// Export utility functions
export const getUtilizationLevel = (utilization: number): 'low' | 'medium' | 'high' | 'critical' => {
  if (utilization >= 0.9) return 'critical';
  if (utilization >= 0.8) return 'high';
  if (utilization >= 0.6) return 'medium';
  return 'low';
};

export const getTimeToReset = (resetTime: string): number => {
  const reset = new Date(resetTime);
  const now = new Date();
  return Math.max(0, Math.floor((reset.getTime() - now.getTime()) / 1000));
};

export const formatTimeRemaining = (seconds: number): string => {
  if (seconds <= 0) return 'Now';
  
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  
  if (minutes > 0) {
    return `${minutes}m ${remainingSeconds}s`;
  }
  
  return `${remainingSeconds}s`;
};
