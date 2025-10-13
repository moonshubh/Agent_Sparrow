"use client"

import { useEffect, useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/ui/dialog'
import { Button } from '@/shared/ui/button'
import { Textarea } from '@/shared/ui/textarea'
import { Label } from '@/shared/ui/label'
import { ScrollArea } from '@/shared/ui/scroll-area'
import type { FeedbackSubmissionPayload } from '@/features/global-knowledge/services/global-knowledge-submissions'
import { submitFeedback } from '@/features/global-knowledge/services/global-knowledge-submissions'

interface FeedbackDialogProps {
  open: boolean
  initialFeedback?: string
  selectedText?: string
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
  sessionId,
  agent,
  model,
  onClose,
}: FeedbackDialogProps) {
  const [feedback, setFeedback] = useState(initialFeedback ?? '')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setFeedback(initialFeedback ?? '')
      setError(null)
    }
  }, [open, initialFeedback])

  const metadata = useMemo(() => buildMetadata(sessionId, agent, model), [agent, model, sessionId])

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
      onClose()
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to submit feedback'
      toast.error('Submission failed', { description: message })
      setError(message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(isOpen) => (isOpen ? undefined : onClose())}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Submit Feedback</DialogTitle>
          <DialogDescription>
            Share corrections or improvements that should apply globally.
          </DialogDescription>
        </DialogHeader>

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

        <DialogFooter className="flex gap-2">
          <Button variant="ghost" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={isSubmitting}>
            {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Submit Feedback
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
