"use client"

import { useEffect, useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/ui/dialog'
import { Button } from '@/shared/ui/button'
import { Textarea } from '@/shared/ui/textarea'
import { Label } from '@/shared/ui/label'
import { ScrollArea } from '@/shared/ui/scroll-area'
import type { CorrectionSubmissionPayload } from '@/features/global-knowledge/services/global-knowledge-submissions'
import { submitCorrection } from '@/features/global-knowledge/services/global-knowledge-submissions'

interface CorrectionDialogProps {
  open: boolean
  initialIncorrect?: string
  initialCorrected?: string
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

export function CorrectionDialog({
  open,
  initialIncorrect,
  initialCorrected,
  sessionId,
  agent,
  model,
  onClose,
}: CorrectionDialogProps) {
  const [incorrectText, setIncorrectText] = useState(initialIncorrect ?? '')
  const [correctedText, setCorrectedText] = useState(initialCorrected ?? '')
  const [explanation, setExplanation] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setIncorrectText(initialIncorrect ?? '')
      setCorrectedText(initialCorrected ?? '')
      setExplanation('')
      setError(null)
    }
  }, [open, initialIncorrect, initialCorrected])

  const metadata = useMemo(() => buildMetadata(sessionId, agent, model), [agent, model, sessionId])

  const handleSubmit = async () => {
    const incorrect = incorrectText.trim()
    const corrected = correctedText.trim()
    if (!incorrect) {
      setError('Original text is required')
      return
    }
    if (!corrected) {
      setError('Corrected text is required')
      return
    }

    setError(null)
    setIsSubmitting(true)

    const payload: CorrectionSubmissionPayload = {
      incorrectText: incorrect,
      correctedText: corrected,
      explanation: explanation.trim() || undefined,
      metadata,
    }

    try {
      await submitCorrection(payload)
      toast.success('Correction submitted for review')
      onClose()
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to submit correction'
      toast.error('Submission failed', { description: message })
      setError(message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(isOpen) => (isOpen ? undefined : onClose())}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Submit Correction</DialogTitle>
          <DialogDescription>
            Highlight the incorrect response and provide the correct information so we can update the global knowledge base.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="space-y-2">
            <Label htmlFor="incorrect-text">Incorrect response</Label>
            <Textarea
              id="incorrect-text"
              value={incorrectText}
              onChange={(event) => setIncorrectText(event.target.value)}
              placeholder="Paste the incorrect assistant response..."
              rows={4}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="corrected-text">Corrected response</Label>
            <Textarea
              id="corrected-text"
              value={correctedText}
              onChange={(event) => setCorrectedText(event.target.value)}
              placeholder="Provide the corrected version..."
              rows={4}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="explanation-text">Explanation (optional)</Label>
            <Textarea
              id="explanation-text"
              value={explanation}
              onChange={(event) => setExplanation(event.target.value)}
              placeholder="Add any additional context or links that help reviewers understand the change."
              rows={3}
            />
          </div>

          {error && (
            <ScrollArea className="rounded border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </ScrollArea>
          )}
        </div>

        <DialogFooter className="flex gap-2">
          <Button variant="ghost" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={isSubmitting}>
            {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Submit Correction
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
