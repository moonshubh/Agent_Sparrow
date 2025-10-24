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
import type { CorrectionSubmissionPayload } from '@/features/global-knowledge/services/global-knowledge-submissions'
import { submitCorrection } from '@/features/global-knowledge/services/global-knowledge-submissions'

interface CorrectionDialogProps {
  open: boolean
  initialIncorrect?: string
  initialCorrected?: string
  initialExplanation?: string
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

export function CorrectionDialog({
  open,
  initialIncorrect,
  initialCorrected,
  initialExplanation,
  metadata: initialMetadata,
  sessionId,
  agent,
  model,
  onClose,
}: CorrectionDialogProps) {
  const [incorrectText, setIncorrectText] = useState(initialIncorrect ?? '')
  const [correctedText, setCorrectedText] = useState(initialCorrected ?? '')
  const [explanation, setExplanation] = useState(initialExplanation ?? '')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showSuccess, setShowSuccess] = useState(false)

  useEffect(() => {
    if (open) {
      setIncorrectText(initialIncorrect ?? '')
      setCorrectedText(initialCorrected ?? '')
      setExplanation('')
      setError(null)
    }
  }, [open, initialIncorrect, initialCorrected])

  const metadata = useMemo(() => ({ ...buildMetadata(sessionId, agent, model), ...(initialMetadata || {}) }), [agent, model, sessionId, initialMetadata])

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
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new Event('global-knowledge:queue-refresh'))
      }
      setShowSuccess(true)
      setTimeout(() => {
        setShowSuccess(false)
        onClose()
      }, 1400)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to submit correction'
      toast.error('Submission failed', { description: message })
      setError(message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <PopoverForm
      title="Submit Correction"
      open={open}
      setOpen={(v) => {
        if (!v) onClose()
      }}
      width="600px"
      showCloseButton={!showSuccess}
      showSuccess={showSuccess}
      openChild={
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (!isSubmitting) handleSubmit()
          }}
        >
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

          <div className="relative mt-4 flex items-center justify-end gap-2">
            <PopoverFormSeparator />
            <PopoverFormButton
              loading={isSubmitting}
              onClick={() => {
                if (!isSubmitting) handleSubmit()
              }}
            >
              Submit Correction
            </PopoverFormButton>
          </div>
        </form>
      }
      successChild={
        <PopoverFormSuccess
          title="Correction Received"
          description="Thank you! We'll review and incorporate it."
        />
      }
    />
  )
}
