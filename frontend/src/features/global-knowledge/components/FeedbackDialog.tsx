"use client"

import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import { Textarea } from '@/shared/ui/textarea'
import { Label } from '@/shared/ui/label'
import { ScrollArea } from '@/shared/ui/scroll-area'
import {
  PopoverForm,
  PopoverFormButton,
  PopoverFormSeparator,
  PopoverFormSuccess,
} from '@/shared/ui/popover-form'
import type { FeedbackSubmissionPayload } from '@/features/global-knowledge/services/global-knowledge-submissions'
import { submitFeedback } from '@/features/global-knowledge/services/global-knowledge-submissions'

interface FeedbackDialogProps {
  open: boolean
  initialFeedback?: string
  selectedText?: string
  metadata?: Record<string, unknown>
  sessionId?: string | null
  agent?: string
  model?: string
  onClose: () => void
}

const buildMetadata = (sessionId?: string | null, agent?: string, model?: string) => {
  const metadata: Record<string, unknown> = {}
  if (sessionId) metadata.session_id = sessionId
  if (agent) metadata.agent = agent
  if (model) metadata.model = model
  return metadata
}

export function FeedbackDialog({
  open,
  initialFeedback,
  selectedText,
  metadata: initialMetadata,
  sessionId,
  agent,
  model,
  onClose,
}: FeedbackDialogProps) {
  const [feedback, setFeedback] = useState(initialFeedback ?? '')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showSuccess, setShowSuccess] = useState(false)

  useEffect(() => {
    if (open) {
      setFeedback(initialFeedback ?? '')
      setError(null)
    }
  }, [open, initialFeedback])

  const metadata = useMemo(() => ({ ...buildMetadata(sessionId, agent, model), ...(initialMetadata || {}) }), [agent, model, sessionId, initialMetadata])

  const handleSubmit = async () => {
    const trimmed = feedback.trim()
    if (!trimmed) {
      setError('Feedback cannot be empty')
      return
    }

    setError(null)
    setIsSubmitting(true)
    const payload: FeedbackSubmissionPayload = {
      feedbackText: trimmed,
      selectedText: selectedText?.trim() || undefined,
      metadata,
    }

    try {
      await submitFeedback(payload)
      toast.success('Feedback submitted for review')
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new Event('global-knowledge:queue-refresh'))
      }
      setShowSuccess(true)
      setTimeout(() => {
        setShowSuccess(false)
        onClose()
      }, 1400)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to submit feedback'
      toast.error('Submission failed', { description: message })
      setError(message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <PopoverForm
      title="Submit Feedback"
      open={open}
      setOpen={(v) => {
        if (!v) onClose()
      }}
      width="520px"
      showCloseButton={!showSuccess}
      showSuccess={showSuccess}
      openChild={
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (!isSubmitting) handleSubmit()
          }}
        >
          <div className="space-y-4">
            {selectedText && (
              <div>
                <Label className="text-xs text-muted-foreground uppercase tracking-wide">Selected snippet</Label>
                <ScrollArea className="mt-2 max-h-40 rounded-md border border-border/50 bg-muted/30 p-3 text-sm leading-relaxed">
                  <pre className="whitespace-pre-wrap font-sans text-muted-foreground">
                    {selectedText}
                  </pre>
                </ScrollArea>
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="feedback-text">Feedback</Label>
              <Textarea
                id="feedback-text"
                value={feedback}
                onChange={(event) => setFeedback(event.target.value)}
                placeholder="Describe what needs to be updated or corrected..."
                rows={6}
              />
              {error && <p className="text-sm text-destructive">{error}</p>}
            </div>
          </div>

          <div className="relative mt-4 flex items-center justify-end gap-2">
            <PopoverFormSeparator />
            <PopoverFormButton
              loading={isSubmitting}
              onClick={() => {
                if (!isSubmitting) handleSubmit()
              }}
            >
              Submit Feedback
            </PopoverFormButton>
          </div>
        </form>
      }
      successChild={
        <PopoverFormSuccess
          title="Feedback Received"
          description="Thank you for supporting our project!"
        />
      }
    />
  )
}
