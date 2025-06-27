/**
 * @vitest-environment jsdom
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CompletenessBadge } from '../CompletenessBadge'

describe('CompletenessBadge', () => {
  it('renders with numeric percentage value', () => {
    render(<CompletenessBadge value={75} />)
    
    expect(screen.getByText('Completeness')).toBeInTheDocument()
    expect(screen.getByText('75%')).toBeInTheDocument()
  })

  it('renders with string percentage value', () => {
    render(<CompletenessBadge value="50%" />)
    
    expect(screen.getByText('Completeness')).toBeInTheDocument()
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('handles decimal values (0-1 range)', () => {
    render(<CompletenessBadge value={0.8} />)
    
    expect(screen.getByText('Completeness')).toBeInTheDocument()
    expect(screen.getByText('80%')).toBeInTheDocument()
  })

  it('clamps values to 0-100 range', () => {
    render(<CompletenessBadge value={150} />)
    expect(screen.getByText('100%')).toBeInTheDocument()

    render(<CompletenessBadge value={-10} />)
    expect(screen.getByText('0%')).toBeInTheDocument()
  })

  it('handles invalid values gracefully', () => {
    render(<CompletenessBadge value="invalid" />)
    expect(screen.getByText('0%')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(<CompletenessBadge value={50} className="custom-class" />)
    expect(container.firstChild).toHaveClass('custom-class')
  })
})