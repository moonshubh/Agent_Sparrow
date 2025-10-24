"use client"

import React, { useMemo, useState } from 'react'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/shared/ui/dialog'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'

export type HumanDecisionType = 'accept' | 'ignore' | 'response' | 'edit'

type Props = {
  open: boolean
  threadId: string
  interrupts: Array<Record<string, unknown>>
  loading?: boolean
  onDecision: (payload: { type: HumanDecisionType; message?: string; action?: string; args?: Record<string, unknown> }) => void
  onClose: () => void
}

function renderInterruptSummary(interrupt: Record<string, unknown>) {
  const title = typeof interrupt?.title === 'string' ? interrupt.title : undefined
  const reason = typeof interrupt?.reason === 'string' ? interrupt.reason : undefined
  const required = typeof interrupt?.required_action === 'string' ? interrupt.required_action : undefined
  const summary = title || reason || required
  if (summary) {
    return <div className="text-sm text-muted-foreground whitespace-pre-wrap">{summary}</div>
  }
  try {
    return (
      <pre className="text-xs text-muted-foreground max-h-60 overflow-auto rounded bg-muted/30 p-2">
        {JSON.stringify(interrupt, null, 2)}
      </pre>
    )
  } catch {
    return null
  }
}

export default function InterruptOverlay({ open, threadId, interrupts, loading, onDecision, onClose }: Props) {
  const [responseText, setResponseText] = useState<string>("")
  const [editAction, setEditAction] = useState<string>("")
  const [editArgs, setEditArgs] = useState<string>("")

  const primary = useMemo(() => interrupts?.[0] as Record<string, unknown> | undefined, [interrupts])

  return (
    <Dialog open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Human approval required</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="text-xs text-muted-foreground">Thread: {threadId}</div>
          {primary && renderInterruptSummary(primary)}
          <div className="grid gap-2">
            <div className="flex items-center gap-2">
              <Button variant="secondary" disabled={!!loading} onClick={() => onDecision({ type: 'accept' })}>Accept</Button>
              <Button variant="outline" disabled={!!loading} onClick={() => onDecision({ type: 'ignore' })}>Ignore</Button>
            </div>
            <div className="grid gap-2">
              <Input value={responseText} onChange={(e) => setResponseText(e.target.value)} placeholder="Respond with a note" />
              <div className="flex items-center gap-2">
                <Button disabled={!!loading || !responseText.trim()} onClick={() => onDecision({ type: 'response', message: responseText.trim() })}>Respond</Button>
                <Button variant="ghost" onClick={() => setResponseText("")}>Clear</Button>
              </div>
            </div>
            <div className="grid gap-2">
              <Input value={editAction} onChange={(e) => setEditAction(e.target.value)} placeholder="Edit action id (optional)" />
              <Input value={editArgs} onChange={(e) => setEditArgs(e.target.value)} placeholder='Edit args JSON, e.g. {"key":"value"}' />
              <Button
                disabled={!!loading}
                onClick={() => {
                  let parsed: Record<string, unknown> | undefined
                  const raw = editArgs.trim()
                  if (raw) {
                    try { parsed = JSON.parse(raw) } catch { parsed = undefined }
                  }
                  onDecision({ type: 'edit', action: editAction || 'manual_edit', args: parsed })
                }}
              >
                Apply Edit
              </Button>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={!!loading}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
