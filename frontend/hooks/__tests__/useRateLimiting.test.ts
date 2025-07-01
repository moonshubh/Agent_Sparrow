import { renderHook, waitFor, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { useRateLimiting } from '../useRateLimiting';
import * as rateLimitApiModule from '@/lib/api/rateLimitApi';

// Mock the API module
vi.mock('@/lib/api/rateLimitApi', () => ({
  rateLimitApi: {
    getStatus: vi.fn(),
    checkRateLimit: vi.fn(),
    resetLimits: vi.fn(),
  },
}));

const mockStatus = {
  timestamp: '2025-07-01T12:00:00Z',
  status: 'healthy' as const,
  message: 'Rate limiting system operating normally',
  details: {
    usage_stats: {
      flash_stats: {
        rpm_limit: 8,
        rpm_used: 2,
        rpm_remaining: 6,
        rpd_limit: 200,
        rpd_used: 50,
        rpd_remaining: 150,
        reset_time_rpm: '2025-07-01T12:01:00Z',
        reset_time_rpd: '2025-07-02T00:00:00Z',
        model: 'gemini-2.5-flash',
        safety_margin: 0.2,
      },
      pro_stats: {
        rpm_limit: 4,
        rpm_used: 1,
        rpm_remaining: 3,
        rpd_limit: 80,
        rpd_used: 20,
        rpd_remaining: 60,
        reset_time_rpm: '2025-07-01T12:01:00Z',
        reset_time_rpd: '2025-07-02T00:00:00Z',
        model: 'gemini-2.5-pro',
        safety_margin: 0.2,
      },
      flash_circuit: {
        state: 'closed' as const,
        failure_count: 0,
        success_count: 0,
        last_failure_time: null,
        next_attempt_time: null,
      },
      pro_circuit: {
        state: 'closed' as const,
        failure_count: 0,
        success_count: 0,
        last_failure_time: null,
        next_attempt_time: null,
      },
      total_requests_today: 70,
      total_requests_this_minute: 3,
      uptime_percentage: 99.5,
      last_updated: '2025-07-01T12:00:00Z',
    },
    health: {
      overall: 'healthy',
    },
    utilization: {
      flash_rpm: 0.25,
      flash_rpd: 0.25,
      pro_rpm: 0.25,
      pro_rpd: 0.25,
    },
  },
};

describe('useRateLimiting', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(mockStatus);
    vi.mocked(rateLimitApiModule.rateLimitApi.checkRateLimit).mockResolvedValue({
      model: 'gemini-2.5-flash',
      allowed: true,
      metadata: mockStatus.details.usage_stats.flash_stats,
      retry_after: null,
      blocked_by: null,
    });
    vi.mocked(rateLimitApiModule.rateLimitApi.resetLimits).mockResolvedValue({
      success: true,
      message: 'Reset successful',
      timestamp: '2025-07-01T12:00:00Z',
    });
  });

  afterEach(() => {
    vi.clearAllTimers();
  });

  it('initializes with loading state', () => {
    const { result } = renderHook(() => useRateLimiting({ autoCheck: false }));
    
    expect(result.current.loading).toBe(true);
    expect(result.current.status).toBe(null);
    expect(result.current.error).toBe(null);
  });

  it('loads status on mount when autoCheck is enabled', async () => {
    const { result } = renderHook(() => useRateLimiting({ autoCheck: true }));
    
    await waitFor(() => {
      expect(result.current.loading).toBe(false);
      expect(result.current.status).toEqual(mockStatus);
      expect(result.current.error).toBe(null);
    });
  });

  it('does not auto-load when autoCheck is disabled', () => {
    renderHook(() => useRateLimiting({ autoCheck: false }));
    
    expect(rateLimitApiModule.rateLimitApi.getStatus).not.toHaveBeenCalled();
  });

  it('calculates warning states correctly', async () => {
    const warningStatus = {
      ...mockStatus,
      details: {
        ...mockStatus.details,
        utilization: {
          flash_rpm: 0.8, // Above warning threshold
          flash_rpd: 0.5,
          pro_rpm: 0.5,
          pro_rpd: 0.5,
        },
      },
    };
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(warningStatus);
    
    const { result } = renderHook(() => useRateLimiting({
      autoCheck: true,
      warningThreshold: 0.7,
      criticalThreshold: 0.85,
    }));
    
    await waitFor(() => {
      expect(result.current.isNearLimit).toBe(true);
      expect(result.current.isCritical).toBe(false);
      expect(result.current.getWarningLevel()).toBe('warning');
    });
  });

  it('calculates critical states correctly', async () => {
    const criticalStatus = {
      ...mockStatus,
      details: {
        ...mockStatus.details,
        utilization: {
          flash_rpm: 0.9, // Above critical threshold
          flash_rpd: 0.5,
          pro_rpm: 0.5,
          pro_rpd: 0.5,
        },
      },
    };
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(criticalStatus);
    
    const { result } = renderHook(() => useRateLimiting({
      autoCheck: true,
      warningThreshold: 0.7,
      criticalThreshold: 0.85,
    }));
    
    await waitFor(() => {
      expect(result.current.isNearLimit).toBe(true);
      expect(result.current.isCritical).toBe(true);
      expect(result.current.getWarningLevel()).toBe('critical');
    });
  });

  it('identifies blocked models correctly', async () => {
    const blockedStatus = {
      ...mockStatus,
      details: {
        ...mockStatus.details,
        utilization: {
          flash_rpm: 1.0, // At limit
          flash_rpd: 0.5,
          pro_rpm: 0.5,
          pro_rpd: 1.0, // At limit
        },
      },
    };
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(blockedStatus);
    
    const { result } = renderHook(() => useRateLimiting({ autoCheck: true }));
    
    await waitFor(() => {
      expect(result.current.blockedModels).toContain('gemini-2.5-flash');
      expect(result.current.blockedModels).toContain('gemini-2.5-pro');
      expect(result.current.isModelBlocked('gemini-2.5-flash')).toBe(true);
      expect(result.current.isModelBlocked('gemini-2.5-pro')).toBe(true);
    });
  });

  it('handles API errors gracefully', async () => {
    const errorMessage = 'Network error';
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockRejectedValue(new Error(errorMessage));
    
    const { result } = renderHook(() => useRateLimiting({ autoCheck: true }));
    
    await waitFor(() => {
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBe(errorMessage);
      expect(result.current.status).toBe(null);
    });
  });

  it('refreshes status manually', async () => {
    const { result } = renderHook(() => useRateLimiting({ autoCheck: false }));
    
    await act(async () => {
      result.current.refreshStatus();
    });
    
    await waitFor(() => {
      expect(result.current.status).toEqual(mockStatus);
      expect(result.current.loading).toBe(false);
    });
  });

  it('checks model availability', async () => {
    const { result } = renderHook(() => useRateLimiting({ autoCheck: false }));
    
    let checkResult;
    await act(async () => {
      checkResult = await result.current.checkModelAvailability('gemini-2.5-flash');
    });
    
    expect(checkResult).toEqual({
      model: 'gemini-2.5-flash',
      allowed: true,
      metadata: mockStatus.details.usage_stats.flash_stats,
      retry_after: null,
      blocked_by: null,
    });
  });

  it('resets limits successfully', async () => {
    const { result } = renderHook(() => useRateLimiting({ autoCheck: false }));
    
    let resetResult;
    await act(async () => {
      resetResult = await result.current.resetLimits('gemini-2.5-flash');
    });
    
    expect(resetResult).toBe(true);
    expect(rateLimitApiModule.rateLimitApi.resetLimits).toHaveBeenCalledWith('gemini-2.5-flash');
  });

  it('handles reset errors', async () => {
    vi.mocked(rateLimitApiModule.rateLimitApi.resetLimits).mockRejectedValue(new Error('Reset failed'));
    
    const { result } = renderHook(() => useRateLimiting({ autoCheck: false }));
    
    let resetResult;
    await act(async () => {
      resetResult = await result.current.resetLimits();
    });
    
    expect(resetResult).toBe(false);
    expect(result.current.error).toBe('Reset failed');
  });

  it('auto-checks at specified intervals', async () => {
    vi.useFakeTimers();
    
    renderHook(() => useRateLimiting({
      autoCheck: true,
      checkInterval: 5000,
    }));
    
    // Initial call
    await waitFor(() => {
      expect(rateLimitApiModule.rateLimitApi.getStatus).toHaveBeenCalledTimes(1);
    });
    
    // Advance time and check for additional calls
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    
    await waitFor(() => {
      expect(rateLimitApiModule.rateLimitApi.getStatus).toHaveBeenCalledTimes(2);
    });
    
    vi.useRealTimers();
  });

  it('returns correct utilization values', async () => {
    const { result } = renderHook(() => useRateLimiting({ autoCheck: true }));
    
    await waitFor(() => {
      expect(result.current.getUtilization('flash', 'rpm')).toBe(0.25);
      expect(result.current.getUtilization('flash', 'rpd')).toBe(0.25);
      expect(result.current.getUtilization('pro', 'rpm')).toBe(0.25);
      expect(result.current.getUtilization('pro', 'rpd')).toBe(0.25);
    });
  });

  it('returns zero utilization when no status available', () => {
    const { result } = renderHook(() => useRateLimiting({ autoCheck: false }));
    
    expect(result.current.getUtilization('flash', 'rpm')).toBe(0);
  });

  it('cleans up intervals on unmount', () => {
    vi.useFakeTimers();
    const clearIntervalSpy = vi.spyOn(global, 'clearInterval');
    
    const { unmount } = renderHook(() => useRateLimiting({
      autoCheck: true,
      checkInterval: 1000,
    }));
    
    unmount();
    
    expect(clearIntervalSpy).toHaveBeenCalled();
    
    vi.useRealTimers();
  });

  it('respects custom thresholds', async () => {
    const customStatus = {
      ...mockStatus,
      details: {
        ...mockStatus.details,
        utilization: {
          flash_rpm: 0.6, // Between custom thresholds
          flash_rpd: 0.5,
          pro_rpm: 0.5,
          pro_rpd: 0.5,
        },
      },
    };
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(customStatus);
    
    const { result } = renderHook(() => useRateLimiting({
      autoCheck: true,
      warningThreshold: 0.5,
      criticalThreshold: 0.8,
    }));
    
    await waitFor(() => {
      expect(result.current.isNearLimit).toBe(true);
      expect(result.current.isCritical).toBe(false);
    });
  });
});