export type PlatformTag = 'windows' | 'macos'

export interface ConversationMetadata {
  tags?: string[]
  ai_note?: string
  ai_comment?: string
  review_status?: 'ready' | 'pending' | 'reviewed'
  ticket_id?: string
  processing_tracker?: {
    message?: string
    progress?: number
  }
  folder_id?: number | null
  extraction_confidence?: number
  [key: string]: any // For backward compatibility with existing metadata
}

export interface ConversationDetail {
  id: number
  title: string
  extracted_text?: string
  processing_status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled'
  processing_method?: string
  approval_status?: 'pending' | 'approved' | 'rejected'
  metadata?: ConversationMetadata
  folder_id?: number | null
  uploaded_by?: string | null
  created_at?: string
  updated_at?: string
}