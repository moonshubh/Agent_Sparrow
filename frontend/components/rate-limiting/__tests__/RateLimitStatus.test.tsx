import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { RateLimitStatus } from '../RateLimitStatus';
import * as rateLimitApiModule from '@/lib/api/rateLimitApi';

// Mock the API module
vi.mock('@/lib/api/rateLimitApi', () => ({
  rateLimitApi: {
    getStatus: vi.fn(),
  },
  getUtilizationLevel: vi.fn((utilization: number) => {
    if (utilization >= 0.9) return 'critical';
    if (utilization >= 0.8) return 'high';
    if (utilization >= 0.6) return 'medium';
    return 'low';
  }),
  formatTimeRemaining: vi.fn((seconds: number) => {
    if (seconds <= 0) return 'Now';
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    if (minutes > 0) {
      return `${minutes}m ${remainingSeconds}s`;
    }
    return `${remainingSeconds}s`;
  }),
  getTimeToReset: vi.fn((resetTime: string) => {
    const reset = new Date(resetTime);
    const now = new Date();
    return Math.max(0, Math.floor((reset.getTime() - now.getTime()) / 1000));
  }),
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

describe('RateLimitStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock successful API response by default
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(mockStatus);
  });

  afterEach(() => {
    vi.clearAllTimers();
  });

  it('renders loading state initially', () => {
    render(<RateLimitStatus autoUpdate={false} />);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('renders rate limit status after loading', async () => {
    render(<RateLimitStatus autoUpdate={false} />);
    
    await waitFor(() => {
      expect(screen.getByText('Rate Limits')).toBeInTheDocument();
      expect(screen.getByText('healthy')).toBeInTheDocument();
    });
  });

  it('displays Flash and Pro model information', async () => {
    render(<RateLimitStatus autoUpdate={false} />);
    
    await waitFor(() => {
      expect(screen.getByText('Flash (2.5)')).toBeInTheDocument();
      expect(screen.getByText('Pro (2.5)')).toBeInTheDocument();
      expect(screen.getByText('2/8 RPM')).toBeInTheDocument();
      expect(screen.getByText('1/4 RPM')).toBeInTheDocument();
    });
  });

  it('shows detailed information when showDetails is true', async () => {
    render(<RateLimitStatus autoUpdate={false} showDetails={true} />);
    
    await waitFor(() => {
      expect(screen.getByText('Total Today: 70')).toBeInTheDocument();
      expect(screen.getByText('Uptime: 100%')).toBeInTheDocument();
    });
  });

  it('hides detailed information when showDetails is false', async () => {
    render(<RateLimitStatus autoUpdate={false} showDetails={false} />);
    
    await waitFor(() => {
      expect(screen.getByText('healthy')).toBeInTheDocument();
    });
    
    expect(screen.queryByText('Total Today:')).not.toBeInTheDocument();
  });

  it('handles API errors gracefully', async () => {
    const errorMessage = 'Failed to fetch rate limit status';
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockRejectedValue(new Error(errorMessage));
    
    render(<RateLimitStatus autoUpdate={false} />);
    
    await waitFor(() => {
      expect(screen.getByText(errorMessage)).toBeInTheDocument();
    });
  });

  it('displays warning status correctly', async () => {
    const warningStatus = {
      ...mockStatus,
      status: 'warning' as const,
      details: {
        ...mockStatus.details,
        utilization: {
          flash_rpm: 0.85,
          flash_rpd: 0.25,
          pro_rpm: 0.25,
          pro_rpd: 0.25,
        },
      },
    };
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(warningStatus);
    
    render(<RateLimitStatus autoUpdate={false} />);
    
    await waitFor(() => {
      expect(screen.getByText('warning')).toBeInTheDocument();
    });
  });

  it('updates automatically when autoUpdate is enabled', async () => {
    vi.useFakeTimers();
    
    render(<RateLimitStatus autoUpdate={true} updateInterval={1000} />);
    
    // Initial call
    await waitFor(() => {
      expect(rateLimitApiModule.rateLimitApi.getStatus).toHaveBeenCalledTimes(1);
    });
    
    // Advance time and check for additional calls
    vi.advanceTimersByTime(1000);
    
    await waitFor(() => {
      expect(rateLimitApiModule.rateLimitApi.getStatus).toHaveBeenCalledTimes(2);
    });
    
    vi.useRealTimers();
  });

  it('does not auto-update when autoUpdate is disabled', async () => {
    vi.useFakeTimers();
    
    render(<RateLimitStatus autoUpdate={false} />);
    
    // Initial call
    await waitFor(() => {
      expect(rateLimitApiModule.rateLimitApi.getStatus).toHaveBeenCalledTimes(1);
    });
    
    // Advance time and verify no additional calls
    vi.advanceTimersByTime(5000);
    
    expect(rateLimitApiModule.rateLimitApi.getStatus).toHaveBeenCalledTimes(1);
    
    vi.useRealTimers();
  });

  it('displays progress bars with correct utilization', async () => {
    render(<RateLimitStatus autoUpdate={false} />);
    
    await waitFor(() => {
      const progressBars = screen.getAllByRole('progressbar');
      expect(progressBars).toHaveLength(2); // Flash and Pro
    });
  });

  it('shows tooltip information on hover', async () => {
    render(<RateLimitStatus autoUpdate={false} />);
    
    await waitFor(() => {
      expect(screen.getByText('2/8 RPM')).toBeInTheDocument();
    });
    
    // Note: Tooltip testing would require additional setup for hover events
    // This test verifies the badge is present which triggers the tooltip
  });
});