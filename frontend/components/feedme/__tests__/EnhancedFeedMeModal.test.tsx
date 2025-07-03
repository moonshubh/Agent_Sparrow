/**
 * Enhanced FeedMe Modal Tests
 * 
 * Comprehensive test suite for the EnhancedFeedMeModal component
 * covering multi-file upload, drag-and-drop, validation, and state management.
 */

import React from 'react'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { EnhancedFeedMeModal } from '../EnhancedFeedMeModal'

// Mock the API functions
vi.mock('@/lib/feedme-api', () => ({
  uploadTranscriptFile: vi.fn(),
  uploadTranscriptText: vi.fn(),
  getProcessingStatus: vi.fn()
}))

// Mock File.prototype.text for testing
global.File.prototype.text = vi.fn().mockImplementation(function() {
  return Promise.resolve('mock file content')
})

// Mock zustand store
vi.mock('@/lib/stores/feedme-store', () => ({
  useFeedMeStore: vi.fn(() => ({
    actions: {
      addNotification: vi.fn(),
      connectWebSocket: vi.fn(),
      disconnectWebSocket: vi.fn()
    }
  }))
}))

// Mock WebSocket hook
vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocketConnection: vi.fn(() => ({
    isConnected: false,
    connectionStatus: 'disconnected',
    connect: vi.fn(),
    disconnect: vi.fn()
  }))
}))

import { uploadTranscriptFile, uploadTranscriptText, getProcessingStatus } from '@/lib/feedme-api'

const mockUploadTranscriptFile = uploadTranscriptFile as any
const mockUploadTranscriptText = uploadTranscriptText as any
const mockGetProcessingStatus = getProcessingStatus as any

describe('EnhancedFeedMeModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    onUploadComplete: vi.fn()
  }

  beforeEach(() => {
    vi.clearAllMocks()
    
    // Setup default mock responses
    mockUploadTranscriptFile.mockResolvedValue({
      id: 1,
      title: 'Test Conversation',
      processing_status: 'completed',
      total_examples: 5
    })
    
    mockUploadTranscriptText.mockResolvedValue({
      id: 2,
      title: 'Text Conversation',
      processing_status: 'completed',
      total_examples: 3
    })
    
    mockGetProcessingStatus.mockResolvedValue({
      status: 'completed'
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('Modal Rendering', () => {
    it('renders the modal when open', () => {
      render(<EnhancedFeedMeModal {...defaultProps} />)
      
      expect(screen.getByText('Enhanced FeedMe Upload')).toBeInTheDocument()
      expect(screen.getByText('Upload customer support transcripts with advanced multi-file support')).toBeInTheDocument()
    })

    it('does not render when closed', () => {
      render(<EnhancedFeedMeModal {...defaultProps} isOpen={false} />)
      
      expect(screen.queryByText('Enhanced FeedMe Upload')).not.toBeInTheDocument()
    })

    it('renders all three tabs', () => {
      render(<EnhancedFeedMeModal {...defaultProps} />)
      
      expect(screen.getByText('Multi-File Upload')).toBeInTheDocument()
      expect(screen.getByText('Single File')).toBeInTheDocument()
      expect(screen.getByText('Paste Text')).toBeInTheDocument()
    })
  })

  describe('Multi-File Upload Tab', () => {
    it('shows the drop zone by default', () => {
      render(<EnhancedFeedMeModal {...defaultProps} />)
      
      expect(screen.getByText('Drag and drop files here, or click to select')).toBeInTheDocument()
      expect(screen.getByText('Supports multiple .txt, .log, .html, .htm, .csv files up to 10MB each')).toBeInTheDocument()
    })

    it('handles file selection via input', async () => {
      const user = userEvent.setup()
      render(<EnhancedFeedMeModal {...defaultProps} />)
      
      const file = new File(['test content'], 'test.txt', { type: 'text/plain' })
      const input = document.querySelector('input[type="file"][multiple]') as HTMLInputElement
      
      await user.upload(input, file)
      
      await waitFor(() => {
        expect(screen.getByDisplayValue('test')).toBeInTheDocument()
      })
    })

    it('validates file types correctly', async () => {
      const user = userEvent.setup()
      render(<EnhancedFeedMeModal {...defaultProps} />)
      
      const invalidFile = new File(['test'], 'test.pdf', { type: 'application/pdf' })
      const input = document.querySelector('input[type="file"][multiple]') as HTMLInputElement
      
      await user.upload(input, invalidFile)
      
      // Should show error for invalid file type
      await waitFor(() => {
        expect(screen.getByText(/Please upload a text or HTML file/)).toBeInTheDocument()
      })
    })

    it('validates file size limits', async () => {
      const user = userEvent.setup()
      render(<EnhancedFeedMeModal {...defaultProps} />)
      
      // Create a file larger than 10MB
      const largeContent = 'x'.repeat(11 * 1024 * 1024) // 11MB
      const largeFile = new File([largeContent], 'large.txt', { type: 'text/plain' })
      const input = document.querySelector('input[type="file"][multiple]') as HTMLInputElement
      
      await user.upload(input, largeFile)
      
      await waitFor(() => {
        expect(screen.getByText(/File size must be less than 10MB/)).toBeInTheDocument()
      })
    })

    it('allows removing files from the queue', async () => {
      const user = userEvent.setup()
      render(<EnhancedFeedMeModal {...defaultProps} />)
      
      const file = new File(['test content'], 'test.txt', { type: 'text/plain' })
      const input = document.querySelector('input[type="file"][multiple]') as HTMLInputElement
      
      await user.upload(input, file)
      
      await waitFor(() => {
        expect(screen.getByDisplayValue('test')).toBeInTheDocument()
      })
      
      const removeButton = screen.getByRole('button', { name: /remove/i })
      await user.click(removeButton)
      
      await waitFor(() => {
        expect(screen.queryByDisplayValue('test')).not.toBeInTheDocument()
      })
    })

    it('shows Upload All button when files are present', async () => {
      const user = userEvent.setup()
      render(<EnhancedFeedMeModal {...defaultProps} />)
      
      const file = new File(['test content'], 'test.txt', { type: 'text/plain' })
      const input = document.querySelector('input[type="file"][multiple]') as HTMLInputElement
      
      await user.upload(input, file)
      
      await waitFor(() => {
        expect(screen.getByText('Upload All')).toBeInTheDocument()
      })
    })
  })

  describe('Batch Upload Functionality', () => {
    it('performs batch upload successfully', async () => {
      const user = userEvent.setup()
      render(<EnhancedFeedMeModal {...defaultProps} />)
      
      const files = [
        new File(['content 1'], 'file1.txt', { type: 'text/plain' }),
        new File(['content 2'], 'file2.txt', { type: 'text/plain' })
      ]
      
      const input = document.querySelector('input[type="file"][multiple]') as HTMLInputElement
      await user.upload(input, files)
      
      await waitFor(() => {
        expect(screen.getByText('Upload All')).toBeInTheDocument()
      })
      
      const uploadButton = screen.getByText('Upload All')
      await user.click(uploadButton)
      
      await waitFor(() => {
        expect(mockUploadTranscriptFile).toHaveBeenCalledTimes(2)
      })
    })

    it('shows batch upload progress', async () => {
      const user = userEvent.setup()
      
      // Mock a delayed response
      mockUploadTranscriptFile.mockImplementation(() => 
        new Promise(resolve => setTimeout(() => resolve({
          id: 1,
          title: 'Test',
          processing_status: 'completed',
          total_examples: 5
        }), 100))
      )
      
      render(<EnhancedFeedMeModal {...defaultProps} />)
      
      const file = new File(['test content'], 'test.txt', { type: 'text/plain' })
      const input = document.querySelector('input[type="file"][multiple]') as HTMLInputElement
      
      await user.upload(input, file)
      
      const uploadButton = screen.getByText('Upload All')
      await user.click(uploadButton)
      
      expect(screen.getByText(/Uploading \(0\/1\)/)).toBeInTheDocument()
      
      await waitFor(() => {
        expect(screen.getByText(/Successfully uploaded 1 file/)).toBeInTheDocument()
      })
    })

    it('handles upload errors gracefully', async () => {
      const user = userEvent.setup()
      
      mockUploadTranscriptFile.mockRejectedValue(new Error('Upload failed'))
      
      render(<EnhancedFeedMeModal {...defaultProps} />)
      
      const file = new File(['test content'], 'test.txt', { type: 'text/plain' })
      const input = document.querySelector('input[type="file"][multiple]') as HTMLInputElement
      
      await user.upload(input, file)
      
      const uploadButton = screen.getByText('Upload All')
      await user.click(uploadButton)
      
      await waitFor(() => {
        expect(screen.getByText(/error/i)).toBeInTheDocument()
      })
    })
  })

  describe('Single File Tab', () => {
    beforeEach(async () => {
      const user = userEvent.setup()
      render(<EnhancedFeedMeModal {...defaultProps} />)
      
      const singleFileTab = screen.getByText('Single File')
      await user.click(singleFileTab)
    })

    it('switches to single file tab', () => {
      expect(screen.getByLabelText('Conversation Title *')).toBeInTheDocument()
      expect(screen.getByText('Drag and drop a file here, or click to select')).toBeInTheDocument()
    })

    it('requires title and file for submission', async () => {
      const user = userEvent.setup()
      
      const uploadButton = screen.getByRole('button', { name: /Upload File/i })
      expect(uploadButton).toBeDisabled()
      
      const titleInput = screen.getByLabelText('Conversation Title *')
      await user.type(titleInput, 'Test Title')
      
      expect(uploadButton).toBeDisabled() // Still disabled without file
      
      const file = new File(['test content'], 'test.txt', { type: 'text/plain' })
      const input = document.querySelector('input[type="file"]:not([multiple])') as HTMLInputElement
      
      await user.upload(input, file)
      
      await waitFor(() => {
        expect(uploadButton).toBeEnabled()
      })
    })

    it('auto-fills title from filename', async () => {
      const user = userEvent.setup()
      
      const file = new File(['test content'], 'support-ticket-123.txt', { type: 'text/plain' })
      const input = document.querySelector('input[type="file"]:not([multiple])') as HTMLInputElement
      
      await user.upload(input, file)
      
      await waitFor(() => {
        expect(screen.getByDisplayValue('support-ticket-123')).toBeInTheDocument()
      })
    })
  })

  describe('Text Input Tab', () => {
    beforeEach(async () => {
      const user = userEvent.setup()
      render(<EnhancedFeedMeModal {...defaultProps} />)
      
      const textTab = screen.getByText('Paste Text')
      await user.click(textTab)
    })

    it('switches to text input tab', () => {
      expect(screen.getByLabelText('Conversation Title *')).toBeInTheDocument()
      expect(screen.getByLabelText('Transcript Content *')).toBeInTheDocument()
    })

    it('shows character count', async () => {
      const user = userEvent.setup()
      
      const textarea = screen.getByLabelText('Transcript Content *')
      await user.type(textarea, 'Hello world')
      
      expect(screen.getByText('11 characters')).toBeInTheDocument()
    })

    it('uploads text content successfully', async () => {
      const user = userEvent.setup()
      
      const titleInput = screen.getByLabelText('Conversation Title *')
      const textarea = screen.getByLabelText('Transcript Content *')
      
      await user.type(titleInput, 'Text Upload Test')
      await user.type(textarea, 'Customer: I need help\nAgent: How can I assist you?')
      
      const uploadButton = screen.getByRole('button', { name: /Upload Text/i })
      await user.click(uploadButton)
      
      await waitFor(() => {
        expect(mockUploadTranscriptText).toHaveBeenCalledWith(
          'Text Upload Test',
          'Customer: I need help\nAgent: How can I assist you?',
          'web-user',
          true
        )
      })
    })
  })

  describe('Drag and Drop', () => {
    it('handles drag and drop events', async () => {
      render(<EnhancedFeedMeModal {...defaultProps} />)
      
      const dropZone = screen.getByText('Drag and drop files here, or click to select').closest('div')
      
      const file = new File(['test content'], 'test.txt', { type: 'text/plain' })
      
      fireEvent.dragEnter(dropZone!, {
        dataTransfer: {
          files: [file]
        }
      })
      
      await waitFor(() => {
        expect(screen.getByText('Drop files here...')).toBeInTheDocument()
      })
      
      fireEvent.drop(dropZone!, {
        dataTransfer: {
          files: [file]
        }
      })
      
      await waitFor(() => {
        expect(screen.getByDisplayValue('test')).toBeInTheDocument()
      })
    })
  })

  describe('File Analysis', () => {
    it('analyzes HTML files and shows preview', async () => {
      const user = userEvent.setup()
      render(<EnhancedFeedMeModal {...defaultProps} />)
      
      const htmlContent = `
        <html>
          <meta name="generator" content="Zendesk">
          <div class="zd-comment">Customer message</div>
          <div class="zd-comment">Agent response</div>
        </html>
      `
      
      const htmlFile = new File([htmlContent], 'ticket.html', { type: 'text/html' })
      const input = document.querySelector('input[type="file"][multiple]') as HTMLInputElement
      
      await user.upload(input, htmlFile)
      
      await waitFor(() => {
        expect(screen.getByText(/Zendesk ticket/)).toBeInTheDocument()
      })
    })

    it('shows file size information', async () => {
      const user = userEvent.setup()
      render(<EnhancedFeedMeModal {...defaultProps} />)
      
      const content = 'a'.repeat(1024) // 1KB
      const file = new File([content], 'test.txt', { type: 'text/plain' })
      const input = document.querySelector('input[type="file"][multiple]') as HTMLInputElement
      
      await user.upload(input, file)
      
      await waitFor(() => {
        expect(screen.getByText('1.0 KB')).toBeInTheDocument()
      })
    })
  })

  describe('Accessibility', () => {
    it('has proper ARIA labels', () => {
      render(<EnhancedFeedMeModal {...defaultProps} />)
      
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByLabelText(/Enhanced FeedMe Upload/)).toBeInTheDocument()
    })

    it('supports keyboard navigation', async () => {
      const user = userEvent.setup()
      render(<EnhancedFeedMeModal {...defaultProps} />)
      
      // Tab through the interface
      await user.tab()
      expect(screen.getByRole('tab', { name: /Multi-File Upload/ })).toHaveFocus()
      
      await user.tab()
      expect(screen.getByRole('tab', { name: /Single File/ })).toHaveFocus()
    })
  })

  describe('Callbacks', () => {
    it('calls onClose when modal is closed', async () => {
      const onClose = vi.fn()
      const user = userEvent.setup()
      
      render(<EnhancedFeedMeModal {...defaultProps} onClose={onClose} />)
      
      // Simulate closing via escape key
      fireEvent.keyDown(document, { key: 'Escape' })
      
      await waitFor(() => {
        expect(onClose).toHaveBeenCalled()
      })
    })

    it('calls onUploadComplete with results', async () => {
      const onUploadComplete = vi.fn()
      const user = userEvent.setup()
      
      render(<EnhancedFeedMeModal {...defaultProps} onUploadComplete={onUploadComplete} />)
      
      const file = new File(['test content'], 'test.txt', { type: 'text/plain' })
      const input = document.querySelector('input[type="file"][multiple]') as HTMLInputElement
      
      await user.upload(input, file)
      
      const uploadButton = screen.getByText('Upload All')
      await user.click(uploadButton)
      
      await waitFor(() => {
        expect(onUploadComplete).toHaveBeenCalledWith([
          expect.objectContaining({
            id: 1,
            title: 'test',
            status: 'completed'
          })
        ])
      })
    })
  })
})