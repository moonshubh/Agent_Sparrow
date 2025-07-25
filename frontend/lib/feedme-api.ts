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
    let message: string
    if (error instanceof Error) {
      if (error.name === 'AbortError') {
        message = 'Request timed out - please check your internet connection'
      } else if (error.message.includes('NetworkError') || error.message.includes('fetch')) {
        message = 'Network error - please check your internet connection'
      } else if (error.message.includes('ECONNREFUSED') || error.message.includes('refused')) {
        message = 'FeedMe service is currently unavailable - please try again later'
      } else {
        message = `Connection failed: ${error.message}`
      }
    } else {
      message = 'Unable to reach FeedMe service - please try again later'
    }
    
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
  // Support both backend schema variations
  total_conversations?: number
  total_pages?: number
}

// Approval Workflow Types
export interface ApprovalRequest {
  approved_by: string
  reviewer_notes?: string
}

export interface RejectionRequest {
  rejected_by: string
  reviewer_notes: string
}

export interface ApprovalResponse {
  conversation: UploadTranscriptResponse
  action: string
  timestamp: string
}

export interface DeleteConversationResponse {
  conversation_id: number
  title: string
  examples_deleted: number
  message: string
}

export interface ApprovalWorkflowStats {
  total_conversations: number
  pending_approval: number
  awaiting_review: number
  approved: number
  rejected: number
  published: number
  currently_processing: number
  processing_failed: number
  avg_quality_score?: number
  avg_processing_time_ms?: number
}

export interface BulkApprovalRequest {
  conversation_ids: number[]
  action: 'approve' | 'reject'
  approved_by: string
  reviewer_notes?: string
}

export interface BulkApprovalResponse {
  successful: number[]
  failed: Array<{ conversation_id: number; error: string }>
  total_requested: number
  total_successful: number
  action_taken: string
}

export interface ExampleReviewRequest {
  reviewed_by: string
  review_status: 'pending' | 'approved' | 'rejected' | 'edited'
  reviewer_notes?: string
  question_text?: string
  answer_text?: string
  tags?: string[]
}

export interface ExampleReviewResponse {
  example: any // Would need the full example type
  action: string
  timestamp: string
}

export interface ExampleListResponse {
  examples: FeedMeExample[]
  total_examples: number
  page: number
  page_size: number
  total_pages: number
}

export interface FeedMeExample {
  id: number
  conversation_id: number
  question_text: string
  answer_text: string
  context_before?: string
  context_after?: string
  tags: string[]
  issue_type?: string
  resolution_type?: string
  confidence_score: number
  usefulness_score: number
  is_active: boolean
  created_at: string
  updated_at: string
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
    uploadedBy?: string,
    searchQuery?: string,
    folderId?: number | null
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

    if (searchQuery) {
      params.append('search', searchQuery)
    }

    if (folderId !== undefined) {
      if (folderId === null) {
        // Don't send folder_id parameter to get all conversations
      } else if (folderId === 0) {
        params.append('folder_id', '0') // Unassigned conversations
      } else {
        params.append('folder_id', folderId.toString())
      }
    }

    const response = await fetchWithRetry(`${this.baseUrl}/conversations?${params.toString()}`)

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

  /**
   * Get conversation examples
   */
  async getConversationExamples(
    conversationId: number,
    page: number = 1,
    pageSize: number = 20,
    isActive?: boolean
  ): Promise<ExampleListResponse> {
    const params = new URLSearchParams({
      page: page.toString(),
      page_size: pageSize.toString(),
    })

    if (isActive !== undefined) {
      params.append('is_active', isActive.toString())
    }

    const response = await fetchWithRetry(`${this.baseUrl}/conversations/${conversationId}/examples?${params.toString()}`)

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || `Failed to get examples: ${response.status} ${response.statusText}`)
    }

    return response.json()
  }

  /**
   * Update an example
   */
  async updateExample(
    exampleId: number,
    updates: Partial<FeedMeExample>
  ): Promise<FeedMeExample> {
    const response = await fetchWithRetry(`${this.baseUrl}/examples/${exampleId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(updates),
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || `Failed to update example: ${response.status} ${response.statusText}`)
    }

    return response.json()
  }

  /**
   * Create folder with Supabase sync
   */
  async createFolderSupabase(folderData: FolderCreate): Promise<any> {
    return createFolderSupabase(folderData)
  }

  /**
   * Update folder with Supabase sync
   */
  async updateFolderSupabase(folderId: number, folderData: FolderUpdate): Promise<any> {
    return updateFolderSupabase(folderId, folderData)
  }

  /**
   * Delete folder with Supabase sync
   */
  async deleteFolderSupabase(folderId: number, moveConversationsTo?: number): Promise<any> {
    return deleteFolderSupabase(folderId, moveConversationsTo)
  }

  /**
   * Assign conversations to folder with Supabase sync
   */
  async assignConversationsToFolderSupabase(folderId: number | null, conversationIds: number[]): Promise<any> {
    return assignConversationsToFolderSupabase(folderId, conversationIds)
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

/**
 * Get formatted Q&A content for editing
 */
export async function getFormattedQAContent(conversationId: number): Promise<{
  formatted_content: string
  total_examples: number
  content_type: 'qa_examples' | 'raw_transcript'
  raw_transcript?: string
  message: string
}> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/conversations/${conversationId}/formatted-content`)

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to get formatted content: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

export function listConversations(
  page?: number,
  pageSize?: number,
  searchQuery?: string,
  sortBy?: string,
  folderId?: number | null
) {
  return feedMeApi.listConversations(page, pageSize, undefined, undefined, searchQuery, folderId)
}

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
  transcript_content: string
  edit_reason: string
  user_id: string
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

// Approval Workflow API Functions

/**
 * Delete a conversation and all associated examples
 */
export async function deleteConversation(conversationId: number): Promise<DeleteConversationResponse> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/conversations/${conversationId}`, {
    method: 'DELETE',
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to delete conversation: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Approve a conversation
 */
export async function approveConversation(
  conversationId: number, 
  approvalRequest: ApprovalRequest
): Promise<ApprovalResponse> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/conversations/${conversationId}/approve`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(approvalRequest),
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to approve conversation: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Reject a conversation
 */
export async function rejectConversation(
  conversationId: number, 
  rejectionRequest: RejectionRequest
): Promise<ApprovalResponse> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/conversations/${conversationId}/reject`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(rejectionRequest),
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to reject conversation: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Get approval workflow statistics
 */
export async function getApprovalWorkflowStats(): Promise<ApprovalWorkflowStats> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/approval/stats`)

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to get approval workflow stats: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Get general FeedMe analytics
 */
export async function getAnalytics(): Promise<any> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/analytics`)

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to get analytics: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Bulk approve or reject conversations
 */
export async function bulkApproveConversations(
  bulkRequest: BulkApprovalRequest
): Promise<BulkApprovalResponse> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/conversations/bulk-approve`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(bulkRequest),
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to complete bulk approval: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Review an individual example
 */
export async function reviewExample(
  exampleId: number, 
  reviewRequest: ExampleReviewRequest
): Promise<ExampleReviewResponse> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/examples/${exampleId}/review`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(reviewRequest),
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to review example: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

// Folder Management API Functions

export interface FeedMeFolder {
  id: number
  name: string
  color: string
  description?: string
  created_by?: string
  created_at: string
  updated_at: string
  conversation_count: number
}

export interface FolderCreate {
  name: string
  color?: string
  description?: string
}

export interface FolderUpdate {
  name?: string
  color?: string
  description?: string
}

export interface AssignFolderRequest {
  folder_id?: number | null
  conversation_ids: number[]
}

export interface FolderListResponse {
  folders: FeedMeFolder[]
  total_count: number
}

/**
 * Get all folders with conversation counts
 */
export async function listFolders(): Promise<FolderListResponse> {
  try {
    console.log('[FeedMe API] Fetching folders...')
    // Increase timeout for database operations
    const response = await fetchWithRetry(`${FEEDME_API_BASE}/folders`, {}, 3, 30000)

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      const errorMessage = errorData.detail || `Failed to list folders: ${response.status} ${response.statusText}`
      console.error('[FeedMe API] Folders error:', errorMessage)
      
      // Check for specific error types
      if (response.status === 503) {
        throw new ApiUnreachableError('FeedMe service is temporarily unavailable')
      }
      
      throw new Error(errorMessage)
    }

    const data = await response.json()
    console.log(`[FeedMe API] Successfully fetched ${data.folders?.length || 0} folders`)
    return data
  } catch (error) {
    console.error('[FeedMe API] Error fetching folders:', error)
    
    // Re-throw ApiUnreachableError as-is
    if (error instanceof ApiUnreachableError) {
      throw error
    }
    
    // Wrap other errors
    throw new Error(
      error instanceof Error 
        ? `Failed to list folders: ${error.message}`
        : 'Failed to list folders: Unknown error'
    )
  }
}

/**
 * Create a new folder
 */
export async function createFolder(folderData: FolderCreate): Promise<FeedMeFolder> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/folders`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(folderData),
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to create folder: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Update an existing folder
 */
export async function updateFolder(folderId: number, folderData: FolderUpdate): Promise<FeedMeFolder> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/folders/${folderId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(folderData),
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to update folder: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Delete a folder and optionally move conversations
 */
export async function deleteFolder(folderId: number, moveConversationsTo?: number): Promise<any> {
  let url = `${FEEDME_API_BASE}/folders/${folderId}`
  if (moveConversationsTo !== undefined) {
    const params = new URLSearchParams({ move_conversations_to: moveConversationsTo.toString() })
    url += `?${params.toString()}`
  }

  const response = await fetchWithRetry(url, {
    method: 'DELETE',
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to delete folder: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Assign conversations to a folder
 */
export async function assignConversationsToFolder(assignRequest: AssignFolderRequest): Promise<any> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/folders/assign`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(assignRequest),
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to assign conversations: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Get conversations in a specific folder
 */
export async function listFolderConversations(folderId: number, page = 1, pageSize = 20): Promise<ConversationListResponse> {
  const params = new URLSearchParams({
    page: page.toString(),
    page_size: pageSize.toString(),
  })

  const response = await fetchWithRetry(`${FEEDME_API_BASE}/folders/${folderId}/conversations?${params.toString()}`)

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to list folder conversations: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

// Supabase-enabled Folder Management Functions

/**
 * Create folder with Supabase sync
 */
export async function createFolderSupabase(folderData: FolderCreate): Promise<any> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/folders/create`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(folderData),
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to create folder: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Update folder with Supabase sync
 */
export async function updateFolderSupabase(folderId: number, folderData: FolderUpdate): Promise<any> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/folders/${folderId}/update`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(folderData),
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to update folder: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Delete folder with Supabase sync
 */
export async function deleteFolderSupabase(folderId: number, moveConversationsTo?: number): Promise<any> {
  let url = `${FEEDME_API_BASE}/folders/${folderId}/remove`
  if (moveConversationsTo !== undefined) {
    const params = new URLSearchParams({ move_conversations_to: moveConversationsTo.toString() })
    url += `?${params.toString()}`
  }

  const response = await fetchWithRetry(url, {
    method: 'DELETE',
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to delete folder: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Assign conversations to folder with Supabase sync
 */
export async function assignConversationsToFolderSupabase(folderId: number | null, conversationIds: number[]): Promise<any> {
  let url: string
  let body: any
  
  if (folderId === null) {
    // Move to root (remove from folder) - use the general assign endpoint
    url = `${FEEDME_API_BASE}/folders/assign`
    body = {
      folder_id: null,
      conversation_ids: conversationIds,
    }
  } else {
    // Move to specific folder - use the folder-specific endpoint
    url = `${FEEDME_API_BASE}/folders/${folderId}/assign`
    body = {
      folder_id: folderId,
      conversation_ids: conversationIds,
    }
  }
  
  const response = await fetchWithRetry(url, {
    method: folderId === null ? 'POST' : 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to assign conversations: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Get conversation examples
 */
export async function getConversationExamples(
  conversationId: number,
  page: number = 1,
  pageSize: number = 20,
  isActive?: boolean
): Promise<ExampleListResponse> {
  const params = new URLSearchParams({
    page: page.toString(),
    page_size: pageSize.toString(),
  })

  if (isActive !== undefined) {
    params.append('is_active', isActive.toString())
  }

  const response = await fetchWithRetry(`${FEEDME_API_BASE}/conversations/${conversationId}/examples?${params.toString()}`)

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to get examples: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Update an example
 */
export async function updateExample(
  exampleId: number,
  updates: Partial<FeedMeExample>
): Promise<FeedMeExample> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/examples/${exampleId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(updates),
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to update example: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Delete an individual Q&A example
 */
export async function deleteExample(exampleId: number): Promise<{
  example_id: number
  conversation_id: number
  conversation_title: string
  question_preview: string
  message: string
}> {
  const response = await fetchWithRetry(`${FEEDME_API_BASE}/examples/${exampleId}`, {
    method: 'DELETE',
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to delete example: ${response.status} ${response.statusText}`)
  }

  return response.json()
}