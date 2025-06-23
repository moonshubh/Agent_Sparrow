import { render, screen } from '@testing-library/react'
import { MarkdownMessage } from '../MarkdownMessage'

describe('MarkdownMessage', () => {
  it('renders basic markdown content', () => {
    const content = '**Hello** world!'
    render(<MarkdownMessage content={content} />)
    
    const strongElement = screen.getByText('Hello')
    expect(strongElement.tagName).toBe('STRONG')
    expect(screen.getByText('world!')).toBeInTheDocument()
  })

  it('renders markdown lists', () => {
    const content = `
## Features

- Item 1
- Item 2
- Item 3

1. First item
2. Second item
    `
    render(<MarkdownMessage content={content} />)
    
    // Check for heading
    expect(screen.getByText('Features')).toBeInTheDocument()
    expect(screen.getByText('Features').tagName).toBe('H2')
    
    // Check for list items
    expect(screen.getByText('Item 1')).toBeInTheDocument()
    expect(screen.getByText('First item')).toBeInTheDocument()
  })

  it('renders code blocks', () => {
    const content = '`inline code` and\n\n```\ncode block\n```'
    render(<MarkdownMessage content={content} />)
    
    expect(screen.getByText('inline code')).toBeInTheDocument()
    expect(screen.getByText('code block')).toBeInTheDocument()
  })

  it('trims whitespace from content', () => {
    const content = '  \n\n  **Test**  \n\n  '
    render(<MarkdownMessage content={content} />)
    
    expect(screen.getByText('Test')).toBeInTheDocument()
  })

  it('applies correct CSS classes for prose styling', () => {
    const content = 'Test content'
    const { container } = render(<MarkdownMessage content={content} />)
    
    const proseDiv = container.querySelector('.prose')
    expect(proseDiv).toBeInTheDocument()
    expect(proseDiv).toHaveClass('prose-sm', 'max-w-none', 'dark:prose-invert')
  })
})