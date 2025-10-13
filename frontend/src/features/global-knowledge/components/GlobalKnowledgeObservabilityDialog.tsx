"use client"

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/shared/ui/dialog'
import { ScrollArea } from '@/shared/ui/scroll-area'
import { ObservabilityTab } from '@/features/feedme/components/feedme-revamped/global-knowledge/ObservabilityTab'

interface GlobalKnowledgeObservabilityDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function GlobalKnowledgeObservabilityDialog({
  open,
  onOpenChange,
}: GlobalKnowledgeObservabilityDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[900px] w-full h-[80vh] p-0 overflow-hidden">
        <DialogHeader className="px-6 pt-6 pb-4 border-b">
          <DialogTitle className="text-lg font-semibold">
            Global Knowledge Observability
          </DialogTitle>
        </DialogHeader>
        <ScrollArea className="h-full">
          <div className="px-6 py-4">
            <ObservabilityTab />
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}
