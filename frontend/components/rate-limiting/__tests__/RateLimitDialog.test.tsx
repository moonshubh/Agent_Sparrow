import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { RateLimitDialog } from '../RateLimitDialog';

// Mock the API utilities
vi.mock('@/lib/api/rateLimitApi', () => ({
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
    // Mock to return a fixed time for testing
    return 300; // 5 minutes
  }),
}));

const mockMetadata = {
  rpm_used: 8,
  rpm_limit: 8,
  rpm_remaining: 0,
  rpd_used: 150,
  rpd_limit: 200,
  rpd_remaining: 50,
  reset_time_rpm: '2025-07-01T12:05:00Z',
  reset_time_rpd: '2025-07-02T00:00:00Z',
  model: 'gemini-2.5-flash',
  safety_margin: 0.2,
};

describe('RateLimitDialog', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    blockedModel: 'gemini-2.5-flash' as const,
    blockedBy: 'rpm' as const,
    metadata: mockMetadata,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders dialog when open', () => {
    render(<RateLimitDialog {...defaultProps} />);
    
    expect(screen.getByText('Rate Limit Reached')).toBeInTheDocument();
    expect(screen.getByText('You\'ve reached the rate limit for Gemini Flash model')).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    render(<RateLimitDialog {...defaultProps} isOpen={false} />);
    
    expect(screen.queryByText('Rate Limit Reached')).not.toBeInTheDocument();
  });

  it('displays correct model information for Flash', () => {
    render(<RateLimitDialog {...defaultProps} />);
    
    expect(screen.getByText('Gemini Flash')).toBeInTheDocument();
    expect(screen.getByText('RPM Limit')).toBeInTheDocument();
  });

  it('displays correct model information for Pro', () => {
    render(
      <RateLimitDialog 
        {...defaultProps} 
        blockedModel="gemini-2.5-pro"
        metadata={{
          ...mockMetadata,
          model: 'gemini-2.5-pro',
          rpm_limit: 4,
        }}
      />
    );
    
    expect(screen.getByText('Gemini Pro')).toBeInTheDocument();
  });

  it('shows RPM limit information when blocked by RPM', () => {
    render(<RateLimitDialog {...defaultProps} blockedBy="rpm" />);
    
    expect(screen.getByText('Requests per minute')).toBeInTheDocument();
    expect(screen.getByText('8/8')).toBeInTheDocument();
  });

  it('shows RPD limit information when blocked by RPD', () => {
    render(<RateLimitDialog {...defaultProps} blockedBy="rpd" />);
    
    expect(screen.getByText('Requests per day')).toBeInTheDocument();
    expect(screen.getByText('150/200')).toBeInTheDocument();
  });

  it('displays progress bar with correct utilization', () => {
    render(<RateLimitDialog {...defaultProps} />);
    
    const progressBar = screen.getByRole('progressbar');
    expect(progressBar).toBeInTheDocument();
    expect(screen.getByText('100% of free tier limit used')).toBeInTheDocument();
  });

  it('shows reset timer', () => {
    render(<RateLimitDialog {...defaultProps} />);
    
    expect(screen.getByText('Limit resets in')).toBeInTheDocument();
    expect(screen.getByText('5m 0s')).toBeInTheDocument();
  });

  it('updates timer countdown', async () => {
    render(<RateLimitDialog {...defaultProps} />);
    
    expect(screen.getByText('5m 0s')).toBeInTheDocument();
    
    // Advance time by 1 second
    vi.advanceTimersByTime(1000);
    
    await waitFor(() => {
      expect(screen.getByText('4m 59s')).toBeInTheDocument();
    });
  });

  it('auto-closes when timer reaches zero', async () => {
    const onClose = vi.fn();
    render(<RateLimitDialog {...defaultProps} onClose={onClose} />);
    
    // Advance time past the reset time
    vi.advanceTimersByTime(301000); // 5 minutes + 1 second
    
    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('calls onClose when close button is clicked', () => {
    const onClose = vi.fn();
    render(<RateLimitDialog {...defaultProps} onClose={onClose} />);
    
    const closeButton = screen.getByText('Close');
    fireEvent.click(closeButton);
    
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('shows retry button when time has elapsed and onRetry is provided', () => {
    const onRetry = vi.fn();
    
    // Mock getTimeToReset to return 0 (time elapsed)
    const { getTimeToReset } = require('@/lib/api/rateLimitApi');
    getTimeToReset.mockReturnValue(0);
    
    render(<RateLimitDialog {...defaultProps} onRetry={onRetry} />);
    
    expect(screen.getByText('Try Again')).toBeInTheDocument();
  });

  it('calls onRetry when retry button is clicked', () => {
    const onRetry = vi.fn();
    
    // Mock getTimeToReset to return 0
    const { getTimeToReset } = require('@/lib/api/rateLimitApi');
    getTimeToReset.mockReturnValue(0);
    
    render(<RateLimitDialog {...defaultProps} onRetry={onRetry} />);
    
    const retryButton = screen.getByText('Try Again');
    fireEvent.click(retryButton);
    
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('shows cancel button when onCancel is provided', () => {
    const onCancel = vi.fn();
    render(<RateLimitDialog {...defaultProps} onCancel={onCancel} />);
    
    expect(screen.getByText('Cancel Request')).toBeInTheDocument();
  });

  it('calls onCancel when cancel button is clicked', () => {
    const onCancel = vi.fn();
    render(<RateLimitDialog {...defaultProps} onCancel={onCancel} />);
    
    const cancelButton = screen.getByText('Cancel Request');
    fireEvent.click(cancelButton);
    
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('displays safety margin information', () => {
    render(<RateLimitDialog {...defaultProps} />);
    
    expect(screen.getByText(/Safety margin:/)).toBeInTheDocument();
    expect(screen.getByText(/20%/)).toBeInTheDocument();
  });

  it('explains what happened and next steps', () => {
    render(<RateLimitDialog {...defaultProps} />);
    
    expect(screen.getByText(/What happened\?/)).toBeInTheDocument();
    expect(screen.getByText(/What's next\?/)).toBeInTheDocument();
  });

  it('shows custom retry after time if provided', () => {
    render(<RateLimitDialog {...defaultProps} retryAfter={180} />);
    
    expect(screen.getByText('3m 0s')).toBeInTheDocument();
  });

  it('handles keyboard interactions for accessibility', () => {
    const onClose = vi.fn();
    render(<RateLimitDialog {...defaultProps} onClose={onClose} />);
    
    // Dialog should be accessible via keyboard
    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();
    
    // Should be able to focus on interactive elements
    const closeButton = screen.getByText('Close');
    expect(closeButton).toBeInTheDocument();
  });

  it('displays different limit types correctly', () => {
    const { rerender } = render(<RateLimitDialog {...defaultProps} blockedBy="rpm" />);
    expect(screen.getByText('per minute')).toBeInTheDocument();
    
    rerender(<RateLimitDialog {...defaultProps} blockedBy="rpd" />);
    expect(screen.getByText('per day')).toBeInTheDocument();
  });

  it('handles edge case when reset time is in the past', () => {
    // Mock getTimeToReset to return negative value
    const { getTimeToReset } = require('@/lib/api/rateLimitApi');
    getTimeToReset.mockReturnValue(-10);
    
    render(<RateLimitDialog {...defaultProps} />);
    
    expect(screen.getByText('Now')).toBeInTheDocument();
  });
});