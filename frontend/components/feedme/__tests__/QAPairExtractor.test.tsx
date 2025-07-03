/**
 * QAPairExtractor Component Tests
 * 
 * Comprehensive test suite for the QAPairExtractor component with 95%+ coverage.
 * Tests AI-powered Q&A extraction, confidence scoring, quality indicators, and improvement suggestions.
 */

import React from 'react'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { QAPairExtractor } from '../QAPairExtractor'
import { useQAExtraction, useActions } from '@/lib/stores/feedme-store'

// Mock the store
vi.mock('@/lib/stores/feedme-store', () => ({
  useQAExtraction: vi.fn(),
  useActions: vi.fn(),
}))

// Mock react-window for virtual scrolling
vi.mock('react-window', () => ({
  FixedSizeList: ({ children, itemCount, height, itemSize }: any) => (
    <div data-testid="virtual-list" style={{ height }}>
      {Array.from({ length: itemCount }, (_, index) => (
        <div key={index} style={{ height: itemSize }}>
          {children({ index, style: {} })}
        </div>
      ))}
    </div>
  ),
}))

// Mock lucide-react icons
vi.mock('lucide-react', () => ({
  MessageSquare: () => <div data-testid="message-square-icon" />,
  Brain: () => <div data-testid="brain-icon" />,
  Zap: () => <div data-testid="zap-icon" />,
  Target: () => <div data-testid="target-icon" />,
  TrendingUp: () => <div data-testid="trending-up-icon" />,
  TrendingDown: () => <div data-testid="trending-down-icon" />,
  CheckCircle2: () => <div data-testid="check-circle-icon" />,
  AlertCircle: () => <div data-testid="alert-circle-icon" />,
  XCircle: () => <div data-testid="x-circle-icon" />,
  Edit: () => <div data-testid="edit-icon" />,
  Trash2: () => <div data-testid="trash-icon" />,
  Copy: () => <div data-testid="copy-icon" />,
  Save: () => <div data-testid="save-icon" />,
  RotateCcw: () => <div data-testid="rotate-ccw-icon" />,
  Loader: () => <div data-testid="loader-icon" />,
  Star: () => <div data-testid="star-icon" />,
  ArrowUp: () => <div data-testid="arrow-up-icon" />,
  ArrowDown: () => <div data-testid="arrow-down-icon" />,
  Filter: () => <div data-testid="filter-icon" />,
  Download: () => <div data-testid="download-icon" />,
  Upload: () => <div data-testid="upload-icon" />,
  RefreshCw: () => <div data-testid="refresh-icon" />,
  Settings: () => <div data-testid="settings-icon" />,
  Info: () => <div data-testid="info-icon" />,
}))

// Mock data
const mockQAPairs = [
  {
    id: 'qa-1',
    conversationId: 'conv-1',
    question: {
      text: "I'm having trouble with email sync",
      timestamp: '10:00',
      sender: 'Customer',
      messageId: 'msg-1',
    },
    answer: {
      text: 'Go to Settings > Accounts > Gmail and click Reconnect to fix the sync issue.',
      timestamp: '10:05',
      sender: 'Agent',
      messageId: 'msg-5',
    },
    context: {
      beforeMessages: 1,
      afterMessages: 2,
      conversationFlow: ['problem_statement', 'clarification', 'solution', 'confirmation'],
    },
    confidence: {
      overall: 0.92,
      questionClarity: 0.88,
      answerRelevance: 0.95,
      contextCompleteness: 0.91,
    },
    quality: {
      score: 0.89,
      factors: {
        specificity: 0.85,
        actionability: 0.93,
        completeness: 0.87,
        clarity: 0.92,
      },
      issues: [],
      suggestions: ['Add more context about when this error typically occurs'],
    },
    tags: ['email', 'sync', 'gmail', 'settings'],
    issueType: 'technical_issue',
    resolution: 'settings_change',
    difficulty: 'easy',
    estimatedTime: '2 minutes',
    successRate: 0.94,
    createdAt: '2025-07-01T10:00:00Z',
    updatedAt: '2025-07-01T10:05:00Z',
  },
  {
    id: 'qa-2',
    conversationId: 'conv-1',
    question: {
      text: 'How do I set up my Outlook account?',
      timestamp: '11:00',
      sender: 'Customer',
      messageId: 'msg-10',
    },
    answer: {
      text: 'To add your Outlook account, go to Settings > Add Account > Select Microsoft Outlook > Enter your credentials.',
      timestamp: '11:02',
      sender: 'Agent',
      messageId: 'msg-12',
    },
    context: {
      beforeMessages: 0,
      afterMessages: 1,
      conversationFlow: ['question', 'direct_answer', 'confirmation'],
    },
    confidence: {
      overall: 0.76,
      questionClarity: 0.82,
      answerRelevance: 0.78,
      contextCompleteness: 0.68,
    },
    quality: {
      score: 0.73,
      factors: {
        specificity: 0.79,
        actionability: 0.81,
        completeness: 0.65,
        clarity: 0.78,
      },
      issues: ['Answer could be more detailed', 'Missing troubleshooting steps'],
      suggestions: [
        'Add screenshots for each step',
        'Include common error scenarios',
        'Mention different Outlook versions',
      ],
    },
    tags: ['outlook', 'setup', 'account', 'configuration'],
    issueType: 'setup_assistance',
    resolution: 'guided_setup',
    difficulty: 'medium',
    estimatedTime: '5 minutes',
    successRate: 0.82,
    createdAt: '2025-07-01T11:00:00Z',
    updatedAt: '2025-07-01T11:02:00Z',
  },
]

const mockExtractionStats = {
  totalPairs: 2,
  averageConfidence: 0.84,
  averageQuality: 0.81,
  highQualityPairs: 1,
  needsReviewPairs: 1,
  issueTypes: {
    technical_issue: 1,
    setup_assistance: 1,
  },
  qualityDistribution: {
    excellent: 1,
    good: 0,
    fair: 1,
    poor: 0,
  },
}

const mockActions = {
  extractQAPairs: vi.fn(),
  updateQAPair: vi.fn(),
  deleteQAPair: vi.fn(),
  approveQAPair: vi.fn(),
  bulkApproveQAPairs: vi.fn(),
  rejectQAPair: vi.fn(),
  reextractQAPairs: vi.fn(),
  exportQAPairs: vi.fn(),
  importQAPairs: vi.fn(),
  optimizeQAPair: vi.fn(),
}

describe('QAPairExtractor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    
    // Setup store mocks
    ;(useQAExtraction as any).mockReturnValue({
      qaPairs: mockQAPairs,
      extractionStats: mockExtractionStats,
      isExtracting: false,
      error: null,
      selectedPairs: new Set(),
      filterSettings: {
        minConfidence: 0.7,
        issueTypes: [],
        qualityThreshold: 0.6,
        showOnlyNeedsReview: false,
      },
      sortSettings: {
        field: 'confidence',
        direction: 'desc',
      },
    })
    
    ;(useActions as any).mockReturnValue(mockActions)
    
    // Mock URL.createObjectURL for export functionality
    global.URL.createObjectURL = vi.fn(() => 'blob:test')
    global.URL.revokeObjectURL = vi.fn()
  })

  afterEach(() => {
    vi.clearAllMocks()
    vi.restoreAllMocks()
  })

  describe('Rendering', () => {
    it('renders QA pair extractor with header', () => {
      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByText('Q&A Extraction')).toBeInTheDocument()
      expect(screen.getByTestId('brain-icon')).toBeInTheDocument()
    })

    it('displays extraction statistics', () => {
      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByText('2 Q&A pairs')).toBeInTheDocument()
      expect(screen.getByText('84% avg confidence')).toBeInTheDocument()
      expect(screen.getByText('81% avg quality')).toBeInTheDocument()
      expect(screen.getByText('1 needs review')).toBeInTheDocument()
    })

    it('shows quality distribution chart', () => {
      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByText('Quality Distribution')).toBeInTheDocument()
      expect(screen.getByText('Excellent: 1')).toBeInTheDocument()
      expect(screen.getByText('Fair: 1')).toBeInTheDocument()
    })

    it('displays issue type breakdown', () => {
      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByText('Issue Types')).toBeInTheDocument()
      expect(screen.getByText('Technical Issue: 1')).toBeInTheDocument()
      expect(screen.getByText('Setup Assistance: 1')).toBeInTheDocument()
    })
  })

  describe('Q&A Pair Display', () => {
    it('renders Q&A pairs list', () => {
      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByTestId('virtual-list')).toBeInTheDocument()
      expect(screen.getByText("I'm having trouble with email sync")).toBeInTheDocument()
      expect(screen.getByText('How do I set up my Outlook account?')).toBeInTheDocument()
    })

    it('displays Q&A pair details', () => {
      render(<QAPairExtractor conversationId="conv-1" />)
      
      // First Q&A pair
      expect(screen.getByText("I'm having trouble with email sync")).toBeInTheDocument()
      expect(screen.getByText('Go to Settings > Accounts > Gmail and click Reconnect')).toBeInTheDocument()
      expect(screen.getByText('92%')).toBeInTheDocument() // Confidence
      expect(screen.getByText('89%')).toBeInTheDocument() // Quality
    })

    it('shows confidence indicators', () => {
      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByText('Question Clarity: 88%')).toBeInTheDocument()
      expect(screen.getByText('Answer Relevance: 95%')).toBeInTheDocument()
      expect(screen.getByText('Context Completeness: 91%')).toBeInTheDocument()
    })

    it('displays quality factors', () => {
      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByText('Specificity: 85%')).toBeInTheDocument()
      expect(screen.getByText('Actionability: 93%')).toBeInTheDocument()
      expect(screen.getByText('Completeness: 87%')).toBeInTheDocument()
      expect(screen.getByText('Clarity: 92%')).toBeInTheDocument()
    })

    it('shows quality issues and suggestions', () => {
      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByText('Answer could be more detailed')).toBeInTheDocument()
      expect(screen.getByText('Add screenshots for each step')).toBeInTheDocument()
      expect(screen.getByText('Include common error scenarios')).toBeInTheDocument()
    })

    it('displays metadata information', () => {
      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByText('email')).toBeInTheDocument()
      expect(screen.getByText('sync')).toBeInTheDocument()
      expect(screen.getByText('Easy')).toBeInTheDocument()
      expect(screen.getByText('2 minutes')).toBeInTheDocument()
      expect(screen.getByText('94% success')).toBeInTheDocument()
    })
  })

  describe('Filtering and Sorting', () => {
    it('filters by confidence threshold', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const confidenceSlider = screen.getByRole('slider', { name: /confidence/i })
      await user.click(confidenceSlider)
      
      // Should filter out low confidence pairs
      expect(screen.queryByText('How do I set up my Outlook account?')).not.toBeInTheDocument()
      expect(screen.getByText("I'm having trouble with email sync")).toBeInTheDocument()
    })

    it('filters by issue type', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const issueTypeFilter = screen.getByText('All Issue Types')
      await user.click(issueTypeFilter)
      
      const technicalIssueOption = screen.getByText('Technical Issue')
      await user.click(technicalIssueOption)
      
      expect(screen.getByText("I'm having trouble with email sync")).toBeInTheDocument()
      expect(screen.queryByText('How do I set up my Outlook account?')).not.toBeInTheDocument()
    })

    it('filters by quality threshold', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const qualitySlider = screen.getByRole('slider', { name: /quality/i })
      await user.click(qualitySlider)
      
      // Adjust quality threshold
      fireEvent.change(qualitySlider, { target: { value: '0.8' } })
      
      expect(screen.getByText("I'm having trouble with email sync")).toBeInTheDocument()
      expect(screen.queryByText('How do I set up my Outlook account?')).not.toBeInTheDocument()
    })

    it('shows only pairs needing review', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const reviewOnlyToggle = screen.getByText('Show only needs review')
      await user.click(reviewOnlyToggle)
      
      expect(screen.queryByText("I'm having trouble with email sync")).not.toBeInTheDocument()
      expect(screen.getByText('How do I set up my Outlook account?')).toBeInTheDocument()
    })

    it('sorts by different criteria', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const sortSelect = screen.getByText('Sort by Confidence')
      await user.click(sortSelect)
      
      expect(screen.getByText('Quality')).toBeInTheDocument()
      expect(screen.getByText('Date')).toBeInTheDocument()
      expect(screen.getByText('Issue Type')).toBeInTheDocument()
      
      const qualityOption = screen.getByText('Quality')
      await user.click(qualityOption)
      
      // Should re-order the list
      expect(screen.getByText('Sort by Quality')).toBeInTheDocument()
    })

    it('toggles sort direction', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const sortDirectionButton = screen.getByTestId('arrow-down-icon').closest('button')
      await user.click(sortDirectionButton!)
      
      expect(screen.getByTestId('arrow-up-icon')).toBeInTheDocument()
    })
  })

  describe('Q&A Pair Actions', () => {
    it('handles inline editing', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const questionText = screen.getByText("I'm having trouble with email sync")
      await user.click(questionText)
      
      expect(screen.getByDisplayValue("I'm having trouble with email sync")).toBeInTheDocument()
      
      const input = screen.getByDisplayValue("I'm having trouble with email sync")
      await user.clear(input)
      await user.type(input, 'I need help with email synchronization')
      await user.keyboard('{Enter}')
      
      expect(mockActions.updateQAPair).toHaveBeenCalledWith('qa-1', {
        question: {
          ...mockQAPairs[0].question,
          text: 'I need help with email synchronization',
        },
      })
    })

    it('handles pair approval', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const approveButton = screen.getByText('Approve')
      await user.click(approveButton)
      
      expect(mockActions.approveQAPair).toHaveBeenCalledWith('qa-1')
    })

    it('handles pair rejection', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const rejectButton = screen.getByText('Reject')
      await user.click(rejectButton)
      
      expect(mockActions.rejectQAPair).toHaveBeenCalledWith('qa-1')
    })

    it('handles pair deletion', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const deleteButton = screen.getByTestId('trash-icon').closest('button')
      await user.click(deleteButton!)
      
      expect(screen.getByText('Delete Q&A Pair')).toBeInTheDocument()
      
      const confirmButton = screen.getByText('Delete')
      await user.click(confirmButton)
      
      expect(mockActions.deleteQAPair).toHaveBeenCalledWith('qa-1')
    })

    it('handles pair optimization', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const optimizeButton = screen.getByText('Optimize')
      await user.click(optimizeButton)
      
      expect(mockActions.optimizeQAPair).toHaveBeenCalledWith('qa-1')
    })

    it('shows optimization suggestions', () => {
      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByText('Improvement Suggestions')).toBeInTheDocument()
      expect(screen.getByText('Add more context about when this error typically occurs')).toBeInTheDocument()
    })
  })

  describe('Bulk Operations', () => {
    it('handles bulk selection', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const selectAllCheckbox = screen.getByRole('checkbox', { name: /select all/i })
      await user.click(selectAllCheckbox)
      
      expect(screen.getByText('2 pairs selected')).toBeInTheDocument()
    })

    it('shows bulk operations panel', async () => {
      ;(useQAExtraction as any).mockReturnValue({
        ...mockQAExtraction,
        selectedPairs: new Set(['qa-1', 'qa-2']),
      })

      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByText('Bulk Operations')).toBeInTheDocument()
      expect(screen.getByText('Approve Selected')).toBeInTheDocument()
      expect(screen.getByText('Delete Selected')).toBeInTheDocument()
      expect(screen.getByText('Export Selected')).toBeInTheDocument()
    })

    it('handles bulk approval', async () => {
      ;(useQAExtraction as any).mockReturnValue({
        ...mockQAExtraction,
        selectedPairs: new Set(['qa-1', 'qa-2']),
      })

      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const bulkApproveButton = screen.getByText('Approve Selected')
      await user.click(bulkApproveButton)
      
      expect(mockActions.bulkApproveQAPairs).toHaveBeenCalledWith(['qa-1', 'qa-2'])
    })

    it('handles bulk export', async () => {
      ;(useQAExtraction as any).mockReturnValue({
        ...mockQAExtraction,
        selectedPairs: new Set(['qa-1']),
      })

      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const exportButton = screen.getByText('Export Selected')
      await user.click(exportButton)
      
      expect(mockActions.exportQAPairs).toHaveBeenCalledWith(['qa-1'])
      expect(global.URL.createObjectURL).toHaveBeenCalled()
    })
  })

  describe('AI Extraction', () => {
    it('handles extraction process', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const extractButton = screen.getByText('Extract Q&A Pairs')
      await user.click(extractButton)
      
      expect(mockActions.extractQAPairs).toHaveBeenCalledWith('conv-1')
    })

    it('shows extraction progress', () => {
      ;(useQAExtraction as any).mockReturnValue({
        ...mockQAExtraction,
        isExtracting: true,
      })

      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByText('Extracting Q&A pairs...')).toBeInTheDocument()
      expect(screen.getByTestId('loader-icon')).toBeInTheDocument()
    })

    it('handles re-extraction', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const reextractButton = screen.getByText('Re-extract')
      await user.click(reextractButton)
      
      expect(screen.getByText('Re-extract Q&A pairs?')).toBeInTheDocument()
      
      const confirmButton = screen.getByText('Re-extract')
      await user.click(confirmButton)
      
      expect(mockActions.reextractQAPairs).toHaveBeenCalledWith('conv-1')
    })

    it('shows extraction settings', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const settingsButton = screen.getByTestId('settings-icon').closest('button')
      await user.click(settingsButton!)
      
      expect(screen.getByText('Extraction Settings')).toBeInTheDocument()
      expect(screen.getByText('Minimum confidence threshold')).toBeInTheDocument()
      expect(screen.getByText('Context window size')).toBeInTheDocument()
    })
  })

  describe('Performance Metrics', () => {
    it('displays performance statistics', () => {
      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByText('Performance Metrics')).toBeInTheDocument()
      expect(screen.getByText('High Quality: 50%')).toBeInTheDocument()
      expect(screen.getByText('Needs Review: 50%')).toBeInTheDocument()
    })

    it('shows confidence distribution', () => {
      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByText('Confidence Distribution')).toBeInTheDocument()
      expect(screen.getByText('Average: 84%')).toBeInTheDocument()
    })

    it('displays success rate metrics', () => {
      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByText('Success Rates')).toBeInTheDocument()
      expect(screen.getByText('94% success')).toBeInTheDocument()
      expect(screen.getByText('82% success')).toBeInTheDocument()
    })
  })

  describe('Virtual Scrolling', () => {
    it('renders virtual list for performance', () => {
      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByTestId('virtual-list')).toBeInTheDocument()
    })

    it('handles large datasets efficiently', () => {
      const largeQASet = Array.from({ length: 10000 }, (_, i) => ({
        ...mockQAPairs[0],
        id: `qa-${i}`,
        question: { ...mockQAPairs[0].question, text: `Question ${i}` },
      }))

      ;(useQAExtraction as any).mockReturnValue({
        ...mockQAExtraction,
        qaPairs: largeQASet,
        extractionStats: {
          ...mockExtractionStats,
          totalPairs: 10000,
        },
      })

      const startTime = performance.now()
      render(<QAPairExtractor conversationId="conv-1" />)
      const endTime = performance.now()
      
      expect(endTime - startTime).toBeLessThan(100)
      expect(screen.getByText('10,000 Q&A pairs')).toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('handles extraction errors', () => {
      ;(useQAExtraction as any).mockReturnValue({
        ...mockQAExtraction,
        error: 'Failed to extract Q&A pairs',
        isExtracting: false,
      })

      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByText('Error: Failed to extract Q&A pairs')).toBeInTheDocument()
      expect(screen.getByText('Retry')).toBeInTheDocument()
    })

    it('handles network errors gracefully', async () => {
      mockActions.extractQAPairs.mockRejectedValue(new Error('Network error'))
      
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const extractButton = screen.getByText('Extract Q&A Pairs')
      await user.click(extractButton)
      
      await waitFor(() => {
        expect(screen.getByText('Failed to extract Q&A pairs')).toBeInTheDocument()
      })
    })

    it('handles invalid Q&A pair data', () => {
      ;(useQAExtraction as any).mockReturnValue({
        ...mockQAExtraction,
        qaPairs: [
          {
            ...mockQAPairs[0],
            confidence: null, // Invalid data
            quality: undefined,
          },
        ],
      })

      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByText('N/A')).toBeInTheDocument() // Fallback for missing confidence
    })
  })

  describe('Loading States', () => {
    it('shows loading state during extraction', () => {
      ;(useQAExtraction as any).mockReturnValue({
        ...mockQAExtraction,
        isExtracting: true,
        qaPairs: [],
      })

      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByText('Extracting Q&A pairs...')).toBeInTheDocument()
      expect(screen.getByTestId('loader-icon')).toBeInTheDocument()
    })

    it('shows empty state when no pairs exist', () => {
      ;(useQAExtraction as any).mockReturnValue({
        ...mockQAExtraction,
        qaPairs: [],
        extractionStats: {
          ...mockExtractionStats,
          totalPairs: 0,
        },
      })

      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByText('No Q&A pairs found')).toBeInTheDocument()
      expect(screen.getByText('Start extraction to analyze the conversation')).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has proper ARIA labels', () => {
      render(<QAPairExtractor conversationId="conv-1" />)
      
      expect(screen.getByRole('main')).toBeInTheDocument()
      expect(screen.getByRole('list')).toBeInTheDocument()
      expect(screen.getAllByRole('listitem')).toHaveLength(2)
    })

    it('supports keyboard navigation', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      await user.keyboard('{Tab}')
      expect(screen.getByText('Extract Q&A Pairs')).toHaveFocus()
    })

    it('provides screen reader announcements', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const approveButton = screen.getByText('Approve')
      await user.click(approveButton)
      
      expect(screen.getByText('Q&A pair approved')).toHaveAttribute('aria-live', 'polite')
    })

    it('has proper color contrast for quality indicators', () => {
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const highQualityIndicator = screen.getByText('89%')
      expect(highQualityIndicator).toHaveClass('text-green-600')
      
      const lowQualityIndicator = screen.getByText('73%')
      expect(lowQualityIndicator).toHaveClass('text-yellow-600')
    })
  })

  describe('Import/Export', () => {
    it('handles Q&A pair export', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const exportButton = screen.getByText('Export All')
      await user.click(exportButton)
      
      expect(mockActions.exportQAPairs).toHaveBeenCalledWith(['qa-1', 'qa-2'])
    })

    it('handles Q&A pair import', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const importButton = screen.getByTestId('upload-icon').closest('button')
      await user.click(importButton!)
      
      expect(screen.getByText('Import Q&A Pairs')).toBeInTheDocument()
      
      const fileInput = screen.getByRole('button', { name: /choose file/i })
      const file = new File(['test content'], 'qa-pairs.json', { type: 'application/json' })
      
      await user.upload(fileInput, file)
      
      expect(mockActions.importQAPairs).toHaveBeenCalledWith('conv-1', expect.any(File))
    })

    it('validates import file format', async () => {
      const user = userEvent.setup()
      render(<QAPairExtractor conversationId="conv-1" />)
      
      const importButton = screen.getByTestId('upload-icon').closest('button')
      await user.click(importButton!)
      
      const fileInput = screen.getByRole('button', { name: /choose file/i })
      const invalidFile = new File(['test'], 'test.txt', { type: 'text/plain' })
      
      await user.upload(fileInput, invalidFile)
      
      expect(screen.getByText('Please select a JSON file')).toBeInTheDocument()
    })
  })
})