import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ExecutiveSummaryRenderer } from '../ExecutiveSummaryRenderer'

describe('ExecutiveSummaryRenderer', () => {
  it('renders markdown content correctly', () => {
    const content = `
# Main Summary

This is a test summary with **bold text** and *italic text*.

## Key Findings
- Finding 1
- Finding 2

### Details
Here are some details.
    `

    render(<ExecutiveSummaryRenderer content={content} />)
    
    expect(screen.getByText('Executive Summary')).toBeInTheDocument() // Header title
    expect(screen.getByText('Main Summary')).toBeInTheDocument() // Markdown content
    expect(screen.getByText('Key Findings')).toBeInTheDocument()
    expect(screen.getByText('Finding 1')).toBeInTheDocument()
  })

  it('filters out implementation timeline sections', () => {
    const content = `
# Main Summary

This is the main content.

## Implementation Timeline
This section should be removed.

### Step 1
This should also be removed.

## Other Section
This should remain.
    `

    render(<ExecutiveSummaryRenderer content={content} />)
    
    expect(screen.getByText('Main Summary')).toBeInTheDocument()
    expect(screen.getByText('Other Section')).toBeInTheDocument()
    expect(screen.queryByText('Implementation Timeline')).not.toBeInTheDocument()
    expect(screen.queryByText('This section should be removed.')).not.toBeInTheDocument()
    expect(screen.queryByText('Step 1')).not.toBeInTheDocument()
  })

  it('handles case-insensitive implementation timeline filtering', () => {
    const content = `
# Summary

Main content here.

## implementation timeline
This should be filtered.

## IMPLEMENTATION TIMELINE  
This should also be filtered.

## Next Steps
This should remain.
    `

    render(<ExecutiveSummaryRenderer content={content} />)
    
    expect(screen.getByText('Summary')).toBeInTheDocument()
    expect(screen.getByText('Next Steps')).toBeInTheDocument()
    expect(screen.queryByText('implementation timeline')).not.toBeInTheDocument()
    expect(screen.queryByText('IMPLEMENTATION TIMELINE')).not.toBeInTheDocument()
  })

  it('returns null for empty content', () => {
    const { container } = render(<ExecutiveSummaryRenderer content="" />)
    expect(container.firstChild).toBeNull()
  })

  it('handles whitespace-only content', () => {
    const { container } = render(<ExecutiveSummaryRenderer content="   \n\t   " />)
    // Since ReactMarkdown may still render a paragraph with whitespace,
    // we just check that the component renders and contains the header
    expect(screen.getByText('Executive Summary')).toBeInTheDocument()
    
    // Check that no other meaningful content is rendered
    const contentDiv = container.querySelector('.prose')
    const proseText = contentDiv?.textContent?.trim()
    expect(proseText?.length || 0).toBeLessThan(10) // Should be minimal whitespace only
  })

  it('preserves other markdown formatting', () => {
    const content = `
# Main Title

Here is a paragraph with \`inline code\` and **bold text**.

\`\`\`javascript
const test = "code block";
\`\`\`

> This is a blockquote

| Column 1 | Column 2 |
|----------|----------|
| Cell 1   | Cell 2   |
    `

    render(<ExecutiveSummaryRenderer content={content} />)
    
    expect(screen.getByText('Main Title')).toBeInTheDocument()
    expect(screen.getByText('inline code')).toBeInTheDocument()
    expect(screen.getByText('bold text')).toBeInTheDocument()
  })

  it('applies exec-summary class for accent color styling', () => {
    const content = `
## Executive Summary
This is a test with **bold text**.
    `

    const { container } = render(<ExecutiveSummaryRenderer content={content} />)
    
    const proseDiv = container.querySelector('.prose')
    expect(proseDiv).toHaveClass('exec-summary')
  })

  it('injects emojis for recognized h2 section headings', () => {
    const content = `
# Main Title

## Executive Summary
This is the executive summary section.

## Key Issues Identified
These are the issues found.

## Recommended Solutions
These are the recommended fixes.

## Other Section
This should not get an emoji.
    `

    render(<ExecutiveSummaryRenderer content={content} />)
    
    // Check that emojis are present in the rendered content
    expect(screen.getByText(/📝.*Executive Summary/)).toBeInTheDocument()
    expect(screen.getByText(/🚩.*Key Issues Identified/)).toBeInTheDocument()
    expect(screen.getByText(/💡.*Recommended Solutions/)).toBeInTheDocument()
    
    // Check that non-matching sections don't get emojis
    const otherSection = screen.getByText('Other Section')
    expect(otherSection.textContent).not.toMatch(/^[📝🚩💡]/)
  })

  it('filters out priority implementation order sections', () => {
    const content = `
# Summary

Main content here.

## Priority Implementation Order
This should be filtered out.

### Priority Step 1
This should also be filtered.

## Solutions
This should remain.
    `

    render(<ExecutiveSummaryRenderer content={content} />)
    
    expect(screen.getByText('Summary')).toBeInTheDocument()
    expect(screen.getByText(/💡.*Solutions/)).toBeInTheDocument()
    expect(screen.queryByText('Priority Implementation Order')).not.toBeInTheDocument()
    expect(screen.queryByText('Priority Step 1')).not.toBeInTheDocument()
  })

  it('handles case-insensitive emoji pattern matching', () => {
    const content = `
## EXECUTIVE SUMMARY
Capital letters test.

## issues found
Lowercase test.

## Recommended SOLUTIONS
Mixed case test.
    `

    render(<ExecutiveSummaryRenderer content={content} />)
    
    expect(screen.getByText(/📝.*EXECUTIVE SUMMARY/)).toBeInTheDocument()
    expect(screen.getByText(/🚩.*issues found/)).toBeInTheDocument()
    expect(screen.getByText(/💡.*Recommended SOLUTIONS/)).toBeInTheDocument()
  })
})