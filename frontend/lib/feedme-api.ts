/**
 * FeedMe API Client
 * 
 * Client functions for interacting with the FeedMe API endpoints.
 * Handles transcript upload, processing status, and conversation management.
 */

// Custom error class for API unreachable scenarios
export class ApiUnreachableError extends Error {
  constructor(message: string, public readonly originalError?: Error) {
    super(message)
    this.name = 'ApiUnreachableError'
  }
}

// Retry and timeout utilities
const fetchWithRetry = async (
  url: string, 
  options: RequestInit = {}, 
  retries: number = 3,
  timeout: number = 10000
): Promise<Response> => {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeout)
  
  try {
    console.log(`[FeedMe API] Attempting fetch to ${url} (retries left: ${retries})`)
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    })
    clearTimeout(timeoutId)
    return response
  } catch (error) {
    clearTimeout(timeoutId)
    console.error(`[FeedMe API] Fetch failed for ${url}:`, error)
    
    if (retries > 0 && (error instanceof Error && error.name !== 'AbortError')) {
      // Wait before retry (exponential backoff)
      const delay = Math.pow(2, 3 - retries) * 1000
      console.log(`[FeedMe API] Retrying in ${delay}ms...`)
      await new Promise(resolve => setTimeout(resolve, delay))
      return fetchWithRetry(url, options, retries - 1, timeout)
    }
    
    // On final failure, throw ApiUnreachableError with friendly message
    const message = error instanceof Error && error.name === 'AbortError' 
      ? 'Request timed out - please check your internet connection'
      : 'Unable to reach FeedMe service - please try again later'
    
    throw new ApiUnreachableError(message, error instanceof Error ? error : new Error(String(error)))
  }
}

// API Base Configuration - Deterministic API base URL without typeof window checks
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? '/api/v1'
const FEEDME_API_BASE = `${API_BASE}/feedme`

console.log('[FeedMe API] Using API_BASE:', API_BASE)
console.log('[FeedMe API] Using FEEDME_API_BASE:', FEEDME_API_BASE)

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
    console.log('[FeedMe API Client] Initialized with baseUrl:', this.baseUrl)
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

    console.log('[FeedMe API] Uploading to:', `${this.baseUrl}/conversations/upload`)
    
    const response = await fetchWithRetry(`${this.baseUrl}/conversations/upload`, {
      method: 'POST',
      body: formData,
    })

    if (!response.ok) {
      console.error('[FeedMe API] Upload failed:', response.status, response.statusText)
      const errorData = await response.json().catch(() => ({}))
      console.error('[FeedMe API] Error details:', errorData)
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

    console.log('[FeedMe API] Uploading to:', `${this.baseUrl}/conversations/upload`)
    
    const response = await fetchWithRetry(`${this.baseUrl}/conversations/upload`, {
      method: 'POST',
      body: formData,
    })

    if (!response.ok) {
      console.error('[FeedMe API] Upload failed:', response.status, response.statusText)
      const errorData = await response.json().catch(() => ({}))
      console.error('[FeedMe API] Error details:', errorData)
      throw new Error(errorData.detail || `Upload failed: ${response.status} ${response.statusText}`)
    }

    return response.json()
  }

  /**
   * Get processing status for a conversation
   */
  async getProcessingStatus(conversationId: number): Promise<ProcessingStatusResponse> {
    const response = await fetchWithRetry(`${this.baseUrl}/conversations/${conversationId}/status`)

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

    const response = await fetchWithRetry(`${this.baseUrl}/conversations?${params}`)

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
    const response = await fetchWithRetry(`${this.baseUrl}/conversations/${conversationId}`)

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
    const response = await fetchWithRetry(`${this.baseUrl}/conversations/${conversationId}`, {
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
    const response = await fetchWithRetry(`${this.baseUrl}/conversations/${conversationId}/reprocess`, {
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
      console.log('[FeedMe API] Health check:', `${this.baseUrl}/analytics`)
      const response = await fetchWithRetry(`${this.baseUrl}/analytics`)
      console.log('[FeedMe API] Health check result:', response.ok, response.status)
      return response.ok
    } catch (error) {
      console.error('[FeedMe API] Health check failed:', error)
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

// Phase 3: Versioning and Edit API Types

export interface ConversationVersion {
  id: number
  conversation_id: number
  version: number
  title: string
  raw_transcript: string
  metadata: Record<string, any>
  is_active: boolean
  updated_by?: string
  created_at: string
  updated_at: string
}

export interface VersionListResponse {
  versions: ConversationVersion[]
  total_count: number
  active_version: number
}

export interface ModifiedLine {
  line_number: number
  original: string
  modified: string
}

export interface VersionDiff {
  from_version: number
  to_version: number
  added_lines: string[]
  removed_lines: string[]
  modified_lines: ModifiedLine[]
  unchanged_lines: string[]
  stats: Record<string, number>
}

export interface ConversationEditRequest {
  title?: string
  raw_transcript?: string
  metadata?: Record<string, any>
  updated_by: string
  reprocess?: boolean
}

export interface ConversationRevertRequest {
  target_version: number
  reverted_by: string
  reason?: string
  reprocess?: boolean
}

export interface EditResponse {
  conversation: UploadTranscriptResponse
  new_version: number
  task_id?: string
  reprocessing: boolean
}

export interface RevertResponse {
  conversation: UploadTranscriptResponse
  new_version: number
  reverted_to_version: number
  task_id?: string
  reprocessing: boolean
}

// Phase 3: Versioning API Functions

/**
 * Edit a conversation and create a new version
 */
export async function editConversation(
  conversationId: number, 
  editRequest: ConversationEditRequest
): Promise<EditResponse> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/conversations/${conversationId}/edit`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(editRequest),
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to edit conversation: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Get all versions of a conversation
 */
export async function getConversationVersions(conversationId: number): Promise<VersionListResponse> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/conversations/${conversationId}/versions`)

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to get conversation versions: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Get a specific version of a conversation
 */
export async function getConversationVersion(
  conversationId: number, 
  versionNumber: number
): Promise<ConversationVersion> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/conversations/${conversationId}/versions/${versionNumber}`)

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to get conversation version: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Generate diff between two versions
 */
export async function getVersionDiff(
  conversationId: number, 
  version1: number, 
  version2: number
): Promise<VersionDiff> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/conversations/${conversationId}/versions/${version1}/diff/${version2}`)

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to generate version diff: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Revert conversation to a previous version
 */
export async function revertConversation(
  conversationId: number,
  targetVersion: number,
  revertRequest: ConversationRevertRequest
): Promise<RevertResponse> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/conversations/${conversationId}/revert/${targetVersion}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(revertRequest),
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to revert conversation: ${response.status} ${response.statusText}`)
  }

  return response.json()
}