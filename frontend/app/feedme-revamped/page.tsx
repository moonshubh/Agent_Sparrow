'use client'

import React, { useState } from 'react'
import dynamic from 'next/dynamic'
import { useRouter } from 'next/navigation'
import Dock from '@/components/feedme-revamped/Dock'
import { Home, FolderOpen, Upload, MessageCircle, BarChart3 } from 'lucide-react'
import EnhancedAnimatedLogo from '@/components/feedme-revamped/EnhancedAnimatedLogo'
import FoldersDialog from '@/components/feedme-revamped/FoldersDialog'
import UploadDialog from '@/components/feedme-revamped/UploadDialog'
import UnassignedDialog from '@/components/feedme-revamped/UnassignedDialog'
import { StatsPopover } from '@/components/feedme-revamped/StatsPopover'
import { ErrorBoundary } from '@/components/feedme-revamped/ErrorBoundary'
import BackendHealthAlert from '@/components/BackendHealthAlert'

const LightRays = dynamic(() => import('@/components/LightRays'), { ssr: false })

export default function FeedMeRevampedPage() {
  const [showCenter, setShowCenter] = useState(true)
  const [foldersOpen, setFoldersOpen] = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [unassignedOpen, setUnassignedOpen] = useState(false)
  const [statsOpen, setStatsOpen] = useState(false)
  const [frameAdvanceTrigger, setFrameAdvanceTrigger] = useState(0)
  const router = useRouter()

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

        {/* No SVG filters needed; dock is icon-only */}

        {/* Light rays background */}
        <div className="pointer-events-none absolute inset-0 z-0 opacity-55">
          <LightRays
            className="w-full h-full"
            raysOrigin="top-center"
            raysColor="hsl(54.9 96.7% 88%)"
            raysSpeed={0.6}
            lightSpread={1.3}
            rayLength={2.0}
            pulsating={false}
            fadeDistance={1.1}
            saturation={1}
            followMouse={false}
            mouseInfluence={0}
            noiseAmount={0}
            distortion={0}
          />
        </div>

        {/* Enhanced FeedMe animated logo - positioned higher and larger */}
        {showCenter && (
          <div className="absolute inset-0 z-5 flex items-center justify-center pointer-events-none -mt-20">
            <EnhancedAnimatedLogo
              className="w-[400px] h-[400px]"
              animationDuration={5000}
              loop={true}
              autoPlay={false}
              triggerAdvance={frameAdvanceTrigger}
            />
          </div>
        )}

        {/* Bottom-centered Dock with safe bottom space */}
        <div className="absolute inset-x-0 bottom-0 z-10 flex items-end justify-center px-4 pb-12">
          <Dock
            items={[
              {
                icon: <Home />,
                label: 'Home',
                onClick: () => {
                  setShowCenter(false)
                  router.push('/chat')
                }
              },
              { icon: <FolderOpen />, label: 'Folders', onClick: () => { setShowCenter(false); setFoldersOpen(true) } },
              { icon: <Upload />, label: 'Upload', onClick: () => { setShowCenter(false); setUploadOpen(true) } },
              { icon: <MessageCircle />, label: 'Unassigned', onClick: () => { setShowCenter(false); setUnassignedOpen(true) } },
              {
                icon: <BarChart3 />,
                label: 'Stats',
                onClick: () => {
                  setShowCenter(false)
                  setStatsOpen(true)
                }
              },
            ]}
            baseItemSize={72}
          />
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
