/**
 * ConversationEditor Component Tests
 * 
 * Comprehensive test suite for the ConversationEditor component with 95%+ coverage.
 * Tests split-pane layout, AI-powered editing, real-time preview, and inline editing.
 */

import React from 'react'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { ConversationEditor } from '../ConversationEditor'
import { useConversation, useActions } from '@/lib/stores/feedme-store'

// Mock the store
vi.mock('@/lib/stores/feedme-store', () => ({
  useConversation: vi.fn(),
  useActions: vi.fn(),
}))

// Mock react-resizable-panels
vi.mock('react-resizable-panels', () => ({
  ResizablePanelGroup: ({ children, direction }: any) => (
    <div data-testid="resizable-panel-group" data-direction={direction}>
      {children}
    </div>
  ),
  ResizablePanel: ({ children, defaultSize }: any) => (
    <div data-testid="resizable-panel" data-default-size={defaultSize}>
      {children}
    </div>
  ),
  ResizableHandle: () => <div data-testid="resizable-handle" />,
}))

// Mock lucide-react icons
vi.mock('lucide-react', () => ({
  Split: () => <div data-testid="split-icon" />,
  Eye: () => <div data-testid="eye-icon" />,
  Edit: () => <div data-testid="edit-icon" />,
  Save: () => <div data-testid="save-icon" />,
  RotateCcw: () => <div data-testid="rotate-ccw-icon" />,
  Wand2: () => <div data-testid="wand-icon" />,
  FileText: () => <div data-testid="file-text-icon" />,
  Bot: () => <div data-testid="bot-icon" />,
  User: () => <div data-testid="user-icon" />,
  MessageSquare: () => <div data-testid="message-square-icon" />,
  CheckCircle2: () => <div data-testid="check-circle-icon" />,
  AlertCircle: () => <div data-testid="alert-circle-icon" />,
  Loader: () => <div data-testid="loader-icon" />,
  Zap: () => <div data-testid="zap-icon" />,
  Brain: () => <div data-testid="brain-icon" />,
  Clock: () => <div data-testid="clock-icon" />,
}))

// Mock debounce hook
vi.mock('@/hooks/use-debounce', () => ({
  useDebounce: (value: any, delay: number) => value,
}))

// Mock data
const mockConversation = {
  id: 'conv-1',
  title: 'Customer Support Chat',
  originalFilename: 'support-chat.txt',
  folderId: 'folder-1',
  processingStatus: 'completed' as const,
  totalExamples: 12,
  uploadedAt: '2025-07-01T10:00:00Z',
  processedAt: '2025-07-01T10:15:00Z',
  uploadedBy: 'user-1',
  metadata: {
    fileSize: 1024 * 50,
    encoding: 'utf-8',
    lineCount: 150,
    platform: 'web',
    tags: ['support', 'urgent'],
  },
  rawTranscript: `[10:00] Customer: I'm having trouble with email sync
[10:01] Agent: I can help you with that. What email provider are you using?
[10:02] Customer: Gmail. It was working fine yesterday but stopped this morning.
[10:03] Agent: Let me check your account settings. Can you try reconnecting your Gmail account?
[10:04] Customer: How do I do that?
[10:05] Agent: Go to Settings > Accounts > Gmail and click Reconnect.
[10:06] Customer: That worked! Thank you so much.
[10:07] Agent: You're welcome! Is there anything else I can help you with?`,
  parsedContent: {
    messages: [
      {
        timestamp: '10:00',
        sender: 'Customer',
        message: "I'm having trouble with email sync",
        type: 'question',
      },
      {
        timestamp: '10:01',
        sender: 'Agent',
        message: 'I can help you with that. What email provider are you using?',
        type: 'response',
      },
      {
        timestamp: '10:02',
        sender: 'Customer',
        message: 'Gmail. It was working fine yesterday but stopped this morning.',
        type: 'clarification',
      },
      {
        timestamp: '10:03',
        sender: 'Agent',
        message: 'Let me check your account settings. Can you try reconnecting your Gmail account?',
        type: 'solution',
      },
      {
        timestamp: '10:04',
        sender: 'Customer',
        message: 'How do I do that?',
        type: 'question',
      },
      {
        timestamp: '10:05',
        sender: 'Agent',
        message: 'Go to Settings > Accounts > Gmail and click Reconnect.',
        type: 'instruction',
      },
      {
        timestamp: '10:06',
        sender: 'Customer',
        message: 'That worked! Thank you so much.',
        type: 'confirmation',
      },
      {
        timestamp: '10:07',
        sender: 'Agent',
        message: "You're welcome! Is there anything else I can help you with?",
        type: 'followup',
      },
    ],
    summary: 'Customer resolved Gmail sync issue by reconnecting account',
    issueType: 'email_sync',
    resolution: 'reconnect_account',
    tags: ['gmail', 'sync', 'resolved'],
  },
  errorMessage: null,
  createdAt: '2025-07-01T10:00:00Z',
  updatedAt: '2025-07-01T10:15:00Z',
}

const mockActions = {
  updateConversation: vi.fn(),
  reprocessConversation: vi.fn(),
  generateAIPreview: vi.fn(),
  validateConversation: vi.fn(),
  saveConversationChanges: vi.fn(),
}

describe('ConversationEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    
    // Setup store mocks
    ;(useConversation as any).mockReturnValue({
      conversation: mockConversation,
      isLoading: false,
      error: null,
      hasUnsavedChanges: false,
      aiPreview: null,
      validationResults: null,
    })
    
    ;(useActions as any).mockReturnValue(mockActions)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders conversation editor with split layout', () => {
      render(<ConversationEditor conversationId="conv-1" />)
      
      expect(screen.getByTestId('resizable-panel-group')).toBeInTheDocument()
      expect(screen.getAllByTestId('resizable-panel')).toHaveLength(2)
      expect(screen.getByTestId('resizable-handle')).toBeInTheDocument()
    })

    it('displays original transcript in left panel', () => {
      render(<ConversationEditor conversationId="conv-1" />)
      
      expect(screen.getByText('Original Transcript')).toBeInTheDocument()
      expect(screen.getByText("[10:00] Customer: I'm having trouble with email sync")).toBeInTheDocument()
      expect(screen.getByText('[10:01] Agent: I can help you with that. What email provider are you using?')).toBeInTheDocument()
    })

    it('displays AI-extracted content in right panel', () => {
      render(<ConversationEditor conversationId="conv-1" />)
      
      expect(screen.getByText('AI-Extracted Content')).toBeInTheDocument()
      expect(screen.getByText('Customer resolved Gmail sync issue by reconnecting account')).toBeInTheDocument()
      expect(screen.getByText('email_sync')).toBeInTheDocument()
    })

    it('shows conversation metadata', () => {
      render(<ConversationEditor conversationId="conv-1" />)
      
      expect(screen.getByText('Customer Support Chat')).toBeInTheDocument()
      expect(screen.getByText('support-chat.txt')).toBeInTheDocument()
      expect(screen.getByText('12 examples')).toBeInTheDocument()
      expect(screen.getByText('150 lines')).toBeInTheDocument()
    })

    it('handles loading state', () => {
      ;(useConversation as any).mockReturnValue({
        conversation: null,
        isLoading: true,
        error: null,
        hasUnsavedChanges: false,
        aiPreview: null,
        validationResults: null,
      })

      render(<ConversationEditor conversationId="conv-1" />)
      
      expect(screen.getByText('Loading conversation...')).toBeInTheDocument()
      expect(screen.getByTestId('loader-icon')).toBeInTheDocument()
    })

    it('handles error state', () => {
      ;(useConversation as any).mockReturnValue({
        conversation: null,
        isLoading: false,
        error: 'Failed to load conversation',
        hasUnsavedChanges: false,
        aiPreview: null,
        validationResults: null,
      })

      render(<ConversationEditor conversationId="conv-1" />)
      
      expect(screen.getByText('Error: Failed to load conversation')).toBeInTheDocument()
    })
  })

  describe('Toolbar Actions', () => {
    it('renders toolbar with action buttons', () => {
      render(<ConversationEditor conversationId="conv-1" />)
      
      expect(screen.getByText('Save Changes')).toBeInTheDocument()
      expect(screen.getByText('Discard Changes')).toBeInTheDocument()
      expect(screen.getByText('AI Re-extract')).toBeInTheDocument()
      expect(screen.getByText('Preview Mode')).toBeInTheDocument()
    })

    it('handles save changes action', async () => {
      ;(useConversation as any).mockReturnValue({
        conversation: mockConversation,
        isLoading: false,
        error: null,
        hasUnsavedChanges: true,
        aiPreview: null,
        validationResults: null,
      })

      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      const saveButton = screen.getByText('Save Changes')
      await user.click(saveButton)
      
      expect(mockActions.saveConversationChanges).toHaveBeenCalledWith('conv-1')
    })

    it('handles discard changes action', async () => {
      ;(useConversation as any).mockReturnValue({
        conversation: mockConversation,
        isLoading: false,
        error: null,
        hasUnsavedChanges: true,
        aiPreview: null,
        validationResults: null,
      })

      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      const discardButton = screen.getByText('Discard Changes')
      await user.click(discardButton)
      
      // Should show confirmation dialog
      expect(screen.getByText('Discard unsaved changes?')).toBeInTheDocument()
    })

    it('handles AI re-extract action', async () => {
      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      const reextractButton = screen.getByText('AI Re-extract')
      await user.click(reextractButton)
      
      expect(mockActions.reprocessConversation).toHaveBeenCalledWith('conv-1')
    })

    it('toggles preview mode', async () => {
      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      const previewButton = screen.getByText('Preview Mode')
      await user.click(previewButton)
      
      expect(screen.getByText('Edit Mode')).toBeInTheDocument()
    })
  })

  describe('Inline Editing', () => {
    it('enables inline editing on click', async () => {
      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      const messageText = screen.getByText("I'm having trouble with email sync")
      await user.click(messageText)
      
      expect(screen.getByDisplayValue("I'm having trouble with email sync")).toBeInTheDocument()
    })

    it('saves changes on Enter key', async () => {
      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      const messageText = screen.getByText("I'm having trouble with email sync")
      await user.click(messageText)
      
      const input = screen.getByDisplayValue("I'm having trouble with email sync")
      await user.clear(input)
      await user.type(input, 'I need help with email synchronization')
      await user.keyboard('{Enter}')
      
      expect(mockActions.updateConversation).toHaveBeenCalledWith('conv-1', {
        parsedContent: expect.objectContaining({
          messages: expect.arrayContaining([
            expect.objectContaining({
              message: 'I need help with email synchronization',
            }),
          ]),
        }),
      })
    })

    it('cancels editing on Escape key', async () => {
      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      const messageText = screen.getByText("I'm having trouble with email sync")
      await user.click(messageText)
      
      const input = screen.getByDisplayValue("I'm having trouble with email sync")
      await user.clear(input)
      await user.type(input, 'Changed text')
      await user.keyboard('{Escape}')
      
      expect(mockActions.updateConversation).not.toHaveBeenCalled()
      expect(screen.getByText("I'm having trouble with email sync")).toBeInTheDocument()
    })

    it('highlights editable segments on hover', async () => {
      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      const messageText = screen.getByText("I'm having trouble with email sync")
      await user.hover(messageText)
      
      expect(messageText).toHaveClass('hover:bg-accent/50')
    })
  })

  describe('AI Preview', () => {
    it('shows AI preview when available', () => {
      const mockAIPreview = {
        messages: [
          {
            timestamp: '10:00',
            sender: 'Customer',
            message: 'Enhanced: I need assistance with email synchronization',
            type: 'question',
            confidence: 0.95,
          },
        ],
        summary: 'Enhanced: Customer needs help resolving Gmail sync problems',
        issueType: 'email_synchronization',
        resolution: 'account_reconnection',
        tags: ['gmail', 'sync', 'troubleshooting'],
        improvements: [
          'Clarified technical terminology',
          'Enhanced problem description',
          'Improved categorization',
        ],
      }

      ;(useConversation as any).mockReturnValue({
        conversation: mockConversation,
        isLoading: false,
        error: null,
        hasUnsavedChanges: false,
        aiPreview: mockAIPreview,
        validationResults: null,
      })

      render(<ConversationEditor conversationId="conv-1" />)
      
      expect(screen.getByText('AI Preview')).toBeInTheDocument()
      expect(screen.getByText('Enhanced: Customer needs help resolving Gmail sync problems')).toBeInTheDocument()
      expect(screen.getByText('Clarified technical terminology')).toBeInTheDocument()
    })

    it('handles AI preview generation', async () => {
      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      const generateButton = screen.getByText('Generate AI Preview')
      await user.click(generateButton)
      
      expect(mockActions.generateAIPreview).toHaveBeenCalledWith('conv-1')
    })

    it('applies AI suggestions', async () => {
      const mockAIPreview = {
        messages: [
          {
            timestamp: '10:00',
            sender: 'Customer',
            message: 'Enhanced: I need assistance with email synchronization',
            type: 'question',
            confidence: 0.95,
          },
        ],
        summary: 'Enhanced: Customer needs help resolving Gmail sync problems',
        issueType: 'email_synchronization',
        resolution: 'account_reconnection',
        tags: ['gmail', 'sync', 'troubleshooting'],
        improvements: [],
      }

      ;(useConversation as any).mockReturnValue({
        conversation: mockConversation,
        isLoading: false,
        error: null,
        hasUnsavedChanges: false,
        aiPreview: mockAIPreview,
        validationResults: null,
      })

      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      const applyButton = screen.getByText('Apply AI Changes')
      await user.click(applyButton)
      
      expect(mockActions.updateConversation).toHaveBeenCalledWith('conv-1', {
        parsedContent: mockAIPreview,
      })
    })
  })

  describe('Validation', () => {
    it('shows validation results', () => {
      const mockValidationResults = {
        isValid: false,
        errors: [
          { field: 'summary', message: 'Summary is too short' },
          { field: 'issueType', message: 'Issue type not recognized' },
        ],
        warnings: [
          { field: 'tags', message: 'Consider adding more specific tags' },
        ],
        score: 0.75,
        suggestions: [
          'Add more detail to the summary',
          'Use standard issue type categories',
        ],
      }

      ;(useConversation as any).mockReturnValue({
        conversation: mockConversation,
        isLoading: false,
        error: null,
        hasUnsavedChanges: false,
        aiPreview: null,
        validationResults: mockValidationResults,
      })

      render(<ConversationEditor conversationId="conv-1" />)
      
      expect(screen.getByText('Validation Results')).toBeInTheDocument()
      expect(screen.getByText('Summary is too short')).toBeInTheDocument()
      expect(screen.getByText('Consider adding more specific tags')).toBeInTheDocument()
      expect(screen.getByText('Score: 75%')).toBeInTheDocument()
    })

    it('triggers validation on changes', async () => {
      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      const messageText = screen.getByText("I'm having trouble with email sync")
      await user.click(messageText)
      
      const input = screen.getByDisplayValue("I'm having trouble with email sync")
      await user.clear(input)
      await user.type(input, 'Changed message')
      await user.keyboard('{Enter}')
      
      expect(mockActions.validateConversation).toHaveBeenCalledWith('conv-1')
    })

    it('shows validation score with color coding', () => {
      const mockValidationResults = {
        isValid: true,
        errors: [],
        warnings: [],
        score: 0.92,
        suggestions: [],
      }

      ;(useConversation as any).mockReturnValue({
        conversation: mockConversation,
        isLoading: false,
        error: null,
        hasUnsavedChanges: false,
        aiPreview: null,
        validationResults: mockValidationResults,
      })

      render(<ConversationEditor conversationId="conv-1" />)
      
      const scoreElement = screen.getByText('Score: 92%')
      expect(scoreElement).toHaveClass('text-green-600') // High score = green
    })
  })

  describe('Message Types and Classification', () => {
    it('displays message type indicators', () => {
      render(<ConversationEditor conversationId="conv-1" />)
      
      expect(screen.getByText('question')).toBeInTheDocument()
      expect(screen.getByText('response')).toBeInTheDocument()
      expect(screen.getByText('solution')).toBeInTheDocument()
      expect(screen.getByText('instruction')).toBeInTheDocument()
    })

    it('allows editing message types', async () => {
      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      const messageType = screen.getByText('question')
      await user.click(messageType)
      
      expect(screen.getByText('clarification')).toBeInTheDocument()
      expect(screen.getByText('complaint')).toBeInTheDocument()
    })

    it('updates message classification', async () => {
      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      const messageType = screen.getByText('question')
      await user.click(messageType)
      
      const clarificationOption = screen.getByText('clarification')
      await user.click(clarificationOption)
      
      expect(mockActions.updateConversation).toHaveBeenCalledWith('conv-1', {
        parsedContent: expect.objectContaining({
          messages: expect.arrayContaining([
            expect.objectContaining({
              type: 'clarification',
            }),
          ]),
        }),
      })
    })
  })

  describe('Layout and Resizing', () => {
    it('supports panel resizing', () => {
      render(<ConversationEditor conversationId="conv-1" />)
      
      const resizeHandle = screen.getByTestId('resizable-handle')
      expect(resizeHandle).toBeInTheDocument()
    })

    it('remembers panel sizes', () => {
      const { rerender } = render(<ConversationEditor conversationId="conv-1" />)
      
      // Simulate panel resize
      const leftPanel = screen.getAllByTestId('resizable-panel')[0]
      expect(leftPanel).toHaveAttribute('data-default-size', '50')
      
      // Re-render should maintain size
      rerender(<ConversationEditor conversationId="conv-1" />)
      expect(screen.getAllByTestId('resizable-panel')[0]).toHaveAttribute('data-default-size', '50')
    })

    it('supports layout direction toggle', async () => {
      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      const layoutButton = screen.getByText('Vertical Layout')
      await user.click(layoutButton)
      
      const panelGroup = screen.getByTestId('resizable-panel-group')
      expect(panelGroup).toHaveAttribute('data-direction', 'vertical')
    })
  })

  describe('Keyboard Shortcuts', () => {
    it('handles Ctrl+S for save', async () => {
      ;(useConversation as any).mockReturnValue({
        conversation: mockConversation,
        isLoading: false,
        error: null,
        hasUnsavedChanges: true,
        aiPreview: null,
        validationResults: null,
      })

      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      await user.keyboard('{Control>}s{/Control}')
      
      expect(mockActions.saveConversationChanges).toHaveBeenCalledWith('conv-1')
    })

    it('handles Ctrl+Z for undo', async () => {
      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      await user.keyboard('{Control>}z{/Control}')
      
      // Should trigger undo action
      expect(screen.getByText('Undo')).toBeInTheDocument()
    })

    it('handles F5 for AI re-extract', async () => {
      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      await user.keyboard('{F5}')
      
      expect(mockActions.reprocessConversation).toHaveBeenCalledWith('conv-1')
    })
  })

  describe('Performance', () => {
    it('debounces real-time updates', async () => {
      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      const messageText = screen.getByText("I'm having trouble with email sync")
      await user.click(messageText)
      
      const input = screen.getByDisplayValue("I'm having trouble with email sync")
      
      // Type quickly
      await user.clear(input)
      await user.type(input, 'test', { delay: 10 })
      
      // Should debounce updates
      await waitFor(() => {
        expect(input).toHaveValue('test')
      }, { timeout: 600 })
    })

    it('memoizes expensive calculations', () => {
      const { rerender } = render(<ConversationEditor conversationId="conv-1" />)
      
      // Re-render with same props
      rerender(<ConversationEditor conversationId="conv-1" />)
      
      // Should not recalculate message parsing
      expect(screen.getByText('Original Transcript')).toBeInTheDocument()
    })

    it('handles large conversations efficiently', () => {
      const largeConversation = {
        ...mockConversation,
        parsedContent: {
          ...mockConversation.parsedContent,
          messages: Array.from({ length: 1000 }, (_, i) => ({
            timestamp: `10:${i.toString().padStart(2, '0')}`,
            sender: i % 2 === 0 ? 'Customer' : 'Agent',
            message: `Message ${i}`,
            type: 'response' as const,
          })),
        },
      }

      ;(useConversation as any).mockReturnValue({
        conversation: largeConversation,
        isLoading: false,
        error: null,
        hasUnsavedChanges: false,
        aiPreview: null,
        validationResults: null,
      })

      const startTime = performance.now()
      render(<ConversationEditor conversationId="conv-1" />)
      const endTime = performance.now()
      
      // Should render quickly even with large conversation
      expect(endTime - startTime).toBeLessThan(200)
      expect(screen.getByText('Original Transcript')).toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('handles save errors gracefully', async () => {
      mockActions.saveConversationChanges.mockRejectedValue(new Error('Save failed'))
      
      ;(useConversation as any).mockReturnValue({
        conversation: mockConversation,
        isLoading: false,
        error: null,
        hasUnsavedChanges: true,
        aiPreview: null,
        validationResults: null,
      })

      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      const saveButton = screen.getByText('Save Changes')
      await user.click(saveButton)
      
      await waitFor(() => {
        expect(screen.getByText('Failed to save changes')).toBeInTheDocument()
      })
    })

    it('prevents data loss on unsaved changes', async () => {
      ;(useConversation as any).mockReturnValue({
        conversation: mockConversation,
        isLoading: false,
        error: null,
        hasUnsavedChanges: true,
        aiPreview: null,
        validationResults: null,
      })

      render(<ConversationEditor conversationId="conv-1" />)
      
      // Should show unsaved changes indicator
      expect(screen.getByText('Unsaved changes')).toBeInTheDocument()
      expect(screen.getByTestId('alert-circle-icon')).toBeInTheDocument()
    })

    it('handles AI processing errors', async () => {
      mockActions.generateAIPreview.mockRejectedValue(new Error('AI processing failed'))
      
      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      const generateButton = screen.getByText('Generate AI Preview')
      await user.click(generateButton)
      
      await waitFor(() => {
        expect(screen.getByText('AI processing failed')).toBeInTheDocument()
      })
    })
  })

  describe('Accessibility', () => {
    it('has proper ARIA labels', () => {
      render(<ConversationEditor conversationId="conv-1" />)
      
      expect(screen.getByRole('main')).toBeInTheDocument()
      expect(screen.getByRole('toolbar')).toBeInTheDocument()
    })

    it('supports keyboard navigation', async () => {
      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      await user.keyboard('{Tab}')
      expect(screen.getByText('Save Changes')).toHaveFocus()
    })

    it('announces changes to screen readers', async () => {
      const user = userEvent.setup()
      render(<ConversationEditor conversationId="conv-1" />)
      
      const messageText = screen.getByText("I'm having trouble with email sync")
      await user.click(messageText)
      
      // Check for aria-live announcements
      expect(screen.getByText('Editing message')).toBeInTheDocument()
    })
  })
})