'use client'

import React, { useState } from 'react'
import dynamic from 'next/dynamic'
import { useRouter } from 'next/navigation'
import Dock from '@/components/feedme-revamped/Dock'
import { Home, FolderOpen, Upload, MessageCircle, BarChart3 } from 'lucide-react'
import CenterHero from '@/components/feedme-revamped/CenterHero'
import FoldersDialog from '@/components/feedme-revamped/FoldersDialog'
import UploadDialog from '@/components/feedme-revamped/UploadDialog'
import UnassignedDialog from '@/components/feedme-revamped/UnassignedDialog'
import { ErrorBoundary } from '@/components/feedme-revamped/ErrorBoundary'
import BackendHealthAlert from '@/components/BackendHealthAlert'

const LightRays = dynamic(() => import('@/components/LightRays'), { ssr: false })

export default function FeedMeRevampedPage() {
  const [showCenter, setShowCenter] = useState(true)
  const [foldersOpen, setFoldersOpen] = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [unassignedOpen, setUnassignedOpen] = useState(false)
  const router = useRouter()
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

        {/* Optional center FeedMe logo (hidden after first dock interaction) */}
        {showCenter && (
          <div className="absolute inset-0 z-5 flex items-center justify-center pointer-events-none">
            <CenterHero src="/center-feedme.png" className="w-[300px] h-[300px] hero-offset" />
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
              { icon: <BarChart3 />, label: 'Stats', onClick: () => setShowCenter(false) },
            ]}
            baseItemSize={72}
          />
        </div>
        <FoldersDialog isOpen={foldersOpen} onClose={() => setFoldersOpen(false)} />
        <UploadDialog isOpen={uploadOpen} onClose={() => setUploadOpen(false)} />
        <UnassignedDialog isOpen={unassignedOpen} onClose={() => setUnassignedOpen(false)} />
      </section>
    </ErrorBoundary>
  )
}
