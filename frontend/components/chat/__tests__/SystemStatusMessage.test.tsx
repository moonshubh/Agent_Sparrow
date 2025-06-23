import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import SystemStatusMessage from '../SystemStatusMessage'

describe('SystemStatusMessage', () => {
  const mockStartTime = new Date('2025-06-23T10:46:00.000Z')

  it('renders analyzing phase with file information', () => {
    render(
      <SystemStatusMessage
        phase="analyzing"
        filesize="98 KB"
        lines={896}
        startedAt={mockStartTime}
      />
    )

    expect(screen.getByText(/🔍 Analyzing "Log\.log"/)).toBeInTheDocument()
    expect(screen.getByText(/98 KB · 896 lines/)).toBeInTheDocument()
  })

  it('renders processing phase', () => {
    render(
      <SystemStatusMessage
        phase="processing"
        filesize="256 KB"
        lines={1200}
        startedAt={mockStartTime}
      />
    )

    expect(screen.getByText(/🔍 Processing "Log\.log"/)).toBeInTheDocument()
    expect(screen.getByText(/256 KB · 1,200 lines/)).toBeInTheDocument()
  })

  it('handles missing file information gracefully', () => {
    render(
      <SystemStatusMessage
        phase="analyzing"
        startedAt={mockStartTime}
      />
    )

    expect(screen.getByText(/🔍 Analyzing "Log\.log"/)).toBeInTheDocument()
    // When no filesize is provided, the component should not render file size/lines info
    expect(screen.queryByText(/KB/)).not.toBeInTheDocument()
    expect(screen.queryByText(/lines/)).not.toBeInTheDocument()
  })

  it('extracts filename from complex filesize string', () => {
    render(
      <SystemStatusMessage
        phase="analyzing"
        filesize='"complex-filename.log" (123.5 KB)'
        lines={500}
        startedAt={mockStartTime}
      />
    )

    expect(screen.getByText(/🔍 Analyzing "complex-filename\.log"/)).toBeInTheDocument()
    expect(screen.getByText(/123\.5 KB · 500 lines/)).toBeInTheDocument()
  })

  it('displays loading animation elements', () => {
    const { container } = render(
      <SystemStatusMessage
        phase="analyzing"
        startedAt={mockStartTime}
      />
    )

    // Check for Skeleton component (loading animation)
    const skeleton = container.querySelector('[class*="bg-primary"]')
    expect(skeleton).toBeInTheDocument()
    
    // Check for animated FileSearch icon with animate-pulse
    const icon = container.querySelector('.animate-pulse')
    expect(icon).toBeInTheDocument()
  })

  it('displays time with clock icon', () => {
    const { container } = render(
      <SystemStatusMessage
        phase="analyzing"
        startedAt={mockStartTime}
      />
    )

    // Look for clock icon
    const clockIcon = container.querySelector('svg.lucide-clock')
    expect(clockIcon).toBeInTheDocument()
    
    // Time should be displayed (format varies by locale)
    expect(container.textContent).toMatch(/\d{1,2}:\d{2}/)
  })
})