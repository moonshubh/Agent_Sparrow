"use client"

import { useCallback, useState, type ComponentType } from 'react'
import Image from 'next/image'
import { useRouter } from 'next/navigation'
import dynamic from 'next/dynamic'

import { Button } from '@/shared/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/shared/ui/tooltip'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/shared/ui/dialog'
import { ErrorBoundary } from '@/shared/ui/ErrorBoundary'

export type FeedMeButtonMode = 'navigate' | 'manager' | 'upload'

interface FeedMeButtonProps {
  onClick?: () => void
  mode?: FeedMeButtonMode
}

type GenericUploadResult = Record<string, unknown>

const FeedMeConversationManager = dynamic(
  () =>
    import('@/features/feedme/components/feedme-revamped/FeedMeConversationManager').then(
      (module: any) => module.default,
    ),
  {
    ssr: false,
    loading: () => (
      <div className="p-6 text-sm text-muted-foreground">Loading FeedMe manager...</div>
    ),
  },
)

type EnhancedModalProps = {
  isOpen: boolean
  onClose: () => void
  onUploadComplete?: (results: GenericUploadResult[]) => void
}

const EnhancedFeedMeModal = dynamic<EnhancedModalProps>(
  () =>
    import('@/features/feedme/components/feedme-revamped/EnhancedFeedMeModal').then(
      (module: any) => module.EnhancedFeedMeModal as ComponentType<EnhancedModalProps>,
    ),
  {
    ssr: false,
    loading: () => (
      <div className="p-6 text-sm text-muted-foreground">Loading uploader...</div>
    ),
  },
)

export function FeedMeButton({ onClick, mode = 'navigate' }: FeedMeButtonProps) {
  const router = useRouter()
  const [isHovered, setIsHovered] = useState(false)
  const [activeModal, setActiveModal] = useState<FeedMeButtonMode | null>(null)

  const openModal = useCallback((nextMode: FeedMeButtonMode) => {
    setActiveModal(nextMode)
  }, [])

  const closeModal = useCallback(() => {
    setActiveModal(null)
  }, [])

  const handleClick = useCallback(() => {
    onClick?.()

    if (mode === 'navigate') {
      router.push('/feedme-revamped')
      return
    }

    if (mode === 'manager' || mode === 'upload') {
      openModal(mode)
    }
  }, [mode, onClick, openModal, router])

  const tooltipText =
    mode === 'upload'
      ? 'FeedMe - Upload transcripts'
      : mode === 'manager'
        ? 'FeedMe - Manage conversations'
        : 'FeedMe - Open full page'

  const isNavigate = mode === 'navigate'

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className={
              isNavigate
                ? 'h-8 px-2 gap-2 hover:bg-mb-blue-300/10 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2'
                : 'h-8 w-8 p-0 hover:bg-mb-blue-300/10 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2'
            }
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
            onClick={handleClick}
            aria-label={tooltipText}
          >
            <Image
              src="/feedme-icon.png"
              alt="FeedMe"
              width={20}
              height={20}
              className={`transition-opacity ${isHovered ? 'opacity-100' : 'opacity-70'}`}
            />
            {isNavigate && <span className="text-sm">FeedMe</span>}
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p>{tooltipText}</p>
        </TooltipContent>
      </Tooltip>

      {activeModal === 'upload' && (
        <EnhancedFeedMeModal
          isOpen
          onClose={closeModal}
          onUploadComplete={() => closeModal()}
        />
      )}

      {activeModal === 'manager' && (
        <Dialog open onOpenChange={open => (open ? undefined : closeModal())}>
          <DialogContent className="max-w-[1200px] w-full h-[85vh] p-0 overflow-hidden">
            <DialogHeader className="px-6 pt-6 pb-4 border-b">
              <DialogTitle className="text-lg font-semibold">FeedMe Conversations</DialogTitle>
            </DialogHeader>
            <div className="h-full overflow-hidden">
              <ErrorBoundary>
                <div className="h-full overflow-hidden">
                  <FeedMeConversationManager />
                </div>
              </ErrorBoundary>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </TooltipProvider>
  )
}
