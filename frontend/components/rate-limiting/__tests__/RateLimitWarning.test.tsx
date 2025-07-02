import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { RateLimitWarning } from '../RateLimitWarning';
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
  getTimeToReset: vi.fn(() => 300), // 5 minutes
}));

const createMockStatus = (utilization: Partial<{
  flash_rpm: number;
  flash_rpd: number;
  pro_rpm: number;
  pro_rpd: number;
}>) => ({
  timestamp: '2025-07-01T12:00:00Z',
  status: 'warning' as const,
  message: 'Approaching rate limits',
  details: {
    usage_stats: {
      flash_stats: {
        rpm_limit: 8,
        rpm_used: Math.floor((utilization.flash_rpm || 0) * 8),
        rpm_remaining: 8 - Math.floor((utilization.flash_rpm || 0) * 8),
        rpd_limit: 200,
        rpd_used: Math.floor((utilization.flash_rpd || 0) * 200),
        rpd_remaining: 200 - Math.floor((utilization.flash_rpd || 0) * 200),
        reset_time_rpm: '2025-07-01T12:05:00Z',
        reset_time_rpd: '2025-07-02T00:00:00Z',
        model: 'gemini-2.5-flash',
        safety_margin: 0.2,
      },
      pro_stats: {
        rpm_limit: 4,
        rpm_used: Math.floor((utilization.pro_rpm || 0) * 4),
        rpm_remaining: 4 - Math.floor((utilization.pro_rpm || 0) * 4),
        rpd_limit: 80,
        rpd_used: Math.floor((utilization.pro_rpd || 0) * 80),
        rpd_remaining: 80 - Math.floor((utilization.pro_rpd || 0) * 80),
        reset_time_rpm: '2025-07-01T12:05:00Z',
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
      total_requests_today: 250,
      total_requests_this_minute: 10,
      uptime_percentage: 99.5,
      last_updated: '2025-07-01T12:00:00Z',
    },
    health: {
      overall: 'healthy',
    },
    utilization: {
      flash_rpm: utilization.flash_rpm || 0,
      flash_rpd: utilization.flash_rpd || 0,
      pro_rpm: utilization.pro_rpm || 0,
      pro_rpd: utilization.pro_rpd || 0,
    },
  },
});

describe('RateLimitWarning', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock console.warn to avoid noisy test output
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.restoreAllMocks();
  });

  it('does not render when utilization is below warning threshold', async () => {
    const mockStatus = createMockStatus({
      flash_rpm: 0.5,
      flash_rpd: 0.5,
      pro_rpm: 0.5,
      pro_rpd: 0.5,
    });
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(mockStatus);
    
    render(<RateLimitWarning autoCheck={false} />);
    
    await waitFor(() => {
      expect(rateLimitApiModule.rateLimitApi.getStatus).toHaveBeenCalled();
    });
    
    expect(screen.queryByText('Warning: Approaching rate limits')).not.toBeInTheDocument();
  });

  it('renders warning when utilization exceeds warning threshold', async () => {
    const mockStatus = createMockStatus({
      flash_rpm: 0.75, // Above default 0.7 threshold
      flash_rpd: 0.5,
      pro_rpm: 0.5,
      pro_rpd: 0.5,
    });
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(mockStatus);
    
    render(<RateLimitWarning autoCheck={false} />);
    
    await waitFor(() => {
      expect(screen.getByText('Warning: Approaching rate limits')).toBeInTheDocument();
    });
  });

  it('renders critical warning when utilization exceeds critical threshold', async () => {
    const mockStatus = createMockStatus({
      flash_rpm: 0.9, // Above default 0.85 critical threshold
      flash_rpd: 0.5,
      pro_rpm: 0.5,
      pro_rpd: 0.5,
    });
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(mockStatus);
    
    render(<RateLimitWarning autoCheck={false} />);
    
    await waitFor(() => {
      expect(screen.getByText('Critical: Rate limits nearly exhausted!')).toBeInTheDocument();
    });
  });

  it('shows details for all models exceeding threshold', async () => {
    const mockStatus = createMockStatus({
      flash_rpm: 0.8,
      flash_rpd: 0.75,
      pro_rpm: 0.85,
      pro_rpd: 0.7,
    });
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(mockStatus);
    
    render(<RateLimitWarning autoCheck={false} />);
    
    await waitFor(() => {
      expect(screen.getByText('Flash RPM')).toBeInTheDocument();
      expect(screen.getByText('Flash RPD')).toBeInTheDocument();
      expect(screen.getByText('Pro RPM')).toBeInTheDocument();
      expect(screen.getByText('Pro RPD')).toBeInTheDocument();
    });
  });

  it('displays utilization percentages correctly', async () => {
    const mockStatus = createMockStatus({
      flash_rpm: 0.8,
      flash_rpd: 0.5,
      pro_rpm: 0.5,
      pro_rpd: 0.5,
    });
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(mockStatus);
    
    render(<RateLimitWarning autoCheck={false} />);
    
    await waitFor(() => {
      expect(screen.getByText('80% used')).toBeInTheDocument();
    });
  });

  it('shows remaining counts and reset times', async () => {
    const mockStatus = createMockStatus({
      flash_rpm: 0.8,
      flash_rpd: 0.5,
      pro_rpm: 0.5,
      pro_rpd: 0.5,
    });
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(mockStatus);
    
    render(<RateLimitWarning autoCheck={false} />);
    
    await waitFor(() => {
      expect(screen.getByText(/remaining • Resets in/)).toBeInTheDocument();
    });
  });

  it('can be dismissed when dismissible is true', async () => {
    const mockStatus = createMockStatus({
      flash_rpm: 0.8,
      flash_rpd: 0.5,
      pro_rpm: 0.5,
      pro_rpd: 0.5,
    });
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(mockStatus);
    
    render(<RateLimitWarning autoCheck={false} dismissible={true} />);
    
    await waitFor(() => {
      expect(screen.getByText('Warning: Approaching rate limits')).toBeInTheDocument();
    });
    
    const dismissButton = screen.getByRole('button');
    fireEvent.click(dismissButton);
    
    expect(screen.queryByText('Warning: Approaching rate limits')).not.toBeInTheDocument();
  });

  it('cannot be dismissed when dismissible is false', async () => {
    const mockStatus = createMockStatus({
      flash_rpm: 0.8,
      flash_rpd: 0.5,
      pro_rpm: 0.5,
      pro_rpd: 0.5,
    });
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(mockStatus);
    
    render(<RateLimitWarning autoCheck={false} dismissible={false} />);
    
    await waitFor(() => {
      expect(screen.getByText('Warning: Approaching rate limits')).toBeInTheDocument();
    });
    
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('calls onDismiss callback when dismissed', async () => {
    const onDismiss = vi.fn();
    const mockStatus = createMockStatus({
      flash_rpm: 0.8,
      flash_rpd: 0.5,
      pro_rpm: 0.5,
      pro_rpd: 0.5,
    });
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(mockStatus);
    
    render(<RateLimitWarning autoCheck={false} onDismiss={onDismiss} />);
    
    await waitFor(() => {
      expect(screen.getByText('Warning: Approaching rate limits')).toBeInTheDocument();
    });
    
    const dismissButton = screen.getByRole('button');
    fireEvent.click(dismissButton);
    
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('auto-checks at specified intervals', async () => {
    vi.useFakeTimers();
    
    const mockStatus = createMockStatus({
      flash_rpm: 0.5,
      flash_rpd: 0.5,
      pro_rpm: 0.5,
      pro_rpd: 0.5,
    });
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(mockStatus);
    
    render(<RateLimitWarning autoCheck={true} checkInterval={5000} />);
    
    // Initial call
    await waitFor(() => {
      expect(rateLimitApiModule.rateLimitApi.getStatus).toHaveBeenCalledTimes(1);
    });
    
    // Advance time and check for additional calls
    vi.advanceTimersByTime(5000);
    
    await waitFor(() => {
      expect(rateLimitApiModule.rateLimitApi.getStatus).toHaveBeenCalledTimes(2);
    });
    
    vi.useRealTimers();
  });

  it('handles API errors gracefully without showing warning', async () => {
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockRejectedValue(new Error('API Error'));
    
    render(<RateLimitWarning autoCheck={false} />);
    
    await waitFor(() => {
      expect(rateLimitApiModule.rateLimitApi.getStatus).toHaveBeenCalled();
    });
    
    // Should not show warning on error
    expect(screen.queryByText('Warning: Approaching rate limits')).not.toBeInTheDocument();
    
    // Console.warn should have been called
    expect(console.warn).toHaveBeenCalledWith('Failed to check rate limits:', expect.any(Error));
  });

  it('respects custom thresholds', async () => {
    const mockStatus = createMockStatus({
      flash_rpm: 0.6, // Between 0.5 (custom warning) and 0.8 (custom critical)
      flash_rpd: 0.5,
      pro_rpm: 0.5,
      pro_rpd: 0.5,
    });
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(mockStatus);
    
    render(
      <RateLimitWarning 
        autoCheck={false} 
        warningThreshold={0.5} 
        criticalThreshold={0.8} 
      />
    );
    
    await waitFor(() => {
      expect(screen.getByText('Warning: Approaching rate limits')).toBeInTheDocument();
    });
  });
});