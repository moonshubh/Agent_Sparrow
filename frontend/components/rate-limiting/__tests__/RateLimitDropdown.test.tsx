import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import { RateLimitDropdown } from '../RateLimitDropdown';
import * as rateLimitApi from '@/lib/api/rateLimitApi';

// Mock the rate limit API
vi.mock('@/lib/api/rateLimitApi', () => ({
  rateLimitApi: {
    getStatus: vi.fn(),
  },
  getUtilizationLevel: vi.fn(() => 'low'),
  formatTimeRemaining: vi.fn(() => '30s'),
  getTimeToReset: vi.fn(() => 30),
}));

const mockRateLimitApi = rateLimitApi.rateLimitApi as any;

const mockStatusData = {
  timestamp: new Date().toISOString(),
  status: 'healthy' as const,
  message: 'All systems operational',
  details: {
    usage_stats: {
      flash_stats: {
        rpm_limit: 8,
        rpm_used: 2,
        rpm_remaining: 6,
        rpd_limit: 200,
        rpd_used: 50,
        rpd_remaining: 150,
        reset_time_rpm: new Date(Date.now() + 60000).toISOString(),
        reset_time_rpd: new Date(Date.now() + 86400000).toISOString(),
        model: 'gemini-2.5-flash',
        safety_margin: 0.8,
      },
      pro_stats: {
        rpm_limit: 4,
        rpm_used: 1,
        rpm_remaining: 3,
        rpd_limit: 80,
        rpd_used: 20,
        rpd_remaining: 60,
        reset_time_rpm: new Date(Date.now() + 60000).toISOString(),
        reset_time_rpd: new Date(Date.now() + 86400000).toISOString(),
        model: 'gemini-2.5-pro',
        safety_margin: 0.8,
      },
      flash_circuit: {
        state: 'closed' as const,
        failure_count: 0,
        success_count: 100,
        last_failure_time: null,
        next_attempt_time: null,
      },
      pro_circuit: {
        state: 'closed' as const,
        failure_count: 0,
        success_count: 50,
        last_failure_time: null,
        next_attempt_time: null,
      },
      total_requests_today: 70,
      total_requests_this_minute: 3,
      uptime_percentage: 99.9,
      last_updated: new Date().toISOString(),
    },
    health: {},
    utilization: {
      flash_rpm: 0.25,
      flash_rpd: 0.25,
      pro_rpm: 0.25,
      pro_rpd: 0.25,
    },
  },
};

describe('RateLimitDropdown', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRateLimitApi.getStatus.mockResolvedValue(mockStatusData);
  });

  it('renders trigger button correctly', async () => {
    render(<RateLimitDropdown />);
    
    // Should show a button with status icon
    const triggerButton = screen.getByRole('button');
    expect(triggerButton).toBeInTheDocument();
    
    // Wait for loading to complete
    await waitFor(() => {
      expect(mockRateLimitApi.getStatus).toHaveBeenCalled();
    });
  });

  it('opens dropdown when clicked', async () => {
    render(<RateLimitDropdown />);
    
    // Wait for initial load
    await waitFor(() => {
      expect(mockRateLimitApi.getStatus).toHaveBeenCalled();
    });

    const triggerButton = screen.getByRole('button');
    fireEvent.click(triggerButton);

    // Should show dropdown content
    await waitFor(() => {
      expect(screen.getByText('Gemini API Limits')).toBeInTheDocument();
      expect(screen.getByText('Flash (2.5)')).toBeInTheDocument();
      expect(screen.getByText('Pro (2.5)')).toBeInTheDocument();
    });
  });

  it('closes dropdown when clicking outside', async () => {
    render(
      <div>
        <RateLimitDropdown />
        <div data-testid="outside">Outside element</div>
      </div>
    );
    
    // Wait for initial load
    await waitFor(() => {
      expect(mockRateLimitApi.getStatus).toHaveBeenCalled();
    });

    // Open dropdown
    const triggerButton = screen.getByRole('button');
    fireEvent.click(triggerButton);

    // Verify dropdown is open
    await waitFor(() => {
      expect(screen.getByText('Gemini API Limits')).toBeInTheDocument();
    });

    // Click outside
    const outsideElement = screen.getByTestId('outside');
    fireEvent.mouseDown(outsideElement);

    // Dropdown should close
    await waitFor(() => {
      expect(screen.queryByText('Gemini API Limits')).not.toBeInTheDocument();
    });
  });

  it('shows loading state initially', () => {
    // Make API call pending
    mockRateLimitApi.getStatus.mockImplementation(() => new Promise(() => {}));
    
    render(<RateLimitDropdown />);
    
    const triggerButton = screen.getByRole('button');
    fireEvent.click(triggerButton);

    expect(screen.getByText('Loading rate limit status...')).toBeInTheDocument();
  });

  it('shows error state when API fails', async () => {
    mockRateLimitApi.getStatus.mockRejectedValue(new Error('API Error'));
    
    render(<RateLimitDropdown />);
    
    const triggerButton = screen.getByRole('button');
    fireEvent.click(triggerButton);

    await waitFor(() => {
      expect(screen.getByText('Error: API Error')).toBeInTheDocument();
    });
  });

  it('displays correct utilization data', async () => {
    render(<RateLimitDropdown />);
    
    // Wait for initial load
    await waitFor(() => {
      expect(mockRateLimitApi.getStatus).toHaveBeenCalled();
    });

    const triggerButton = screen.getByRole('button');
    fireEvent.click(triggerButton);

    await waitFor(() => {
      // Check for RPM badges
      expect(screen.getByText('2/8 RPM')).toBeInTheDocument();
      expect(screen.getByText('1/4 RPM')).toBeInTheDocument();
    });
  });

  it('auto-closes after timeout', async () => {
    vi.useFakeTimers();
    
    render(<RateLimitDropdown />);
    
    // Wait for initial load
    await waitFor(() => {
      expect(mockRateLimitApi.getStatus).toHaveBeenCalled();
    });

    const triggerButton = screen.getByRole('button');
    fireEvent.click(triggerButton);

    // Verify dropdown is open
    await waitFor(() => {
      expect(screen.getByText('Gemini API Limits')).toBeInTheDocument();
    });

    // Fast-forward time by 10 seconds
    vi.advanceTimersByTime(10000);

    // Dropdown should close
    await waitFor(() => {
      expect(screen.queryByText('Gemini API Limits')).not.toBeInTheDocument();
    });

    vi.useRealTimers();
  });
});