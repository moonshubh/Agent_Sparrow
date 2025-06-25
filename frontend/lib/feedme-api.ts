/**
 * FeedMe API Client
 * 
 * Client functions for interacting with the FeedMe API endpoints.
 * Handles transcript upload, processing status, and conversation management.
 */

// API Base Configuration
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const FEEDME_API_BASE = `${API_BASE_URL}/api/v1/feedme`

// Types
export interface UploadTranscriptRequest {
  title: string
  transcript_content?: string
  uploaded_by?: string
  auto_process?: boolean
}

export interface UploadTranscriptResponse {
  id: number
  title: string
  processing_status: 'pending' | 'processing' | 'completed' | 'failed'
  total_examples: number
  created_at: string
  metadata: Record<string, any>
}

export interface ProcessingStatusResponse {
  conversation_id: number
  status: 'pending' | 'processing' | 'completed' | 'failed'
  progress_percentage: number
  error_message?: string
  examples_extracted: number
  estimated_completion?: string
}

export interface ConversationListResponse {
  conversations: UploadTranscriptResponse[]
  total_count: number
  page: number
  page_size: number
  has_next: boolean
}

// API Client Class
export class FeedMeApiClient {
  private baseUrl: string

  constructor(baseUrl: string = FEEDME_API_BASE) {
    this.baseUrl = baseUrl
  }

  /**
   * Upload a transcript via file upload
   */
  async uploadTranscriptFile(
    title: string,
    file: File,
    uploadedBy?: string,
    autoProcess: boolean = true
  ): Promise<UploadTranscriptResponse> {
    const formData = new FormData()
    formData.append('title', title)
    formData.append('transcript_file', file)
    formData.append('auto_process', autoProcess.toString())
    
    if (uploadedBy) {
      formData.append('uploaded_by', uploadedBy)
    }

    const response = await fetch(`${this.baseUrl}/conversations/upload`, {
      method: 'POST',
      body: formData,
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || `Upload failed: ${response.status} ${response.statusText}`)
    }

    return response.json()
  }

  /**
   * Upload a transcript via text content
   */
  async uploadTranscriptText(
    title: string,
    transcriptContent: string,
    uploadedBy?: string,
    autoProcess: boolean = true
  ): Promise<UploadTranscriptResponse> {
    const formData = new FormData()
    formData.append('title', title)
    formData.append('transcript_content', transcriptContent)
    formData.append('auto_process', autoProcess.toString())
    
    if (uploadedBy) {
      formData.append('uploaded_by', uploadedBy)
    }

    const response = await fetch(`${this.baseUrl}/conversations/upload`, {
      method: 'POST',
      body: formData,
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || `Upload failed: ${response.status} ${response.statusText}`)
    }

    return response.json()
  }

  /**
   * Get processing status for a conversation
   */
  async getProcessingStatus(conversationId: number): Promise<ProcessingStatusResponse> {
    const response = await fetch(`${this.baseUrl}/conversations/${conversationId}/status`)

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || `Failed to get status: ${response.status} ${response.statusText}`)
    }

    return response.json()
  }

  /**
   * List conversations with pagination
   */
  async listConversations(
    page: number = 1,
    pageSize: number = 20,
    status?: string,
    uploadedBy?: string
  ): Promise<ConversationListResponse> {
    const params = new URLSearchParams({
      page: page.toString(),
      page_size: pageSize.toString(),
    })

    if (status) {
      params.append('status', status)
    }

    if (uploadedBy) {
      params.append('uploaded_by', uploadedBy)
    }

    const response = await fetch(`${this.baseUrl}/conversations?${params}`)

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || `Failed to list conversations: ${response.status} ${response.statusText}`)
    }

    return response.json()
  }

  /**
   * Get a specific conversation
   */
  async getConversation(conversationId: number): Promise<UploadTranscriptResponse> {
    const response = await fetch(`${this.baseUrl}/conversations/${conversationId}`)

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || `Failed to get conversation: ${response.status} ${response.statusText}`)
    }

    return response.json()
  }

  /**
   * Delete a conversation
   */
  async deleteConversation(conversationId: number): Promise<void> {
    const response = await fetch(`${this.baseUrl}/conversations/${conversationId}`, {
      method: 'DELETE',
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || `Failed to delete conversation: ${response.status} ${response.statusText}`)
    }
  }

  /**
   * Reprocess a conversation
   */
  async reprocessConversation(conversationId: number): Promise<void> {
    const response = await fetch(`${this.baseUrl}/conversations/${conversationId}/reprocess`, {
      method: 'POST',
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || `Failed to reprocess conversation: ${response.status} ${response.statusText}`)
    }
  }

  /**
   * Check if FeedMe service is available
   */
  async healthCheck(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/analytics`)
      return response.ok
    } catch {
      return false
    }
  }
}

// Default client instance
export const feedMeApi = new FeedMeApiClient()

// Utility functions
export const uploadTranscriptFile = (
  title: string,
  file: File,
  uploadedBy?: string,
  autoProcess?: boolean
) => feedMeApi.uploadTranscriptFile(title, file, uploadedBy, autoProcess)

export const uploadTranscriptText = (
  title: string,
  transcriptContent: string,
  uploadedBy?: string,
  autoProcess?: boolean
) => feedMeApi.uploadTranscriptText(title, transcriptContent, uploadedBy, autoProcess)

export const getProcessingStatus = (conversationId: number) => 
  feedMeApi.getProcessingStatus(conversationId)

export const listConversations = (
  page?: number,
  pageSize?: number,
  status?: string,
  uploadedBy?: string
) => feedMeApi.listConversations(page, pageSize, status, uploadedBy)

// Helper function to simulate upload progress
export const simulateUploadProgress = (
  onProgress: (progress: number) => void,
  duration: number = 2000
): Promise<void> => {
  return new Promise((resolve) => {
    const steps = 20
    const stepDuration = duration / steps
    let currentStep = 0

    const interval = setInterval(() => {
      currentStep++
      const progress = (currentStep / steps) * 100
      onProgress(Math.min(100, progress))

      if (currentStep >= steps) {
        clearInterval(interval)
        resolve()
      }
    }, stepDuration)
  })
}