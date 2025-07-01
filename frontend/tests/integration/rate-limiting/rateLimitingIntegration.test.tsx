import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { RateLimitStatus, RateLimitWarning } from '@/components/rate-limiting';
import * as rateLimitApiModule from '@/lib/api/rateLimitApi';

// Mock the API module
vi.mock('@/lib/api/rateLimitApi', () => ({
  rateLimitApi: {
    getStatus: vi.fn(),
    checkRateLimit: vi.fn(),
    resetLimits: vi.fn(),
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

const createMockStatus = (utilization: {
  flash_rpm: number;
  flash_rpd: number;
  pro_rpm: number;
  pro_rpd: number;
}) => ({
  timestamp: '2025-07-01T12:00:00Z',
  status: 'healthy' as const,
  message: 'Rate limiting system operating normally',
  details: {
    usage_stats: {
      flash_stats: {
        rpm_limit: 8,
        rpm_used: Math.floor(utilization.flash_rpm * 8),
        rpm_remaining: 8 - Math.floor(utilization.flash_rpm * 8),
        rpd_limit: 200,
        rpd_used: Math.floor(utilization.flash_rpd * 200),
        rpd_remaining: 200 - Math.floor(utilization.flash_rpd * 200),
        reset_time_rpm: '2025-07-01T12:05:00Z',
        reset_time_rpd: '2025-07-02T00:00:00Z',
        model: 'gemini-2.5-flash',
        safety_margin: 0.2,
      },
      pro_stats: {
        rpm_limit: 4,
        rpm_used: Math.floor(utilization.pro_rpm * 4),
        rpm_remaining: 4 - Math.floor(utilization.pro_rpm * 4),
        rpd_limit: 80,
        rpd_used: Math.floor(utilization.pro_rpd * 80),
        rpd_remaining: 80 - Math.floor(utilization.pro_rpd * 80),
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
    utilization,
  },
});

// Component that integrates both status and warning
const IntegratedRateLimitingDemo: React.FC = () => {
  return (
    <div>
      <RateLimitStatus 
        autoUpdate={false}
        showDetails={true}
      />
      <RateLimitWarning 
        autoCheck={false}
        warningThreshold={0.7}
        criticalThreshold={0.85}
      />
    </div>
  );
};

describe('Rate Limiting Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock console.warn to avoid noisy test output
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.restoreAllMocks();
  });

  it('shows healthy status and no warnings under normal conditions', async () => {
    const healthyStatus = createMockStatus({
      flash_rpm: 0.25,
      flash_rpd: 0.25,
      pro_rpm: 0.25,
      pro_rpd: 0.25,
    });
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(healthyStatus);
    
    render(<IntegratedRateLimitingDemo />);
    
    await waitFor(() => {
      expect(screen.getByText('healthy')).toBeInTheDocument();
      expect(screen.getByText('Flash (2.5)')).toBeInTheDocument();
      expect(screen.getByText('Pro (2.5)')).toBeInTheDocument();
    });
    
    // No warnings should be shown
    expect(screen.queryByText('Warning: Approaching rate limits')).not.toBeInTheDocument();
    expect(screen.queryByText('Critical: Rate limits nearly exhausted!')).not.toBeInTheDocument();
  });

  it('shows warning status and warning alert when approaching limits', async () => {
    const warningStatus = createMockStatus({
      flash_rpm: 0.8, // Above warning threshold
      flash_rpd: 0.5,
      pro_rpm: 0.5,
      pro_rpd: 0.5,
    });
    
    warningStatus.status = 'warning';
    warningStatus.message = 'Approaching rate limits';
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(warningStatus);
    
    render(<IntegratedRateLimitingDemo />);
    
    await waitFor(() => {
      expect(screen.getByText('warning')).toBeInTheDocument();
      expect(screen.getByText('Warning: Approaching rate limits')).toBeInTheDocument();
    });
    
    // Should show details about the specific limit being approached
    expect(screen.getByText('Flash RPM')).toBeInTheDocument();
    expect(screen.getByText('80% used')).toBeInTheDocument();
  });

  it('shows critical status and critical alert when nearly exhausted', async () => {
    const criticalStatus = createMockStatus({
      flash_rpm: 0.95, // Above critical threshold
      flash_rpd: 0.5,
      pro_rpm: 0.5,
      pro_rpd: 0.5,
    });
    
    criticalStatus.status = 'degraded';
    criticalStatus.message = 'Rate limits nearly exhausted';
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(criticalStatus);
    
    render(<IntegratedRateLimitingDemo />);
    
    await waitFor(() => {
      expect(screen.getByText('degraded')).toBeInTheDocument();
      expect(screen.getByText('Critical: Rate limits nearly exhausted!')).toBeInTheDocument();
    });
    
    // Should show critical-level messaging
    expect(screen.getByText(/Consider reducing usage or wait for limits to reset/)).toBeInTheDocument();
  });

  it('handles multiple models approaching limits simultaneously', async () => {
    const multipleWarningsStatus = createMockStatus({
      flash_rpm: 0.75, // Warning
      flash_rpd: 0.8,  // Warning
      pro_rpm: 0.85,   // Critical
      pro_rpd: 0.7,    // Warning
    });
    
    multipleWarningsStatus.status = 'warning';
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(multipleWarningsStatus);
    
    render(<IntegratedRateLimitingDemo />);
    
    await waitFor(() => {
      // Should show all models that are approaching limits
      expect(screen.getByText('Flash RPM')).toBeInTheDocument();
      expect(screen.getByText('Flash RPD')).toBeInTheDocument();
      expect(screen.getByText('Pro RPM')).toBeInTheDocument();
      expect(screen.getByText('Pro RPD')).toBeInTheDocument();
    });
    
    // Should show percentages for each
    expect(screen.getByText('75% used')).toBeInTheDocument();
    expect(screen.getByText('80% used')).toBeInTheDocument();
    expect(screen.getByText('85% used')).toBeInTheDocument();
    expect(screen.getByText('70% used')).toBeInTheDocument();
  });

  it('updates status and warnings together when API returns new data', async () => {
    // Start with healthy status
    const healthyStatus = createMockStatus({
      flash_rpm: 0.25,
      flash_rpd: 0.25,
      pro_rpm: 0.25,
      pro_rpd: 0.25,
    });
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(healthyStatus);
    
    const { rerender } = render(<IntegratedRateLimitingDemo />);
    
    await waitFor(() => {
      expect(screen.getByText('healthy')).toBeInTheDocument();
    });
    
    // Update to warning status
    const warningStatus = createMockStatus({
      flash_rpm: 0.8,
      flash_rpd: 0.25,
      pro_rpm: 0.25,
      pro_rpd: 0.25,
    });
    warningStatus.status = 'warning';
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(warningStatus);
    
    rerender(<IntegratedRateLimitingDemo />);
    
    await waitFor(() => {
      expect(screen.getByText('warning')).toBeInTheDocument();
      expect(screen.getByText('Warning: Approaching rate limits')).toBeInTheDocument();
    });
  });

  it('handles API errors consistently across components', async () => {
    const apiError = new Error('Network connection failed');
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockRejectedValue(apiError);
    
    render(<IntegratedRateLimitingDemo />);
    
    await waitFor(() => {
      // Status component should show error
      expect(screen.getByText('Network connection failed')).toBeInTheDocument();
    });
    
    // Warning component should handle error gracefully (not show warning)
    expect(screen.queryByText('Warning: Approaching rate limits')).not.toBeInTheDocument();
    
    // Console.warn should have been called by warning component
    expect(console.warn).toHaveBeenCalledWith('Failed to check rate limits:', apiError);
  });

  it('dismisses warnings independently of status updates', async () => {
    const warningStatus = createMockStatus({
      flash_rpm: 0.8,
      flash_rpd: 0.25,
      pro_rpm: 0.25,
      pro_rpd: 0.25,
    });
    warningStatus.status = 'warning';
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(warningStatus);
    
    render(<IntegratedRateLimitingDemo />);
    
    await waitFor(() => {
      expect(screen.getByText('Warning: Approaching rate limits')).toBeInTheDocument();
    });
    
    // Dismiss the warning
    const dismissButton = screen.getByRole('button');
    fireEvent.click(dismissButton);
    
    // Warning should be hidden but status should still show warning state
    expect(screen.queryByText('Warning: Approaching rate limits')).not.toBeInTheDocument();
    expect(screen.getByText('warning')).toBeInTheDocument();
  });

  it('shows real-time countdown in status tooltips', async () => {
    const status = createMockStatus({
      flash_rpm: 0.8,
      flash_rpd: 0.25,
      pro_rpm: 0.25,
      pro_rpd: 0.25,
    });
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(status);
    
    render(<IntegratedRateLimitingDemo />);
    
    await waitFor(() => {
      // Check that the formatted time is displayed
      expect(screen.getByText('5m 0s')).toBeInTheDocument();
    });
  });

  it('handles circuit breaker states correctly', async () => {
    const status = createMockStatus({
      flash_rpm: 0.25,
      flash_rpd: 0.25,
      pro_rpm: 0.25,
      pro_rpd: 0.25,
    });
    
    // Set circuit breakers to open state
    status.details.usage_stats.flash_circuit.state = 'open';
    status.details.usage_stats.pro_circuit.state = 'open';
    status.status = 'degraded';
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(status);
    
    render(<IntegratedRateLimitingDemo />);
    
    await waitFor(() => {
      expect(screen.getByText('degraded')).toBeInTheDocument();
    });
  });

  it('respects different thresholds for different components', async () => {
    const status = createMockStatus({
      flash_rpm: 0.6, // Between different thresholds
      flash_rpd: 0.25,
      pro_rpm: 0.25,
      pro_rpd: 0.25,
    });
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(status);
    
    // Render components with different thresholds
    render(
      <div>
        <RateLimitStatus autoUpdate={false} showDetails={true} />
        <RateLimitWarning 
          autoCheck={false}
          warningThreshold={0.5}  // Lower threshold
          criticalThreshold={0.8}
        />
      </div>
    );
    
    await waitFor(() => {
      // Status might show healthy but warning should trigger
      expect(screen.getByText('Warning: Approaching rate limits')).toBeInTheDocument();
    });
  });

  it('maintains performance with frequent updates', async () => {
    vi.useFakeTimers();
    
    const status = createMockStatus({
      flash_rpm: 0.25,
      flash_rpd: 0.25,
      pro_rpm: 0.25,
      pro_rpd: 0.25,
    });
    
    vi.mocked(rateLimitApiModule.rateLimitApi.getStatus).mockResolvedValue(status);
    
    render(
      <div>
        <RateLimitStatus autoUpdate={true} updateInterval={1000} />
        <RateLimitWarning autoCheck={true} checkInterval={1000} />
      </div>
    );
    
    // Initial calls
    await waitFor(() => {
      expect(rateLimitApiModule.rateLimitApi.getStatus).toHaveBeenCalledTimes(2);
    });
    
    // Advance time multiple times
    for (let i = 0; i < 5; i++) {
      act(() => {
        vi.advanceTimersByTime(1000);
      });
    }
    
    await waitFor(() => {
      // Should have made additional calls but not excessive
      expect(rateLimitApiModule.rateLimitApi.getStatus).toHaveBeenCalledTimes(12); // 2 initial + 5*2 updates
    });
    
    vi.useRealTimers();
  });
});