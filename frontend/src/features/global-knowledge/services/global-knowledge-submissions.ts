"use client"

import { apiClient } from '@/services/api/api-client'

export type GlobalKnowledgeAttachment = {
  kind?: 'link' | 'image'
  url?: string
  title?: string
  mime?: string
}

export interface FeedbackSubmissionPayload {
  feedbackText: string
  selectedText?: string
  attachments?: GlobalKnowledgeAttachment[]
  metadata?: Record<string, unknown>
}

export interface CorrectionSubmissionPayload {
  incorrectText: string
  correctedText: string
  explanation?: string
  attachments?: GlobalKnowledgeAttachment[]
  metadata?: Record<string, unknown>
}

export interface SubmissionResponse {
  success: boolean
  submission_id?: number
  status?: string
  store_written: boolean
}

const FEEDBACK_ENDPOINT = '/api/v1/global-knowledge/feedback'
const CORRECTION_ENDPOINT = '/api/v1/global-knowledge/corrections'

export async function submitFeedback(payload: FeedbackSubmissionPayload): Promise<SubmissionResponse> {
  return apiClient.post<SubmissionResponse>(FEEDBACK_ENDPOINT, {
    feedback_text: payload.feedbackText,
    selected_text: payload.selectedText,
    attachments: payload.attachments,
    metadata: payload.metadata,
  })
}

export async function submitCorrection(payload: CorrectionSubmissionPayload): Promise<SubmissionResponse> {
  return apiClient.post<SubmissionResponse>(CORRECTION_ENDPOINT, {
    incorrect_text: payload.incorrectText,
    corrected_text: payload.correctedText,
    explanation: payload.explanation,
    attachments: payload.attachments,
    metadata: payload.metadata,
  })
}
