/**
 * @vitest-environment jsdom
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ActionBar } from '../ActionBar'

describe('ActionBar', () => {
  const defaultProps = {
    activeTab: 'system',
    onTabChange: vi.fn(),
    issueCount: 5,
    hasInsights: true,
    onSystemOverviewClick: vi.fn()
  }

  it('renders all four tabs', () => {
    render(<ActionBar {...defaultProps} />)
    
    expect(screen.getByText('System Overview')).toBeInTheDocument()
    expect(screen.getByText('Issues')).toBeInTheDocument()
    expect(screen.getByText('Insights')).toBeInTheDocument()
    expect(screen.getByText('Actions')).toBeInTheDocument()
  })

  it('shows issue count when issueCount > 0', () => {
    render(<ActionBar {...defaultProps} issueCount={3} />)
    
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('disables insights tab when hasInsights is false', () => {
    render(<ActionBar {...defaultProps} hasInsights={false} />)
    
    const insightsTab = screen.getByRole('tab', { name: /insights/i })
    expect(insightsTab).toBeDisabled()
  })

  it('marks active tab as selected', () => {
    render(<ActionBar {...defaultProps} activeTab="issues" />)
    
    const issuesTab = screen.getByRole('tab', { name: /issues/i })
    expect(issuesTab).toHaveAttribute('aria-selected', 'true')
  })

  it('calls onTabChange when non-system tab is clicked', () => {
    const onTabChange = vi.fn()
    render(<ActionBar {...defaultProps} onTabChange={onTabChange} />)
    
    fireEvent.click(screen.getByRole('tab', { name: /issues/i }))
    expect(onTabChange).toHaveBeenCalledWith('issues')
  })

  it('calls onSystemOverviewClick when system tab is clicked', () => {
    const onSystemOverviewClick = vi.fn()
    render(<ActionBar {...defaultProps} onSystemOverviewClick={onSystemOverviewClick} />)
    
    fireEvent.click(screen.getByRole('tab', { name: /system overview/i }))
    expect(onSystemOverviewClick).toHaveBeenCalled()
  })
})