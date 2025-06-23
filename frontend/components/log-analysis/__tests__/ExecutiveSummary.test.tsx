import { render, screen } from '@testing-library/react'
import { ExecutiveSummary } from '../ExecutiveSummary'

describe('ExecutiveSummary', () => {
  it('renders executive summary when content is provided', () => {
    const mockContent = `
# Analysis Report

This is a test executive summary with **bold text** and a table:

| Account | Status | Issues |
|---------|--------|--------|
| test@example.com | Active | 2 |
| user@test.com | Degraded | 5 |

## Key Findings

- Critical authentication issues detected
- Database optimization required
    `

    render(<ExecutiveSummary content={mockContent} />)
    
    // Check that the section with ID exists (for Cypress testing)
    expect(screen.getByTestId('executive-summary')).toBeInTheDocument()
    
    // Check that the header is present
    expect(screen.getByText('Executive Summary')).toBeInTheDocument()
    
    // Check that markdown content is rendered
    expect(screen.getByText('Key Findings')).toBeInTheDocument()
    expect(screen.getByText('Critical authentication issues detected')).toBeInTheDocument()
    
    // Check that table is rendered
    expect(screen.getByText('test@example.com')).toBeInTheDocument()
    expect(screen.getByText('Active')).toBeInTheDocument()
  })

  it('does not render when content is empty', () => {
    const { container } = render(<ExecutiveSummary content="" />)
    expect(container.firstChild).toBeNull()
  })

  it('does not render when content is whitespace only', () => {
    const whitespaceContent = "   \n\t  "
    const { container } = render(<ExecutiveSummary content={whitespaceContent} />)
    expect(container.firstChild).toBeNull()
  })
})