'use client'

import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import Dock, { Card, DockCard } from '@/features/feedme/components/Dock'
import EnhancedAnimatedLogo from '@/features/feedme/components/EnhancedAnimatedLogo'
import FoldersDialog from '@/features/feedme/components/FoldersDialog'
import UploadDialog from '@/features/feedme/components/UploadDialog'
import UnassignedDialog from '@/features/feedme/components/UnassignedDialog'
import { StatsPopover } from '@/features/feedme/components/StatsPopover'
import { ErrorBoundary } from '@/features/feedme/components/ErrorBoundary'
import BackendHealthAlert from '@/shared/components/BackendHealthAlert'
import { LampContainer } from '@/shared/ui/lamp'

export default function FeedMeRevampedPage() {
  const [showCenter, setShowCenter] = useState(true)
  const [foldersOpen, setFoldersOpen] = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [unassignedOpen, setUnassignedOpen] = useState(false)
  const [statsOpen, setStatsOpen] = useState(false)
  const [frameAdvanceTrigger, setFrameAdvanceTrigger] = useState(0)
  const router = useRouter()

  const dockItems = [
    {
      id: 'home',
      label: 'Home',
      iconSrc: '/feedme-dock/Home.png',
      onClick: () => {
        setShowCenter(false)
        router.push('/chat')
      },
    },
    {
      id: 'folders',
      label: 'Folders',
      iconSrc: '/feedme-dock/Folders.png',
      onClick: () => {
        setShowCenter(false)
        setFoldersOpen(true)
      },
    },
    {
      id: 'upload',
      label: 'Upload',
      iconSrc: '/feedme-dock/Upload.png',
      onClick: () => {
        setShowCenter(false)
        setUploadOpen(true)
      },
    },
    {
      id: 'unassigned',
      label: 'Unassigned',
      iconSrc: '/feedme-dock/Unassigned Conversations.png',
      onClick: () => {
        setShowCenter(false)
        setUnassignedOpen(true)
      },
    },
    {
      id: 'stats',
      label: 'Stats',
      iconSrc: '/feedme-dock/Stats.png',
      onClick: () => {
        setShowCenter(false)
        setStatsOpen(true)
      },
    },
  ]

  // Function to advance logo frame on user actions
  const advanceLogoFrame = () => {
    setFrameAdvanceTrigger(prev => prev + 1)
  }

  return (
    <ErrorBoundary>
      <section className="relative h-screen w-screen overflow-hidden bg-background">
        {/* Backend health monitoring alert */}
        <div className="absolute top-4 right-4 z-50 max-w-md">
          <BackendHealthAlert showWhenHealthy={false} />
        </div>

        {/* Enhanced FeedMe animated logo - positioned higher and larger */}
        {showCenter && (
          <div className="absolute inset-0 z-5 -mt-20 flex items-center justify-center pointer-events-none">
            <LampContainer>
              <div className="relative h-[440px] w-[440px]">
                <EnhancedAnimatedLogo className="h-full w-full" triggerAdvance={frameAdvanceTrigger} />
              </div>
            </LampContainer>
          </div>
        )}

        {/* Bottom-centered Dock with safe bottom space */}
        <div className="absolute inset-x-0 bottom-0 z-10 flex items-end justify-center px-4 pb-12">
          <Dock className="max-w-[1024px]" baseSize={82} magnification={1.3} distance={190}>
            {dockItems.map((item) => (
              <DockCard key={item.id} id={item.id} label={item.label} onClick={item.onClick}>
                <Card src={item.iconSrc} alt={`${item.label} icon`} />
              </DockCard>
            ))}
          </Dock>
        </div>

        {/* Dialogs */}
        <FoldersDialog
          isOpen={foldersOpen}
          onClose={() => {
            setFoldersOpen(false)
            setShowCenter(true)
            advanceLogoFrame()
          }}
          onSubDialogClose={advanceLogoFrame}
        />
        <UploadDialog
          isOpen={uploadOpen}
          onClose={() => {
            setUploadOpen(false)
            setShowCenter(true)
            advanceLogoFrame()
          }}
        />
        <UnassignedDialog
          isOpen={unassignedOpen}
          onClose={() => {
            setUnassignedOpen(false)
            setShowCenter(true)
            advanceLogoFrame()
          }}
        />
        <StatsPopover
          open={statsOpen}
          onOpenChange={(open) => {
            setStatsOpen(open)
            if (!open) {
              setShowCenter(true)
              advanceLogoFrame()
            }
          }}
        />
      </section>
    </ErrorBoundary>
  )
}
